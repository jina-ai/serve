import asyncio
import json
import threading
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Type

import grpc
from grpc import RpcError

from jina._docarray import Document, docarray_v2
from jina.clients.base import BaseClient
from jina.clients.base.stream_rpc import StreamRpc
from jina.clients.base.unary_rpc import UnaryRpc
from jina.clients.helper import callback_exec
from jina.excepts import BadClientInput, BadServerFlow, InternalNetworkError
from jina.logging.profile import ProgressBar
from jina.proto import jina_pb2, jina_pb2_grpc
from jina.serve.helper import extract_trailing_metadata, get_default_grpc_options
from jina.serve.networking.utils import get_grpc_channel
from jina.types.request.data import SingleDocumentRequest

if TYPE_CHECKING:  # pragma: no cover
    from jina.clients.base import CallbackFnType, InputType


class GRPCBaseClient(BaseClient):
    """A simple Python client for connecting to the gRPC gateway.

    It manages the asyncio event loop internally, so all interfaces are synchronous from the outside.
    """

    _lock = threading.RLock()

    async def _is_flow_ready(self, **kwargs) -> bool:
        """Sends a dry run to the Flow to validate if the Flow is ready to receive requests

        :param kwargs: potential kwargs received passed from the public interface
        :return: boolean indicating the health/readiness of the Flow
        """
        try:
            async with get_grpc_channel(
                f'{self.args.host}:{self.args.port}',
                asyncio=True,
                tls=self.args.tls,
            ) as channel:
                stub = jina_pb2_grpc.JinaGatewayDryRunRPCStub(channel)
                self.logger.debug(f'connected to {self.args.host}:{self.args.port}')
                call_result = stub.dry_run(
                    jina_pb2.google_dot_protobuf_dot_empty__pb2.Empty(),
                    metadata=kwargs.get('metadata', None),
                    credentials=kwargs.get('credentials', None),
                    timeout=kwargs.get('timeout', None),
                )
                metadata, response = (
                    await call_result.trailing_metadata(),
                    await call_result,
                )
                if response.code == jina_pb2.StatusProto.SUCCESS:
                    return True
                else:
                    self.logger.error(
                        f'Returned code is not expected! Exception: {response.exception}'
                    )
        except RpcError as e:
            self.logger.error(f'RpcError: {e.details()}')
        except Exception as e:
            self.logger.error(f'Error while getting response from grpc server {e!r}')

        return False

    async def _get_results(
        self,
        inputs: 'InputType',
        on_done: 'CallbackFnType',
        on_error: Optional['CallbackFnType'] = None,
        on_always: Optional['CallbackFnType'] = None,
        compression: Optional[str] = None,
        max_attempts: int = 1,
        initial_backoff: float = 0.5,
        max_backoff: float = 2,
        backoff_multiplier: float = 1.5,
        results_in_order: bool = False,
        stream: bool = True,
        prefetch: Optional[int] = None,
        **kwargs,
    ):
        try:
            self.compression = (
                getattr(grpc.Compression, compression)
                if compression
                else grpc.Compression.NoCompression
            )

            req_iter, inputs_length = self._get_requests(inputs=inputs, **kwargs)
            continue_on_error = self.continue_on_error
            # while loop with retries, check in which state the `iterator` remains after failure
            options = client_grpc_options(
                backoff_multiplier,
                initial_backoff,
                max_attempts,
                max_backoff,
                self.args.grpc_channel_options,
            )

            metadata = kwargs.pop('metadata', ())
            if results_in_order:
                metadata = metadata + (('__results_in_order__', 'true'),)

            if prefetch:
                metadata = metadata + (('__prefetch__', str(prefetch)),)

            with self._lock:
                async with get_grpc_channel(
                    f'{self.args.host}:{self.args.port}',
                    options=options,
                    asyncio=True,
                    tls=self.args.tls,
                    aio_tracing_client_interceptors=self.aio_tracing_client_interceptors(),
                ) as channel:
                    self.logger.debug(f'connected to {self.args.host}:{self.args.port}')

                    with ProgressBar(
                        total_length=inputs_length, disable=not self.show_progress
                    ) as p_bar:
                        try:
                            if stream:
                                stream_rpc = StreamRpc(
                                    channel=channel,
                                    continue_on_error=continue_on_error,
                                    metadata=metadata,
                                    on_always=on_always,
                                    on_done=on_done,
                                    on_error=on_error,
                                    p_bar=p_bar,
                                    req_iter=req_iter,
                                    max_attempts=max_attempts,
                                    backoff_multiplier=backoff_multiplier,
                                    initial_backoff=initial_backoff,
                                    max_backoff=max_backoff,
                                    logger=self.logger,
                                    show_progress=self.show_progress,
                                    compression=self.compression,
                                    **kwargs,
                                )
                                async for (
                                    response
                                ) in stream_rpc.stream_rpc_with_retry():
                                    yield response
                            else:
                                unary_rpc = UnaryRpc(
                                    channel=channel,
                                    continue_on_error=continue_on_error,
                                    metadata=metadata,
                                    on_always=on_always,
                                    on_done=on_done,
                                    on_error=on_error,
                                    p_bar=p_bar,
                                    req_iter=req_iter,
                                    max_attempts=max_attempts,
                                    backoff_multiplier=backoff_multiplier,
                                    initial_backoff=initial_backoff,
                                    max_backoff=max_backoff,
                                    logger=self.logger,
                                    show_progress=self.show_progress,
                                    compression=self.compression,
                                    client_args=self.args,
                                    prefetch=prefetch,
                                    results_in_order=results_in_order,
                                    **kwargs,
                                )
                                async for response in unary_rpc.unary_rpc_with_retry():
                                    yield response
                        except (grpc.aio.AioRpcError, InternalNetworkError) as err:
                            await self._handle_error_and_metadata(err)
        except KeyboardInterrupt:
            self.logger.warning('user cancel the process')
        except asyncio.CancelledError as ex:
            self.logger.warning(f'process error: {ex!r}')
            raise
        except:
            # Not sure why, adding this line helps in fixing a hanging test
            raise

    async def _handle_error_and_metadata(self, err):
        my_code = err.code()
        my_details = err.details()
        trailing_metadata = extract_trailing_metadata(err)
        msg = f'gRPC error: {my_code} {my_details}\n{trailing_metadata}'
        if my_code == grpc.StatusCode.UNAVAILABLE:
            self.logger.error(
                f'{msg}\nThe ongoing request is terminated as the server is not available or closed already.'
            )
            raise ConnectionError(msg)
        if my_code == grpc.StatusCode.NOT_FOUND:
            self.logger.error(
                f'{msg}\nThe ongoing request is terminated as a resource cannot be found.'
            )
            raise ConnectionError(msg)
        elif my_code == grpc.StatusCode.DEADLINE_EXCEEDED:
            self.logger.error(
                f'{msg}\nThe ongoing request is terminated due to a server-side timeout.'
            )
            raise ConnectionError(msg)
        elif my_code == grpc.StatusCode.INTERNAL:
            self.logger.error(f'{msg}\ninternal error on the server side')
            raise err
        elif (
            my_code == grpc.StatusCode.UNKNOWN
            and 'asyncio.exceptions.TimeoutError' in my_details
        ):
            raise BadClientInput(
                f'{msg}\n'
                'often the case is that you define/send a bad input iterator to jina, '
                'please double check your input iterator'
            ) from err
        else:
            raise BadServerFlow(msg) from err

    async def stream_doc_endpoint(
        self,
        request: SingleDocumentRequest,
        timeout: Optional[float] = None,
    ):
        """
        Use the stream_doc stub to send one document and stream documents back from the Executor

        :param request: The request to be sent
        :param timeout: defines timeout for sending request

        :yields: response document
        """
        async with get_grpc_channel(
            f'{self.args.host}:{self.args.port}',
            asyncio=True,
            tls=self.args.tls,
            aio_tracing_client_interceptors=self.aio_tracing_client_interceptors(),
        ) as channel:
            stub = jina_pb2_grpc.JinaSingleDocumentRequestRPCStub(channel)
            try:
                async for response in stub.stream_doc(request, timeout=timeout):
                    callback_exec(
                        response=response,
                        logger=self.logger,
                    )
                    yield response
            except (grpc.aio.AioRpcError, InternalNetworkError) as err:
                await self._handle_error_and_metadata(err)

    async def _get_streaming_results(
        self,
        on: str,
        inputs: 'Document',
        parameters: Optional[Dict] = None,
        return_type: Type[Document] = Document,
        timeout: Optional[int] = None,
        **kwargs,
    ):
        req = SingleDocumentRequest()
        req.header.exec_endpoint = on
        req.document_cls = inputs.__class__
        req.data.doc = inputs
        async for response in self.stream_doc_endpoint(request=req, timeout=timeout):
            yield return_type.from_protobuf(response.document)


def client_grpc_options(
    backoff_multiplier: float,
    initial_backoff: float,
    max_attempts: int,
    max_backoff: float,
    args_channel_options: Optional[Dict[str, Any]],
) -> List[Tuple[str, Any]]:
    """
    Builds grpc options for the client by taking into account the retry parameters, default gRPC options and additional gRPC options.
    :param max_attempts: Maximum number of attempts that are allowed.
    :param backoff_multiplier: Factor that will be raised to the exponent of (attempt - 1) for calculating the backoff wait time.
    :param initial_backoff: The backoff time on the first error. This will be multiplied by the backoff_multiplier exponent for subsequent wait time calculations.
    :param max_backoff: The maximum backoff wait time.
    :param args_channel_options: additional gRPC options that must be merged with the default options
    :return: List of gRPC options
    """
    grpc_options = get_default_grpc_options()

    if args_channel_options:
        grpc_options.extend(list(args_channel_options))

    if max_attempts > 1:
        options_with_retry_config = remove_grpc_service_config(grpc_options)
        service_config_json = json.dumps(
            {
                "methodConfig": [
                    {
                        # To apply retry to all methods, put [{}] in the "name" field
                        "name": [{}],
                        "retryPolicy": {
                            "maxAttempts": max_attempts,
                            "initialBackoff": f"{initial_backoff}s",
                            "maxBackoff": f"{max_backoff}s",
                            "backoffMultiplier": backoff_multiplier,
                            "retryableStatusCodes": [
                                "UNAVAILABLE",
                                "DEADLINE_EXCEEDED",
                                "INTERNAL",
                            ],
                        },
                    }
                ]
            }
        )
        # NOTE: the retry feature will be enabled by default >=v1.40.0
        options_with_retry_config.append(("grpc.enable_retries", 1))
        options_with_retry_config.append(("grpc.service_config", service_config_json))
        return options_with_retry_config

    return grpc_options


def remove_grpc_service_config(options: List[Tuple[str, Any]]) -> List[Tuple[str, Any]]:
    """
    Removes the 'grpc.service_config' configuration from the list of options.
    :param options: List of gRPC options
    :return: List of gRPC options
    """
    return [tup for tup in options if tup[0] != 'grpc.service_config']
