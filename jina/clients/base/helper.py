import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, Optional, Union

import aiohttp
from aiohttp import WSMsgType
from aiohttp.payload import BytesPayload
from starlette import status

from jina._docarray import docarray_v2
from jina.clients.base import retry
from jina.enums import WebsocketSubProtocols
from jina.excepts import BadClient
from jina.importer import ImportExtensions
from jina.types.request import Request
from jina.types.request.data import DataRequest
from jina.types.request.status import StatusMessage

if TYPE_CHECKING:  # pragma: no cover
    from opentelemetry import trace

    from jina._docarray import Document
    from jina.logging.logger import JinaLogger

if docarray_v2:
    from docarray.base_doc.io.json import orjson_dumps

    class JinaJsonPayload(BytesPayload):
        """A JSON payload for Jina Requests"""

        def __init__(
            self,
            value,
            *args,
            **kwargs,
        ) -> None:
            super().__init__(
                orjson_dumps(value),
                content_type="application/json",
                encoding="utf-8",
                *args,
                **kwargs,
            )


class AioHttpClientlet(ABC):
    """aiohttp session manager"""

    def __init__(
        self,
        logger: 'JinaLogger',
        max_attempts: int = 1,
        initial_backoff: float = 0.5,
        max_backoff: float = 2,
        backoff_multiplier: float = 1.5,
        tracer_provider: Optional['trace.TraceProvider'] = None,
        **kwargs,
    ) -> None:
        """HTTP Client to be used with the streamer

        :param logger: jina logger
        :param max_attempts: Number of sending attempts, including the original request.
        :param initial_backoff: The first retry will happen with a delay of random(0, initial_backoff)
        :param max_backoff: The maximum accepted backoff after the exponential incremental delay
        :param backoff_multiplier: The n-th attempt will occur at random(0, min(initialBackoff*backoffMultiplier**(n-1), maxBackoff))
        :param tracer_provider: Optional tracer_provider that will be used to configure aiohttp tracing.
        :param kwargs: kwargs  which will be forwarded to the `aiohttp.Session` instance. Used to pass headers to requests
        """
        self.logger = logger
        self.msg_recv = 0
        self.msg_sent = 0
        if tracer_provider:
            from opentelemetry.instrumentation.aiohttp_client import create_trace_config

            self._trace_config = [create_trace_config(tracer_provider=tracer_provider)]
        else:
            self._trace_config = None
        self.session = None
        self._session_kwargs = {}
        if kwargs.get('headers', None):
            self._session_kwargs['headers'] = kwargs.get('headers')
        if kwargs.get('auth', None):
            self._session_kwargs['auth'] = kwargs.get('auth')
        if kwargs.get('cookies', None):
            self._session_kwargs['cookies'] = kwargs.get('cookies')
        if kwargs.get('timeout', None):
            timeout = aiohttp.ClientTimeout(total=kwargs.get('timeout'))
            self._session_kwargs['timeout'] = timeout
        self.max_attempts = max_attempts
        self.initial_backoff = initial_backoff
        self.max_backoff = max_backoff
        self.backoff_multiplier = backoff_multiplier

    @abstractmethod
    async def send_message(self, **kwargs):
        """Send message to Gateway
        :param kwargs: kwargs which will be forwarded to the `aiohttp.Session.post` method. Used to pass headers to requests
        """
        ...

    @abstractmethod
    async def send_dry_run(self, **kwargs):
        """Query the dry_run endpoint from Gateway
        :param kwargs: kwargs which will be forwarded to the `aiohttp.Session.post` method. Used to pass headers to requests
        """
        ...

    @abstractmethod
    async def recv_message(self):
        """Receive message from Gateway"""
        ...

    async def recv_dry_run(self):
        """Receive dry run response from Gateway"""
        pass

    async def __aenter__(self):
        """enter async context

        :return: start self
        """
        return await self.start()

    async def start(self):
        """Create ClientSession and enter context

        :return: self
        """
        with ImportExtensions(required=True):
            import aiohttp
        self.session = aiohttp.ClientSession(
            **self._session_kwargs, trace_configs=self._trace_config
        )
        await self.session.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close(exc_type, exc_val, exc_tb)

    async def close(self, *args, **kwargs):
        """Close ClientSession

        :param args: positional args
        :param kwargs: keyword args"""
        await self.session.__aexit__(*args, **kwargs)


class HTTPClientlet(AioHttpClientlet):
    """HTTP Client to be used with the streamer"""

    UPDATE_EVENT_PREFIX = 14  # the update event has the following format: "event: update: {document_json}"

    async def send_message(self, url, request: 'Request'):
        """Sends a POST request to the server

        :param url: the URL where to send the message
        :param request: request as dict
        :return: send post message
        """
        req_dict = request.to_dict()
        req_dict['exec_endpoint'] = req_dict['header']['exec_endpoint']
        if 'target_executor' in req_dict['header']:
            req_dict['target_executor'] = req_dict['header']['target_executor']
        for attempt in range(1, self.max_attempts + 1):
            try:
                request_kwargs = {'url': url}
                if not docarray_v2:
                    request_kwargs['json'] = req_dict
                else:
                    from docarray.base_doc.io.json import orjson_dumps

                    request_kwargs['data'] = JinaJsonPayload(value=req_dict)

                async with self.session.post(**request_kwargs) as response:
                    try:
                        r_str = await response.json()
                    except aiohttp.ContentTypeError:
                        r_str = await response.text()
                    r_status = response.status
                    handle_response_status(r_status, r_str, url)
                return r_status, r_str
            except (ValueError, ConnectionError, BadClient, aiohttp.ClientError, aiohttp.ClientConnectionError) as err:
                self.logger.debug(f'Got an error of type {type(err)}: {err} sending POST to {url} in attempt {attempt}/{self.max_attempts}')
                await retry.wait_or_raise_err(
                    attempt=attempt,
                    err=err,
                    max_attempts=self.max_attempts,
                    backoff_multiplier=self.backoff_multiplier,
                    initial_backoff=self.initial_backoff,
                    max_backoff=self.max_backoff,
                )
            except Exception as exc:
                self.logger.debug(
                    f'Got a non-retried error of type {type(exc)}: {exc} sending POST to {url}')
                raise exc

    async def send_streaming_message(self, url, doc: 'Document', on: str):
        """Sends a GET SSE request to the server

        :param url: the URL where to send the message
        :param doc: Request Document
        :param on: Request endpoint
        :yields: responses
        """
        req_dict = doc.to_dict() if hasattr(doc, "to_dict") else doc.dict()
        request_kwargs = {
            'url': url,
            'headers': {'Accept': 'text/event-stream'},
            'json': req_dict,
        }

        async with self.session.get(**request_kwargs) as response:
            async for chunk in response.content.iter_any():
                events = chunk.split(b'event: ')[1:]
                for event in events:
                    if event.startswith(b'update'):
                        yield event[self.UPDATE_EVENT_PREFIX :].decode()
                    elif event.startswith(b'end'):
                        pass

    async def send_dry_run(self, url, **kwargs):
        """Query the dry_run endpoint from Gateway
        :param url: the URL where to send the message
        :param kwargs: keyword arguments to make sure compatible API with other clients
        :return: send get message
        """
        return await self.session.get(
            url=url, timeout=kwargs.get('timeout', None)
        ).__aenter__()

    async def recv_message(self):
        """Receive message for HTTP (sleep)

        :return: await sleep
        """
        return await asyncio.sleep(1e10)

    async def recv_dry_run(self):
        """Receive dry run response for HTTP (sleep)

        :return: await sleep
        """
        return await asyncio.sleep(1e10)


class WsResponseIter:
    """
    Iterates over all the responses that come in over the websocket connection.
    In contrast to the iterator built into AioHTTP, this also records the message that was sent at closing-time.
    """

    def __init__(self, websocket):
        self.websocket = websocket
        self.close_message = None

    def __aiter__(self):
        return self

    async def __anext__(self):
        msg = await self.websocket.receive()
        if msg.type in (WSMsgType.CLOSE, WSMsgType.CLOSING, WSMsgType.CLOSED):
            self.close_message = msg
            raise StopAsyncIteration
        return msg


class WebsocketClientlet(AioHttpClientlet):
    """Websocket Client to be used with the streamer"""

    def __init__(self, url, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.url = url
        self.websocket = None
        self.response_iter = None

    async def send_message(self, request: 'Request'):
        """Send request in bytes to the server.

        :param request: request object
        :return: send request as bytes awaitable
        """
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await self.websocket.send_bytes(request.SerializeToString())
            except aiohttp.ClientError as err:
                await retry.wait_or_raise_err(
                    attempt=attempt,
                    err=err,
                    max_attempts=self.max_attempts,
                    backoff_multiplier=self.backoff_multiplier,
                    initial_backoff=self.initial_backoff,
                    max_backoff=self.max_backoff,
                )

    async def send_dry_run(self, **kwargs):
        """Query the dry_run endpoint from Gateway
        :param kwargs: keyword arguments to make sure compatible API with other clients
        :return: send dry_run as bytes awaitable
        """

        try:
            return await self.websocket.send_bytes(b'')
        except ConnectionResetError:
            self.logger.critical(f'server connection closed already!')

    async def send_eoi(self):
        """To confirm end of iteration, we send `bytes(True)` to the server.

        :return: send `bytes(True)` awaitable
        """
        try:
            return await self.websocket.send_bytes(bytes(True))
        except ConnectionResetError:
            # server might be in a `CLOSING` state while sending EOI signal
            # which raises a `ConnectionResetError`, this can be ignored.
            pass

    async def recv_message(self) -> 'DataRequest':
        """Receive messages in bytes from server and convert to `DataRequest`

        ..note::
            aiohttp allows only one task which can `receive` concurrently.
            we need to make sure we don't create multiple tasks with `recv_message`

        :yield: response objects received from server
        """
        async for response in self.response_iter:
            yield DataRequest(response.data)

    async def recv_dry_run(self):
        """Receive dry run response in bytes from server

        ..note::
            aiohttp allows only one task which can `receive` concurrently.
            we need to make sure we don't create multiple tasks with `recv_message`

        :yield: response objects received from server
        """
        async for response in self.response_iter:
            yield StatusMessage(response.data)

    async def __aenter__(self):
        for attempt in range(1, self.max_attempts + 1):
            try:
                await super().__aenter__()
                self.websocket = await self.session.ws_connect(
                    url=self.url,
                    protocols=(WebsocketSubProtocols.BYTES.value,),
                    **self._session_kwargs,
                ).__aenter__()
                self.response_iter = WsResponseIter(self.websocket)
                return self
            except aiohttp.ClientError as err:
                await retry.wait_or_raise_err(
                    attempt=attempt,
                    err=err,
                    max_attempts=self.max_attempts,
                    backoff_multiplier=self.backoff_multiplier,
                    initial_backoff=self.initial_backoff,
                    max_backoff=self.max_backoff,
                )

    @property
    def close_message(self):
        """:return: the close message (reason) of the ws closing response"""
        return self.response_iter.close_message.extra if self.response_iter else None

    @property
    def close_code(self):
        """:return: the close code of the ws closing response"""
        return self.websocket.close_code if self.websocket else None


def handle_response_status(
    http_status: int, response_content: Union[Dict, str], url: str
):
    """
    Raise BadClient exception for HTTP 404 status.
    Raise ConnectionError for HTTP status codes 504, 504 if header information is available.
    Raise ValueError for everything other non 200 status code.
    :param http_status: http status code
    :param response_content: response content as json dict or string
    :param url: request url string
    """
    if http_status == status.HTTP_404_NOT_FOUND:
        raise BadClient(f'no such endpoint {url}')
    elif (
        http_status == status.HTTP_503_SERVICE_UNAVAILABLE
        or http_status == status.HTTP_504_GATEWAY_TIMEOUT
    ):
        if (
            isinstance(response_content, dict)
            and 'header' in response_content
            and 'status' in response_content['header']
            and 'description' in response_content['header']['status']
        ):
            raise ConnectionError(response_content['header']['status']['description'])
        else:
            raise ValueError(response_content)
    elif (
        http_status < status.HTTP_200_OK
        or http_status > status.HTTP_300_MULTIPLE_CHOICES
    ):  # failure codes
        raise ValueError(response_content)
