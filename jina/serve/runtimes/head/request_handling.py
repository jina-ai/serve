import argparse
import asyncio
import json
import os
from collections import defaultdict
from typing import TYPE_CHECKING, AsyncIterator, Dict, List, Optional, Tuple, Any

import grpc

from jina.enums import PollingType
from jina.constants import __default_endpoint__
from jina.excepts import InternalNetworkError
from jina.helper import get_full_version
from jina.proto import jina_pb2
from jina.serve.networking import GrpcConnectionPool
from jina.serve.runtimes.monitoring import MonitoringRequestMixin
from jina.serve.runtimes.worker.request_handling import WorkerRequestHandler
from jina.types.request.data import DataRequest, Response
from jina._docarray import docarray_v2, is_pydantic_v2

if docarray_v2:
    if not is_pydantic_v2:
        from jina.serve.runtimes.helper import _create_pydantic_model_from_schema as create_base_doc_from_schema
    else:
        from docarray.utils.create_dynamic_doc_class import create_base_doc_from_schema
    from docarray import DocList
    from docarray.base_doc.any_doc import AnyDoc

    from jina._docarray import LegacyDocumentJina

    legacy_doc_schema = LegacyDocumentJina.schema()


if TYPE_CHECKING:  # pragma: no cover
    from prometheus_client import CollectorRegistry

    from jina.logging.logger import JinaLogger
    from jina.types.request import Request
    from jina.types.request.data import DataRequest


class HeaderRequestHandler(MonitoringRequestMixin):
    """
    Class that handles the requests arriving to the head and the results extracted from the requests future.

    :param metrics_registry: optional metrics registry for prometheus. Used if we need to expose metrics from the executor or from the data request handler
    :param runtime_name: optional runtime_name that will be registered during monitoring
    """

    DEFAULT_POLLING = PollingType.ANY

    def __init__(
        self,
        args: 'argparse.Namespace',
        logger: 'JinaLogger',
        metrics_registry: Optional['CollectorRegistry'] = None,
        meter=None,
        runtime_name: Optional[str] = None,
        aio_tracing_client_interceptors=None,
        tracing_client_interceptor=None,
        **kwargs,
    ):
        if args.name is None:
            args.name = ''
        self.logger = logger
        self.args = args
        self.meter = meter
        self.metrics_registry = metrics_registry
        self.name = args.name
        self._deployment_name = os.getenv('JINA_DEPLOYMENT_NAME', 'worker')
        self.aio_tracing_client_interceptors = aio_tracing_client_interceptors
        self.tracing_client_interceptor = tracing_client_interceptor
        self.connection_pool = GrpcConnectionPool(
            runtime_name=self.name,
            logger=self.logger,
            compression=args.compression,
            metrics_registry=self.metrics_registry,
            meter=self.meter,
            aio_tracing_client_interceptors=self.aio_tracing_client_interceptors,
            tracing_client_interceptor=self.tracing_client_interceptor,
            channel_options=self.args.grpc_channel_options,
        )
        self._retries = self.args.retries

        polling = getattr(args, 'polling', self.DEFAULT_POLLING.name)
        try:
            # try loading the polling args as json
            endpoint_polling = json.loads(polling)
            # '*' is used a wildcard and will match all endpoints, except /index, /search and explicitly defined endpoins
            default_polling = (
                PollingType.from_string(endpoint_polling['*'])
                if '*' in endpoint_polling
                else self.DEFAULT_POLLING
            )
            self._polling = self._default_polling_dict(default_polling)
            for endpoint in endpoint_polling:
                self._polling[endpoint] = PollingType(
                    endpoint_polling[endpoint]
                    if type(endpoint_polling[endpoint]) == int
                    else PollingType.from_string(endpoint_polling[endpoint])
                )
        except (ValueError, TypeError):
            # polling args is not a valid json, try interpreting as a polling enum type
            default_polling = (
                polling
                if type(polling) == PollingType
                else PollingType.from_string(polling)
            )
            self._polling = self._default_polling_dict(default_polling)

        if hasattr(args, 'connection_list') and args.connection_list:
            connection_list = json.loads(args.connection_list)
            for shard_id in connection_list:
                shard_connections = connection_list[shard_id]
                if isinstance(shard_connections, str):
                    self.connection_pool.add_connection(
                        deployment=self._deployment_name,
                        address=shard_connections,
                        shard_id=int(shard_id),
                    )
                else:
                    for connection in shard_connections:
                        self.connection_pool.add_connection(
                            deployment=self._deployment_name,
                            address=connection,
                            shard_id=int(shard_id),
                        )

        self.uses_before_address = args.uses_before_address
        self.timeout_send = args.timeout_send
        if self.timeout_send:
            self.timeout_send /= 1e3  # convert ms to seconds

        if self.uses_before_address:
            self.connection_pool.add_connection(
                deployment='uses_before', address=self.uses_before_address
            )
        self.uses_after_address = args.uses_after_address
        if self.uses_after_address:
            self.connection_pool.add_connection(
                deployment='uses_after', address=self.uses_after_address
            )
        self._reduce = not args.no_reduce
        super().__init__(metrics_registry, meter, runtime_name)
        self.logger = logger
        self._executor_endpoint_mapping = None
        self._gathering_endpoints = False
        self.runtime_name = runtime_name
        self._pydantic_models_by_endpoint = None
        self.endpoints_discovery_stop_event = asyncio.Event()
        self.endpoints_discovery_task = None
        if docarray_v2:
            self.endpoints_discovery_task = asyncio.create_task(
                self._get_endpoints_from_workers(
                    connection_pool=self.connection_pool,
                    name=self._deployment_name,
                    retries=self._retries,
                    stop_event=self.endpoints_discovery_stop_event,
                )
            )

    def _default_polling_dict(self, default_polling):
        return defaultdict(
            lambda: default_polling,
            {'/search': PollingType.ALL, '/index': PollingType.ANY},
        )

    async def _gather_worker_tasks(
        self,
        requests,
        connection_pool,
        deployment_name,
        polling_type,
        timeout_send,
        retries,
    ):
        worker_send_tasks = connection_pool.send_requests(
            requests=requests,
            deployment=deployment_name,
            polling_type=polling_type,
            timeout=timeout_send,
            retries=retries,
        )

        all_worker_results = await asyncio.gather(*worker_send_tasks)
        worker_results = list(
            filter(lambda x: isinstance(x, Tuple), all_worker_results)
        )
        exceptions = list(
            filter(
                lambda x: issubclass(type(x), BaseException),
                all_worker_results,
            )
        )
        total_shards = len(worker_send_tasks)
        failed_shards = len(exceptions)
        if failed_shards:
            self.logger.warning(f'{failed_shards} shards out of {total_shards} failed.')

        return worker_results, exceptions, total_shards, failed_shards

    @staticmethod
    def _merge_metadata(
        metadata,
        uses_after_metadata,
        uses_before_metadata,
        total_shards,
        failed_shards,
    ):
        merged_metadata = {}
        if uses_before_metadata:
            for key, value in uses_before_metadata:
                merged_metadata[key] = value
        for meta in metadata:
            for key, value in meta:
                merged_metadata[key] = value
        if uses_after_metadata:
            for key, value in uses_after_metadata:
                merged_metadata[key] = value

        merged_metadata['total_shards'] = str(total_shards)
        merged_metadata['failed_shards'] = str(failed_shards)
        return merged_metadata

    async def _handle_data_request(
        self,
        requests,
        connection_pool,
        uses_before_address,
        uses_after_address,
        timeout_send,
        retries,
        reduce,
        polling_type,
        deployment_name,
        endpoint,
    ) -> Tuple['DataRequest', Dict]:
        for req in requests:
            if docarray_v2:
                req.document_array_cls = DocList[AnyDoc]
            self._update_start_request_metrics(req)

        if self._pydantic_models_by_endpoint is None and docarray_v2:
            try:
                await self.endpoints_discovery_task
            except:
                raise

        WorkerRequestHandler.merge_routes(requests)

        uses_before_metadata = None
        if uses_before_address:
            result = await connection_pool.send_requests_once(
                requests,
                deployment='uses_before',
                timeout=timeout_send,
                retries=retries,
            )
            if issubclass(type(result), BaseException):
                raise result
            else:
                response, uses_before_metadata = result
                requests = [response]

        (
            worker_results,
            exceptions,
            total_shards,
            failed_shards,
        ) = await self._gather_worker_tasks(
            requests=requests,
            deployment_name=deployment_name,
            timeout_send=timeout_send,
            connection_pool=connection_pool,
            polling_type=polling_type,
            retries=retries,
        )
        if len(worker_results) == 0:
            if exceptions:
                # raise the underlying error first
                self._update_end_failed_requests_metrics()
                raise exceptions[0]
            raise RuntimeError(
                f'Head {self.runtime_name} did not receive a response when sending message to worker pods'
            )

        worker_results, metadata = zip(*worker_results)

        response_request = worker_results[0]
        found = False
        if docarray_v2:
            check_endpoint = endpoint
            if endpoint not in self._pydantic_models_by_endpoint:
                check_endpoint = __default_endpoint__
            model = self._pydantic_models_by_endpoint[check_endpoint]['output']
        for i, worker_result in enumerate(worker_results):
            if docarray_v2:
                worker_result.document_array_cls = DocList[model]
            if not found and worker_result.status.code == jina_pb2.StatusProto.SUCCESS:
                response_request = worker_result
                found = True

        uses_after_metadata = None
        if uses_after_address:
            result = await connection_pool.send_requests_once(
                worker_results,
                deployment='uses_after',
                timeout=timeout_send,
                retries=retries,
            )
            if issubclass(type(result), BaseException):
                self._update_end_failed_requests_metrics()
                raise result
            else:
                response_request, uses_after_metadata = result
        elif len(worker_results) > 1 and reduce:
            response_request = WorkerRequestHandler.reduce_requests(worker_results)
        elif len(worker_results) > 1 and not reduce:
            # worker returned multiple responses, but the head is configured to skip reduction
            # just concatenate the docs in this case
            response_request.data.docs = WorkerRequestHandler.get_docs_from_request(
                requests
            )

        merged_metadata = self._merge_metadata(
            metadata,
            uses_after_metadata,
            uses_before_metadata,
            total_shards,
            failed_shards,
        )

        self._update_end_request_metrics(response_request)
        return response_request, merged_metadata

    def _get_endpoints_from_workers(
        self, connection_pool: GrpcConnectionPool, name: str, retries: int, stop_event
    ):
        from google.protobuf import json_format

        async def task():
            self.logger.debug(
                f'starting get endpoints from workers task for deployment {name}'
            )
            while not stop_event.is_set():
                try:
                    endpoints = await connection_pool.send_discover_endpoint(
                        name, retries=retries, shard_id=0, head=False
                    )
                    if endpoints is not None:
                        endp, _ = endpoints
                        schemas = json_format.MessageToDict(endp.schemas)
                        self._pydantic_models_by_endpoint = {}
                        models_created_by_name = {}
                        for endpoint, inner_dict in schemas.items():
                            input_model_name = inner_dict['input']['name']
                            input_model_schema = inner_dict['input']['model']
                            output_model_name = inner_dict['output']['name']
                            output_model_schema = inner_dict['output']['model']

                            if input_model_schema == legacy_doc_schema:
                                models_created_by_name[input_model_name] = (
                                    LegacyDocumentJina
                                )
                            elif input_model_name not in models_created_by_name:
                                input_model = create_base_doc_from_schema(
                                    input_model_schema, input_model_name, {}
                                )
                                models_created_by_name[input_model_name] = input_model

                            if output_model_name == legacy_doc_schema:
                                models_created_by_name[output_model_name] = (
                                    LegacyDocumentJina
                                )
                            elif output_model_name not in models_created_by_name:
                                output_model = create_base_doc_from_schema(
                                    output_model_schema, output_model_name, {}
                                )
                                models_created_by_name[output_model_name] = output_model

                            self._pydantic_models_by_endpoint[endpoint] = {
                                'input': models_created_by_name[input_model_name],
                                'output': models_created_by_name[output_model_name],
                            }
                        stop_event.set()
                        return
                    else:
                        await asyncio.sleep(0.1)
                except Exception as exc:
                    self.logger.debug(
                        f'Exception raised from sending discover endpoint {exc}'
                    )
                    await asyncio.sleep(0.1)

        return task()

    def cancel_endpoint_discovery_from_workers_task(self):
        """Cancel endpoint_discovery_from_worker task if exists and is not completed. Cancellation is required if the Flow is being terminated before the
        task is successful or hasn't reached the max timeout.
        """
        if self.endpoints_discovery_task:
            try:
                if not self.endpoints_discovery_task.done():
                    self.logger.debug(f'Cancelling endpoint discovery task.')
                    self.endpoints_discovery_stop_event.set()  # this event is useless if simply cancel
                    self.endpoints_discovery_task.cancel()
            except Exception as ex:
                self.logger.debug(
                    f'exception during endpoint discovery task cancellation: {ex}'
                )
                pass

    async def close(self):
        """Close the data request handler, by closing the executor and the batch queues."""
        self.logger.debug(f'Closing Request Handler')
        self.cancel_endpoint_discovery_from_workers_task()
        await self.connection_pool.close()
        self.logger.debug(f'Request Handler closed')

    async def process_single_data(self, request: DataRequest, context) -> DataRequest:
        """
        Process the received requests and return the result as a new request

        :param request: the data request to process
        :param context: grpc context
        :returns: the response request
        """
        return await self.process_data([request], context)

    def _handle_internalnetworkerror(self, err, context, response):
        err_code = err.code()
        if err_code == grpc.StatusCode.UNAVAILABLE:
            context.set_details(
                f'|Head: Failed to connect to worker (Executor) pod at address {err.dest_addr}. It may be down.'
            )
        elif err_code == grpc.StatusCode.DEADLINE_EXCEEDED:
            context.set_details(
                f'|Head: Connection to worker (Executor) pod at address {err.dest_addr} could be established, but timed out.'
            )
        elif err_code == grpc.StatusCode.NOT_FOUND:
            context.set_details(
                f'|Head: Connection to worker (Executor) pod at address {err.dest_addr} could be established, but resource was not found.'
            )
        context.set_code(err.code())
        self.logger.error(f'Error while getting responses from Pods: {err.details()}')
        if err.request_id:
            response.header.request_id = err.request_id
        return response

    async def process_data(self, requests: List[DataRequest], context) -> DataRequest:
        """
        Process the received data request and return the result as a new request

        :param requests: the data requests to process
        :param context: grpc context
        :returns: the response request
        """
        try:
            endpoint = dict(context.invocation_metadata()).get('endpoint')
            self.logger.debug(f'recv {len(requests)} DataRequest(s)')
            response, metadata = await self._handle_data_request(
                requests=requests,
                connection_pool=self.connection_pool,
                uses_before_address=self.uses_before_address,
                uses_after_address=self.uses_after_address,
                retries=self._retries,
                reduce=self._reduce,
                timeout_send=self.timeout_send,
                polling_type=self._polling[endpoint],
                deployment_name=self._deployment_name,
                endpoint=endpoint,
            )
            context.set_trailing_metadata(metadata.items())
            return response
        except (
            InternalNetworkError
        ) as err:  # can't connect, Flow broken, interrupt the streaming through gRPC error mechanism
            return self._handle_internalnetworkerror(
                err=err, context=context, response=Response()
            )
        except (
            RuntimeError,
            Exception,
        ) as ex:  # some other error, keep streaming going just add error info
            self.logger.error(
                (
                    f'{ex!r}'
                    + f'\n add "--quiet-error" to suppress the exception details'
                    if not self.args.quiet_error
                    else ''
                ),
                exc_info=not self.args.quiet_error,
            )
            requests[0].add_exception(ex, executor=None)
            context.set_trailing_metadata((('is-error', 'true'),))
            return requests[0]

    async def endpoint_discovery(self, empty, context) -> jina_pb2.EndpointsProto:
        """
        Uses the connection pool to send a discover endpoint call to the workers

        :param empty: The service expects an empty protobuf message
        :param context: grpc context
        :returns: the response request
        """
        self.logger.debug('got an endpoint discovery request')
        response = jina_pb2.EndpointsProto()
        try:
            if self.uses_before_address:
                (
                    uses_before_response,
                    _,
                ) = await self.connection_pool.send_discover_endpoint(
                    deployment='uses_before', head=False
                )
                response.endpoints.extend(uses_before_response.endpoints)
            if self.uses_after_address:
                (
                    uses_after_response,
                    _,
                ) = await self.connection_pool.send_discover_endpoint(
                    deployment='uses_after', head=False
                )
                response.endpoints.extend(uses_after_response.endpoints)

            worker_response, _ = await self.connection_pool.send_discover_endpoint(
                deployment=self._deployment_name, head=False
            )
            response.endpoints.extend(worker_response.endpoints)
            response.schemas.update(worker_response.schemas)
        except (
            InternalNetworkError
        ) as err:  # can't connect, Flow broken, interrupt the streaming through gRPC error mechanism
            return self._handle_internalnetworkerror(
                err=err, context=context, response=response
            )

        return response

    async def _status(self, empty, context) -> jina_pb2.JinaInfoProto:
        """
        Process the the call requested and return the JinaInfo of the Runtime

        :param empty: The service expects an empty protobuf message
        :param context: grpc context
        :returns: the response request
        """
        self.logger.debug('recv _status request')
        infoProto = jina_pb2.JinaInfoProto()
        version, env_info = get_full_version()
        for k, v in version.items():
            infoProto.jina[k] = str(v)
        for k, v in env_info.items():
            infoProto.envs[k] = str(v)
        return infoProto

    async def stream(
        self, request_iterator, context=None, *args, **kwargs
    ) -> AsyncIterator['Request']:
        """
        stream requests from client iterator and stream responses back.

        :param request_iterator: iterator of requests
        :param context: context of the grpc call
        :param args: positional arguments
        :param kwargs: keyword arguments
        :yield: responses to the request
        """
        async for request in request_iterator:
            yield await self.process_data([request], context)

    Call = stream
