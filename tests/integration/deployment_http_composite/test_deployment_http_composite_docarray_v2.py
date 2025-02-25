import os
import time
from typing import Dict

import pytest

from jina import Client, Deployment, Executor, requests
from jina._docarray import docarray_v2
from jina.helper import random_port

if docarray_v2:
    from docarray import BaseDoc, DocList
    from docarray.documents.legacy import LegacyDocument

    class InputTestDoc(BaseDoc):
        text: str = ""
        price: int = 2
        tags: Dict[str, str] = {}

    class OutputTestDoc(BaseDoc):
        text: str = ""
        flag: bool = False
        tags: Dict[str, str] = {}

    class SingleExecutorDeployment(Executor):
        def __init__(self, init_sleep_time=0, *args, **kwargs):
            super().__init__(*args, **kwargs)
            time.sleep(init_sleep_time)

        @requests(on='/foo')
        async def foo(
            self, docs: DocList[InputTestDoc], **kwargs
        ) -> DocList[OutputTestDoc]:
            for doc in docs:
                doc.text += f'return foo {os.getpid()}'
                doc.tags['pid'] = os.getpid()

        @requests(on='/bar')
        async def bar(
            self, docs: DocList[InputTestDoc], **kwargs
        ) -> DocList[OutputTestDoc]:
            for doc in docs:
                doc.text += f'return bar {os.getpid()}'
                doc.tags['pid'] = os.getpid()

        @requests(on='/error')
        async def raise_error(
            self, docs: DocList[InputTestDoc], **kwargs
        ) -> DocList[OutputTestDoc]:
            raise Exception('Raised exception in request')

        @requests(on='/parameters')
        async def return_parameters(self, docs: DocList[InputTestDoc], **kwargs):
            return {'pid': os.getpid()}

        @requests(on='/docsparams')
        async def docs_with_params(
            self, docs: DocList[InputTestDoc], parameters, **kwargs
        ) -> DocList[OutputTestDoc]:
            for doc in docs:
                doc.text = parameters['key']


@pytest.mark.parametrize('replicas', [1, 3])
@pytest.mark.parametrize('include_gateway', [True, False])
@pytest.mark.parametrize('cors', [True, False])
@pytest.mark.parametrize('protocols', [['grpc'], ['http']])
@pytest.mark.parametrize('init_sleep_time', [0, 5])
@pytest.mark.skipif(not docarray_v2, reason='tests support for docarray>=0.30')
def test_slow_load_executor_docarray_v2(
    replicas, include_gateway, protocols, init_sleep_time, cors
):
    if replicas > 1 and not include_gateway:
        return
    ports = [random_port() for _ in range(len(protocols))]
    d = Deployment(
        uses=SingleExecutorDeployment,
        uses_with={'init_sleep_time': init_sleep_time},
        replicas=replicas,
        protocol=protocols,
        port=ports,
        include_gateway=include_gateway,
        cors=cors,
    )
    with d:
        for protocol, port in zip(protocols, ports):
            c = Client(protocol=protocol, port=port)
            res = c.post(
                on='/foo',
                inputs=DocList[InputTestDoc]([InputTestDoc() for _ in range(100)]),
                request_size=1,
                return_type=DocList[OutputTestDoc],
            )
            assert len(res) == 100
            assert all(['foo' in doc.text for doc in res])
            different_pids = set([doc.tags['pid'] for doc in res])
            assert len(different_pids) == replicas
            res = c.post(
                on='/bar',
                inputs=DocList[InputTestDoc]([InputTestDoc() for _ in range(100)]),
                request_size=1,
                return_type=DocList[OutputTestDoc],
            )
            assert len(res) == 100
            assert all(['bar' in doc.text for doc in res])
            assert all([not doc.flag for doc in res])
            different_pids = set([doc.tags['pid'] for doc in res])
            assert len(different_pids) == replicas


@pytest.mark.parametrize('replicas', [1, 3])
@pytest.mark.parametrize('include_gateway', [True, False])
@pytest.mark.parametrize('protocol', ['grpc', 'http'])
@pytest.mark.parametrize('init_sleep_time', [0, 5])
@pytest.mark.skipif(not docarray_v2, reason='tests support for docarray>=0.30')
def test_post_from_deployment_docarray_v2(replicas, include_gateway, protocol, init_sleep_time):
    if replicas > 1 and not include_gateway:
        return
    d = Deployment(
        uses=SingleExecutorDeployment,
        uses_with={'init_sleep_time': init_sleep_time},
        replicas=replicas,
        protocol=protocol,
        include_gateway=include_gateway,
    )
    with d:
        res = d.post(
            on='/foo',
            inputs=DocList[InputTestDoc]([InputTestDoc() for _ in range(100)]),
            request_size=1,
            return_type=DocList[OutputTestDoc],
        )
        assert all(['foo' in doc.text for doc in res])
        different_pids = set([doc.tags['pid'] for doc in res])
        assert len(different_pids) == replicas
        res = d.post(
            on='/bar',
            inputs=DocList[InputTestDoc]([InputTestDoc() for _ in range(100)]),
            request_size=1,
            return_type=DocList[OutputTestDoc],
        )
        assert len(res) == 100
        assert all(['bar' in doc.text for doc in res])
        different_pids = set([doc.tags['pid'] for doc in res])
        assert len(different_pids) == replicas


@pytest.mark.parametrize('replicas', [1, 3])
@pytest.mark.parametrize('include_gateway', [True, False])
@pytest.mark.parametrize('protocols', [['http'], ['grpc', 'http']])
@pytest.mark.skipif(not docarray_v2, reason='tests support for docarray>=0.30')
def test_base_executor_docarray_v2(replicas, include_gateway, protocols):
    if replicas > 1 and not include_gateway:
        return
    ports = [random_port() for _ in range(len(protocols))]
    d = Deployment(
        replicas=replicas,
        protocol=protocols,
        port=ports,
        include_gateway=include_gateway,
    )
    with d:
        for protocol, port in zip(protocols, ports):
            c = Client(protocol=protocol, port=port)
            res = c.post(
                on='/default',
                inputs=DocList[LegacyDocument]([LegacyDocument() for _ in range(10)]),
                request_size=1,
                return_type=DocList[LegacyDocument],
            )
            assert len(res) == 10


@pytest.mark.parametrize('replicas', [1])
@pytest.mark.parametrize('include_gateway', [False])
@pytest.mark.parametrize('protocols', [['grpc', 'http']])
@pytest.mark.parametrize('init_sleep_time', [0, 5])
@pytest.mark.skipif(not docarray_v2, reason='tests support for docarray>=0.30')
def test_return_parameters_docarray_v2(replicas, include_gateway, protocols, init_sleep_time):
    if replicas > 1 and not include_gateway:
        return
    ports = [random_port() for _ in range(len(protocols))]
    d = Deployment(
        uses=SingleExecutorDeployment,
        uses_with={'init_sleep_time': init_sleep_time},
        replicas=replicas,
        protocol=protocols,
        port=ports,
        include_gateway=include_gateway,
    )
    with d:
        for protocol, port in zip(protocols, ports):
            c = Client(protocol=protocol, port=port)
            res = c.post(
                on='/parameters',
                inputs=DocList[InputTestDoc]([InputTestDoc() for _ in range(100)]),
                request_size=1,
                return_type=DocList[OutputTestDoc],
                return_responses=True,
            )
            assert len(res) == 100
            assert all(
                ['__results__' in response.parameters.keys() for response in res]
            )
            different_pids = set(
                [
                    list(response.parameters['__results__'].values())[0]['pid']
                    for response in res
                ]
            )
            assert len(different_pids) == replicas
            res = c.post(
                on='/docsparams',
                inputs=DocList[InputTestDoc]([InputTestDoc() for _ in range(100)]),
                parameters={'key': 'value'},
                request_size=1,
                return_type=DocList[OutputTestDoc],
            )
            assert len(res) == 100
            assert all([doc.text == 'value' for doc in res])


@pytest.mark.parametrize('replicas', [1, 3])
@pytest.mark.parametrize('include_gateway', [True, False])
@pytest.mark.parametrize('protocols', [['http'], ['grpc', 'http']])
@pytest.mark.skipif(not docarray_v2, reason='tests support for docarray>=0.30')
def test_invalid_protocols_with_shards_docarray_v2(replicas, include_gateway, protocols):
    if replicas > 1 and not include_gateway:
        return
    with pytest.raises(RuntimeError):
        d = Deployment(
            replicas=replicas,
            protocol=protocols,
            include_gateway=include_gateway,
            shards=2,
        )
        with d:
            pass


@pytest.mark.parametrize('replicas', [1, 3])
@pytest.mark.parametrize('include_gateway', [True, False])
@pytest.mark.parametrize('protocols', [['websocket'], ['grpc', 'websocket']])
@pytest.mark.skipif(not docarray_v2, reason='tests support for docarray>=0.30')
def test_invalid_websocket_protocol_docarray_v2(replicas, include_gateway, protocols):
    if replicas > 1 and not include_gateway:
        return
    with pytest.raises(RuntimeError):
        d = Deployment(
            replicas=replicas, protocol=protocols, include_gateway=include_gateway
        )
        with d:
            pass
