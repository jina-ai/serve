import asyncio
import json
import time

import pytest
from docarray import Document, DocumentArray
from pytest import FixtureRequest

from jina import Client, Document, Executor, requests
from jina.enums import PollingType
from jina.helper import random_port
from jina.orchestrate.deployments import Deployment
from jina.parsers import set_deployment_parser, set_gateway_parser


@pytest.mark.asyncio
# test gateway, head and worker pod by creating them manually in the most simple configuration
async def test_deployments_trivial_topology(port_generator):
    deployment_port = port_generator()
    port = port_generator()
    graph_description = (
        '{"start-gateway": ["deployment0"], "deployment0": ["end-gateway"]}'
    )
    deployments_addresses = f'{{"deployment0": ["0.0.0.0:{deployment_port}"]}}'

    deployments_metadata = '{"deployment0": {"key": "value"}}'

    # create a single worker pod
    worker_deployment = _create_regular_deployment(deployment_port)

    # create a single gateway pod
    gateway_deployment = _create_gateway_deployment(
        graph_description, deployments_addresses, deployments_metadata, port
    )

    with worker_deployment, gateway_deployment:
        # send requests to the gateway
        c = Client(host='localhost', port=port, asyncio=True)
        responses = c.post(
            '/', inputs=async_inputs, request_size=1, return_responses=True
        )

        response_list = []
        try:
            async for response in responses:
                response_list.append(response)
        except Exception:
            pass

    assert len(response_list) == 20
    assert len(response_list[0].docs) == 1


@pytest.fixture
def complete_graph_dict():
    return {
        'start-gateway': ['deployment0', 'deployment4', 'deployment6'],
        'deployment0': ['deployment1', 'deployment2'],
        'deployment1': ['end-gateway'],
        'deployment2': ['deployment3'],
        'deployment4': ['deployment5'],
        'merger': ['deployment_last'],
        'deployment5': ['merger'],
        'deployment3': ['merger'],
        'deployment6': [],  # hanging_deployment
        'deployment_last': ['end-gateway'],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize('uses_before', [True, False])
@pytest.mark.parametrize('uses_after', [True, False])
# test gateway, head and worker pod by creating them manually in a more Flow like topology with branching/merging
async def test_deployments_flow_topology(
    complete_graph_dict, uses_before, uses_after, port_generator
):
    deployments = [
        deployment_name
        for deployment_name in complete_graph_dict.keys()
        if 'gateway' not in deployment_name
    ]
    started_deployments = []
    deployments_addresses = '{'
    for deployment in deployments:
        head_port = port_generator()
        deployments_addresses += f'"{deployment}": ["0.0.0.0:{head_port}"],'
        regular_deployment = _create_regular_deployment(
            port=head_port,
            name=f'{deployment}',
            uses_before=uses_before,
            uses_after=uses_after,
            shards=2,
        )

        started_deployments.append(regular_deployment)
        regular_deployment.start()

    # remove last comma
    deployments_addresses = deployments_addresses[:-1]
    deployments_addresses += '}'
    port = port_generator()

    deployments_metadata = '{"deployment0": {"key": "value"}}'

    # create a single gateway pod

    gateway_deployment = _create_gateway_deployment(
        json.dumps(complete_graph_dict),
        deployments_addresses,
        deployments_metadata,
        port,
    )
    gateway_deployment.start()

    await asyncio.sleep(0.1)

    # send requests to the gateway
    c = Client(host='localhost', port=port, asyncio=True)
    responses = c.post('/', inputs=async_inputs, request_size=1, return_responses=True)
    response_list = []
    async for response in responses:
        response_list.append(response)

    # clean up deployments
    gateway_deployment.close()
    for deployment in started_deployments:
        deployment.close()

    assert len(response_list) == 20
    expected_docs = 1
    if uses_before and uses_after:
        expected_docs = 3 + 1 + 1
    elif uses_before or uses_after:
        expected_docs = 3
    assert len(response_list[0].docs) == expected_docs


@pytest.mark.asyncio
@pytest.mark.parametrize('polling', [PollingType.ALL, PollingType.ANY])
# test simple topology with shards
async def test_deployments_shards(polling, port_generator):
    head_port = port_generator()
    port = port_generator()
    graph_description = (
        '{"start-gateway": ["deployment0"], "deployment0": ["end-gateway"]}'
    )
    deployments_addresses = f'{{"deployment0": ["0.0.0.0:{head_port}"]}}'
    deployments_metadata = '{"deployment0": {"key": "value"}}'

    deployment = _create_regular_deployment(
        port=head_port, name='deployment', polling=polling, shards=10
    )
    deployment.start()

    gateway_deployment = _create_gateway_deployment(
        graph_description, deployments_addresses, deployments_metadata, port
    )
    gateway_deployment.start()

    await asyncio.sleep(1.0)

    c = Client(host='localhost', port=port, asyncio=True)
    responses = c.post('/', inputs=async_inputs, request_size=1, return_responses=True)
    response_list = []
    async for response in responses:
        response_list.append(response)

    gateway_deployment.close()
    deployment.close()

    assert len(response_list) == 20
    assert len(response_list[0].docs) == 1 if polling == PollingType.ANY else 10


@pytest.mark.asyncio
# test simple topology with replicas
async def test_deployments_replicas(port_generator):
    head_port = port_generator()
    port = port_generator()
    graph_description = (
        '{"start-gateway": ["deployment0"], "deployment0": ["end-gateway"]}'
    )

    deployment = _create_regular_deployment(
        port=head_port, name='deployment', replicas=10
    )
    deployment.start()

    connections = [f'0.0.0.0:{port}' for port in deployment.ports]
    deployments_addresses = f'{{"deployment0": {json.dumps(connections)}}}'
    deployments_metadata = '{"deployment0": {"key": "value"}}'
    gateway_deployment = _create_gateway_deployment(
        graph_description, deployments_addresses, deployments_metadata, port
    )
    gateway_deployment.start()

    await asyncio.sleep(1.0)

    c = Client(host='localhost', port=port, asyncio=True)
    responses = c.post('/', inputs=async_inputs, request_size=1, return_responses=True)
    response_list = []
    async for response in responses:
        response_list.append(response)

    gateway_deployment.close()
    deployment.close()

    assert len(response_list) == 20
    assert len(response_list[0].docs) == 1


@pytest.mark.asyncio
async def test_deployments_with_executor(port_generator):
    graph_description = (
        '{"start-gateway": ["deployment0"], "deployment0": ["end-gateway"]}'
    )

    head_port = port_generator()
    deployments_addresses = f'{{"deployment0": ["0.0.0.0:{head_port}"]}}'
    deployments_metadata = '{"deployment0": {"key": "value"}}'

    regular_deployment = _create_regular_deployment(
        port=head_port,
        name='deployment',
        executor='NameChangeExecutor',
        uses_before=True,
        uses_after=True,
        polling=PollingType.ANY,
        shards=2,
    )
    regular_deployment.start()

    port = port_generator()
    gateway_deployment = _create_gateway_deployment(
        graph_description, deployments_addresses, deployments_metadata, port
    )
    gateway_deployment.start()

    await asyncio.sleep(1.0)

    c = Client(host='localhost', port=port, asyncio=True)
    responses = c.post('/', inputs=async_inputs, request_size=1, return_responses=True)
    response_list = []
    async for response in responses:
        response_list.append(response.docs)

    gateway_deployment.close()
    regular_deployment.close()

    assert len(response_list) == 20
    assert len(response_list[0]) == 4

    doc_texts = [doc.text for doc in response_list[0]]
    assert doc_texts.count('client0-Request') == 1
    assert doc_texts.count('deployment/uses_before-0') == 1
    assert doc_texts.count('deployment/uses_after-0') == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('stream', [True, False])
async def test_deployments_with_replicas_advance_faster(port_generator, stream):
    head_port = port_generator()
    port = port_generator()
    graph_description = (
        '{"start-gateway": ["deployment0"], "deployment0": ["end-gateway"]}'
    )

    deployment = _create_regular_deployment(
        port=head_port, name='deployment', executor='FastSlowExecutor', replicas=10
    )
    deployment.start()

    connections = [f'0.0.0.0:{port}' for port in deployment.ports]
    deployments_addresses = f'{{"deployment0": {json.dumps(connections)}}}'
    deployments_metadata = '{"deployment0": {"key": "value"}}'

    gateway_deployment = _create_gateway_deployment(
        graph_description, deployments_addresses, deployments_metadata, port
    )
    gateway_deployment.start()

    await asyncio.sleep(1.0)

    c = Client(host='localhost', port=port, asyncio=True)
    input_docs = [Document(text='slow'), Document(text='fast')]
    responses = c.post(
        '/', inputs=input_docs, request_size=1, return_responses=True, stream=stream
    )
    response_list = []
    async for response in responses:
        response_list.append(response)

    gateway_deployment.close()
    deployment.close()

    assert len(response_list) == 2
    for response in response_list:
        assert len(response.docs) == 1

    assert response_list[0].docs[0].text == 'fast'
    assert response_list[1].docs[0].text == 'slow'


class NameChangeExecutor(Executor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = self.runtime_args.name

    @requests
    def foo(self, docs, **kwargs):
        docs.append(Document(text=self.name))
        return docs


class FastSlowExecutor(Executor):
    @requests
    def foo(self, docs, **kwargs):
        for doc in docs:
            if doc.text == 'slow':
                time.sleep(1.0)


def _create_regular_deployment(
    port,
    name='',
    executor=None,
    uses_before=False,
    uses_after=False,
    polling=PollingType.ANY,
    shards=None,
    replicas=None,
):
    args = set_deployment_parser().parse_args(['--port', str(port)])
    args.name = name
    if shards:
        args.shards = shards
    if replicas:
        args.replicas = replicas
    args.polling = polling
    if executor:
        args.uses = executor if executor else 'NameChangeExecutor'
    if uses_after:
        args.uses_after = executor if executor else 'NameChangeExecutor'
    if uses_before:
        args.uses_before = executor if executor else 'NameChangeExecutor'
    return Deployment(args, include_gateway=False)


def _create_gateway_deployment(
    graph_description, deployments_addresses, deployments_metadata, port
):
    return Deployment(
        set_gateway_parser().parse_args(
            [
                '--graph-description',
                graph_description,
                '--deployments-addresses',
                deployments_addresses,
                '--deployments-metadata',
                deployments_metadata,
                '--port',
                str(port),
            ]
        ),
        include_gateway=False,
    )


async def async_inputs():
    for _ in range(20):
        yield Document(text='client0-Request')


class DummyExecutor(Executor):
    @requests(on='/foo')
    def foo(self, docs, **kwargs): ...



@pytest.mark.parametrize(
    'uses', [DummyExecutor, 'executor.yml']
)
def test_deployment_uses(uses):
    depl = Deployment(uses=uses)

    with depl:
        pass


@pytest.mark.parametrize(
    'config_file,expected_replicas,expected_shards,expected_text',
    [
        ('deployment-nested-executor-config.yml', 3, 2, 'hello'),
        ('deployment-embedded-executor-config.yml', 2, 3, 'world'),
        ('deployment-overridden-executor-config.yml', 3, 3, 'helloworld'),
    ],
)
def test_deployment_load_config(
    config_file, expected_replicas, expected_shards, expected_text
):
    depl = Deployment.load_config(config_file)

    with depl:
        assert depl.args.replicas == expected_replicas
        assert depl.args.shards == expected_shards
        docs = depl.post(on='/', inputs=DocumentArray.empty(5))
        assert len(docs) == 5
        assert all(doc.text == expected_text for doc in docs)


class MyServeExec(Executor):
    @requests
    def foo(self, docs, **kwargs):
        docs.texts = ['foo' for _ in docs]

    @requests(on='/bar')
    def bar(self, docs, **kwargs):
        docs.texts = ['bar' for _ in docs]


@pytest.fixture()
def exposed_port():
    port = random_port()
    yield port


@pytest.fixture(autouse=False)
def served_depl(request: FixtureRequest, exposed_port):
    import threading
    import time

    def serve_depl(stop_event, **kwargs):
        depl = Deployment(uses=MyServeExec, **kwargs)
        with depl:
            depl.block(stop_event)

    stop_event = threading.Event()

    kwargs = {'port': exposed_port}
    enable_dynamic_batching = request.param
    if enable_dynamic_batching:
        kwargs['uses_dynamic_batching'] = {
            '/bar': {'preferred_batch_size': 4, 'timeout': 5000}
        }

    t = threading.Thread(
        name='serve-depl',
        target=serve_depl,
        args=(stop_event,),
        kwargs=kwargs,
    )
    t.start()
    time.sleep(3)  # allow Deployment to start

    yield

    stop_event.set()  # set event and stop (unblock) the Deployment
    t.join()


@pytest.mark.repeat(10)
@pytest.mark.parametrize('served_depl', [False, True], indirect=True)
def test_deployment_dynamic_batching(served_depl, exposed_port):
    docs = Client(port=exposed_port).post(on='/bar', inputs=DocumentArray.empty(5))
    assert docs.texts == ['bar' for _ in docs]


@pytest.mark.repeat(10)
@pytest.mark.parametrize('enable_dynamic_batching', [False, True])
def test_deployment_client_dynamic_batching(enable_dynamic_batching):
    kwargs = {'port': random_port()}
    if enable_dynamic_batching:
        kwargs['uses_dynamic_batching'] = {
            '/bar': {'preferred_batch_size': 4, 'timeout': 5000}
        }

    depl = Deployment(uses=MyServeExec, **kwargs)
    with depl:
        docs = depl.post(on='/bar', inputs=DocumentArray.empty(5))

    assert docs.texts == ['bar' for _ in docs]


@pytest.mark.parametrize('shards', [1, 2])
@pytest.mark.parametrize('replicas', [1, 2, 3])
def test_deployment_shards_replicas(shards, replicas):

    class PIDExecutor(Executor):

        @requests
        def foo(self, docs, **kwargs):
            import os

            for doc in docs:
                doc.tags['pid'] = os.getpid()

    dep = Deployment(uses=PIDExecutor, shards=shards, replicas=replicas)

    with dep:
        docs = dep.post(on='/', inputs=DocumentArray.empty(20), request_size=1)

    returned_pids = set([doc.tags['pid'] for doc in docs])
    assert len(returned_pids) == shards * replicas
