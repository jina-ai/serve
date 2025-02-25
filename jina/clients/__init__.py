"""Module wrapping the Client of Jina."""

import argparse
from typing import TYPE_CHECKING, List, Optional, Union, overload

from jina.helper import parse_client

__all__ = ['Client']

from jina.enums import ProtocolType

if TYPE_CHECKING:  # pragma: no cover
    from jina.clients.grpc import AsyncGRPCClient, GRPCClient
    from jina.clients.http import AsyncHTTPClient, HTTPClient
    from jina.clients.websocket import AsyncWebSocketClient, WebSocketClient


# overload_inject_start_client
@overload
def Client(
    *,
    asyncio: Optional[bool] = False,
    grpc_channel_options: Optional[dict] = None,
    host: Optional[str] = '0.0.0.0',
    log_config: Optional[str] = None,
    metrics: Optional[bool] = False,
    metrics_exporter_host: Optional[str] = None,
    metrics_exporter_port: Optional[int] = None,
    port: Optional[int] = None,
    prefetch: Optional[int] = 1000,
    protocol: Optional[Union[str, List[str]]] = 'GRPC',
    proxy: Optional[bool] = False,
    reuse_session: Optional[bool] = False,
    suppress_root_logging: Optional[bool] = False,
    tls: Optional[bool] = False,
    traces_exporter_host: Optional[str] = None,
    traces_exporter_port: Optional[int] = None,
    tracing: Optional[bool] = False,
    **kwargs
) -> Union[
    'AsyncWebSocketClient',
    'WebSocketClient',
    'AsyncGRPCClient',
    'GRPCClient',
    'HTTPClient',
    'AsyncHTTPClient',
]:
    """Create a Client. Client is how user interact with Flow

    :param asyncio: If set, then the input and output of this Client work in an asynchronous manner.
    :param grpc_channel_options: Dictionary of kwargs arguments that will be passed to the grpc channel as options when creating a channel, example : {'grpc.max_send_message_length': -1}. When max_attempts > 1, the 'grpc.service_config' option will not be applicable.
    :param host: The host of the Gateway, which the client should connect to, by default it is 0.0.0.0.
    :param log_config: The config name or the absolute path to the YAML config file of the logger used in this object.
    :param metrics: If set, the sdk implementation of the OpenTelemetry metrics will be available for default monitoring and custom measurements. Otherwise a no-op implementation will be provided.
    :param metrics_exporter_host: If tracing is enabled, this hostname will be used to configure the metrics exporter agent.
    :param metrics_exporter_port: If tracing is enabled, this port will be used to configure the metrics exporter agent.
    :param port: The port of the Gateway, which the client should connect to.
    :param prefetch: Number of requests fetched from the client before feeding into the first Executor.

              Used to control the speed of data input into a Flow. 0 disables prefetch (1000 requests is the default)
    :param protocol: Communication protocol between server and client.
    :param proxy: If set, respect the http_proxy and https_proxy environment variables. otherwise, it will unset these proxy variables before start. gRPC seems to prefer no proxy
    :param reuse_session: True if HTTPClient should reuse ClientSession. If true, user will be responsible to close it
    :param suppress_root_logging: If set, then no root handlers will be suppressed from logging.
    :param tls: If set, connect to gateway using tls encryption
    :param traces_exporter_host: If tracing is enabled, this hostname will be used to configure the trace exporter agent.
    :param traces_exporter_port: If tracing is enabled, this port will be used to configure the trace exporter agent.
    :param tracing: If set, the sdk implementation of the OpenTelemetry tracer will be available and will be enabled for automatic tracing of requests and customer span creation. Otherwise a no-op implementation will be provided.
    :return: the new Client object

    .. # noqa: DAR202
    .. # noqa: DAR101
    .. # noqa: DAR003
    """
    # overload_inject_end_client


def Client(args: Optional['argparse.Namespace'] = None, **kwargs) -> Union[
    'AsyncWebSocketClient',
    'WebSocketClient',
    'AsyncGRPCClient',
    'GRPCClient',
    'HTTPClient',
    'AsyncHTTPClient',
]:
    # implementation_stub_inject_start_client

    """Convenience function that returns client instance for given protocol.

    EXAMPLE USAGE

    .. code-block:: python

        from jina import Client
        from docarray import Document

        # select protocol from 'grpc', 'http', or 'websocket'; default is 'grpc'
        # select asyncio True of False; default is False
        # select host address to connect to
        c = Client(
            protocol='grpc', asyncio=False, host='grpc://my.awesome.flow:1234'
        )  # returns GRPCClient instance
        c.post(on='/index', inputs=Document(text='hello!'))

    :param asyncio: If set, then the input and output of this Client work in an asynchronous manner.
    :param grpc_channel_options: Dictionary of kwargs arguments that will be passed to the grpc channel as options when creating a channel, example : {'grpc.max_send_message_length': -1}. When max_attempts > 1, the 'grpc.service_config' option will not be applicable.
    :param host: The host of the Gateway, which the client should connect to, by default it is 0.0.0.0.
    :param log_config: The config name or the absolute path to the YAML config file of the logger used in this object.
    :param metrics: If set, the sdk implementation of the OpenTelemetry metrics will be available for default monitoring and custom measurements. Otherwise a no-op implementation will be provided.
    :param metrics_exporter_host: If tracing is enabled, this hostname will be used to configure the metrics exporter agent.
    :param metrics_exporter_port: If tracing is enabled, this port will be used to configure the metrics exporter agent.
    :param port: The port of the Gateway, which the client should connect to.
    :param prefetch: Number of requests fetched from the client before feeding into the first Executor.

              Used to control the speed of data input into a Flow. 0 disables prefetch (1000 requests is the default)
    :param protocol: Communication protocol between server and client.
    :param proxy: If set, respect the http_proxy and https_proxy environment variables. otherwise, it will unset these proxy variables before start. gRPC seems to prefer no proxy
    :param reuse_session: True if HTTPClient should reuse ClientSession. If true, user will be responsible to close it
    :param suppress_root_logging: If set, then no root handlers will be suppressed from logging.
    :param tls: If set, connect to gateway using tls encryption
    :param traces_exporter_host: If tracing is enabled, this hostname will be used to configure the trace exporter agent.
    :param traces_exporter_port: If tracing is enabled, this port will be used to configure the trace exporter agent.
    :param tracing: If set, the sdk implementation of the OpenTelemetry tracer will be available and will be enabled for automatic tracing of requests and customer span creation. Otherwise a no-op implementation will be provided.
    :return: the new Client object

    .. # noqa: DAR102
    .. # noqa: DAR202
    .. # noqa: DAR101
    .. # noqa: DAR003
    """
    # implementation_stub_inject_end_client
    if not (
        args and isinstance(args, argparse.Namespace)
    ):  # we need to parse the kwargs as soon as possible otherwise to get the gateway type
        args = parse_client(kwargs)

    protocol = args.protocol if args else kwargs.get('protocol', ProtocolType.GRPC)
    if isinstance(protocol, str):
        protocol = ProtocolType.from_string(protocol)

    is_async = (args and args.asyncio) or kwargs.get('asyncio', False)

    if protocol == ProtocolType.GRPC:
        if is_async:
            from jina.clients.grpc import AsyncGRPCClient

            return AsyncGRPCClient(args, **kwargs)
        else:
            from jina.clients.grpc import GRPCClient

            return GRPCClient(args, **kwargs)
    elif protocol == ProtocolType.WEBSOCKET:
        if is_async:
            from jina.clients.websocket import AsyncWebSocketClient

            return AsyncWebSocketClient(args, **kwargs)
        else:
            from jina.clients.websocket import WebSocketClient

            return WebSocketClient(args, **kwargs)
    elif protocol == ProtocolType.HTTP:
        if is_async:
            from jina.clients.http import AsyncHTTPClient

            return AsyncHTTPClient(args, **kwargs)
        else:
            from jina.clients.http import HTTPClient

            return HTTPClient(args, **kwargs)
