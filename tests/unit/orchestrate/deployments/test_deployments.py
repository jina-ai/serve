import json
import os

import pytest
import yaml

from jina import Document, DocumentArray, Executor, requests
from jina.clients.request import request_generator
from jina.constants import __default_executor__, __default_host__
from jina.enums import PollingType
from jina.excepts import RuntimeFailToStart
from jina.orchestrate.deployments import Deployment
from jina.parsers import set_deployment_parser, set_gateway_parser
from jina.serve.networking.utils import send_request_sync
from tests.unit.test_helper import MyDummyExecutor

cur_dir = os.path.dirname(os.path.abspath(__file__))


def get_deployment_args_with_host(hostname, runtime_cls):
    args = [
        '--name',
        'host_args',
        '--host',
        hostname,
        '--runtime-cls',
        runtime_cls,
    ]
    if runtime_cls != 'GatewayRuntime':
        return set_deployment_parser().parse_args(args)
    else:
        return set_gateway_parser().parse_args(args)


@pytest.fixture(scope='function')
def pod_args():
    args = [
        '--name',
        'test',
        '--replicas',
        '2',
        '--host',
        __default_host__,
    ]
    return set_deployment_parser().parse_args(args)


@pytest.fixture
def graph_description():
    return '{"start-gateway": ["pod0"], "pod0": ["end-gateway"]}'


@pytest.fixture(scope='function')
def pod_args_singleton():
    args = [
        '--name',
        'test2',
        '--uses-before',
        __default_executor__,
        '--replicas',
        '1',
        '--host',
        __default_host__,
    ]
    return set_deployment_parser().parse_args(args)


def test_name(pod_args):
    with Deployment(pod_args, include_gateway=False) as pod:
        assert pod.name == 'test'


@pytest.mark.parametrize(
    'runtime_cls', ['GatewayRuntime', 'WorkerRuntime', 'HeadRuntime']
)
@pytest.mark.parametrize('hostname', ['localhost', '127.0.0.1', '0.0.0.0'])
def test_host(hostname, runtime_cls):
    with Deployment(
        get_deployment_args_with_host(hostname, runtime_cls), include_gateway=False
    ) as pod:
        assert pod.host == hostname
        assert pod.head_host is None


@pytest.mark.parametrize(
    'runtime_cls', ['GatewayRuntime', 'WorkerRuntime', 'HeadRuntime']
)
def test_wrong_hostname(runtime_cls):
    with pytest.raises(RuntimeFailToStart):
        with Deployment(
            get_deployment_args_with_host('inexisting.hostname.local', runtime_cls),
            include_gateway=False,
        ) as pod:
            pass


def test_is_ready(pod_args):
    with Deployment(pod_args) as pod:
        assert pod.is_ready is True


def test_equal(pod_args, pod_args_singleton):
    pod1 = Deployment(pod_args, include_gateway=False)
    pod2 = Deployment(pod_args, include_gateway=False)
    assert pod1 == pod2
    pod1.close()
    pod2.close()
    # test not equal
    pod1 = Deployment(pod_args, include_gateway=False)
    pod2 = Deployment(pod_args_singleton, include_gateway=False)
    assert pod1 != pod2
    pod1.close()
    pod2.close()


class ChildDummyExecutor(MyDummyExecutor):
    pass


class ChildDummyExecutor2(MyDummyExecutor):
    pass


@pytest.mark.parametrize('shards', [2, 1])
def test_uses_before_after(pod_args, shards):
    pod_args.replicas = 1
    pod_args.shards = shards
    pod_args.uses_before = 'MyDummyExecutor'
    pod_args.uses_after = 'ChildDummyExecutor2'
    pod_args.uses = 'ChildDummyExecutor'
    with Deployment(pod_args, include_gateway=False) as pod:
        if shards == 2:
            assert (
                pod.head_args.uses_before_address
                == f'{pod.uses_before_args.host}:{pod.uses_before_args.port[0]}'
            )
            assert (
                pod.head_args.uses_after_address
                == f'{pod.uses_after_args.host}:{pod.uses_after_args.port[0]}'
            )
        else:
            assert pod.head_args is None

        assert pod.num_pods == 5 if shards == 2 else 1


@pytest.mark.skip('jinahub not available')
def test_mermaid_str_no_secret(pod_args):
    pod_args.replicas = 3
    pod_args.shards = 3
    pod_args.uses_before = 'jinahub+docker://MyDummyExecutor:Dummy@Secret'
    pod_args.uses_after = 'ChildDummyExecutor2'
    pod_args.uses = 'jinahub://ChildDummyExecutor:Dummy@Secret'
    pod = Deployment(pod_args, include_gateway=False)
    assert 'Dummy@Secret' not in ''.join(pod._mermaid_str)


@pytest.mark.slow
@pytest.mark.parametrize('replicas', [1, 2, 4])
def test_pod_context_replicas(replicas):
    args_list = ['--replicas', str(replicas)]
    args = set_deployment_parser().parse_args(args_list)
    with Deployment(args, include_gateway=False) as bp:
        assert bp.num_pods == replicas

    Deployment(args, include_gateway=False).start().close()


@pytest.mark.slow
@pytest.mark.parametrize('shards', [1, 2, 4])
def test_pod_context_shards_replicas(shards):
    args_list = ['--replicas', str(3)]
    args_list.extend(['--shards', str(shards)])
    args = set_deployment_parser().parse_args(args_list)
    with Deployment(args, include_gateway=False) as bp:
        assert bp.num_pods == shards * 3 + 1 if shards > 1 else 3

    Deployment(args, include_gateway=False).start().close()


@pytest.mark.parametrize('metadata', [{'key1': 'value1', 'key2': 'value2'}])
def test_pod_context_grpc_metadata(metadata):
    args_list = []
    for k, v in metadata.items():
        args_list.extend(['--grpc-metadata', f'{k}:{v}'])
    args = set_deployment_parser().parse_args(args_list)
    with Deployment(args, include_gateway=False) as bp:
        assert bp.grpc_metadata == metadata


class SetNameExecutor(Executor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = self.runtime_args.name

    @requests
    def foo(self, docs: DocumentArray, **kwargs):
        for doc in docs:
            doc.text = str(self.name)


@pytest.mark.slow
def test_pod_in_flow_activates_shards_replicas():
    shards = 2
    replicas = 3
    args_list = ['--replicas', str(replicas), '--shards', str(shards), '--no-reduce']
    args = set_deployment_parser().parse_args(args_list)
    args.uses = 'SetNameExecutor'
    with Deployment(args, include_gateway=False) as pod:
        assert pod.num_pods == 7
        response_texts = set()
        # replicas and shards are used in a round robin fashion, so sending 6 requests should hit each one time
        for _ in range(6):
            response = send_request_sync(
                _create_test_data_message(),
                f'{pod.head_args.host}:{pod.head_args.port[0]}',
            )
            response_texts.update(response.response.docs.texts)
        print(response_texts)
        assert 6 == len(response_texts)
        assert all(
            text in response_texts
            for text in [
                f'executor/shard-{s}/rep-{r}'
                for s in range(shards)
                for r in range(replicas)
            ]
        )

    Deployment(args, include_gateway=False).start().close()


@pytest.mark.slow
@pytest.mark.parametrize('shards', [1, 2])
@pytest.mark.parametrize('replicas', [1, 2, 3])
def test_standalone_deployment_activates_shards_replicas(shards, replicas):
    with Deployment(
        shards=shards,
        replicas=replicas,
        uses=SetNameExecutor,
    ) as dep:
        head_exists = 0 if shards == 1 else 1
        assert dep.num_pods == shards * replicas + 1 + head_exists
        response_texts = set()
        # replicas and shards are used in a round robin fashion, so sending shards * replicas requests should hit each one time

        docs = dep.post(on='/', inputs=DocumentArray.empty(20), request_size=1)

        response_texts.update(docs.texts)
        print(response_texts)
        assert shards * replicas == len(response_texts)
        assert all(
            text in response_texts
            for text in [
                f'executor/shard-{s}/rep-{r}' if shards > 1 else f'executor/rep-{r}'
                for s in range(shards)
                for r in range(replicas)
            ]
        )


class AppendParamExecutor(Executor):
    def __init__(self, param, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.param = param

    @requests
    def foo(self, docs: DocumentArray, **kwargs):
        docs.append(Document(text=str(self.param)))
        return docs


async def _send_requests(pod):
    response_texts = set()
    for _ in range(3):
        response = send_request_sync(
            _create_test_data_message(),
            f'{pod.head_args.host}:{pod.head_args.port[0]}',
        )
        response_texts.update(response.response.docs.texts)
    return response_texts


class AppendShardExecutor(Executor):
    def __init__(self, runtime_args, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.shard_id = runtime_args['shard_id']

    @requests
    def foo(self, docs: DocumentArray, **kwargs):
        docs.append(Document(text=str(self.shard_id)))
        return docs


def test_pod_naming_with_shards():
    args = set_deployment_parser().parse_args(
        [
            '--name',
            'pod',
            '--shards',
            '2',
            '--replicas',
            '3',
        ]
    )
    with Deployment(args, include_gateway=False) as pod:
        assert pod.head_pod.name == 'pod/head'

        assert pod.shards[0].args[0].name == 'pod/shard-0/rep-0'
        assert pod.shards[0].args[1].name == 'pod/shard-0/rep-1'
        assert pod.shards[0].args[2].name == 'pod/shard-0/rep-2'

        assert pod.shards[1].args[0].name == 'pod/shard-1/rep-0'
        assert pod.shards[1].args[1].name == 'pod/shard-1/rep-1'
        assert pod.shards[1].args[2].name == 'pod/shard-1/rep-2'


@pytest.mark.slow
def test_pod_activates_shards():
    args_list = ['--replicas', '3']
    args_list.extend(['--shards', '3'])
    args = set_deployment_parser().parse_args(args_list)
    args.uses = 'AppendShardExecutor'
    args.polling = PollingType.ALL
    with Deployment(args, include_gateway=False) as pod:
        assert pod.num_pods == 3 * 3 + 1
        response_texts = set()
        # replicas are used in a round robin fashion, so sending 3 requests should hit each one time
        response = send_request_sync(
            _create_test_data_message(),
            f'{pod.head_args.host}:{pod.head_args.port[0]}',
        )
        response_texts.update(response.response.docs.texts)
        assert 4 == len(response.response.docs.texts)
        assert 4 == len(response_texts)
        assert all(text in response_texts for text in ['0', '1', '2', 'client'])

    Deployment(args, include_gateway=False).start().close()


@pytest.mark.slow
@pytest.mark.skipif(
    'GITHUB_WORKFLOW' in os.environ,
    reason='for unknown reason, this test is flaky on Github action, '
    'but locally it SHOULD work fine',
)
@pytest.mark.parametrize(
    'protocol, uses',
    [
        ('grpc', 'GRPCGateway'),
    ],
)
def test_gateway_pod(protocol, uses, graph_description):
    args = set_gateway_parser().parse_args(
        [
            '--graph-description',
            graph_description,
            '--deployments-addresses',
            '{"pod0": ["0.0.0.0:1234"]}',
            '--protocol',
            protocol,
        ]
    )
    with Deployment(args, include_gateway=False) as p:
        assert len(p.all_args) == 1
        assert p.all_args[0].uses == uses

    Deployment(args, include_gateway=False).start().close()


def test_pod_naming_with_replica():
    args = set_deployment_parser().parse_args(['--name', 'pod', '--replicas', '2'])
    with Deployment(args, include_gateway=False) as bp:
        assert bp.head_pod is None
        assert bp.shards[0]._pods[0].name == 'pod/rep-0'
        assert bp.shards[0]._pods[1].name == 'pod/rep-1'


def test_pod_args_remove_uses_ba():
    args = set_deployment_parser().parse_args([])
    with Deployment(args, include_gateway=False) as p:
        assert p.num_pods == 1

    args = set_deployment_parser().parse_args(
        ['--uses-before', __default_executor__, '--uses-after', __default_executor__]
    )
    with Deployment(args, include_gateway=False) as p:
        assert p.num_pods == 1

    args = set_deployment_parser().parse_args(
        [
            '--uses-before',
            __default_executor__,
            '--uses-after',
            __default_executor__,
            '--replicas',
            '2',
        ]
    )
    with Deployment(args, include_gateway=False) as p:
        assert p.num_pods == 2


class DynamicPollingExecutor(Executor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @requests(on='/any')
    def any(self, docs: DocumentArray, **kwargs):
        docs.append(Document(text='added'))
        return docs

    @requests(on='/all')
    def all(self, docs: DocumentArray, **kwargs):
        docs.append(Document(text='added'))
        return docs

    @requests(on='/no_polling')
    def no_polling(self, docs: DocumentArray, **kwargs):
        docs.append(Document(text='added'))
        return docs


@pytest.mark.parametrize('polling', ['any', 'all'])
def test_dynamic_polling_with_config(polling):
    endpoint_polling = {'/any': PollingType.ANY, '/all': PollingType.ALL, '*': polling}

    args = set_deployment_parser().parse_args(
        [
            '--uses',
            'DynamicPollingExecutor',
            '--shards',
            str(2),
            '--polling',
            json.dumps(endpoint_polling),
        ]
    )
    pod = Deployment(args, include_gateway=False)

    with pod:
        response = send_request_sync(
            _create_test_data_message(endpoint='/all'),
            f'{pod.head_args.host}:{pod.head_args.port[0]}',
            endpoint='/all',
        )
        assert len(response.docs) == 1 + 2  # 1 source doc + 2 docs added by each shard

        response = send_request_sync(
            _create_test_data_message(endpoint='/any'),
            f'{pod.head_args.host}:{pod.head_args.port[0]}',
            endpoint='/any',
        )
        assert (
            len(response.docs) == 1 + 1
        )  # 1 source doc + 1 doc added by the one shard

        response = send_request_sync(
            _create_test_data_message(endpoint='/no_polling'),
            f'{pod.head_args.host}:{pod.head_args.port[0]}',
            endpoint='/no_polling',
        )
        if polling == 'any':
            assert (
                len(response.docs) == 1 + 1
            )  # 1 source doc + 1 doc added by the one shard
        else:
            assert (
                len(response.docs) == 1 + 2
            )  # 1 source doc + 1 doc added by the two shards


class DynamicPollingExecutorDefaultNames(Executor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @requests(on='/index')
    def index(self, docs: DocumentArray, **kwargs):
        docs.append(Document(text='added'))
        return docs

    @requests(on='/search')
    def search(self, docs: DocumentArray, **kwargs):
        docs.append(Document(text='added'))
        return docs


@pytest.mark.parametrize('polling', ['any', 'all'])
def test_dynamic_polling_default_config(polling):
    args = set_deployment_parser().parse_args(
        [
            '--uses',
            'DynamicPollingExecutorDefaultNames',
            '--shards',
            str(2),
            '--polling',
            polling,
        ]
    )
    pod = Deployment(args, include_gateway=False)

    with pod:
        response = send_request_sync(
            _create_test_data_message(endpoint='/search'),
            f'{pod.head_args.host}:{pod.head_args.port[0]}',
            endpoint='/search',
        )
        assert len(response.docs) == 1 + 2

        response = send_request_sync(
            _create_test_data_message(endpoint='/index'),
            f'{pod.head_args.host}:{pod.head_args.port[0]}',
            endpoint='/index',
        )
        assert len(response.docs) == 1 + 1


@pytest.mark.parametrize('polling', ['any', 'all'])
def test_dynamic_polling_overwrite_default_config(polling):
    endpoint_polling = {'/search': PollingType.ANY, '*': polling}
    args = set_deployment_parser().parse_args(
        [
            '--uses',
            'DynamicPollingExecutorDefaultNames',
            '--shards',
            str(2),
            '--polling',
            json.dumps(endpoint_polling),
        ]
    )
    pod = Deployment(args, include_gateway=False)

    with pod:
        response = send_request_sync(
            _create_test_data_message(endpoint='/search'),
            f'{pod.head_args.host}:{pod.head_args.port[0]}',
            endpoint='/search',
        )
        assert (
            len(response.docs) == 1 + 1
        )  # 1 source doc + 1 doc added by the one shard

        response = send_request_sync(
            _create_test_data_message(endpoint='/index'),
            f'{pod.head_args.host}:{pod.head_args.port[0]}',
            endpoint='/index',
        )
        assert (
            len(response.docs) == 1 + 1
        )  # 1 source doc + 1 doc added by the one shard


def _create_test_data_message(endpoint='/'):
    return list(request_generator(endpoint, DocumentArray([Document(text='client')])))[
        0
    ]


@pytest.mark.parametrize('num_shards, num_replicas', [(1, 1), (1, 2), (2, 1), (3, 2)])
def test_pod_remote_pod_replicas_host(num_shards, num_replicas):
    args = set_deployment_parser().parse_args(
        [
            '--shards',
            str(num_shards),
            '--replicas',
            str(num_replicas),
            '--host',
            __default_host__,
        ]
    )
    assert args.host == [__default_host__]
    with Deployment(args, include_gateway=False) as pod:
        assert pod.num_pods == num_shards * num_replicas + (1 if num_shards > 1 else 0)
        pod_args = dict(pod.pod_args['pods'])
        for k, replica_args in pod_args.items():
            assert len(replica_args) == num_replicas
            for replica_arg in replica_args:
                assert replica_arg.host == __default_host__


@pytest.mark.skip('jinahub not available')
@pytest.mark.parametrize(
    'uses',
    ['jinahub+docker://DummyHubExecutor', 'jinaai+docker://jina-ai/DummyHubExecutor'],
)
@pytest.mark.parametrize('shards', [1, 2, 3])
@pytest.mark.parametrize('replicas', [1, 2, 3])
def test_to_k8s_yaml(tmpdir, uses, replicas, shards):
    dep = Deployment(uses=uses, replicas=replicas, shards=shards)
    dep.to_kubernetes_yaml(output_base_path=tmpdir)

    if shards == 1:
        shards_iter = ['']
    else:
        shards_iter = [f'-{shard}' for shard in range(shards)]
    for shard in shards_iter:
        with open(os.path.join(tmpdir, f'executor{shard}.yml'), encoding='utf-8') as f:
            exec_yaml = list(yaml.safe_load_all(f))[-1]
            assert exec_yaml['spec']['replicas'] == replicas
            assert exec_yaml['spec']['template']['spec']['containers'][0][
                'image'
            ].startswith('registry')

    if shards != 1:
        with open(os.path.join(tmpdir, f'executor-head.yml'), encoding='utf-8') as f:
            head_yaml = list(yaml.safe_load_all(f))[-1]
            assert head_yaml['metadata']['name'] == 'executor-head'
            assert head_yaml['spec']['replicas'] == 1
            assert head_yaml['spec']['template']['spec']['containers'][0][
                'image'
            ].startswith('jinaai/')


def test_gateway(pod_args):
    with Deployment(pod_args, include_gateway=True) as pod:
        assert pod.gateway_pod


def test_log_config(pod_args, monkeypatch):
    monkeypatch.delenv('JINA_LOG_LEVEL', raising=True)  # ignore global env
    log_config_path = os.path.join(cur_dir, '../../logging/yaml/file.yml')
    with Deployment(pod_args, log_config=log_config_path, include_gateway=True) as pod:
        assert pod.args.log_config == log_config_path
        assert pod.gateway_pod.args.log_config == log_config_path
        for _, pods in pod.pod_args['pods'].items():
            for replica_args in pods:
                assert replica_args.log_config == log_config_path


def test_log_config_shards(pod_args, monkeypatch):
    pod_args.shards = 3
    monkeypatch.delenv('JINA_LOG_LEVEL', raising=True)  # ignore global env
    log_config_path = os.path.join(cur_dir, '../../logging/yaml/file.yml')
    with Deployment(pod_args, log_config=log_config_path, include_gateway=True) as pod:
        assert pod.args.log_config == log_config_path
        assert pod.gateway_pod.args.log_config == log_config_path
        assert pod.head_args.log_config == log_config_path
        assert pod.head_pod.args.log_config == log_config_path
        for _, shards in pod.pod_args['pods'].items():
            for shard_args in shards:
                assert shard_args.log_config == log_config_path
