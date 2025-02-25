import contextlib
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List

import docker
import pytest
from pytest import FixtureRequest
from pytest_kind import KindCluster

from jina.logging.logger import JinaLogger

client = docker.from_env()
cur_dir = os.path.dirname(__file__)


class KindClusterWrapper:
    def __init__(self, kind_cluster: KindCluster, logger: JinaLogger) -> None:
        self._cluster = kind_cluster
        self._cluster.ensure_kubectl()
        self._kube_config_path = os.path.join(
            os.getcwd(), '.pytest-kind/pytest-kind/kubeconfig'
        )
        self._log = logger
        self._set_kube_config()
        self._install_linkerd(kind_cluster)
        self._loaded_images = set()

    def _linkerd_install_cmd(
            self, kind_cluster: KindCluster, cmd, tool_name: str
    ) -> None:
        self._log.info(f'Installing {tool_name} to Cluster...')
        kube_out = subprocess.check_output(
            (str(kind_cluster.kubectl_path), 'version'),
            env=os.environ,
        )
        self._log.info(f'kubernetes versions: {kube_out}')

        # since we need to pipe to commands and the linkerd output can bee too long
        # there is a risk of deadlock and hanging tests: https://docs.python.org/3/library/subprocess.html#popen-objects
        # to avoid this, the right mechanism is implemented in subprocess.run and subprocess.check_output, but output
        # must be piped to a file-like object, not to stdout
        proc_stdout = tempfile.TemporaryFile()
        proc = subprocess.run(
            cmd,
            stdout=proc_stdout,
            env={"KUBECONFIG": str(kind_cluster.kubeconfig_path)},
        )

        proc_stdout.seek(0)
        kube_out = subprocess.check_output(
            (
                str(kind_cluster.kubectl_path),
                'apply',
                '-f',
                '-',
            ),
            stdin=proc_stdout,
            env=os.environ,
        )

        returncode = proc.returncode
        self._log.info(
            f'Installing {tool_name} to Cluster returned code {returncode}, kubectl output was {kube_out}'
        )
        if returncode is not None and returncode != 0:
            raise Exception(f'Installing {tool_name} failed with {returncode}')

    def _install_linkerd(self, kind_cluster: KindCluster) -> None:
        # linkerd < 2.12: only linkerd install is needed
        # in later versions, linkerd install --crds will be needed
        self._linkerd_install_cmd(
            kind_cluster, [f'{Path.home()}/.linkerd2/bin/linkerd', 'install'], 'Linkerd'
        )

        self._log.info('check linkerd status')
        try:
            out = subprocess.check_output(
                [f'{Path.home()}/.linkerd2/bin/linkerd', 'check'],
                env=os.environ,
                stderr=subprocess.STDOUT,
            )
            print(f'linkerd check yields {out.decode() if out else "nothing"}')
        except subprocess.CalledProcessError as e:
            print(
                f'linkerd check failed with error code {e.returncode} and output {e.output}, and stderr {e.stderr}'
            )
            raise

    def install_linkerd_smi(self) -> None:
        self._log.info('Installing Linkerd SMI to Cluster...')
        proc = subprocess.Popen(
            [f'{Path.home()}/.linkerd2/bin/linkerd-smi', 'install'],
            stdout=subprocess.PIPE,
            env={"KUBECONFIG": str(self._cluster.kubeconfig_path)},
        )
        kube_out = subprocess.check_output(
            (
                str(self._cluster.kubectl_path),
                'apply',
                '-f',
                '-',
            ),
            stdin=proc.stdout,
            env=os.environ,
        )
        self._log.info('Poll status of linkerd smi install')
        returncode = proc.poll()
        self._log.info(
            f'Installing Linkerd to Cluster returned code {returncode}, kubectl output was {kube_out}'
        )
        if returncode is not None and returncode != 0:
            raise Exception(f"Installing linkerd failed with {returncode}")

        self._log.info('check linkerd status')
        try:
            out = subprocess.check_output(
                [f'{Path.home()}/.linkerd2/bin/linkerd-smi', 'check'],
                env=os.environ,
                stderr=subprocess.STDOUT,
            )
            print(f'linkerd check yields {out.decode() if out else "nothing"}')
        except subprocess.CalledProcessError as e:
            print(
                f'linkerd check failed with error code {e.returncode} and output {e.output}, and stderr {e.stderr}'
            )
            raise

    def _set_kube_config(self):
        self._log.info(f'Setting KUBECONFIG to {self._kube_config_path}')
        os.environ['KUBECONFIG'] = self._kube_config_path
        load_cluster_config()

    def load_docker_images(
            self, images: List[str], image_tag_map: Dict[str, str]
    ) -> None:
        for image in images:
            full_image_name = image + ':' + image_tag_map[image]
            if full_image_name not in self._loaded_images:
                if image != 'alpine' and image != 'jinaai/jina':
                    build_docker_image(image, image_tag_map)
                self._cluster.load_docker_image(full_image_name)
                self._loaded_images.add(full_image_name)


@pytest.fixture()
def test_dir() -> str:
    return cur_dir


@pytest.fixture
def logger() -> JinaLogger:
    return JinaLogger('kubernetes-testing')


@pytest.fixture(scope='session')
def k8s_cluster(kind_cluster: KindCluster) -> KindClusterWrapper:
    return KindClusterWrapper(kind_cluster, JinaLogger('kubernetes-cluster-logger'))


@pytest.fixture
def image_name_tag_map() -> Dict[str, str]:
    return {
        'reload-executor': '0.13.1',
        'test-executor': '0.13.1',
        'test-executor-torch': '0.13.1',
        'slow-process-executor': '0.14.1',
        'executor-merger': '0.1.1',
        'set-text-executor': '0.1.1',
        'failing-executor': '0.1.1',
        'jinaai/jina': 'test-pip',
        'custom-gateway': '0.1.1',
        'test-stateful-executor': '0.13.1',
        'multiprotocol-gateway': '0.1.1',
        'slow-load-executor': '0.1.1',
    }


def build_docker_image(image_name: str, image_name_tag_map: Dict[str, str]) -> str:
    logger = JinaLogger('kubernetes-testing')
    image_tag = image_name + ':' + image_name_tag_map[image_name]
    image, build_logs = client.images.build(
        path=os.path.join(cur_dir, image_name), tag=image_tag
    )
    for chunk in build_logs:
        if 'stream' in chunk:
            for line in chunk['stream'].splitlines():
                logger.debug(line)
    return image.tags[-1]


@pytest.fixture(autouse=True)
def set_test_pip_version() -> None:
    os.environ['JINA_GATEWAY_IMAGE'] = 'jinaai/jina:test-pip'
    yield
    if 'JINA_GATEWAY_IMAGE' in os.environ:  # maybe another fixture has already removed
        del os.environ['JINA_GATEWAY_IMAGE']


def load_cluster_config() -> None:
    import kubernetes

    try:
        # try loading kube config from disk first
        kubernetes.config.load_kube_config()
    except kubernetes.config.config_exception.ConfigException:
        # if the config could not be read from disk, try loading in cluster config
        # this works if we are running inside k8s
        kubernetes.config.load_incluster_config()


@pytest.fixture
def docker_images(
        request: FixtureRequest,
        image_name_tag_map: Dict[str, str],
        k8s_cluster: KindClusterWrapper,
) -> List[str]:
    image_names: List[str] = request.param
    k8s_cluster.load_docker_images(image_names, image_name_tag_map)
    images = [
        image_name + ':' + image_name_tag_map[image_name] for image_name in image_names
    ]
    return images


@contextlib.contextmanager
def shell_portforward(
        kubectl_path, pod_or_service, port1, port2, namespace, waiting: float = 1
):
    try:
        proc = subprocess.Popen(
            [
                kubectl_path,
                'port-forward',
                pod_or_service,
                f'{port1}:{port2}',
                '--namespace',
                namespace,
            ]
        )
        # Go and the port-forwarding needs some ms to be ready
        time.sleep(waiting)

        yield None
        time.sleep(waiting)

    except Exception as err:
        # Suppress extension exception
        raise OSError(err) from None

    finally:
        proc.kill()
