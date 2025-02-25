import asyncio
import os
import random
import string
import tempfile
import time

import pytest

from jina import helper


@pytest.fixture(scope='function')
def random_workspace_name():
    """Generate a random workspace name with digits and letters."""
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f'JINA_TEST_WORKSPACE_{rand}'


@pytest.fixture(scope='function')
def test_metas(tmpdir, random_workspace_name):
    from jina.serve.executors.metas import get_default_metas

    os.environ[random_workspace_name] = str(tmpdir)
    metas = get_default_metas()
    metas['workspace'] = os.environ[random_workspace_name]
    yield metas
    del os.environ[random_workspace_name]


@pytest.fixture()
def docker_compose(request):
    os.system(
        f"docker compose -f {request.param} --project-directory . up  --build -d --remove-orphans"
    )
    time.sleep(10)
    yield
    os.system(
        f"docker compose -f {request.param} --project-directory . down --remove-orphans"
    )


@pytest.fixture(scope='function')
def port_generator():
    generated_ports = set()

    def random_port():
        port = helper.random_port()
        while port in generated_ports:
            port = helper.random_port()
        generated_ports.add(port)
        return port

    return random_port


@pytest.fixture(autouse=True)
def test_log_level(monkeypatch):
    monkeypatch.setenv('JINA_LOG_LEVEL', 'DEBUG')


@pytest.fixture(autouse=True)
def test_grpc_fork_support_true(monkeypatch):
    monkeypatch.setenv('GRPC_ENABLE_FORK_SUPPORT', 'true')


@pytest.fixture(autouse=True)
def test_timeout_ctrl_time(monkeypatch):
    monkeypatch.setenv('JINA_DEFAULT_TIMEOUT_CTRL', '500')


@pytest.fixture(autouse=True)
def test_disable_telemetry(monkeypatch):
    monkeypatch.setenv('JINA_OPTOUT_TELEMETRY', 'True')


@pytest.fixture(autouse=True)
def tmpfile(tmpdir):
    tmpfile = f'jina_test_{next(tempfile._get_candidate_names())}.db'
    return tmpdir / tmpfile


@pytest.fixture(scope='session')
def event_loop(request):
    """
    Valid only for `pytest.mark.asyncio` tests
    """
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def set_test_pip_version() -> None:
    os.environ['JINA_GATEWAY_IMAGE'] = 'jinaai/jina:test-pip'
    yield
    if 'JINA_GATEWAY_IMAGE' in os.environ:  # maybe another fixture has already removed
        del os.environ['JINA_GATEWAY_IMAGE']
