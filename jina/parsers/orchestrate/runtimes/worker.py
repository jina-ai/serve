"""Argparser module for WorkerRuntime"""

from jina.parsers.helper import KVAppendAction, add_arg_group
from jina.parsers.orchestrate.runtimes.grpc_channel import (
    mixin_grpc_channel_options_parser,
)
from jina.parsers.orchestrate.runtimes.runtime import (
    mixin_base_runtime_parser,
    mixin_raft_parser,
)


def mixin_worker_runtime_parser(parser):
    """Mixing in arguments required by :class:`WorkerRuntime` into the given parser.
    :param parser: the parser instance to which we add arguments
    """

    gp = add_arg_group(parser, title='WorkerRuntime')
    from jina.constants import __default_executor__

    gp.add_argument(
        '--uses',
        type=str,
        default=__default_executor__,
        help='''
        The config of the executor, it could be one of the followings:
        * the string literal of an Executor class name
        * an Executor YAML file (.yml, .yaml, .jaml)
        * a Jina Hub Executor (must start with `jinahub://` or `jinahub+docker://`)
        * a docker image (must start with `docker://`)
        * the string literal of a YAML config (must start with `!` or `jtype: `)
        * the string literal of a JSON config

        When use it under Python, one can use the following values additionally:
        - a Python dict that represents the config
        - a text file stream has `.read()` interface
        ''',
    )
    gp.add_argument(
        '--uses-with',
        action=KVAppendAction,
        metavar='KEY: VALUE',
        nargs='*',
        help='''
    Dictionary of keyword arguments that will override the `with` configuration in `uses`
    ''',
    )
    gp.add_argument(
        '--uses-metas',
        action=KVAppendAction,
        metavar='KEY: VALUE',
        nargs='*',
        help='''
    Dictionary of keyword arguments that will override the `metas` configuration in `uses`
    ''',
    )
    gp.add_argument(
        '--uses-requests',
        action=KVAppendAction,
        metavar='KEY: VALUE',
        nargs='*',
        help='''
        Dictionary of keyword arguments that will override the `requests` configuration in `uses`
        ''',
    )
    gp.add_argument(
        '--uses-dynamic-batching',
        action=KVAppendAction,
        metavar='KEY: VALUE',
        nargs='*',
        help='''
        Dictionary of keyword arguments that will override the `dynamic_batching` configuration in `uses`
        ''',
    )
    gp.add_argument(
        '--py-modules',
        type=str,
        nargs='*',
        metavar='PATH',
        help='''
The customized python modules need to be imported before loading the executor

Note that the recommended way is to only import a single module - a simple python file, if your
executor can be defined in a single file, or an ``__init__.py`` file if you have multiple files,
which should be structured as a python package. For more details, please see the
`Executor cookbook <https://jina.ai/serve/concepts/executor/executor-files/>`__
''',
    )

    gp.add_argument(
        '--output-array-type',
        type=str,
        default=None,
        help='''
The type of array `tensor` and `embedding` will be serialized to.

Supports the same types as `docarray.to_protobuf(.., ndarray_type=...)`, which can be found 
`here <https://docarray.jina.ai/fundamentals/document/serialization/#from-to-protobuf>`.
Defaults to retaining whatever type is returned by the Executor.
''',
    )

    gp.add_argument(
        '--exit-on-exceptions',
        type=str,
        default=[],
        nargs='*',
        help='List of exceptions that will cause the Executor to shut down.',
    )

    gp.add_argument(
        '--no-reduce',
        '--disable-reduce',
        action='store_true',
        default=False,
        help='Disable the built-in reduction mechanism. Set this if the reduction is to be handled by the Executor '
        'itself by operating on a `docs_matrix` or `docs_map`',
    )

    gp.add_argument(
        '--allow-concurrent',
        action='store_true',
        default=False,
        help='Allow concurrent requests to be processed by the Executor. This is only recommended if the Executor is thread-safe.',
    )

    mixin_base_runtime_parser(gp)
    mixin_raft_parser(gp)
    mixin_grpc_channel_options_parser(gp)
