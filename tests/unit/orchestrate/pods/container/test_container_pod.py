import os
import time

import pytest
import requests

from jina import Flow
from jina.constants import __cache_path__
from jina.enums import ProtocolType
from jina.excepts import RuntimeFailToStart
from jina.helper import random_port
from jina.orchestrate.pods.container import ContainerPod
from jina.serve.runtimes import servers
from jina.parsers import set_gateway_parser
from tests.helper import _generate_pod_args, _validate_dummy_custom_gateway_response

cur_dir = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope='module')
def env_checker_docker_image_built():
    import docker

    client = docker.from_env()
    client.images.build(path=os.path.join(cur_dir, 'env-checker/'), tag='env-checker')
    client.close()
    yield
    time.sleep(2)
    client = docker.from_env()
    client.containers.prune()


@pytest.fixture(scope='module')
def dummy_exec_docker_image_built():
    import docker

    client = docker.from_env()
    client.images.build(path=os.path.join(cur_dir, 'dummy-exec/'), tag='dummy-exec')
    client.close()
    yield
    time.sleep(2)
    client = docker.from_env()
    client.containers.prune()


def test_container_pod_pass_envs(env_checker_docker_image_built):
    import docker

    args = _generate_pod_args(
        [
            '--uses',
            'docker://env-checker',
            '--env',
            'key1=value1',
            '--env',
            'key2=value2',
        ]
    )
    with ContainerPod(args) as pod:
        container = pod._container
        status = container.status
        time.sleep(
            2
        )  # to avoid desync between the start and close process which could lead to container never get terminated

    assert status == 'running'
    client = docker.from_env()
    containers = client.containers.list()
    assert container.id not in containers


@pytest.mark.parametrize(
    'pod_args,expected_source,expected_destination',
    [
        (
            [
                '--uses',
                'docker://dummy-exec',
            ],
            '',
            '',
        ),
        (
            ['--uses', 'docker://dummy-exec', '--volumes'],
            'my/very/cool',
            '/custom/volume',
        ),
    ],
)
def test_container_pod_volume_setting(
    pod_args,
    expected_source,
    expected_destination,
    dummy_exec_docker_image_built,
    tmpdir,
):
    if expected_source:
        expected_source = os.path.join(tmpdir, expected_source)
        volume_arg = str(expected_source) + ':' + expected_destination
        pod_args.append(volume_arg)

    default_workspace = __cache_path__

    with ContainerPod(_generate_pod_args(pod_args)) as pod:
        container = pod._container
        source = container.attrs['Mounts'][0]['Source']
        destination = container.attrs['Mounts'][0]['Destination']
        time.sleep(
            2
        )  # to avoid desync between the start and close process which could lead to container never get terminated

    expected_source = (
        os.path.abspath(expected_source)
        if expected_source
        else os.path.abspath(default_workspace)
    )
    expected_destination = expected_destination if expected_destination else '/app'

    assert source.startswith(
        expected_source
    )  # there is a random workspace id at the end!
    assert destination == expected_destination


@pytest.fixture(scope='module')
def fail_start_docker_image_built():
    import docker

    client = docker.from_env()
    client.images.build(path=os.path.join(cur_dir, 'fail-start/'), tag='fail-start')
    client.close()
    yield
    time.sleep(2)
    client = docker.from_env()
    client.containers.prune()


def test_failing_executor(fail_start_docker_image_built):
    import docker

    args = _generate_pod_args(
        [
            '--uses',
            'docker://fail-start',
        ]
    )

    with pytest.raises(RuntimeFailToStart):
        pod = ContainerPod(args)
        with pod:
            pass

    with pytest.raises(docker.errors.NotFound):
        pod._container


@pytest.mark.skip('jinahub not available')
def test_pass_arbitrary_kwargs(monkeypatch, mocker):
    import docker

    def _mock_is_ready(*args, **kwargs):
        return True

    monkeypatch.setattr(
        servers.BaseServer,
        'is_ready',
        _mock_is_ready,
    )

    class MockContainers:
        class MockContainer:
            def reload(self):
                pass

            def logs(self, **kwargs):
                return []

            @property
            def id(self):
                return 'mock-id'

            def reload(self):
                pass

            def stop(self, *args, **kwargs):
                pass

        def __init__(self):
            pass

        def list(self):
            return []

        def get(self, *args):
            return MockContainers.MockContainer()

        def run(self, *args, **kwargs):
            assert 'ports' in kwargs
            assert 'environment' in kwargs
            envs = kwargs['environment']
            assert 'JINA_DEPLOYMENT_NAME' in envs
            assert 'VAR1' in envs
            assert envs['VAR1'] == 'BAR'
            assert 'VAR2' in envs
            assert envs['VAR2'] == 'FOO'
            assert 'hello' in kwargs
            assert kwargs['hello'] == 0
            return MockContainers.MockContainer()

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            pass

        def version(self):
            return {'Version': '20.0.1'}

        @property
        def networks(self):
            return {'bridge': None}

        @property
        def containers(self):
            return MockContainers()

        @property
        def images(self):
            return {}

    monkeypatch.setattr(docker, 'from_env', MockClient)
    args = _generate_pod_args(
        [
            '--uses',
            'docker://jinahub/pod',
            '--env',
            '--env',
            'VAR1=BAR',
            '--env',
            'VAR2=FOO',
            '--docker-kwargs',
            'hello: 0',
        ]
    )
    with ContainerPod(args) as pod:
        time.sleep(
            2
        )  # to avoid desync between the start and close process which could lead to container never get terminated
    pod.join()
    assert pod.worker.exitcode == 0


@pytest.fixture(scope='module')
def dummy_custom_gateway_docker_image_built():
    import docker

    client = docker.from_env()
    client.images.build(
        path=os.path.join(cur_dir, 'custom-gateway/'), tag='custom-gateway'
    )
    client.close()
    yield
    time.sleep(2)
    client = docker.from_env()
    client.containers.prune()


def test_container_pod_custom_gateway(dummy_custom_gateway_docker_image_built):
    import docker

    port = str(random_port())
    with ContainerPod(
        set_gateway_parser().parse_args(
            ['--uses', 'docker://custom-gateway', '--port', port, '--protocol', 'http']
        )
    ) as pod:
        container = pod._container
        status = pod._container.status
        _validate_dummy_custom_gateway_response(
            port, {'arg1': 'hello', 'arg2': 'world', 'arg3': 'default-arg3'}
        )

        # validate protocol inside the gateway
        resp = requests.get(f'http://127.0.0.1:{port}/runtime_info').json()
        assert resp['protocols'] == [ProtocolType.HTTP]
        assert resp['ports'] == [int(port)]

        time.sleep(
            2
        )  # to avoid desync between the start and close process which could lead to container never get terminated

    assert status == 'running'
    client = docker.from_env()
    containers = client.containers.list()
    assert container.id not in containers


def test_container_pod_with_flow_custom_gateway(
    dummy_custom_gateway_docker_image_built,
):
    flow = Flow().config_gateway(uses='docker://custom-gateway', protocol='http')
    with flow:
        _validate_dummy_custom_gateway_response(
            flow.port, {'arg1': 'hello', 'arg2': 'world', 'arg3': 'default-arg3'}
        )
