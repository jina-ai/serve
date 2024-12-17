import argparse
import asyncio
import functools
import json
import os
import tempfile
import threading
import uuid
import warnings
from typing import (
    TYPE_CHECKING,
    AsyncIterator,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Union,
)

from google.protobuf.struct_pb2 import Struct

from jina._docarray import DocumentArray, docarray_v2
from jina.constants import __default_endpoint__
from jina.excepts import BadConfigSource, RuntimeTerminated
from jina.helper import get_full_version
from jina.importer import ImportExtensions
from jina.proto import jina_pb2
from jina.serve.executors import BaseExecutor
from jina.serve.instrumentation import MetricsTimer
from jina.serve.runtimes.worker.batch_queue import BatchQueue
from jina.types.request.data import DataRequest, SingleDocumentRequest

if docarray_v2:
    from docarray import DocList

if TYPE_CHECKING:  # pragma: no cover
    import grpc
    from opentelemetry import metrics, trace
    from opentelemetry.context.context import Context
    from opentelemetry.propagate import Context
    from prometheus_client import CollectorRegistry

    from jina.logging.logger import JinaLogger
    from jina.types.request import Request


class WorkerRequestHandler:
    """Object to encapsulate the code related to handle the data requests passing to executor and its returned values"""

    _KEY_RESULT = '__results__'

    def __init__(
        self,
        args: 'argparse.Namespace',
        logger: 'JinaLogger',
        metrics_registry: Optional['CollectorRegistry'] = None,
        tracer_provider: Optional['trace.TracerProvider'] = None,
        meter_provider: Optional['metrics.MeterProvider'] = None,
        meter=None,
        tracer=None,
        deployment_name: str = '',
        **kwargs,
    ):
        """Initialize private parameters and execute private loading functions.

        :param args: args from CLI
        :param logger: the logger provided by the user
        :param metrics_registry: optional metrics registry for prometheus used if we need to expose metrics from the executor of from the data request handler
        :param tracer_provider: Optional tracer_provider that will be provided to the executor for tracing
        :param meter_provider: Optional meter_provider that will be provided to the executor for metrics
        :param meter: meter object from runtime
        :param tracer: tracer object from runtime
        :param deployment_name: name of the deployment to use as Executor name to set in requests
        :param kwargs: extra keyword arguments
        """
        super().__init__()
        self.meter = meter
        self.metrics_registry = metrics_registry
        self.tracer = tracer
        self.args = args
        self.logger = logger
        self._is_closed = False
        if self.metrics_registry:
            with ImportExtensions(
                required=True,
                help_text='You need to install the `prometheus_client` to use the montitoring functionality of jina',
            ):
                from prometheus_client import Counter, Summary

            self._summary = Summary(
                'receiving_request_seconds',
                'Time spent processing request',
                registry=self.metrics_registry,
                namespace='jina',
                labelnames=('runtime_name',),
            ).labels(self.args.name)

            self._failed_requests_metrics = Counter(
                'failed_requests',
                'Number of failed requests',
                registry=self.metrics_registry,
                namespace='jina',
                labelnames=('runtime_name',),
            ).labels(self.args.name)

            self._successful_requests_metrics = Counter(
                'successful_requests',
                'Number of successful requests',
                registry=self.metrics_registry,
                namespace='jina',
                labelnames=('runtime_name',),
            ).labels(self.args.name)

        else:
            self._summary = None
            self._failed_requests_metrics = None
            self._successful_requests_metrics = None

        if self.meter:
            self._receiving_request_seconds = self.meter.create_histogram(
                name='jina_receiving_request_seconds',
                description='Time spent processing request',
            )
            self._failed_requests_counter = self.meter.create_counter(
                name='jina_failed_requests',
                description='Number of failed requests',
            )

            self._successful_requests_counter = self.meter.create_counter(
                name='jina_successful_requests',
                description='Number of successful requests',
            )
        else:
            self._receiving_request_seconds = None
            self._failed_requests_counter = None
            self._successful_requests_counter = None
        self._metric_attributes = {'runtime_name': self.args.name}
        self._load_executor(
            metrics_registry=metrics_registry,
            tracer_provider=tracer_provider,
            meter_provider=meter_provider,
        )
        meter = (
            meter_provider.get_meter(self.__class__.__name__)
            if meter_provider
            else None
        )
        self._init_monitoring(metrics_registry, meter)
        self.deployment_name = deployment_name
        # In order to support batching parameters separately, we have to lazily create batch queues
        # So we store the config for each endpoint in the initialization
        self._batchqueue_config: Dict[str, Dict] = {}
        # the below is of "shape" exec_endpoint_name -> parameters_key -> batch_queue
        self._batchqueue_instances: Dict[str, Dict[str, BatchQueue]] = {}
        self._init_batchqueue_dict()
        self._snapshot = None
        self._did_snapshot_raise_exception = None
        self._restore = None
        self._did_restore_raise_exception = None
        self._snapshot_thread = None
        self._restore_thread = None
        self._snapshot_parent_directory = tempfile.mkdtemp()
        self._hot_reload_task = None
        if self.args.reload:
            self._hot_reload_task = asyncio.create_task(self._hot_reload())

    def _http_fastapi_default_app(self, **kwargs):
        from jina.serve.runtimes.worker.http_fastapi_app import (  # For Gateway, it works as for head
            get_fastapi_app,
        )

        request_models_map = self._executor._get_endpoint_models_dict()

        def call_handle(request):
            is_generator = request_models_map[request.header.exec_endpoint][
                'is_generator'
            ]

            return self.process_single_data(request, None, http=True, is_generator=is_generator)

        app = get_fastapi_app(
            request_models_map=request_models_map, caller=call_handle, **kwargs
        )

        @app.on_event('shutdown')
        async def _shutdown():
            await self.close()

        from jina.helper import extend_rest_interface

        return extend_rest_interface(app)

    def _http_fastapi_csp_app(self, **kwargs):
        from jina.serve.runtimes.worker.http_csp_app import get_fastapi_app

        request_models_map = self._executor._get_endpoint_models_dict()

        def call_handle(request):
            is_generator = request_models_map[request.header.exec_endpoint][
                'is_generator'
            ]

            return self.process_single_data(request, None, http=True, is_generator=is_generator)

        app = get_fastapi_app(
            request_models_map=request_models_map, caller=call_handle, **kwargs
        )

        @app.on_event('shutdown')
        async def _shutdown():
            await self.close()

        return app

    async def _hot_reload(self):
        import inspect

        executor_file = inspect.getfile(self._executor.__class__)
        watched_files = set([executor_file] + (self.args.py_modules or []))
        executor_base_path = os.path.dirname(os.path.abspath(executor_file))
        extra_paths = [
            os.path.join(path, name)
            for path, subdirs, files in os.walk(executor_base_path)
            for name in files
        ]
        extra_python_paths = list(filter(lambda x: x.endswith('.py'), extra_paths))
        for extra_python_file in extra_python_paths:
            watched_files.add(extra_python_file)

        with ImportExtensions(
            required=True,
            logger=self.logger,
            help_text='''hot reload requires watchfiles dependency to be installed. You can do `pip install 
                watchfiles''',
        ):
            from watchfiles import awatch

        async for changes in awatch(*watched_files):
            changed_files = [changed_file for _, changed_file in changes]
            self.logger.info(
                f'detected changes in: {changed_files}. Refreshing the Executor'
            )
            self._refresh_executor(changed_files)
            self.logger.info(f'Executor refreshed')

    def _all_batch_queues(self) -> List[BatchQueue]:
        """Returns a list of all batch queue instances
        :return: List of all batch queues for this request handler
        """
        return [
            batch_queue
            for param_to_queue in self._batchqueue_instances.values()
            for batch_queue in param_to_queue.values()
        ]

    def _init_batchqueue_dict(self):
        """Determines how endpoints and method names map to batch queues. Afterwards, this method initializes the
        dynamic batching state of the request handler:
            * _batchqueue_instances of "shape" exec_endpoint_name -> parameters_key -> batch_queue
            * _batchqueue_config mapping each exec_endpoint_name to a dynamic batching configuration
        """
        if getattr(self._executor, 'dynamic_batching', None) is not None:
            # We need to sort the keys into endpoints and functions
            # Endpoints allow specific configurations while functions allow configs to be applied to all endpoints of the function
            self.logger.debug(
                f'Executor Dynamic Batching configs: {self._executor.dynamic_batching}'
            )
            dbatch_endpoints = []
            dbatch_functions = []
            request_models_map = self._executor._get_endpoint_models_dict()

            for key, dbatch_config in self._executor.dynamic_batching.items():
                if request_models_map.get(key, {}).get('parameters', {}).get('model', None) is not None:
                    error_msg = f'Executor Dynamic Batching cannot be used for endpoint {key} because it depends on parameters.'
                    self.logger.error(
                        error_msg
                    )
                    raise Exception(error_msg)

                if key.startswith('/'):
                    dbatch_endpoints.append((key, dbatch_config))
                else:
                    dbatch_functions.append((key, dbatch_config))

            # Specific endpoint configs take precedence over function configs
            for endpoint, dbatch_config in dbatch_endpoints:
                self._batchqueue_config[endpoint] = dbatch_config

            # Process function configs
            func_endpoints: Dict[str, List[str]] = {
                func.fn.__name__: [] for func in self._executor.requests.values()
            }
            for endpoint, func in self._executor.requests.items():
                if func.fn.__name__ in func_endpoints:
                    # For SageMaker, not all endpoints are there
                    func_endpoints[func.fn.__name__].append(endpoint)
            for func_name, dbatch_config in dbatch_functions:
                if func_name in func_endpoints: # For SageMaker, not all endpoints are there
                    for endpoint in func_endpoints[func_name]:
                        if endpoint not in self._batchqueue_config:
                            self._batchqueue_config[endpoint] = dbatch_config
                        else:
                            # we need to eventually copy the `custom_metric`
                            if dbatch_config.get('custom_metric', None) is not None:
                                self._batchqueue_config[endpoint]['custom_metric'] = dbatch_config.get('custom_metric')

            keys_to_remove = []
            for k, batch_config in self._batchqueue_config.items():
                if not batch_config.get('use_dynamic_batching', True):
                    keys_to_remove.append(k)

            for k in keys_to_remove:
                self._batchqueue_config.pop(k)

            self.logger.debug(
                f'Endpoint Batch Queue Configs: {self._batchqueue_config}'
            )

            self._batchqueue_instances = {
                endpoint: {} for endpoint in self._batchqueue_config.keys()
            }

    def _init_monitoring(
        self,
        metrics_registry: Optional['CollectorRegistry'] = None,
        meter: Optional['metrics.Meter'] = None,
    ):
        if metrics_registry:
            with ImportExtensions(
                required=True,
                help_text='You need to install the `prometheus_client` to use the montitoring functionality of jina',
            ):
                from prometheus_client import Counter, Summary

                from jina.serve.monitoring import _SummaryDeprecated

                self._document_processed_metrics = Counter(
                    'document_processed',
                    'Number of Documents that have been processed by the executor',
                    namespace='jina',
                    labelnames=('executor_endpoint', 'executor', 'runtime_name'),
                    registry=metrics_registry,
                )

                self._request_size_metrics = _SummaryDeprecated(
                    old_name='request_size_bytes',
                    name='received_request_bytes',
                    documentation='The size in bytes of the request returned to the gateway',
                    namespace='jina',
                    labelnames=('executor_endpoint', 'executor', 'runtime_name'),
                    registry=metrics_registry,
                )

                self._sent_response_size_metrics = Summary(
                    'sent_response_bytes',
                    'The size in bytes of the response sent to the gateway',
                    namespace='jina',
                    labelnames=('executor_endpoint', 'executor', 'runtime_name'),
                    registry=metrics_registry,
                )
        else:
            self._document_processed_metrics = None
            self._request_size_metrics = None
            self._sent_response_size_metrics = None

        if meter:
            self._document_processed_counter = meter.create_counter(
                name='jina_document_processed',
                description='Number of Documents that have been processed by the executor',
            )

            self._request_size_histogram = meter.create_histogram(
                name='jina_received_request_bytes',
                description='The size in bytes of the request returned to the gateway',
            )

            self._sent_response_size_histogram = meter.create_histogram(
                name='jina_sent_response_bytes',
                description='The size in bytes of the response sent to the gateway',
            )
        else:
            self._document_processed_counter = None
            self._request_size_histogram = None
            self._sent_response_size_histogram = None

    def _load_executor(
        self,
        metrics_registry: Optional['CollectorRegistry'] = None,
        tracer_provider: Optional['trace.TracerProvider'] = None,
        meter_provider: Optional['metrics.MeterProvider'] = None,
    ):
        """
        Load the executor to this runtime, specified by ``uses`` CLI argument.
        :param metrics_registry: Optional prometheus metrics registry that will be passed to the executor so that it can expose metrics
        :param tracer_provider: Optional tracer_provider that will be provided to the executor for tracing
        :param meter_provider: Optional meter_provider that will be provided to the executor for metrics
        """
        try:
            self._executor: BaseExecutor = BaseExecutor.load_config(
                self.args.uses,
                uses_with=self.args.uses_with,
                uses_metas=self.args.uses_metas,
                uses_requests=self.args.uses_requests,
                uses_dynamic_batching=self.args.uses_dynamic_batching,
                runtime_args={  # these are not parsed to the yaml config file but are pass directly during init
                    'workspace': self.args.workspace,
                    'shard_id': self.args.shard_id,
                    'shards': self.args.shards,
                    'replicas': self.args.replicas,
                    'name': self.args.name,
                    'provider': self.args.provider,
                    'provider_endpoint': self.args.provider_endpoint,
                    'metrics_registry': metrics_registry,
                    'tracer_provider': tracer_provider,
                    'meter_provider': meter_provider,
                    'allow_concurrent': self.args.allow_concurrent,
                },
                py_modules=self.args.py_modules,
                extra_search_paths=self.args.extra_search_paths,
            )
            self.logger.debug(f'{self._executor} is successfully loaded!')

        except BadConfigSource:
            self.logger.error(f'fail to load config from {self.args.uses}')
            raise
        except FileNotFoundError:
            self.logger.error(f'fail to load file dependency')
            raise
        except Exception:
            self.logger.critical(f'can not load the executor from {self.args.uses}')
            raise

    def _refresh_executor(self, changed_files):
        import copy
        import importlib
        import inspect
        import sys

        try:
            sys_mod_files_modules = {
                getattr(module, '__file__', ''): module
                for module in sys.modules.values()
            }

            for file in changed_files:
                if file in sys_mod_files_modules:
                    file_module = sys_mod_files_modules[file]
                    # TODO: unable to reload main module (for instance, Executor implementation and Executor.serve are
                    #  in the same file). Raising a warning for now
                    if file_module.__name__ == '__main__':
                        self.logger.warning(
                            'The main module file was changed, cannot reload Executor, please restart '
                            'the application'
                        )
                    self.logger.debug(f'Reloading {file_module}')
                    try:
                        importlib.reload(file_module)
                    except ModuleNotFoundError:
                        spec = importlib.util.spec_from_file_location(
                            file_module.__name__, file_module.__file__
                        )
                        spec.loader.exec_module(file_module)

                    self.logger.debug(f'Reloaded {file_module} successfully')
                else:
                    self.logger.debug(
                        f'Changed file {file} was not previously imported.'
                    )
        except Exception as exc:
            self.logger.error(
                f'Exception when refreshing Executor when changes detected in {changed_files}: {exc}'
            )
            raise exc

        executor_module = inspect.getmodule(self._executor.__class__)
        try:
            importlib.reload(executor_module)
        except ModuleNotFoundError:
            spec = importlib.util.spec_from_file_location(
                executor_module.__name__, executor_module.__file__
            )
            spec.loader.exec_module(file_module)
        requests = copy.copy(self._executor.requests)
        old_cls = self._executor.__class__
        new_cls = getattr(importlib.import_module(old_cls.__module__), old_cls.__name__)
        new_executor = new_cls.__new__(new_cls)
        new_executor.__dict__ = self._executor.__dict__
        for k, v in requests.items():
            requests[k] = getattr(new_executor.__class__, requests[k].fn.__name__)
        self._executor = new_executor
        self._executor.requests.clear()
        requests = {k: v.__name__ for k, v in requests.items()}
        self._executor._add_requests(requests)

    @staticmethod
    def _parse_params(parameters: Union[Dict, Struct], executor_name: str):
        parsed_params = dict(parameters)
        specific_parameters = parsed_params.get(executor_name, None)
        if specific_parameters:
            parsed_params.update(**specific_parameters)

        return parsed_params

    @staticmethod
    def _metric_attributes(executor_endpoint, executor, runtime_name):
        return {
            'executor_endpoint': executor_endpoint,
            'executor': executor,
            'runtime_name': runtime_name,
        }

    def _record_request_size_monitoring(self, requests):
        for req in requests:
            if self._request_size_metrics:
                self._request_size_metrics.labels(
                    requests[0].header.exec_endpoint,
                    self._executor.__class__.__name__,
                    self.args.name,
                ).observe(req.nbytes)
            if self._request_size_histogram:
                attributes = WorkerRequestHandler._metric_attributes(
                    requests[0].header.exec_endpoint,
                    self._executor.__class__.__name__,
                    self.args.name,
                )
                self._request_size_histogram.record(req.nbytes, attributes=attributes)

    def _record_docs_processed_monitoring(self, requests, len_docs: int):
        if self._document_processed_metrics:
            self._document_processed_metrics.labels(
                requests[0].header.exec_endpoint,
                self._executor.__class__.__name__,
                self.args.name,
            ).inc(
                len_docs
            )  # TODO we can optimize here and access the
            # lenght of the da without loading the da in memory

        if self._document_processed_counter:
            attributes = WorkerRequestHandler._metric_attributes(
                requests[0].header.exec_endpoint,
                self._executor.__class__.__name__,
                self.args.name,
            )
            self._document_processed_counter.add(
                len_docs, attributes=attributes
            )  # TODO same as above

    def _record_response_size_monitoring(self, requests):
        if self._sent_response_size_metrics:
            self._sent_response_size_metrics.labels(
                requests[0].header.exec_endpoint,
                self._executor.__class__.__name__,
                self.args.name,
            ).observe(requests[0].nbytes)
        if self._sent_response_size_histogram:
            attributes = WorkerRequestHandler._metric_attributes(
                requests[0].header.exec_endpoint,
                self._executor.__class__.__name__,
                self.args.name,
            )
            self._sent_response_size_histogram.record(
                requests[0].nbytes, attributes=attributes
            )

    def _set_result(self, requests, return_data, docs, http=False):
        # assigning result back to request
        if return_data is not None:
            if isinstance(return_data, DocumentArray):
                docs = return_data
            elif isinstance(return_data, dict):
                params = requests[0].parameters
                results_key = self._KEY_RESULT

                if not results_key in params.keys():
                    params[results_key] = dict()

                params[results_key].update({self.args.name: return_data})
                requests[0].parameters = params

            else:
                raise TypeError(
                    f'The return type must be DocList / Dict / `None`, '
                    f'but getting {return_data!r}'
                )
        if not http:
            WorkerRequestHandler.replace_docs(
                requests[0], docs, self.args.output_array_type
            )
        else:
            requests[0].direct_docs = docs
        return docs

    def _setup_req_doc_array_cls(self, requests, exec_endpoint, is_response=False):
        """Set the request document_array_cls.

        :param requests: the requests to execute
        :param exec_endpoint: the execution endpoint to use
        :param is_response: flag indicating if the schema needs to come from request or response
        """
        endpoint_info = self._executor.requests[exec_endpoint]
        for req in requests:
            try:
                if not docarray_v2:
                    req.document_array_cls = DocumentArray
                else:
                    if (
                        not endpoint_info.is_generator
                        and not endpoint_info.is_singleton_doc
                    ):
                        req.document_array_cls = (
                            endpoint_info.request_schema
                            if not is_response
                            else endpoint_info.response_schema
                        )
                    else:
                        req.document_array_cls = (
                            DocList[endpoint_info.request_schema]
                            if not is_response
                            else DocList[endpoint_info.response_schema]
                        )
            except AttributeError:
                pass

    def _setup_requests(
        self,
        requests: List['DataRequest'],
        exec_endpoint: str,
    ):
        """Execute a request using the executor.

        :param requests: the requests to execute
        :param exec_endpoint: the execution endpoint to use
        :return: the result of the execution
        """

        self._record_request_size_monitoring(requests)

        params = self._parse_params(requests[0].parameters, self._executor.metas.name)
        self._setup_req_doc_array_cls(requests, exec_endpoint, is_response=False)
        return requests, params

    async def handle_generator(
        self, requests: List['DataRequest'], tracing_context: Optional['Context'] = None
    ) -> Generator:
        """Prepares and executes a request for generator endpoints.

        :param requests: The messages to handle containing a DataRequest
        :param tracing_context: Optional OpenTelemetry tracing context from the originating request.
        :returns: the processed message
        """
        # skip executor if endpoints mismatch
        exec_endpoint: str = requests[0].header.exec_endpoint
        if exec_endpoint not in self._executor.requests:
            if __default_endpoint__ in self._executor.requests:
                exec_endpoint = __default_endpoint__
            else:
                raise RuntimeError(
                    f'Request endpoint must match one of the available endpoints.'
                )

        requests, params = self._setup_requests(requests, exec_endpoint)
        if exec_endpoint in self._batchqueue_config:
            warnings.warn(
                'Batching is not supported for generator executors endpoints. Ignoring batch size.'
            )
        doc = requests[0].docs[0]
        docs_matrix, docs_map = None, None
        return await self._executor.__acall__(
            req_endpoint=exec_endpoint,
            doc=doc,
            parameters=params,
            docs_matrix=docs_matrix,
            docs_map=docs_map,
            tracing_context=tracing_context,
        )

    async def handle(
        self, requests: List['DataRequest'], http=False, tracing_context: Optional['Context'] = None
    ) -> DataRequest:
        """Initialize private parameters and execute private loading functions.

        :param requests: The messages to handle containing a DataRequest
        :param http: Flag indicating if it is used by the HTTP server for some optims
        :param tracing_context: Optional OpenTelemetry tracing context from the originating request.
        :returns: the processed message
        """
        # skip executor if endpoints mismatch
        exec_endpoint: str = requests[0].header.exec_endpoint
        if exec_endpoint not in self._executor.requests:
            if __default_endpoint__ in self._executor.requests:
                exec_endpoint = __default_endpoint__
            else:
                self.logger.debug(
                    f'skip executor: endpoint mismatch. '
                    f'Request endpoint: `{exec_endpoint}`. '
                    'Available endpoints: '
                    f'{", ".join(list(self._executor.requests.keys()))}'
                )
                return requests[0]

        requests, params = self._setup_requests(requests, exec_endpoint)
        len_docs = len(requests[0].docs)  # TODO we can optimize here and access the
        if exec_endpoint in self._batchqueue_config:
            assert len(requests) == 1, 'dynamic batching does not support no_reduce'

            param_key = json.dumps(params, sort_keys=True)
            if param_key not in self._batchqueue_instances[exec_endpoint]:
                self._batchqueue_instances[exec_endpoint][param_key] = BatchQueue(
                    functools.partial(self._executor.__acall__, exec_endpoint),
                    request_docarray_cls=self._executor.requests[
                        exec_endpoint
                    ].request_schema,
                    response_docarray_cls=self._executor.requests[
                        exec_endpoint
                    ].response_schema,
                    output_array_type=self.args.output_array_type,
                    params=params,
                    **self._batchqueue_config[exec_endpoint],
                )
            # This is necessary because push might need to await for the queue to be emptied
            # the batch queue will change the request in-place
            queue = await self._batchqueue_instances[exec_endpoint][param_key].push(
                requests[0], http=http
            )
            item = await queue.get()
            queue.task_done()
            if isinstance(item, Exception):
                raise item
        else:
            docs = WorkerRequestHandler.get_docs_from_request(requests)
            docs_matrix, docs_map = WorkerRequestHandler._get_docs_matrix_from_request(
                requests
            )
            return_data = await self._executor.__acall__(
                req_endpoint=exec_endpoint,
                docs=docs,
                parameters=params,
                docs_matrix=docs_matrix,
                docs_map=docs_map,
                tracing_context=tracing_context,
            )
            _ = self._set_result(requests, return_data, docs, http=http)

        for req in requests:
            req.add_executor(self.deployment_name)

        self._record_docs_processed_monitoring(requests, len_docs)
        try:
            self._setup_req_doc_array_cls(requests, exec_endpoint, is_response=True)
        except AttributeError:
            pass
        self._record_response_size_monitoring(requests)

        return requests[0]

    @staticmethod
    def replace_docs(
        request: List['DataRequest'], docs: 'DocumentArray', ndarray_type: str = None
    ) -> None:
        """Replaces the docs in a message with new Documents.

        :param request: The request object
        :param docs: the new docs to be used
        :param ndarray_type: type tensor and embedding will be converted to
        """
        request.data.set_docs_convert_arrays(docs, ndarray_type=ndarray_type)

    @staticmethod
    def replace_parameters(request: List['DataRequest'], parameters: Dict) -> None:
        """Replaces the parameters in a message with new Documents.

        :param request: The request object
        :param parameters: the new parameters to be used
        """
        request.parameters = parameters

    @staticmethod
    def merge_routes(requests: List['DataRequest']) -> None:
        """Merges all routes found in requests into the first message

        :param requests: The messages containing the requests with the routes to merge
        """
        if len(requests) <= 1:
            return
        existing_executor_routes = [r.executor for r in requests[0].routes]
        for request in requests[1:]:
            for route in request.routes:
                if route.executor not in existing_executor_routes:
                    requests[0].routes.append(route)
                    existing_executor_routes.append(route.executor)

    async def close(self):
        """Close the data request handler, by closing the executor and the batch queues."""
        self.logger.debug(f'Closing Request Handler')
        if self._hot_reload_task is not None:
            self._hot_reload_task.cancel()
        if not self._is_closed:
            self.logger.debug(f'Await closing all the batching queues')
            await asyncio.gather(*[q.close() for q in self._all_batch_queues()])
            self._executor.close()
            self._is_closed = True
        self.logger.debug(f'Request Handler closed')

    @staticmethod
    def _get_docs_matrix_from_request(
        requests: List['DataRequest'],
    ) -> Tuple[Optional[List['DocumentArray']], Optional[Dict[str, 'DocumentArray']]]:
        """
        Returns a docs matrix from a list of DataRequest objects.

        :param requests: List of DataRequest objects
        :return: docs matrix and doc: list of DocumentArray objects
        """
        docs_map = {}
        docs_matrix = []
        for req in requests:
            docs_matrix.append(req.docs)
            docs_map[req.last_executor] = req.docs

        # to unify all length=0 DocumentArray (or any other results) will simply considered as None
        # otherwise, the executor has to handle [None, None, None] or [DocArray(0), DocArray(0), DocArray(0)]
        len_r = sum(len(r) for r in docs_matrix)
        if len_r == 0:
            docs_matrix = None

        return docs_matrix, docs_map

    @staticmethod
    def get_parameters_dict_from_request(
        requests: List['DataRequest'],
    ) -> 'Dict':
        """
        Returns a parameters dict from a list of DataRequest objects.
        :param requests: List of DataRequest objects
        :return: parameters matrix: list of parameters (Dict) objects
        """
        key_result = WorkerRequestHandler._KEY_RESULT
        parameters = requests[0].parameters
        if key_result not in parameters.keys():
            parameters[key_result] = dict()
        # we only merge the results and make the assumption that the others params does not change during execution

        for req in requests:
            parameters[key_result].update(req.parameters.get(key_result, dict()))

        return parameters

    @staticmethod
    def get_docs_from_request(
        requests: List['DataRequest'],
    ) -> 'DocumentArray':
        """
        Gets a field from the message

        :param requests: requests to get the docs from

        :returns: DocumentArray extracted from the field from all messages
        """
        if len(requests) > 1:
            result = DocumentArray(d for r in requests for d in getattr(r, 'docs'))
        else:
            result = getattr(requests[0], 'docs')

        return result

    @staticmethod
    def reduce(docs_matrix: List['DocumentArray']) -> Optional['DocumentArray']:
        """
        Reduces a list of DocumentArrays into one DocumentArray. Changes are applied to the first
        DocumentArray in-place.

        Reduction consists in reducing every DocumentArray in `docs_matrix` sequentially using
        :class:`DocumentArray`.:method:`reduce`.
        The resulting DocumentArray contains Documents of all DocumentArrays.
        If a Document exists in many DocumentArrays, data properties are merged with priority to the left-most
        DocumentArrays (that is, if a data attribute is set in a Document belonging to many DocumentArrays, the
        attribute value of the left-most DocumentArray is kept).
        Matches and chunks of a Document belonging to many DocumentArrays are also reduced in the same way.
        Other non-data properties are ignored.

        .. note::
            - Matches are not kept in a sorted order when they are reduced. You might want to re-sort them in a later
                step.
            - The final result depends on the order of DocumentArrays when applying reduction.

        :param docs_matrix: List of DocumentArrays to be reduced
        :return: the resulting DocumentArray
        """
        if docs_matrix:
            if not docarray_v2:
                da = docs_matrix[0]
                da.reduce_all(docs_matrix[1:])
            else:
                from docarray.utils.reduce import reduce_all

                da = reduce_all(docs_matrix)
            return da

    @staticmethod
    def reduce_requests(requests: List['DataRequest']) -> 'DataRequest':
        """
        Reduces a list of requests containing DocumentArrays into one request object. Changes are applied to the first
        request object in-place.

        Reduction consists in reducing every DocumentArray in `requests` sequentially using
        :class:`DocumentArray`.:method:`reduce`.
        The resulting DataRequest object contains Documents of all DocumentArrays inside requests.

        :param requests: List of DataRequest objects
        :return: the resulting DataRequest
        """
        response_request = requests[0]
        for i, worker_result in enumerate(requests):
            if worker_result.status.code == jina_pb2.StatusProto.SUCCESS:
                response_request = worker_result
                break
        docs_matrix, _ = WorkerRequestHandler._get_docs_matrix_from_request(requests)

        # Reduction is applied in-place to the first DocumentArray in the matrix
        da = WorkerRequestHandler.reduce(docs_matrix)
        WorkerRequestHandler.replace_docs(response_request, da)

        params = WorkerRequestHandler.get_parameters_dict_from_request(requests)
        WorkerRequestHandler.replace_parameters(response_request, params)

        return response_request

    # serving part
    async def process_single_data(
        self, request: DataRequest, context, http: bool = False, is_generator: bool = False
    ) -> DataRequest:
        """
        Process the received requests and return the result as a new request

        :param request: the data request to process
        :param context: grpc context
        :param http: Flag indicating if it is used by the HTTP server for some optims
        :param is_generator: whether the request should be handled with streaming
        :returns: the response request
        """
        self.logger.debug('recv a process_single_data request')
        return await self.process_data([request], context, http=http, is_generator=is_generator)

    async def stream_doc(
        self, request: SingleDocumentRequest, context: 'grpc.aio.ServicerContext'
    ) -> SingleDocumentRequest:
        """
        Process the received requests and return the result as a new request, used for streaming behavior, one doc IN, several out

        :param request: the data request to process
        :param context: grpc context
        :yields: the response request
        """
        self.logger.debug('recv an stream_doc request')
        request_endpoint = self._executor.requests.get(
            request.header.exec_endpoint
        ) or self._executor.requests.get(__default_endpoint__)

        if request_endpoint is None:
            self.logger.debug(
                f'skip executor: endpoint mismatch. '
                f'Request endpoint: `{request.header.exec_endpoint}`. '
                'Available endpoints: '
                f'{", ".join(list(self._executor.requests.keys()))}'
            )
            yield request

        is_generator = getattr(request_endpoint.fn, '__is_generator__', False)
        if not is_generator:
            ex = ValueError('endpoint must be generator')
            self.logger.error(
                (
                    f'{ex!r}'
                    + f'\n add "--quiet-error" to suppress the exception details'
                    if not self.args.quiet_error
                    else ''
                ),
                exc_info=not self.args.quiet_error,
            )
            request.add_exception(ex)
            yield request
        else:
            request_schema = request_endpoint.request_schema
            data_request = DataRequest()
            data_request.header.exec_endpoint = request.header.exec_endpoint
            data_request.header.request_id = request.header.request_id
            if not docarray_v2:
                from docarray import Document

                data_request.data.docs = DocumentArray(
                    [Document.from_protobuf(request.document)]
                )
            else:
                from docarray import DocList

                data_request.data.docs = DocList[request_endpoint.request_schema](
                    [request_schema.from_protobuf(request.document)]
                )

            result = await self.process_data(
                [data_request], context, is_generator=is_generator
            )
            async for doc in result:
                if not isinstance(doc, request_endpoint.response_schema):
                    ex = ValueError(
                        f'output document type {doc.__class__.__name__} does not match the endpoint output type {request_endpoint.response_schema.__name__}'
                    )
                    self.logger.error(
                        (
                            f'{ex!r}'
                            + f'\n add "--quiet-error" to suppress the exception details'
                            if not self.args.quiet_error
                            else ''
                        ),
                        exc_info=not self.args.quiet_error,
                    )
                    req = SingleDocumentRequest()
                    req.add_exception(ex)
                else:
                    req = SingleDocumentRequest()
                    req.document_cls = doc.__class__
                    req.data.doc = doc

                self.logger.debug('yielding response')
                yield req

    async def endpoint_discovery(self, empty, context) -> jina_pb2.EndpointsProto:
        """
        Process the the call requested and return the list of Endpoints exposed by the Executor wrapped inside this Runtime

        :param empty: The service expects an empty protobuf message
        :param context: grpc context
        :returns: the response request
        """
        from google.protobuf import json_format

        self.logger.debug('recv an endpoint discovery request')
        endpoints_proto = jina_pb2.EndpointsProto()
        endpoints_proto.endpoints.extend(list(self._executor.requests.keys()))
        endpoints_proto.write_endpoints.extend(list(self._executor.write_endpoints))
        schemas = self._executor._get_endpoint_models_dict()
        if docarray_v2:
            from docarray.documents.legacy import LegacyDocument

            from jina.serve.runtimes.helper import _create_aux_model_doc_list_to_list

            legacy_doc_schema = LegacyDocument.schema()
            for endpoint_name, inner_dict in schemas.items():
                if inner_dict['input']['model'].schema() == legacy_doc_schema:
                    inner_dict['input']['model'] = legacy_doc_schema
                else:
                    inner_dict['input']['model'] = _create_aux_model_doc_list_to_list(
                        inner_dict['input']['model']
                    ).schema()

                if inner_dict['output']['model'].schema() == legacy_doc_schema:
                    inner_dict['output']['model'] = legacy_doc_schema
                else:
                    inner_dict['output']['model'] = _create_aux_model_doc_list_to_list(
                        inner_dict['output']['model']
                    ).schema()

                if inner_dict['parameters']['model'] is not None:
                    inner_dict['parameters']['model'] = inner_dict['parameters'][
                        'model'
                    ].schema()
        else:
            for endpoint_name, inner_dict in schemas.items():
                inner_dict['input']['model'] = inner_dict['input']['model'].schema()
                inner_dict['output']['model'] = inner_dict['output']['model'].schema()
                inner_dict['parameters'] = {}
        json_format.ParseDict(schemas, endpoints_proto.schemas)
        return endpoints_proto

    def _extract_tracing_context(
        self, metadata: 'grpc.aio.Metadata'
    ) -> Optional['Context']:
        if self.tracer:
            from opentelemetry.propagate import extract
            context = extract(dict(metadata))
            return context

        return None

    async def process_data(
        self, requests: List[DataRequest], context, http=False, is_generator: bool = False
    ) -> DataRequest:
        """
        Process the received requests and return the result as a new request

        :param requests: the data requests to process
        :param context: grpc context
        :param http: Flag indicating if it is used by the HTTP server for some optims
        :param is_generator: whether the request should be handled with streaming
        :returns: the response request
        """
        self.logger.debug('recv a process_data request')
        with MetricsTimer(
            self._summary, self._receiving_request_seconds, self._metric_attributes
        ):
            try:
                if self.logger.debug_enabled:
                    self.logger.debug(
                        f'recv DataRequest at {requests[0].header.exec_endpoint} with id: {requests[0].header.request_id}'
                    )

                if context is not None:
                    tracing_context = self._extract_tracing_context(
                        context.invocation_metadata()
                    )
                else:
                    tracing_context = None

                if is_generator:
                    result = await self.handle_generator(
                        requests=requests, tracing_context=tracing_context
                    )
                else:
                    result = await self.handle(
                        requests=requests, http=http, tracing_context=tracing_context
                    )

                if self._successful_requests_metrics:
                    self._successful_requests_metrics.inc()
                if self._successful_requests_counter:
                    self._successful_requests_counter.add(
                        1, attributes=self._metric_attributes
                    )
                if self.logger.debug_enabled:
                    if isinstance(result, DataRequest):
                        self.logger.debug(
                            f'return DataRequest from {result.header.exec_endpoint} with id: {result.header.request_id}'
                        )
                return result
            except (RuntimeError, Exception) as ex:
                self.logger.error(
                    (
                        f'{ex!r}'
                        + f'\n add "--quiet-error" to suppress the exception details'
                        if not self.args.quiet_error
                        else ''
                    ),
                    exc_info=not self.args.quiet_error,
                )

                requests[0].add_exception(ex, self._executor)
                if context is not None:
                    context.set_trailing_metadata((('is-error', 'true'),))
                if self._failed_requests_metrics:
                    self._failed_requests_metrics.inc()
                if self._failed_requests_counter:
                    self._failed_requests_counter.add(
                        1, attributes=self._metric_attributes
                    )

                if (
                    self.args.exit_on_exceptions
                    and type(ex).__name__ in self.args.exit_on_exceptions
                ):
                    self.logger.info('Exiting because of "--exit-on-exceptions".')
                    raise RuntimeTerminated
                return requests[0]

    async def _status(self, empty, context) -> jina_pb2.JinaInfoProto:
        """
        Process the the call requested and return the JinaInfo of the Runtime

        :param empty: The service expects an empty protobuf message
        :param context: grpc context
        :returns: the response request
        """
        self.logger.debug('recv _status request')
        info_proto = jina_pb2.JinaInfoProto()
        version, env_info = get_full_version()
        for k, v in version.items():
            info_proto.jina[k] = str(v)
        for k, v in env_info.items():
            info_proto.envs[k] = str(v)
        return info_proto

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
        self.logger.debug('recv a stream request')
        async for request in request_iterator:
            yield await self.process_data([request], context)

    Call = stream

    def _create_snapshot_status(
        self,
        snapshot_directory: str,
    ) -> 'jina_pb2.SnapshotStatusProto':
        _id = str(uuid.uuid4())
        self.logger.debug(f'Generated snapshot id: {_id}')
        return jina_pb2.SnapshotStatusProto(
            id=jina_pb2.SnapshotId(value=_id),
            status=jina_pb2.SnapshotStatusProto.Status.RUNNING,
            snapshot_file=os.path.join(
                os.path.join(snapshot_directory, _id), 'state.bin'
            ),
        )

    def _create_restore_status(
        self,
    ) -> 'jina_pb2.SnapshotStatusProto':
        _id = str(uuid.uuid4())
        self.logger.debug(f'Generated restore id: {_id}')
        return jina_pb2.RestoreSnapshotStatusProto(
            id=jina_pb2.RestoreId(value=_id),
            status=jina_pb2.RestoreSnapshotStatusProto.Status.RUNNING,
        )

    async def snapshot(self, request, context) -> 'jina_pb2.SnapshotStatusProto':
        """
        method to start a snapshot process of the Executor
        :param request: the empty request
        :param context: grpc context

        :return: the status of the snapshot
        """
        self.logger.debug('Calling snapshot')
        if (
            self._snapshot
            and self._snapshot_thread
            and self._snapshot_thread.is_alive()
        ):
            raise RuntimeError(
                f'A snapshot with id {self._snapshot.id.value} is currently in progress. Cannot start another.'
            )
        else:
            self._snapshot = self._create_snapshot_status(
                self._snapshot_parent_directory,
            )
            self._did_snapshot_raise_exception = threading.Event()
            self._snapshot_thread = threading.Thread(
                target=self._executor._run_snapshot,
                args=(self._snapshot.snapshot_file, self._did_snapshot_raise_exception),
            )
            self._snapshot_thread.start()
            return self._snapshot

    async def snapshot_status(
        self, request: 'jina_pb2.SnapshotId', context
    ) -> 'jina_pb2.SnapshotStatusProto':
        """
        method to start a snapshot process of the Executor
        :param request: the snapshot Id to get the status from
        :param context: grpc context

        :return: the status of the snapshot
        """
        self.logger.debug(
            f'Checking status of snapshot with ID of request {request.value} and current snapshot {self._snapshot.id.value if self._snapshot else "DOES NOT EXIST"}'
        )
        if not self._snapshot or (self._snapshot.id.value != request.value):
            return jina_pb2.SnapshotStatusProto(
                id=jina_pb2.SnapshotId(value=request.value),
                status=jina_pb2.SnapshotStatusProto.Status.NOT_FOUND,
            )
        elif self._snapshot_thread and self._snapshot_thread.is_alive():
            return jina_pb2.SnapshotStatusProto(
                id=jina_pb2.SnapshotId(value=request.value),
                status=jina_pb2.SnapshotStatusProto.Status.RUNNING,
            )
        elif self._snapshot_thread and not self._snapshot_thread.is_alive():
            status = jina_pb2.SnapshotStatusProto.Status.SUCCEEDED
            if self._did_snapshot_raise_exception.is_set():
                status = jina_pb2.SnapshotStatusProto.Status.FAILED
            self._did_snapshot_raise_exception = None
            return jina_pb2.SnapshotStatusProto(
                id=jina_pb2.SnapshotId(value=request.value),
                status=status,
            )

        return jina_pb2.SnapshotStatusProto(
            id=jina_pb2.SnapshotId(value=request.value),
            status=jina_pb2.SnapshotStatusProto.Status.NOT_FOUND,
        )

    async def restore(self, request: 'jina_pb2.RestoreSnapshotCommand', context):
        """
        method to start a restore process of the Executor
        :param request: the command request with the path from where to restore the Executor
        :param context: grpc context

        :return: the status of the snapshot
        """
        self.logger.debug(f'Calling restore')
        if self._restore and self._restore_thread and self._restore_thread.is_alive():
            raise RuntimeError(
                f'A restore with id {self._restore.id.value} is currently in progress. Cannot start another.'
            )
        else:
            self._restore = self._create_restore_status()
            self._did_restore_raise_exception = threading.Event()

            self._restore_thread = threading.Thread(
                target=self._executor._run_restore,
                args=(request.snapshot_file, self._did_restore_raise_exception),
            )
            self._restore_thread.start()
        return self._restore

    async def restore_status(
        self, request, context
    ) -> 'jina_pb2.RestoreSnapshotStatusProto':
        """
        method to start a snapshot process of the Executor
        :param request: the request with the Restore ID from which to get status
        :param context: grpc context

        :return: the status of the snapshot
        """
        self.logger.debug(
            f'Checking status of restore with ID of request {request.value} and current restore {self._restore.id.value if self._restore else "DOES NOT EXIST"}'
        )
        if not self._restore or (self._restore.id.value != request.value):
            return jina_pb2.RestoreSnapshotStatusProto(
                id=jina_pb2.RestoreId(value=request.value),
                status=jina_pb2.RestoreSnapshotStatusProto.Status.NOT_FOUND,
            )
        elif self._restore_thread and self._restore_thread.is_alive():
            return jina_pb2.RestoreSnapshotStatusProto(
                id=jina_pb2.RestoreId(value=request.value),
                status=jina_pb2.RestoreSnapshotStatusProto.Status.RUNNING,
            )
        elif self._restore_thread and not self._restore_thread.is_alive():
            status = jina_pb2.RestoreSnapshotStatusProto.Status.SUCCEEDED
            if self._did_restore_raise_exception.is_set():
                status = jina_pb2.RestoreSnapshotStatusProto.Status.FAILED
            self._did_restore_raise_exception = None
            return jina_pb2.RestoreSnapshotStatusProto(
                id=jina_pb2.RestoreId(value=request.value),
                status=status,
            )

        return jina_pb2.RestoreSnapshotStatusProto(
            id=jina_pb2.RestoreId(value=request.value),
            status=jina_pb2.RestoreSnapshotStatusProto.Status.NOT_FOUND,
        )
