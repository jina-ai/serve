import asyncio
import time
from typing import AsyncGenerator, Generator, Optional, ClassVar

import pytest
from docarray import BaseDoc, DocList

from jina import Client, Deployment, Executor, Flow, requests
from jina.helper import random_port


class MyDocument(BaseDoc):
    # Not exposed to client
    input_type_name: ClassVar[str] = 'MyDocumentType'

    text: str
    number: Optional[int] = None


class OutputDocument(BaseDoc):
    text: str


class MyExecutor(Executor):
    @requests(on='/hello')
    async def task(self, doc: MyDocument, **kwargs) -> MyDocument:
        for i in range(100):
            yield MyDocument(text=f'{doc.text} {doc.number + i}')


class CustomResponseExecutor(Executor):
    @requests(on='/task1')
    async def task1(self, doc: MyDocument, **kwargs) -> OutputDocument:
        for i in range(100):
            yield OutputDocument(text=f'{doc.text} {doc.number}-{i}-task1')

    @requests(on='/task2')
    async def task2(
        self, doc: MyDocument, **kwargs
    ) -> Generator[OutputDocument, None, None]:
        for i in range(100):
            yield OutputDocument(text=f'{doc.text} {doc.number}-{i}-task2')

    @requests(on='/task3')
    async def task3(
        self, doc: MyDocument, **kwargs
    ) -> AsyncGenerator[OutputDocument, None]:
        for i in range(100):
            yield OutputDocument(text=f'{doc.text} {doc.number}-{i}-task3')


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['http', 'grpc'])
@pytest.mark.parametrize('include_gateway', [False, True])
async def test_streaming_deployment(protocol, include_gateway):
    port = random_port()

    with Deployment(
        uses=MyExecutor,
        protocol=protocol,
        cors=True,
        port=port,
        include_gateway=include_gateway,
    ):
        client = Client(port=port, protocol=protocol, cors=True, asyncio=True)
        i = 10
        async for doc in client.stream_doc(
            on='/hello',
            inputs=MyDocument(text='hello world', number=i),
            return_type=MyDocument,
        ):
            assert doc.text == f'hello world {i}'
            i += 1
            assert doc.input_type_name == 'MyDocumentType'


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['http', 'grpc'])
async def test_streaming_flow(protocol):
    port = random_port()

    with Flow(protocol=protocol, port=port, cors=True).add(
        uses=MyExecutor,
    ):
        client = Client(port=port, protocol=protocol, asyncio=True)
        i = 10
        async for doc in client.stream_doc(
            on='/hello',
            inputs=MyDocument(text='hello world', number=i),
            return_type=MyDocument,
        ):
            assert doc.text == f'hello world {i}'
            i += 1


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['http', 'grpc'])
@pytest.mark.parametrize('endpoint', ['task1', 'task2', 'task3'])
@pytest.mark.parametrize('include_gateway', [False, True])
async def test_streaming_custom_response(protocol, endpoint, include_gateway):
    port = random_port()

    with Deployment(
        uses=CustomResponseExecutor,
        protocol=protocol,
        cors=True,
        port=port,
        include_gateway=include_gateway,
    ):
        client = Client(port=port, protocol=protocol, cors=True, asyncio=True)
        i = 0
        async for doc in client.stream_doc(
            on=f'/{endpoint}',
            inputs=MyDocument(text='hello world', number=5),
            return_type=OutputDocument,
        ):
            assert doc.text == f'hello world 5-{i}-{endpoint}'
            i += 1


class WaitStreamExecutor(Executor):
    @requests(on='/hello')
    async def task(self, doc: MyDocument, **kwargs) -> MyDocument:
        for i in range(5):
            yield MyDocument(text=f'{doc.text} {doc.number + i}')
            await asyncio.sleep(0.5)


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['http', 'grpc'])
@pytest.mark.parametrize('include_gateway', [False, True])
async def test_streaming_delay(protocol, include_gateway):
    from jina import Deployment

    port = random_port()

    with Deployment(
        uses=WaitStreamExecutor,
        timeout_ready=-1,
        protocol=protocol,
        port=port,
        include_gateway=include_gateway,
    ):
        client = Client(port=port, protocol=protocol, asyncio=True)
        i = 0
        start_time = time.time()
        async for doc in client.stream_doc(
            on='/hello',
            inputs=MyDocument(text='hello world', number=i),
            return_type=MyDocument,
        ):
            assert doc.text == f'hello world {i}'
            i += 1

            # 0.5 seconds between each request + 0.5 seconds tolerance interval
            assert time.time() - start_time < (0.5 * i) + 0.6


@pytest.mark.asyncio
@pytest.mark.parametrize('protocol', ['http', 'grpc'])
@pytest.mark.parametrize('endpoint', ['task1', 'task2', 'task3'])
async def test_streaming_custom_response_flow_one_executor(protocol, endpoint):
    port = random_port()

    with Flow(
        protocol=protocol,
        cors=True,
        port=port,
    ).add(uses=CustomResponseExecutor):
        client = Client(port=port, protocol=protocol, cors=True, asyncio=True)
        i = 0
        async for doc in client.stream_doc(
            on=f'/{endpoint}',
            inputs=MyDocument(text='hello world', number=5),
            return_type=OutputDocument,
        ):
            assert doc.text == f'hello world 5-{i}-{endpoint}'
            i += 1


class Executor1(Executor):
    @requests
    def generator(self, doc: MyDocument, **kwargs) -> MyDocument:
        yield MyDocument(text='new document')

    @requests(on='/non_generator')
    def non_generator(self, docs: DocList[BaseDoc], **kwargs):
        return docs


class Executor2(Executor):
    @requests
    def non_generator(self, docs: DocList[BaseDoc], **kwargs):
        return docs

    @requests(on='/generator')
    def generator(self, doc: MyDocument, **kwargs):
        yield MyDocument(text='new document')


class Executor3(Executor):
    @requests(on='/non_generator')
    def non_generator(self, docs: DocList[BaseDoc], **kwargs):
        return docs

    @requests(on='/generator')
    def generator(self, doc: MyDocument, **kwargs):
        yield MyDocument(text='new document')


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'executor,expected',
    [
        ('Executor1', {'/default': True, '/non_generator': False}),
        ('Executor2', {'/default': False, '/generator': True}),
        ('Executor3', {'/generator': True, '/non_generator': False}),
    ],
)
async def test_endpoint_discovery(executor, expected):
    from google.protobuf import json_format

    from jina.logging.logger import JinaLogger
    from jina.parsers import set_pod_parser
    from jina.serve.runtimes.worker.request_handling import WorkerRequestHandler

    args = set_pod_parser().parse_args(['--uses', executor])
    handler = WorkerRequestHandler(args, JinaLogger('data request handler'))
    res = await handler.endpoint_discovery(None, None)
    for endpoint, is_generator in expected.items():
        assert (
            json_format.MessageToDict(res.schemas)[endpoint]['is_generator']
            == is_generator
        )
