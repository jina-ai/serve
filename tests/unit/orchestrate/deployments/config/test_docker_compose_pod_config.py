import json
import os
from typing import Dict, Tuple, Union

import pytest
from hubble.executor import HubExecutor
from hubble.executor.hubio import HubIO

from jina.helper import Namespace
from jina.orchestrate.deployments.config.docker_compose import DockerComposeConfig
from jina.parsers import set_deployment_parser, set_gateway_parser


def namespace_equal(
    n1: Union[Namespace, Dict], n2: Union[Namespace, Dict], skip_attr: Tuple = ()
) -> bool:
    """
    Checks that two `Namespace` object have equal public attributes.
    It skips attributes that start with a underscore and additional `skip_attr`.
    """
    if n1 is None and n2 is None:
        return True
    for attr in filter(lambda x: x not in skip_attr and not x.startswith('_'), dir(n1)):
        if not getattr(n1, attr) == getattr(n2, attr):
            print(f' differ in {attr}')
            return False
    return True


@pytest.mark.parametrize('shards', [1, 5])
@pytest.mark.parametrize('replicas', [1, 5])
@pytest.mark.parametrize(
    'uses_before',
    [
        None,
        'jinaai+docker://jina-ai/HubBeforeExecutor',
    ],
)
@pytest.mark.parametrize('uses_after', [None, 'docker://docker_after_image:latest'])
@pytest.mark.parametrize('uses_with', ['{"paramkey": "paramvalue"}', None])
@pytest.mark.parametrize('uses_metas', ['{"workspace": "workspacevalue"}', None])
def test_parse_args(
    shards: int,
    replicas: int,
    uses_with,
    uses_metas,
    uses_before,
    uses_after,
):
    args_list = [
        '--shards',
        str(shards),
        '--replicas',
        str(replicas),
        '--name',
        'executor',
    ]
    if uses_before is not None:
        args_list.extend(['--uses-before', uses_before])

    if uses_after is not None:
        args_list.extend(['--uses-after', uses_after])

    if uses_with is not None:
        args_list.extend(['--uses-with', uses_with])

    if uses_metas is not None:
        args_list.extend(['--uses-metas', uses_metas])
    args = set_deployment_parser().parse_args(args_list)
    deployment_config = DockerComposeConfig(args)
    args.host = args.host[0]

    assert namespace_equal(
        deployment_config.services_args['head_service'],
        args,
        skip_attr=(
            'runtime_cls',
            'pod_role',
            'port',
            'k8s_namespace',
            'name',
            'uses',
            'connection_list',
            'uses_with',
            'uses_metas',
            'uses_before',
            'uses_after',
            'uses_before_address',
            'uses_after_address',
            'replicas',
        ),
    )

    if shards > 1:
        assert deployment_config.services_args['head_service'].name == 'executor/head'
        assert (
            deployment_config.services_args['head_service'].runtime_cls == 'HeadRuntime'
        )
        assert deployment_config.services_args['head_service'].uses is None
        assert deployment_config.services_args['head_service'].uses_before is None
        assert deployment_config.services_args['head_service'].uses_after is None
        assert deployment_config.services_args['head_service'].uses_metas is None
        assert deployment_config.services_args['head_service'].uses_with is None
        if uses_before is None:
            assert (
                deployment_config.services_args['head_service'].uses_before_address
                is None
            )
        else:
            assert (
                deployment_config.services_args['head_service'].uses_before_address
                == 'executor-uses-before:8081'
            )
        if uses_after is None:
            assert (
                deployment_config.services_args['head_service'].uses_after_address
                is None
            )
        else:
            assert (
                deployment_config.services_args['head_service'].uses_after_address
                == 'executor-uses-after:8081'
            )
        if replicas == 1:
            candidate_connection_list = {
                str(i): [f'executor-{i}:8081'] for i in range(shards)
            }
        else:
            candidate_connection_list = {}
            for shard_id in range(shards):
                candidate_connection_list[str(shard_id)] = []
                for replica in range(replicas):  # TODO
                    candidate_connection_list[str(shard_id)].append(
                        f'executor-{shard_id}-rep-{replica}:8081'
                    )

    else:
        if replicas == 1:
            candidate_connection_list = {'0': [f'executor:8081']}
        else:
            candidate_connection_list = {'0': []}
            for replica in range(replicas):  # TODO
                candidate_connection_list['0'].append(f'executor-rep-{replica}:8081')

    if shards > 1:
        assert deployment_config.services_args[
            'head_service'
        ].connection_list == json.dumps(candidate_connection_list)

        if uses_before is not None:
            assert (
                deployment_config.services_args['uses_before_service'].name
                == 'executor/uses-before'
            )
            assert (
                deployment_config.services_args['uses_before_service'].runtime_cls
                == 'WorkerRuntime'
            )
            assert (
                deployment_config.services_args['uses_before_service'].uses
                == uses_before
            )
            assert (
                deployment_config.services_args['uses_before_service'].uses_before
                is None
            )
            assert (
                deployment_config.services_args['uses_before_service'].uses_after
                is None
            )
            assert (
                deployment_config.services_args['uses_before_service'].uses_metas
                is None
            )
            assert (
                deployment_config.services_args['uses_before_service'].uses_with is None
            )
            assert deployment_config.services_args['uses_before_service'].shard_id == 0
            assert deployment_config.services_args['uses_before_service'].replicas == 1

        if uses_after is not None:
            assert (
                deployment_config.services_args['uses_after_service'].name
                == 'executor/uses-after'
            )
            assert (
                deployment_config.services_args['uses_after_service'].runtime_cls
                == 'WorkerRuntime'
            )
            assert (
                deployment_config.services_args['uses_after_service'].uses == uses_after
            )
            assert (
                deployment_config.services_args['uses_after_service'].uses_before
                is None
            )
            assert (
                deployment_config.services_args['uses_after_service'].uses_after is None
            )
            assert (
                deployment_config.services_args['uses_after_service'].uses_metas is None
            )
            assert (
                deployment_config.services_args['uses_after_service'].uses_with is None
            )
            assert deployment_config.services_args['uses_after_service'].shard_id == 0
            assert deployment_config.services_args['uses_after_service'].replicas == 1

    for i, depl_arg in enumerate(deployment_config.services_args['services']):
        import copy

        assert (
            depl_arg.name == f'executor-{i}'
            if len(deployment_config.services_args['services']) > 1
            else 'executor'
        )
        cargs = copy.deepcopy(args)
        cargs.shard_id = i
        assert namespace_equal(
            depl_arg,
            cargs,
            skip_attr=(
                'runtime_cls',
                'pod_role',
                'port',
                'k8s_namespace',
                'uses_before',  # the uses_before and after is head business
                'uses_after',
                'name',
            ),
        )


@pytest.mark.parametrize('shards', [1, 5])
@pytest.mark.parametrize('replicas', [1, 5])
def test_parse_args_custom_executor(shards: int, replicas: int):
    uses_before = 'custom-executor-before'
    uses_after = 'custom-executor-after'
    args = set_deployment_parser().parse_args(
        [
            '--shards',
            str(shards),
            '--replicas',
            str(replicas),
            '--uses-before',
            uses_before,
            '--uses-after',
            uses_after,
            '--name',
            'executor',
        ]
    )
    deployment_config = DockerComposeConfig(args)
    args.host = args.host[0]

    if shards > 1:
        assert (
            deployment_config.services_args['head_service'].runtime_cls == 'HeadRuntime'
        )
        assert deployment_config.services_args['head_service'].uses_before is None
        assert (
            deployment_config.services_args['head_service'].uses_before_address
            == 'executor-uses-before:8081'
        )
        assert deployment_config.services_args['head_service'].uses is None
        assert deployment_config.services_args['head_service'].uses_after is None
        assert (
            deployment_config.services_args['head_service'].uses_after_address
            == f'executor-uses-after:8081'
        )

        assert deployment_config.services_args['head_service'].uses_before is None

        assert deployment_config.services_args['head_service'].uses_after is None

        assert (
            deployment_config.services_args['uses_before_service'].name
            == 'executor/uses-before'
        )
        assert (
            deployment_config.services_args['uses_before_service'].runtime_cls
            == 'WorkerRuntime'
        )
        assert (
            deployment_config.services_args['uses_before_service'].uses == uses_before
        )
        assert (
            deployment_config.services_args['uses_before_service'].uses_before is None
        )
        assert deployment_config.services_args['uses_before_service'].uses_after is None
        assert deployment_config.services_args['uses_before_service'].uses_metas is None
        assert deployment_config.services_args['uses_before_service'].uses_with is None
        assert deployment_config.services_args['uses_before_service'].shard_id == 0
        assert deployment_config.services_args['uses_before_service'].replicas == 1

        assert (
            deployment_config.services_args['uses_after_service'].name
            == 'executor/uses-after'
        )
        assert (
            deployment_config.services_args['uses_after_service'].runtime_cls
            == 'WorkerRuntime'
        )
        assert deployment_config.services_args['uses_after_service'].uses == uses_after
        assert deployment_config.services_args['uses_after_service'].uses_before is None
        assert deployment_config.services_args['uses_after_service'].uses_after is None
        assert deployment_config.services_args['uses_after_service'].uses_metas is None
        assert deployment_config.services_args['uses_after_service'].uses_with is None
        assert deployment_config.services_args['uses_after_service'].shard_id == 0
        assert deployment_config.services_args['uses_after_service'].replicas == 1

    for i, depl_arg in enumerate(deployment_config.services_args['services']):
        import copy

        assert (
            depl_arg.name == f'executor-{i}'
            if len(deployment_config.services_args['services']) > 1
            else 'executor'
        )
        cargs = copy.deepcopy(args)
        cargs.shard_id = i
        assert namespace_equal(
            depl_arg,
            cargs,
            skip_attr=(
                'uses_before',
                'uses_after',
                'port',
                'k8s_namespace',
                'name',
            ),
        )


@pytest.mark.parametrize(
    ['name', 'shards'],
    [
        (
            'gateway',
            '1',
        ),
        (
            'test-deployment',
            '1',
        ),
        (
            'test-deployment',
            '2',
        ),
    ],
)
def test_worker_services(name: str, shards: str):
    args = set_deployment_parser().parse_args(['--name', name, '--shards', shards])
    deployment_config = DockerComposeConfig(args)
    args.host = args.host[0]

    actual_services = deployment_config.worker_services

    assert len(actual_services) == int(shards)
    for i, deploy in enumerate(actual_services):
        if int(shards) > 1:
            assert deploy.name == f'{name}-{i}'
        else:
            assert deploy.name == name
        assert deploy.jina_deployment_name == name
        assert deploy.shard_id == i


@pytest.mark.parametrize('deployments_addresses', [None, {'1': 'executor-head:8081'}])
@pytest.mark.parametrize(
    'port,protocol',
    [
        (['12345'], None),
        (['12345'], ['grpc']),
        (['12345', '12344'], ['grpc', 'http']),
        (['12345', '12344', '12343'], ['grpc', 'http', 'websocket']),
    ],
)
@pytest.mark.parametrize(
    'custom_gateway', ['jinaai+docker://jina/custom-gateway', None]
)
def test_docker_compose_gateway(
    monkeypatch, deployments_addresses, custom_gateway, port, protocol
):
    from hubble.executor.hubio import HubExecutor, HubIO

    def _mock_fetch(
        name,
        *args,
        **kwargs,
    ):
        return (
            HubExecutor(
                uuid='hello',
                name='custom-gateway',
                tag='v0',
                image_name='jina/custom-gateway',
                md5sum=None,
                visibility=True,
                archive_url=None,
            ),
            False,
        )

    monkeypatch.setattr(HubIO, 'fetch_meta', _mock_fetch)
    args_list = ['--env', 'ENV_VAR:ENV_VALUE', '--port', *port]
    if protocol:
        args_list.extend(['--protocol', *protocol])
    if custom_gateway:
        args_list.extend(['--uses', custom_gateway])
    args = set_gateway_parser().parse_args(args_list)  # envs are
    # ignored for gateway
    deployment_config = DockerComposeConfig(
        args, deployments_addresses=deployments_addresses
    )
    name, gateway_config = deployment_config.to_docker_compose_config()[0]
    assert name == 'gateway'
    assert (
        gateway_config['image'] == 'jina/custom-gateway'
        if custom_gateway
        else f'jinaai/jina:test-pip'
    )
    assert gateway_config['entrypoint'] == ['jina']
    assert gateway_config['ports'] == [f'{_port}:{_port}' for _port in args.port]
    assert gateway_config['expose'] == args.port
    args = gateway_config['command']
    assert args[0] == 'gateway'
    assert '--port' in args

    for i, _port in enumerate(port):
        assert args[args.index('--port') + i + 1] == _port

    assert '--env' not in args
    if deployments_addresses is not None:
        assert '--deployments-addresses' in args
        assert args[args.index('--deployments-addresses') + 1] == json.dumps(
            deployments_addresses
        )


@pytest.mark.skip('jinahub not available')
@pytest.mark.parametrize('shards', [3, 1])
@pytest.mark.parametrize('replicas', [3, 1])
@pytest.mark.parametrize(
    'uses',
    [
        'docker://docker_image:latest',
        'jinaai+docker://jina-ai/HubExecutor',
    ],
)
@pytest.mark.parametrize(
    'uses_before',
    [
        None,
        'jinaai+docker://jina-ai/HubBeforeExecutor',
    ],
)
@pytest.mark.parametrize(
    'uses_after',
    [
        None,
        'jinaai+docker://jina-ai/HubAfterExecutor',
    ],
)
@pytest.mark.parametrize('uses_with', ['{"paramkey": "paramvalue"}', None])
@pytest.mark.parametrize('uses_metas', ['{"workspace": "workspacevalue"}', None])
@pytest.mark.parametrize('polling', ['ANY', 'ALL'])
def test_docker_compose_yaml_regular_deployment(
    uses_before,
    uses_after,
    uses,
    shards,
    replicas,
    uses_with,
    uses_metas,
    polling,
    monkeypatch,
):
    def _mock_fetch(
        name,
        *args,
        **kwargs,
    ):
        return (
            HubExecutor(
                uuid='hello',
                name='alias_dummy',
                tag='v0',
                image_name=f'jinahub/{name}',
                md5sum=None,
                visibility=True,
                archive_url=None,
            ),
            False,
        )

    monkeypatch.setattr(HubIO, 'fetch_meta', _mock_fetch)
    args_list = [
        '--name',
        'executor',
        '--uses',
        uses,
        '--env',
        'ENV_VAR:ENV_VALUE',
        '--replicas',
        str(replicas),
        '--shards',
        str(shards),
        '--polling',
        str(polling),
    ]
    if uses_before is not None:
        args_list.extend(['--uses-before', uses_before])

    if uses_after is not None:
        args_list.extend(['--uses-after', uses_after])

    if uses_with is not None:
        args_list.extend(['--uses-with', uses_with])

    if uses_metas is not None:
        args_list.extend(['--uses-metas', uses_metas])

    args = set_deployment_parser().parse_args(args_list)
    # ignored for gateway
    deployment_config = DockerComposeConfig(args)
    yaml_configs = deployment_config.to_docker_compose_config()
    assert len(yaml_configs) == shards * replicas + (
        (1 + (1 if uses_before else 0) + (1 if uses_after else 0)) if shards > 1 else 0
    )

    if shards > 1:
        head_name, head_config = yaml_configs[0]
        assert head_name == 'executor-head'
        assert head_config['image'] == f'jinaai/jina:test-pip'
        assert head_config['entrypoint'] == ['jina']
        head_args = head_config['command']
        assert head_args[0] == 'executor'
        assert '--native' in head_args
        assert '--runtime-cls' in head_args
        assert head_args[head_args.index('--runtime-cls') + 1] == 'HeadRuntime'
        assert '--name' in head_args
        assert head_args[head_args.index('--name') + 1] == 'executor/head'
        assert '--port' in head_args
        assert head_args[head_args.index('--port') + 1] == '8081'
        assert '--env' not in head_args
        assert '--pod-role' in head_args
        assert head_args[head_args.index('--pod-role') + 1] == 'HEAD'
        assert '--connection-list' in head_args
        connection_list_string = head_args[head_args.index('--connection-list') + 1]
        candidate_connection_list = {}
        if shards > 1:
            if replicas == 1:
                candidate_connection_list = {
                    str(shard_id): [f'executor-{shard_id}:8081']
                    for shard_id in range(shards)
                }
            else:
                candidate_connection_list = {}
                for shard_id in range(shards):
                    candidate_connection_list[str(shard_id)] = []
                    for replica in range(replicas):
                        candidate_connection_list[str(shard_id)].append(
                            f'executor-{shard_id}-rep-{replica}:8081'
                        )
        else:
            if shards == 1:
                if replicas == 1:
                    candidate_connection_list = {'0': [f'executor:8081']}
                else:
                    candidate_connection_list = {'0': []}
                    for replica in range(replicas):
                        candidate_connection_list['0'].append(
                            f'executor-rep-{replica}:8081'
                        )

        assert connection_list_string == json.dumps(candidate_connection_list)

        if polling == 'ANY':
            assert '--polling' not in head_args
        else:
            assert '--polling' in head_args
            assert head_args[head_args.index('--polling') + 1] == 'ALL'

        if uses_before is not None:
            uses_before_name, uses_before_config = yaml_configs[1]
            assert uses_before_name == 'executor-uses-before'
            assert uses_before_config['image'] in {
                'jinahub/HubBeforeExecutor',
                'jinahub/jina-ai/HubBeforeExecutor',
            }
            assert uses_before_config['entrypoint'] == ['jina']
            uses_before_args = uses_before_config['command']
            assert uses_before_args[0] == 'executor'
            assert '--native' in uses_before_args
            assert '--name' in uses_before_args
            assert '--env' not in uses_before_args
            assert (
                uses_before_args[uses_before_args.index('--name') + 1]
                == 'executor/uses-before'
            )
            assert '--port' in uses_before_args
            assert uses_before_args[uses_before_args.index('--port') + 1] == '8081'
            assert '--connection-list' not in uses_before_args
            assert '--polling' not in uses_before_args

        if uses_after is not None:
            uses_after_name, uses_after_config = (
                yaml_configs[1] if uses_before is None else yaml_configs[2]
            )
            assert uses_after_name == 'executor-uses-after'
            assert uses_after_config['image'] in {
                'jinahub/HubAfterExecutor',
                'jinahub/jina-ai/HubAfterExecutor',
            }
            assert uses_after_config['entrypoint'] == ['jina']
            uses_after_args = uses_after_config['command']
            assert uses_after_args[0] == 'executor'
            assert '--native' in uses_after_args
            assert '--name' in uses_after_args
            assert '--env' not in uses_after_args
            assert (
                uses_after_args[uses_after_args.index('--name') + 1]
                == 'executor/uses-after'
            )
            assert '--port' in uses_after_args
            assert uses_after_args[uses_after_args.index('--port') + 1] == '8081'
            assert '--connection-list' not in uses_after_args
            assert '--polling' not in uses_after_args

    num_shards_replicas_configs = shards * replicas
    shards_replicas_configs = yaml_configs[-num_shards_replicas_configs:]
    for shard_id in range(shards):
        replicas_configs = shards_replicas_configs[
            shard_id * replicas : shard_id * replicas + replicas
        ]
        for i_replica, (replica_name, replica_config) in enumerate(replicas_configs):
            expected_name = 'executor'
            expected_arg_name = 'executor'
            if shards > 1:
                expected_name += f'-{shard_id}'
                expected_arg_name += f'-{shard_id}'
            if replicas > 1:
                expected_name += f'-rep-{i_replica}'
                expected_arg_name += f'/rep-{i_replica}'
            assert replica_name == expected_name
            assert replica_config['image'] in {
                'docker_image:latest',
                'jinahub/HubExecutor',
                'jinahub/jina-ai/HubExecutor',
            }
            assert replica_config['entrypoint'] == ['jina']
            replica_args = replica_config['command']
            assert replica_args[0] == 'executor'
            assert '--native' in replica_args
            assert '--name' in replica_args
            assert replica_args[replica_args.index('--name') + 1] == expected_arg_name
            assert '--port' in replica_args
            assert replica_args[replica_args.index('--port') + 1] == '8081'
            assert '--env' not in replica_args
            assert '--connection-list' not in replica_args
            if uses_with is not None:
                assert '--uses-with' in replica_args
                assert replica_args[replica_args.index('--uses-with') + 1] == uses_with
            else:
                assert '--uses-with' not in replica_args

            expected_uses_metas = {}
            if uses_metas is not None:
                expected_uses_metas = json.loads(uses_metas)
                assert '--uses-metas' in replica_args
                assert replica_args[
                    replica_args.index('--uses-metas') + 1
                ] == json.dumps(expected_uses_metas)
