# kind version has to be bumped to v0.11.1 since pytest-kind is just using v0.10.0 which does not work on ubuntu in ci
import os

import pytest
import requests as req

from jina import Client, Document, Flow
from jina.helper import random_port
from jina.serve.runtimes.servers import BaseServer
from tests.docker_compose.conftest import DockerComposeServices
from tests.helper import (
    _validate_custom_gateway_process,
    _validate_dummy_custom_gateway_response,
)


async def run_test(flow, endpoint, num_docs=10, request_size=10):
    # start port forwarding
    from jina.clients import Client

    client_kwargs = dict(
        host='localhost',
        port=flow.port,
        asyncio=True,
    )
    client_kwargs.update(flow._common_kwargs)

    client = Client(**client_kwargs)
    client.show_progress = True
    responses = []
    async for resp in client.post(
        endpoint,
        inputs=[Document() for _ in range(num_docs)],
        request_size=request_size,
        return_responses=True,
    ):
        responses.append(resp)

    return responses


@pytest.fixture()
def flow_with_sharding(docker_images, polling):
    flow = Flow(name='test-flow-with-sharding', port=9090, protocol='grpc').add(
        name='test_executor_sharding',
        shards=2,
        replicas=2,
        uses=f'docker://{docker_images[0]}',
        uses_after=f'docker://{docker_images[1]}',
        polling=polling,
    )
    return flow


@pytest.fixture
def flow_configmap(docker_images):
    flow = Flow(name='k8s-flow-configmap', port=9091, protocol='http').add(
        name='test_executor_configmap',
        uses=f'docker://{docker_images[0]}',
        env={'k1': 'v1', 'k2': 'v2'},
    )
    return flow


@pytest.fixture
def flow_with_needs(docker_images):
    flow = (
        Flow(
            name='test-flow-with-needs',
            port=9092,
            protocol='http',
        )
        .add(
            name='segmenter',
            uses=f'docker://{docker_images[0]}',
            replicas=2,
        )
        .add(
            name='textencoder',
            uses=f'docker://{docker_images[0]}',
            needs='segmenter',
        )
        .add(
            name='imageencoder',
            uses=f'docker://{docker_images[0]}',
            needs='segmenter',
        )
        .add(
            name='merger',
            uses=f'docker://{docker_images[1]}',
            needs=['imageencoder', 'textencoder'],
            disable_reduce=True,
        )
    )
    return flow


@pytest.mark.asyncio
@pytest.mark.timeout(3600)
@pytest.mark.parametrize(
    'docker_images',
    [['test-executor', 'executor-merger', 'jinaai/jina']],
    indirect=True,
)
async def test_flow_with_needs(logger, flow_with_needs, tmpdir, docker_images):
    dump_path = os.path.join(str(tmpdir), 'docker-compose-flow-with-need.yml')
    flow_with_needs.to_docker_compose_yaml(dump_path, 'default')
    with DockerComposeServices(dump_path):
        resp = await run_test(
            flow=flow_with_needs,
            endpoint='/debug',
        )
        expected_traversed_executors_0 = {
            'segmenter/rep-0',
            'imageencoder',
            'textencoder',
        }
        expected_traversed_executors_1 = {
            'segmenter/rep-1',
            'imageencoder',
            'textencoder',
        }

        docs = resp[0].docs
        assert len(docs) == 10
        for doc in docs:
            path_1 = (
                set(doc.tags['traversed-executors']) == expected_traversed_executors_0
            )
            path_2 = (
                set(doc.tags['traversed-executors']) == expected_traversed_executors_1
            )
            assert path_1 or path_2


@pytest.mark.asyncio
@pytest.mark.timeout(3600)
@pytest.mark.parametrize(
    'docker_images',
    [['test-executor', 'executor-merger', 'jinaai/jina']],
    indirect=True,
)
async def test_flow_monitoring(logger, tmpdir, docker_images, port_generator):
    dump_path = os.path.join(str(tmpdir), 'docker-compose-flow-monitoring.yml')
    port1 = port_generator()
    port2 = port_generator()

    flow = Flow(
        name='test-flow-monitoring', monitoring=True, port_monitoring=port1
    ).add(
        name='segmenter',
        uses=f'docker://{docker_images[0]}',
        monitoring=True,
        port_monitoring=port2,
    )
    flow.to_docker_compose_yaml(dump_path, 'default')
    with DockerComposeServices(dump_path):
        for port in [port1, port2]:
            resp = req.get(f'http://localhost:{port}/')
            assert resp.status_code == 200


@pytest.mark.timeout(3600)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    'docker_images',
    [['test-executor', 'executor-merger', 'jinaai/jina']],
    indirect=True,
)
@pytest.mark.parametrize('polling', ['ANY', 'ALL'])
async def test_flow_with_sharding(flow_with_sharding, polling, tmpdir):
    dump_path = os.path.join(str(tmpdir), 'docker-compose-flow-sharding.yml')
    flow_with_sharding.to_docker_compose_yaml(dump_path)

    with DockerComposeServices(dump_path):
        resp = await run_test(
            flow=flow_with_sharding, endpoint='/debug', num_docs=10, request_size=1
        )

    assert len(resp) == 10
    docs = resp[0].docs
    for r in resp[1:]:
        docs.extend(r.docs)
    assert len(docs) == 10

    runtimes_to_visit = {
        'test_executor_sharding-0/rep-0',
        'test_executor_sharding-1/rep-0',
        'test_executor_sharding-0/rep-1',
        'test_executor_sharding-1/rep-1',
    }

    for doc in docs:
        if polling == 'ALL':
            assert len(set(doc.tags['traversed-executors'])) == 2
            assert set(doc.tags['shard_id']) == {0, 1}
            assert doc.tags['parallel'] == [2, 2]
            assert doc.tags['shards'] == [2, 2]
            for executor in doc.tags['traversed-executors']:
                if executor in runtimes_to_visit:
                    runtimes_to_visit.remove(executor)
        else:
            assert len(set(doc.tags['traversed-executors'])) == 1
            assert len(set(doc.tags['shard_id'])) == 1
            assert 0 in set(doc.tags['shard_id']) or 1 in set(doc.tags['shard_id'])
            assert doc.tags['parallel'] == [2]
            assert doc.tags['shards'] == [2]
            for executor in doc.tags['traversed-executors']:
                if executor in runtimes_to_visit:
                    runtimes_to_visit.remove(executor)

    assert len(runtimes_to_visit) == 0


@pytest.mark.timeout(3600)
@pytest.mark.asyncio
@pytest.mark.parametrize(
    'docker_images', [['test-executor', 'jinaai/jina']], indirect=True
)
async def test_flow_with_configmap(flow_configmap, docker_images, tmpdir):
    dump_path = os.path.join(str(tmpdir), 'docker-compose-flow-configmap.yml')
    flow_configmap.to_docker_compose_yaml(dump_path)

    with DockerComposeServices(dump_path):
        resp = await run_test(
            flow=flow_configmap,
            endpoint='/env',
        )

    docs = resp[0].docs
    assert len(docs) == 10
    for doc in docs:
        assert doc.tags['k1'] == 'v1'
        assert doc.tags['k2'] == 'v2'
        assert doc.tags['env'] == {'k1': 'v1', 'k2': 'v2'}


# @pytest.mark.asyncio
# @pytest.mark.timeout(3600)
# @pytest.mark.parametrize(
#     'docker_images',
#     [['test-executor-torch', 'jinaai/jina']],
#     indirect=True,
# )
# async def test_flow_with_workspace_and_tensors(logger, docker_images, tmpdir):
#     flow = Flow(
#         name='docker-compose-flow-with_workspace', port=9090, protocol='http'
#     ).add(
#         name='test_executor',
#         uses=f'docker://{docker_images[0]}',
#         workspace='/shared',
#     )
#
#     dump_path = os.path.join(str(tmpdir), 'docker-compose-flow-workspace.yml')
#     flow.to_docker_compose_yaml(dump_path)
#
#     with DockerComposeServices(dump_path):
#         resp = await run_test(
#             flow=flow,
#             endpoint='/workspace',
#         )
#
#     docs = resp[0].docs
#     assert len(docs) == 10
#     for doc in docs:
#         assert doc.tags['workspace'] == '/shared/TestExecutor/0'
#         assert doc.embedding.shape == (1000,)
#         assert doc.tensor.shape == (1000,)


@pytest.mark.asyncio
@pytest.mark.timeout(3600)
@pytest.mark.parametrize(
    'docker_images',
    [['custom-gateway', 'test-executor']],
    indirect=True,
)
async def test_flow_with_custom_gateway(logger, docker_images, tmpdir):
    flow = (
        Flow(name='docker-compose-flow-custom-gateway')
        .config_gateway(
            port=9090,
            protocol='http',
            uses=f'docker://{docker_images[0]}',
            uses_with={'arg1': 'overridden-hello'},
        )
        .add(
            name='test_executor',
            uses=f'docker://{docker_images[1]}',
        )
    )

    dump_path = os.path.join(str(tmpdir), 'docker-compose-flow-custom-gateway.yml')
    flow.to_docker_compose_yaml(dump_path)

    with DockerComposeServices(dump_path):

        _validate_dummy_custom_gateway_response(
            flow.port,
            {'arg1': 'overridden-hello', 'arg2': 'world', 'arg3': 'default-arg3'},
        )
        _validate_custom_gateway_process(
            flow.port,
            'hello',
            {
                'text': 'hello',
                'tags': {
                    'traversed-executors': ['test_executor'],
                    'shard_id': 0,
                    'shards': 1,
                    'parallel': 1,
                },
            },
        )


@pytest.mark.asyncio
@pytest.mark.timeout(3600)
@pytest.mark.parametrize(
    'docker_images',
    [['multiprotocol-gateway']],
    indirect=True,
)
@pytest.mark.parametrize('stream', [False, True])
def test_flow_with_multiprotocol_gateway(logger, docker_images, tmpdir, stream):
    http_port = random_port()
    grpc_port = random_port()
    flow = Flow().config_gateway(
        uses=f'docker://{docker_images[0]}',
        port=[http_port, grpc_port],
        protocol=['http', 'grpc'],
    )

    dump_path = os.path.join(
        str(tmpdir), 'docker-compose-flow-multiprotocol-gateway.yml'
    )
    flow.to_docker_compose_yaml(dump_path)

    with DockerComposeServices(dump_path):
        import requests

        grpc_client = Client(protocol='grpc', port=grpc_port)
        grpc_client.post('/', inputs=Document(), stream=stream)
        resp = requests.get(f'http://localhost:{http_port}').json()
        assert resp['protocol'] == 'http'
        assert BaseServer.is_ready(f'localhost:{grpc_port}')
