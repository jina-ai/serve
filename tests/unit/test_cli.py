import json
import os
import subprocess

import pytest

from jina.checker import NetworkChecker
from jina.jaml import JAML
from jina.orchestrate.pods.factory import PodFactory
from jina.parsers import set_deployment_parser
from jina.parsers.ping import set_ping_parser
from jina_cli.autocomplete import ac_table
from jina_cli.export import api_to_dict
from jina_cli.lookup import _build_lookup_table, lookup_and_print
from tests.helper import _generate_pod_args


def test_export_api(tmpdir):
    with open(tmpdir / 'test.yml', 'w', encoding='utf-8') as fp:
        JAML.dump(api_to_dict(), fp)
    with open(tmpdir / 'test.json', 'w', encoding='utf-8') as fp:
        json.dump(api_to_dict(), fp)


@pytest.mark.parametrize('cli', ac_table['commands'])
def test_help_lookup(cli, capsys):
    nkw2kw, kw2info = _build_lookup_table()
    if cli not in {'--help', '--version', '--version-full'}:
        assert cli in nkw2kw
        lookup_and_print(cli)
        captured = capsys.readouterr()
        assert 'Traceback (most recent call last)' not in captured.out


def test_main_cli():
    subprocess.check_call(['jina'])


def test_cli_help():
    subprocess.check_call(['jina', 'help', 'deployment'])


@pytest.mark.skip("jinahub not available")
@pytest.mark.parametrize('uses', ['jinaai://jina-ai/DummyHubExecutor'])
def test_cli_hub(uses):
    subprocess.check_call(['jina', 'hub', '--help'])
    for cmd in ['new', 'status', 'pull', 'push']:
        subprocess.check_call(['jina', 'hub', cmd, '--help'])
    subprocess.check_call(['jina', 'hub', 'pull', uses])


def test_cli_warn_unknown_args():
    subprocess.check_call(['jina', 'help', 'deployment', '--abcdefg'])


@pytest.mark.parametrize('cli', ac_table['commands'])
def test_all_cli(cli):
    subprocess.check_call(['jina', cli, '--help'])


@pytest.mark.parametrize('smethod', ['fork', 'spawn'])
def test_all_start_method(smethod):
    s = subprocess.check_output(
        ['jina', '-v'],
        env=dict(os.environ, JINA_MP_START_METHOD=smethod),
        stderr=subprocess.STDOUT,
    )
    assert 'UserWarning' in s.decode()
    assert smethod in s.decode()


def test_help_non_exist():
    s = subprocess.check_output(
        ['jina', 'help', 'abcdefg'],
        stderr=subprocess.STDOUT,
    )
    assert 'misspelling' in s.decode()


def test_help_exist():
    s = subprocess.check_output(
        ['jina', 'help', 'port'],
        stderr=subprocess.STDOUT,
    )
    assert 'a CLI argument of Jina' in s.decode()


def test_parse_env_map():
    a = set_deployment_parser().parse_args(
        ['--env', 'key1=value1', '--env', 'key2=value2']
    )
    assert a.env == {'key1': 'value1', 'key2': 'value2'}

    a = set_deployment_parser().parse_args(
        ['--env', 'key1=value1', 'key2=value2', 'key3=3']
    )
    assert a.env == {'key1': 'value1', 'key2': 'value2', 'key3': 3}


@pytest.mark.slow
def test_ping():
    a1 = _generate_pod_args()
    a2 = set_ping_parser().parse_args(['executor', f'0.0.0.0:{a1.port[0]}'])

    a3 = set_ping_parser().parse_args(
        ['executor', f'0.0.0.1:{a1.port[0]}', '--timeout', '1000']
    )

    with pytest.raises(SystemExit) as cm:
        with PodFactory.build_pod(a1):
            NetworkChecker(a2)

    assert cm.value.code == 0

    # test with bad address
    with pytest.raises(SystemExit) as cm:
        with PodFactory.build_pod(a1):
            NetworkChecker(a3)

    assert cm.value.code == 1


@pytest.mark.parametrize(
    'cmd',
    [
        ['jina', 'ping', 'flow', '127.0.0.1:8080'],
        ['jina', 'help', 'port'],
        ['jina', 'hub'],
    ],
)
def test_logo_silence(cmd):
    from jina.constants import __resources_path__

    with open(os.path.join(__resources_path__, 'jina.logo'), encoding='utf-8') as fp:
        logo_str = fp.read()

    s = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
    )
    assert logo_str not in s.stdout.decode()
