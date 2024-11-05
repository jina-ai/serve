"""Base argparser module for Pod and Deployment runtime"""

import argparse
import os

from jina.enums import PollingType
from jina.helper import random_identity
from jina.parsers.helper import _SHOW_ALL_ARGS, add_arg_group


def mixin_essential_parser(parser, default_name=None):
    """Mixing in arguments required by every module into the given parser.
    :param parser: the parser instance to which we add arguments
    :param default_name: default pod name
    """
    gp = add_arg_group(parser, title='Essential')
    gp.add_argument(
        '--name',
        type=str,
        default=default_name,
        help='''
    The name of this object.

    This will be used in the following places:
    - how you refer to this object in Python/YAML/CLI
    - visualization
    - log message header
    - ...

    When not given, then the default naming strategy will apply.
                        ''',
    )

    gp.add_argument(
        '--workspace',
        type=str,
        default=None,
        help='The working directory for any IO operations in this object. '
        'If not set, then derive from its parent `workspace`.',
    )

    gp.add_argument(
        '--log-config',
        type=str,
        default='default',
        help='The config name or the absolute path to the YAML config file of the logger used in this object.',
    )

    gp.add_argument(
        '--quiet',
        action='store_true',
        default=False,
        help='If set, then no log will be emitted from this object.',
    )

    gp.add_argument(
        '--quiet-error',
        action='store_true',
        default=False,
        help='If set, then exception stack information will not be added to the log',
    )

    gp.add_argument(
        '--workspace-id',
        type=str,
        default=random_identity(),
        help=(
            'the UUID for identifying the workspace. When not given a random id will be assigned.'
            'Multiple Pod/Deployment/Flow will work under the same workspace if they share the same '
            '`workspace-id`.'
            if _SHOW_ALL_ARGS
            else argparse.SUPPRESS
        ),
    )


def mixin_base_deployment_parser(parser, title='Base Deployment', default_name=None):
    """Mixing in arguments required by a deployment into the given parser.
    The Deployment doesn't have scalable features like shards, replicas and polling
    :param parser: the parser instance to which we add arguments
    :param title: the title of the create args group
    :param default_name: default pod name
    :return: returns the created arg group
    """

    mixin_essential_parser(parser, default_name=default_name)

    gp = add_arg_group(parser, title=title)

    gp.add_argument(
        '--extra-search-paths',
        type=str,
        default=[],
        nargs='*',
        help=(
            'Extra search paths to be used when loading modules and finding YAML config files.'
            if _SHOW_ALL_ARGS
            else argparse.SUPPRESS
        ),
    )

    gp.add_argument(
        '--timeout-ctrl',
        type=int,
        default=int(os.getenv('JINA_DEFAULT_TIMEOUT_CTRL', '60')),
        help='The timeout in milliseconds of the control request, -1 for waiting forever',
    )

    gp.add_argument(
        '--k8s-namespace',
        type=str,
        help=(
            'Name of the namespace where Kubernetes deployment should be deployed, to be filled by flow name'
            if _SHOW_ALL_ARGS
            else argparse.SUPPRESS
        ),
    )

    return gp


def mixin_scalable_deployment_parser(parser, default_name=None):
    """Mixing in arguments required by a scalable deployment into the given parser.
    The deployment is scalable and can have shards, replicas and polling
    :param parser: the parser instance to which we add arguments
    :param default_name: default pod name
    """
    gp = mixin_base_deployment_parser(
        parser, title='Scalable Deployment', default_name=default_name
    )

    gp.add_argument(
        '--polling',
        type=str,
        default=PollingType.ANY.name,
        help='''
    The polling strategy of the Deployment and its endpoints (when `shards>1`).
    Can be defined for all endpoints of a Deployment or by endpoint.
    Define per Deployment:
    - ANY: only one (whoever is idle) Pod polls the message
    - ALL: all Pods poll the message (like a broadcast)
    Define per Endpoint:
    JSON dict, {endpoint: PollingType}
    {'/custom': 'ALL', '/search': 'ANY', '*': 'ANY'}
    
    ''',
    )

    gp.add_argument(
        '--shards',
        type=int,
        default=1,
        help='The number of shards in the deployment running at the same time. For more details check '
        'https://jina.ai/serve/concepts/flow/create-flow/#complex-flow-topologies',
    )

    gp.add_argument(
        '--replicas',
        type=int,
        default=1,
        help='The number of replicas in the deployment',
    )

    gp.add_argument(
        '--native',
        action='store_true',
        default=False,
        help='If set, only native Executors is allowed, and the Executor is always run inside WorkerRuntime.',
    )
