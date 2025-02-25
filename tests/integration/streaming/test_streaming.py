import asyncio
import time

import pytest

from jina import Client, Deployment, Executor, requests
from jina._docarray import Document, DocumentArray
from jina.excepts import BadServer
from jina.helper import random_port


class MyExecutor(Executor):
    @requests(on='/hello')
    async def task(self, doc: Document, **kwargs):
        for i in range(100):
            yield Document(text=f'{doc.text} {i}')

    @requests(on='/world')
    async def non_gen_task(self, docs: DocumentArray, **kwargs):
        return docs


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['http', 'grpc'])
@pytest.mark.parametrize('include_gateway', [False, True])
@pytest.mark.parametrize('reuse_session', [False, True])
async def test_streaming_deployment(protocol, include_gateway, reuse_session):
    if reuse_session and protocol != 'http':
        return

    port = random_port()
    docs = []

    with Deployment(
        uses=MyExecutor,
        timeout_ready=-1,
        protocol=protocol,
        port=port,
        include_gateway=include_gateway,
    ):
        client = Client(port=port, protocol=protocol, asyncio=True, reuse_session=reuse_session)
        i = 0
        async for doc in client.stream_doc(
            on='/hello',
            inputs=Document(text='hello world'),
            return_type=Document,
            input_type=Document,
        ):
            docs.append(doc.text)
            i += 1
        assert docs == [f'hello world {i}' for i in range(100)]
        assert len(docs) == 100


class WaitStreamExecutor(Executor):
    @requests(on='/hello')
    async def task(self, doc: Document, **kwargs):
        for i in range(5):
            yield Document(text=f'{doc.text} {i}')
            await asyncio.sleep(0.5)


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['http', 'grpc'])
@pytest.mark.parametrize('include_gateway', [False, True])
@pytest.mark.parametrize('reuse_session', [False, True])
async def test_streaming_delay(protocol, include_gateway, reuse_session):
    if reuse_session and protocol != 'http':
        return
    from jina import Deployment

    port = random_port()

    with Deployment(
        uses=WaitStreamExecutor,
        timeout_ready=-1,
        protocol=protocol,
        port=port,
        include_gateway=include_gateway,
    ):
        client = Client(port=port, protocol=protocol, asyncio=True, reuse_session=reuse_session)
        i = 0
        start_time = time.time()
        async for doc in client.stream_doc(
            on='/hello', inputs=Document(text='hello world')
        ):
            assert doc.text == f'hello world {i}'
            i += 1

            # 0.5 seconds between each request + 0.5 seconds tolerance interval
            assert time.time() - start_time < (0.5 * i) + 0.5


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['grpc'])
async def test_streaming_client_non_gen_endpoint(protocol):
    from jina import Deployment

    port = random_port()

    with Deployment(
        uses=MyExecutor,
        timeout_ready=-1,
        protocol=protocol,
        port=port,
        include_gateway=False,
    ):
        client = Client(port=port, protocol=protocol, asyncio=True)
        i = 0
        with pytest.raises(BadServer):
            async for _ in client.stream_doc(
                on='/world', inputs=Document(text='hello world')
            ):
                pass


def test_invalid_executor():
    with pytest.raises(RuntimeError) as exc_info:

        class InvalidExecutor3(Executor):
            @requests(on='/invalid')
            async def invalid(self, docs: DocumentArray, **kwargs):
                yield docs[0]

    assert type(exc_info.value.__cause__) is AssertionError

    with pytest.raises(RuntimeError) as exc_info:

        class InvalidExecutor4(Executor):
            @requests(on='/invalid')
            def invalid(self, docs: DocumentArray, **kwargs):
                yield docs[0]

    assert type(exc_info.value.__cause__) is AssertionError
