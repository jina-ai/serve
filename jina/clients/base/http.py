import asyncio
import json
from contextlib import AsyncExitStack
from typing import TYPE_CHECKING, Dict, Optional, Tuple, Type

from jina._docarray import Document, DocumentArray, docarray_v2
from jina.clients.base import BaseClient
from jina.clients.base.helper import HTTPClientlet, handle_response_status
from jina.clients.helper import callback_exec
from jina.importer import ImportExtensions
from jina.logging.profile import ProgressBar
from jina.serve.stream import RequestStreamer
from jina.types.request import Request
from jina.types.request.data import DataRequest

if TYPE_CHECKING:  # pragma: no cover
    from jina.clients.base import CallbackFnType, InputType


class HTTPBaseClient(BaseClient):
    """A MixIn for HTTP Client."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._endpoints = []
        self.reuse_session = False
        self._lock = AsyncExitStack()
        self.iolet = None

    async def close(self):
        """Closes the potential resources of the Client.
        :return: Return whatever a close method may return
        """
        ret = super().close()
        if self.iolet is not None:
            await self.iolet.__aexit__(None, None, None)
        return ret

    async def _get_endpoints_from_openapi(self, **kwargs):
        def extract_paths_by_method(spec):
            paths_by_method = {}
            for path, methods in spec['paths'].items():
                for method, details in methods.items():
                    if method not in paths_by_method:
                        paths_by_method[method] = []
                    paths_by_method[method].append(path.strip('/'))

            return paths_by_method

        import json

        import aiohttp

        session_kwargs = {}
        if 'headers' in kwargs:
            session_kwargs = {'headers': kwargs['headers']}

        proto = 'https' if self.args.tls else 'http'
        target_url = f'{proto}://{self.args.host}:{self.args.port}/openapi.json'
        try:

            async with aiohttp.ClientSession(**session_kwargs) as session:
                async with session.get(target_url) as response:
                    content = await response.read()
                    openapi_response = json.loads(content.decode())
                    self._endpoints = extract_paths_by_method(openapi_response).get(
                        'post', []
                    )
        except:
            pass

    async def _is_flow_ready(self, **kwargs) -> bool:
        """Sends a dry run to the Flow to validate if the Flow is ready to receive requests

        :param kwargs: kwargs coming from the public interface. Includes arguments to be passed to the `HTTPClientlet`
        :return: boolean indicating the health/readiness of the Flow
        """
        from jina.proto import jina_pb2

        async with AsyncExitStack() as stack:
            try:
                proto = 'https' if self.args.tls else 'http'
                url = f'{proto}://{self.args.host}:{self.args.port}/dry_run'

                if not self.reuse_session:
                    iolet = await stack.enter_async_context(
                        HTTPClientlet(
                            logger=self.logger,
                            tracer_provider=self.tracer_provider,
                            **kwargs,
                        )
                    )
                else:
                    async with self._lock:
                        if self.iolet is None:
                            self.iolet = HTTPClientlet(
                                logger=self.logger,
                                tracer_provider=self.tracer_provider,
                                **kwargs,
                            )
                            await self.iolet.__aenter__()
                        iolet = self.iolet

                response = await iolet.send_dry_run(url=url, **kwargs)
                r_status = response.status

                r_str = await response.json()
                handle_response_status(r_status, r_str, url)
                if r_str['code'] == jina_pb2.StatusProto.SUCCESS:
                    return True
                else:
                    self.logger.error(
                        f'Returned code is not expected! Description: {r_str["description"]}'
                    )
            except Exception as e:
                self.logger.error(
                    f'Error while fetching response from HTTP server {e!r}'
                )
        return False

    async def _get_results(
            self,
            inputs: 'InputType',
            on_done: 'CallbackFnType',
            on_error: Optional['CallbackFnType'] = None,
            on_always: Optional['CallbackFnType'] = None,
            max_attempts: int = 1,
            initial_backoff: float = 0.5,
            max_backoff: float = 0.1,
            backoff_multiplier: float = 1.5,
            results_in_order: bool = False,
            prefetch: Optional[int] = None,
            timeout: Optional[int] = None,
            return_type: Type[DocumentArray] = DocumentArray,
            **kwargs,
    ):
        """
        :param inputs: the callable
        :param on_done: the callback for on_done
        :param on_error: the callback for on_error
        :param on_always: the callback for on_always
        :param max_attempts: Number of sending attempts, including the original request.
        :param initial_backoff: The first retry will happen with a delay of random(0, initial_backoff)
        :param max_backoff: The maximum accepted backoff after the exponential incremental delay
        :param backoff_multiplier: The n-th attempt will occur at random(0, min(initialBackoff*backoffMultiplier**(n-1), maxBackoff))
        :param results_in_order: return the results in the same order as the inputs
        :param prefetch: How many Requests are processed from the Client at the same time.
        :param timeout: Timeout for the client to remain connected to the server.
        :param return_type: the DocumentArray type to be returned. By default, it is `DocumentArray`.
        :param kwargs: kwargs coming from the public interface. Includes arguments to be passed to the `HTTPClientlet`
        :yields: generator over results
        """
        with ImportExtensions(required=True):
            pass

        request_iterator, inputs_length = self._get_requests(inputs=inputs, **kwargs)
        on = kwargs.get('on', '/post')
        if len(self._endpoints) == 0:
            await self._get_endpoints_from_openapi(**kwargs)

        async with AsyncExitStack() as stack:
            cm1 = ProgressBar(
                total_length=inputs_length, disable=not self.show_progress
            )
            p_bar = stack.enter_context(cm1)
            proto = 'https' if self.args.tls else 'http'
            endpoint = on.strip('/')
            has_default_endpoint = 'default' in self._endpoints

            if endpoint != '' and endpoint in self._endpoints:
                url = f'{proto}://{self.args.host}:{self.args.port}/{on.strip("/")}'
            elif has_default_endpoint:
                url = f'{proto}://{self.args.host}:{self.args.port}/default'
            else:
                url = f'{proto}://{self.args.host}:{self.args.port}/post'

            if not self.reuse_session:
                iolet = await stack.enter_async_context(
                    HTTPClientlet(
                        logger=self.logger,
                        tracer_provider=self.tracer_provider,
                        timeout=timeout,
                        max_attempts=max_attempts,
                        initial_backoff=initial_backoff,
                        max_backoff=max_backoff,
                        backoff_multiplier=backoff_multiplier,
                        **kwargs,
                    )
                )
            else:
                async with self._lock:
                    if self.iolet is None:
                        self.iolet = HTTPClientlet(
                            logger=self.logger,
                            tracer_provider=self.tracer_provider,
                            timeout=timeout,
                            max_attempts=max_attempts,
                            initial_backoff=initial_backoff,
                            max_backoff=max_backoff,
                            backoff_multiplier=backoff_multiplier,
                            **kwargs,
                        )
                        self.iolet = await self.iolet.__aenter__()
                iolet = self.iolet

            def _request_handler(
                    request: 'Request', **kwargs
            ) -> 'Tuple[asyncio.Future, Optional[asyncio.Future]]':
                """
                For HTTP Client, for each request in the iterator, we `send_message` using
                http POST request and add it to the list of tasks which is awaited and yielded.
                :param request: current request in the iterator
                :param kwargs: kwargs
                :return: asyncio Task for sending message
                """
                return asyncio.ensure_future(iolet.send_message(url=url, request=request)), None

            def _result_handler(result):
                return result

            streamer_args = vars(self.args)
            if prefetch:
                streamer_args['prefetch'] = prefetch
            streamer = RequestStreamer(
                request_handler=_request_handler,
                result_handler=_result_handler,
                logger=self.logger,
                **streamer_args,
            )
            async for response in streamer.stream(
                    request_iterator=request_iterator, results_in_order=results_in_order
            ):
                r_status, r_str = response
                handle_response_status(r_status, r_str, url)

                da = None
                if 'data' in r_str and r_str['data'] is not None:
                    from jina._docarray import DocumentArray, docarray_v2

                    if not docarray_v2:
                        da = DocumentArray.from_dict(r_str['data'])
                    else:
                        from docarray import DocList

                        if issubclass(return_type, DocList):
                            da = return_type(
                                [return_type.doc_type(**v) for v in r_str['data']]
                            )
                        else:
                            da = DocList[return_type](
                                [return_type(**v) for v in r_str['data']]
                            )
                    del r_str['data']

                resp = DataRequest(r_str)
                if da is not None:
                    resp.direct_docs = da

                callback_exec(
                    response=resp,
                    logger=self.logger,
                    on_error=on_error,
                    on_done=on_done,
                    on_always=on_always,
                    continue_on_error=self.continue_on_error,
                )
                if self.show_progress:
                    p_bar.update()
                yield resp

    async def _get_streaming_results(
            self,
            on: str,
            inputs: 'Document',
            parameters: Optional[Dict] = None,
            return_type: Type[Document] = Document,
            timeout: Optional[int] = None,
            **kwargs,
    ):
        proto = 'https' if self.args.tls else 'http'
        endpoint = on.strip('/')
        has_default_endpoint = 'default' in self._endpoints

        if (endpoint != '' and endpoint in self._endpoints) or not has_default_endpoint:
            url = f'{proto}://{self.args.host}:{self.args.port}/{endpoint}'
        else:
            url = f'{proto}://{self.args.host}:{self.args.port}/default'
        async with AsyncExitStack() as stack:
            if not self.reuse_session:
                iolet = await stack.enter_async_context(
                    HTTPClientlet(
                        logger=self.logger,
                        tracer_provider=self.tracer_provider,
                        timeout=timeout,
                        **kwargs,
                    )
                )
            else:
                async with self._lock:
                    if self.iolet is None:
                        self.iolet = HTTPClientlet(
                            logger=self.logger,
                            tracer_provider=self.tracer_provider,
                            timeout=timeout,
                            **kwargs,
                        )
                        await self.iolet.__aenter__()
                    iolet = self.iolet
            async for doc in iolet.send_streaming_message(url=url, doc=inputs, on=on):
                if not docarray_v2:
                    yield Document.from_dict(json.loads(doc))
                else:
                    yield return_type(**json.loads(doc))
