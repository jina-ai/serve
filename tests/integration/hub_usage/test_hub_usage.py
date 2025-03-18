import os
from pathlib import Path

import pytest

from jina import Flow
from jina.excepts import RuntimeFailToStart
from jina.orchestrate.deployments import Deployment
from jina.parsers import set_deployment_parser
from jina.serve.executors import BaseExecutor

cur_dir = os.path.dirname(os.path.abspath(__file__))

@pytest.mark.skip('jinahub not available')
def test_simple_use_abs_import_shall_fail():
    with pytest.raises(ModuleNotFoundError):
        from .dummyhub_abs import DummyHubExecutorAbs

        DummyHubExecutorAbs()

    with pytest.raises(RuntimeFailToStart):
        with Flow().add(uses='DummyHubExecutorAbs'):
            pass

@pytest.mark.skip('jinahub not available')
def test_simple_use_relative_import():
    from .dummyhub import DummyHubExecutor

    DummyHubExecutor()

    with Flow().add(uses='DummyHubExecutor'):
        pass

@pytest.mark.skip('jinahub not available')
def test_use_from_local_dir_exe_level():
    with BaseExecutor.load_config('dummyhub/config.yml'):
        pass

@pytest.mark.skip('jinahub not available')
def test_use_from_local_dir_deployment_level():
    a = set_deployment_parser().parse_args(['--uses', 'dummyhub/config.yml'])
    with Deployment(a):
        pass

@pytest.mark.skip('jinahub not available')
def test_use_from_local_dir_flow_level():
    with Flow().add(uses='dummyhub/config.yml'):
        pass


@pytest.fixture
def local_hub_executor(tmpdir):
    from hubble.executor import HubExecutor, helper, hubapi

    pkg_path = Path(__file__).parent / 'dummyhub'
    stream_data = helper.archive_package(pkg_path)
    with open(tmpdir / 'dummy_test.zip', 'wb') as temp_zip_file:
        temp_zip_file.write(stream_data.getvalue())

    hubapi.install_local(
        Path(tmpdir) / 'dummy_test.zip', HubExecutor(uuid='hello', tag='v0')
    )

@pytest.mark.skip('jinahub not available')
@pytest.mark.parametrize('uses', ['jinahub://hello', 'jinaai://jina-ai/hello'])
def test_use_from_local_hub_deployment_level(
    mocker, monkeypatch, local_hub_executor, uses
):
    from hubble.executor.hubio import HubExecutor, HubIO

    mock = mocker.Mock()

    def _mock_fetch(
        name,
        *args,
        **kwargs,
    ):
        mock(name=name)
        return (
            HubExecutor(
                uuid='hello',
                name='alias_dummy',
                tag='v0',
                image_name='jinahub/pod.dummy_mwu_encoder',
                md5sum=None,
                visibility=True,
                archive_url=None,
            ),
            False,
        )

    monkeypatch.setattr(HubIO, 'fetch_meta', _mock_fetch)
    a = set_deployment_parser().parse_args(['--uses', uses])
    with Deployment(a):
        pass

@pytest.mark.skip('jinahub not available')
@pytest.mark.parametrize('uses', ['jinahub://hello', 'jinaai://jina-ai/hello'])
def test_use_from_local_hub_flow_level(mocker, monkeypatch, local_hub_executor, uses):
    from hubble.executor.hubio import HubExecutor, HubIO

    mock = mocker.Mock()

    def _mock_fetch(
        name,
        *args,
        **kwargs,
    ):
        mock(name=name)
        return (
            HubExecutor(
                uuid='hello',
                name='alias_dummy',
                tag='v0',
                image_name='jinahub/pod.dummy_mwu_encoder',
                md5sum=None,
                visibility=True,
                archive_url=None,
            ),
            False,
        )

    monkeypatch.setattr(HubIO, 'fetch_meta', _mock_fetch)

    with Flow().add(uses=uses, install_requirements=True):
        pass
