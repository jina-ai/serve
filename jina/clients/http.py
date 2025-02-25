from jina.clients.base.http import HTTPBaseClient
from jina.clients.mixin import (
    AsyncHealthCheckMixin,
    AsyncMutateMixin,
    AsyncPostMixin,
    AsyncProfileMixin,
    HealthCheckMixin,
    MutateMixin,
    PostMixin,
    ProfileMixin,
)
import asyncio


class HTTPClient(
    HTTPBaseClient, PostMixin, ProfileMixin, MutateMixin, HealthCheckMixin
):
    """A client connecting to a Gateway using gRPC protocol.

    Instantiate this class through the :meth:`jina.Client` convenience method.

    EXAMPLE USAGE

    .. code-block:: python

        from jina import Client
        from docarray import Document

        # select host address to connect to
        c = Client(
            protocol='http', asyncio=False, host='http://my.awesome.flow:1234'
        )  # returns HTTPClient instance
        c.post(on='/index', inputs=Document(text='hello!'))

    """


class AsyncHTTPClient(
    HTTPBaseClient,
    AsyncPostMixin,
    AsyncMutateMixin,
    AsyncProfileMixin,
    AsyncHealthCheckMixin,
):
    """
    Asynchronous client connecting to a Gateway using HTTP protocol.

    Instantiate this class through the :meth:`jina.Client` convenience method.

    Unlike :class:`HTTPClient`, here :meth:`post` is a coroutine (i.e. declared with the async/await syntax),
    simply calling them will not schedule them to be executed.

    To actually run a coroutine, user need to put them in an event loop, e.g. via ``asyncio.run()``,
    ``asyncio.create_task()``.

    :class:`AsyncHTTPClient` can be very useful in
    the integration settings, where Jina/Flow/Client is NOT the main logic, but rather served as a part of other program.
    In this case, users often do not want to let Jina control the ``asyncio.eventloop``. On contrary, :class:`Client`
    is controlling and wrapping the event loop internally, making the Client looks synchronous from outside.

    EXAMPLE USAGE

    .. code-block:: python

        from jina import Client
        from docarray import Document

        # async inputs for the client
        async def async_inputs():
            for _ in range(10):
                yield Document()
                await asyncio.sleep(0.1)


        # select host address to connect to
        c = Client(
            protocol='http', asyncio=True, host='http://my.awesome.flow:1234'
        )  # returns AsyncHTTPClient instance

        async for resp in client.post(on='/index', async_inputs, request_size=1):
            print(resp)

    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lock = asyncio.Lock()
        self.reuse_session = self.args.reuse_session
