import argparse
import asyncio
import base64
import copy
import inspect
import json
import multiprocessing
import os
import sys
import threading
import time
import uuid
import warnings
from collections import OrderedDict
from contextlib import ExitStack
from typing import (
    TYPE_CHECKING,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Type,
    Union,
    overload,
)

from rich import print
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)

from jina.clients import Client
from jina.clients.mixin import AsyncPostMixin, HealthCheckMixin, PostMixin, ProfileMixin
from jina.constants import __default_host__, __windows__
from jina.enums import DeploymentRoleType, FlowBuildLevel, FlowInspectType, ProtocolType
from jina.excepts import (
    FlowMissingDeploymentError,
    FlowTopologyError,
    PortAlreadyUsed,
    RuntimeFailToStart,
)
from jina.helper import (
    GATEWAY_NAME,
    ArgNamespace,
    download_mermaid_url,
    is_port_free,
    random_ports,
    send_telemetry_event,
    typename,
)
from jina.importer import ImportExtensions
from jina.jaml import JAMLCompatible
from jina.logging.logger import JinaLogger
from jina.orchestrate.deployments import Deployment
from jina.orchestrate.flow.builder import _hanging_deployments, allowed_levels
from jina.orchestrate.orchestrator import BaseOrchestrator
from jina.parsers import (
    set_client_cli_parser,
    set_deployment_parser,
    set_gateway_parser,
)
from jina.parsers.flow import set_flow_parser

__all__ = ['Flow']
GATEWAY_ARGS_BLACKLIST = ['uses', 'uses_with']
EXECUTOR_ARGS_BLACKLIST = [
    'port',
    'ports',
    'port_monitoring',
    'uses',
    'uses_with',
    'protocol',
    'protocols',
]


class FlowType(type(ExitStack), type(JAMLCompatible)):
    """Type of Flow, metaclass of :class:`BaseFlow`"""

    pass


_regex_port = r'(.*?):([0-9]{1,4}|[1-5][0-9]{4}|6[0-4][0-9]{3}|65[0-4][0-9]{2}|655[0-2][0-9]|6553[0-5])$'

if TYPE_CHECKING:  # pragma: no cover
    from jina.clients.base import BaseClient
    from jina.orchestrate.flow.asyncio import AsyncFlow
    from jina.serve.executors import BaseExecutor

FALLBACK_PARSERS = [
    set_gateway_parser(),
    set_deployment_parser(),
    set_client_cli_parser(),
    set_flow_parser(),
]


class Flow(
    PostMixin,
    ProfileMixin,
    HealthCheckMixin,
    JAMLCompatible,
    BaseOrchestrator,
    metaclass=FlowType,
):
    """Flow is how Jina streamlines and distributes Executors."""

    # overload_inject_start_client_flow
    @overload
    def __init__(
        self,
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
        **kwargs,
    ):
        """Create a Flow. Flow is how Jina streamlines and scales Executors. This overloaded method provides arguments from `jina client` CLI.

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

        .. # noqa: DAR202
        .. # noqa: DAR101
        .. # noqa: DAR003
        """

    # overload_inject_end_client_flow

    # overload_inject_start_gateway_flow
    @overload
    def __init__(
        self,
        *,
        compression: Optional[str] = None,
        cors: Optional[bool] = False,
        deployments_addresses: Optional[str] = '{}',
        deployments_metadata: Optional[str] = '{}',
        deployments_no_reduce: Optional[str] = '[]',
        description: Optional[str] = None,
        docker_kwargs: Optional[dict] = None,
        entrypoint: Optional[str] = None,
        env: Optional[dict] = None,
        expose_endpoints: Optional[str] = None,
        expose_graphql_endpoint: Optional[bool] = False,
        floating: Optional[bool] = False,
        graph_conditions: Optional[str] = '{}',
        graph_description: Optional[str] = '{}',
        grpc_channel_options: Optional[dict] = None,
        grpc_server_options: Optional[dict] = None,
        host: Optional[str] = '0.0.0.0',
        log_config: Optional[str] = None,
        metrics: Optional[bool] = False,
        metrics_exporter_host: Optional[str] = None,
        metrics_exporter_port: Optional[int] = None,
        monitoring: Optional[bool] = False,
        name: Optional[str] = 'gateway',
        no_crud_endpoints: Optional[bool] = False,
        no_debug_endpoints: Optional[bool] = False,
        port: Optional[int] = None,
        port_monitoring: Optional[int] = None,
        prefetch: Optional[int] = 1000,
        protocol: Optional[Union[str, List[str]]] = ['GRPC'],
        provider: Optional[str] = ['NONE'],
        provider_endpoint: Optional[str] = None,
        proxy: Optional[bool] = False,
        py_modules: Optional[List] = None,
        quiet: Optional[bool] = False,
        quiet_error: Optional[bool] = False,
        reload: Optional[bool] = False,
        replicas: Optional[int] = 1,
        retries: Optional[int] = -1,
        runtime_cls: Optional[str] = 'GatewayRuntime',
        ssl_certfile: Optional[str] = None,
        ssl_keyfile: Optional[str] = None,
        stateful: Optional[bool] = False,
        timeout_ctrl: Optional[int] = 60,
        timeout_ready: Optional[int] = 600000,
        timeout_send: Optional[int] = None,
        title: Optional[str] = None,
        traces_exporter_host: Optional[str] = None,
        traces_exporter_port: Optional[int] = None,
        tracing: Optional[bool] = False,
        uses: Optional[Union[str, Type['BaseExecutor'], dict]] = None,
        uses_with: Optional[dict] = None,
        uvicorn_kwargs: Optional[dict] = None,
        workspace: Optional[str] = None,
        **kwargs,
    ):
        """Create a Flow. Flow is how Jina streamlines and scales Executors. This overloaded method provides arguments from `jina gateway` CLI.

        :param compression: The compression mechanism used when sending requests from the Head to the WorkerRuntimes. For more details, check https://grpc.github.io/grpc/python/grpc.html#compression.
        :param cors: If set, a CORS middleware is added to FastAPI frontend to allow cross-origin access.
        :param deployments_addresses: JSON dictionary with the input addresses of each Deployment
        :param deployments_metadata: JSON dictionary with the request metadata for each Deployment
        :param deployments_no_reduce: list JSON disabling the built-in merging mechanism for each Deployment listed
        :param description: The description of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param docker_kwargs: Dictionary of kwargs arguments that will be passed to Docker SDK when starting the docker '
          container.

          More details can be found in the Docker SDK docs:  https://docker-py.readthedocs.io/en/stable/
        :param entrypoint: The entrypoint command overrides the ENTRYPOINT in Docker image. when not set then the Docker image ENTRYPOINT takes effective.
        :param env: The map of environment variables that are available inside runtime
        :param expose_endpoints: A JSON string that represents a map from executor endpoints (`@requests(on=...)`) to HTTP endpoints.
        :param expose_graphql_endpoint: If set, /graphql endpoint is added to HTTP interface.
        :param floating: If set, the current Pod/Deployment can not be further chained, and the next `.add()` will chain after the last Pod/Deployment not this current one.
        :param graph_conditions: Dictionary stating which filtering conditions each Executor in the graph requires to receive Documents.
        :param graph_description: Routing graph for the gateway
        :param grpc_channel_options: Dictionary of kwargs arguments that will be passed to the grpc channel as options when creating a channel, example : {'grpc.max_send_message_length': -1}. When max_attempts > 1, the 'grpc.service_config' option will not be applicable.
        :param grpc_server_options: Dictionary of kwargs arguments that will be passed to the grpc server as options when starting the server, example : {'grpc.max_send_message_length': -1}
        :param host: The host address of the runtime, by default it is 0.0.0.0.
        :param log_config: The config name or the absolute path to the YAML config file of the logger used in this object.
        :param metrics: If set, the sdk implementation of the OpenTelemetry metrics will be available for default monitoring and custom measurements. Otherwise a no-op implementation will be provided.
        :param metrics_exporter_host: If tracing is enabled, this hostname will be used to configure the metrics exporter agent.
        :param metrics_exporter_port: If tracing is enabled, this port will be used to configure the metrics exporter agent.
        :param monitoring: If set, spawn an http server with a prometheus endpoint to expose metrics
        :param name: The name of this object.

              This will be used in the following places:
              - how you refer to this object in Python/YAML/CLI
              - visualization
              - log message header
              - ...

              When not given, then the default naming strategy will apply.
        :param no_crud_endpoints: If set, `/index`, `/search`, `/update`, `/delete` endpoints are removed from HTTP interface.

                  Any executor that has `@requests(on=...)` bound with those values will receive data requests.
        :param no_debug_endpoints: If set, `/status` `/post` endpoints are removed from HTTP interface.
        :param port: The port for input data to bind the gateway server to, by default, random ports between range [49152, 65535] will be assigned. The port argument can be either 1 single value in case only 1 protocol is used or multiple values when many protocols are used.
        :param port_monitoring: The port on which the prometheus server is exposed, default is a random port between [49152, 65535]
        :param prefetch: Number of requests fetched from the client before feeding into the first Executor.

              Used to control the speed of data input into a Flow. 0 disables prefetch (1000 requests is the default)
        :param protocol: Communication protocol of the server exposed by the Gateway. This can be a single value or a list of protocols, depending on your chosen Gateway. Choose the convenient protocols from: ['GRPC', 'HTTP', 'WEBSOCKET'].
        :param provider: If set, Executor is translated to a custom container compatible with the chosen provider. Choose the convenient providers from: ['NONE', 'SAGEMAKER', 'AZURE'].
        :param provider_endpoint: If set, Executor endpoint will be explicitly chosen and used in the custom container operated by the provider.
        :param proxy: If set, respect the http_proxy and https_proxy environment variables. otherwise, it will unset these proxy variables before start. gRPC seems to prefer no proxy
        :param py_modules: The customized python modules need to be imported before loading the gateway

          Note that the recommended way is to only import a single module - a simple python file, if your
          gateway can be defined in a single file, or an ``__init__.py`` file if you have multiple files,
          which should be structured as a python package.
        :param quiet: If set, then no log will be emitted from this object.
        :param quiet_error: If set, then exception stack information will not be added to the log
        :param reload: If set, the Gateway will restart while serving if YAML configuration source is changed.
        :param replicas: The number of replicas of the Gateway. This replicas will only be applied when converted into Kubernetes YAML
        :param retries: Number of retries per gRPC call. If <0 it defaults to max(3, num_replicas)
        :param runtime_cls: The runtime class to run inside the Pod
        :param ssl_certfile: the path to the certificate file
        :param ssl_keyfile: the path to the key file
        :param stateful: If set, start consensus module to make sure write operations are properly replicated between all the replicas
        :param timeout_ctrl: The timeout in milliseconds of the control request, -1 for waiting forever
        :param timeout_ready: The timeout in milliseconds of a Pod waits for the runtime to be ready, -1 for waiting forever
        :param timeout_send: The timeout in milliseconds used when sending data requests to Executors, -1 means no timeout, disabled by default
        :param title: The title of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param traces_exporter_host: If tracing is enabled, this hostname will be used to configure the trace exporter agent.
        :param traces_exporter_port: If tracing is enabled, this port will be used to configure the trace exporter agent.
        :param tracing: If set, the sdk implementation of the OpenTelemetry tracer will be available and will be enabled for automatic tracing of requests and customer span creation. Otherwise a no-op implementation will be provided.
        :param uses: The config of the gateway, it could be one of the followings:
                  * the string literal of an Gateway class name
                  * a Gateway YAML file (.yml, .yaml, .jaml)
                  * a docker image (must start with `docker://`)
                  * the string literal of a YAML config (must start with `!` or `jtype: `)
                  * the string literal of a JSON config

                  When use it under Python, one can use the following values additionally:
                  - a Python dict that represents the config
                  - a text file stream has `.read()` interface
        :param uses_with: Dictionary of keyword arguments that will override the `with` configuration in `uses`
        :param uvicorn_kwargs: Dictionary of kwargs arguments that will be passed to Uvicorn server when starting the server

          More details can be found in Uvicorn docs: https://www.uvicorn.org/settings/
        :param workspace: The working directory for any IO operations in this object. If not set, then derive from its parent `workspace`.

        .. # noqa: DAR202
        .. # noqa: DAR101
        .. # noqa: DAR003
        """

    # overload_inject_end_gateway_flow
    # overload_inject_start_flow
    @overload
    def __init__(
        self,
        *,
        env: Optional[dict] = None,
        inspect: Optional[str] = 'COLLECT',
        log_config: Optional[str] = None,
        name: Optional[str] = None,
        quiet: Optional[bool] = False,
        quiet_error: Optional[bool] = False,
        reload: Optional[bool] = False,
        suppress_root_logging: Optional[bool] = False,
        uses: Optional[str] = None,
        workspace: Optional[str] = None,
        **kwargs,
    ):
        """Create a Flow. Flow is how Jina streamlines and scales Executors. This overloaded method provides arguments from `jina flow` CLI.

        :param env: The map of environment variables that are available inside runtime
        :param inspect: The strategy on those inspect deployments in the flow.

              If `REMOVE` is given then all inspect deployments are removed when building the flow.
        :param log_config: The config name or the absolute path to the YAML config file of the logger used in this object.
        :param name: The name of this object.

              This will be used in the following places:
              - how you refer to this object in Python/YAML/CLI
              - visualization
              - log message header
              - ...

              When not given, then the default naming strategy will apply.
        :param quiet: If set, then no log will be emitted from this object.
        :param quiet_error: If set, then exception stack information will not be added to the log
        :param reload: If set, auto-reloading on file changes is enabled: the Flow will restart while blocked if  YAML configuration source is changed. This also applies apply to underlying Executors, if their source code or YAML configuration has changed.
        :param suppress_root_logging: If set, then no root handlers will be suppressed from logging.
        :param uses: The YAML path represents a flow. It can be either a local file path or a URL.
        :param workspace: The working directory for any IO operations in this object. If not set, then derive from its parent `workspace`.

        .. # noqa: DAR202
        .. # noqa: DAR101
        .. # noqa: DAR003
        """

    # overload_inject_end_flow
    def __init__(
        self,
        args: Optional['argparse.Namespace'] = None,
        **kwargs,
    ):
        # implementation_stub_inject_start_flow

        """Create a Flow. Flow is how Jina streamlines and scales Executors.

        EXAMPLE USAGE

            Python API

            .. code-block:: python

                from jina import Flow

                f = Flow().add(uses='jinahub+docker://SimpleIndexer')  # create Flow and add Executor
                with f:
                    f.bock()  # serve Flow

            To and from YAML configuration

            .. code-block:: python

                from jina import Flow

                f = Flow().add(uses='jinahub+docker://SimpleIndexer')  # create Flow and add Executor
                f.save_config('flow.yml')  # save YAML config file
                f = Flow.load_config('flow.yml')  # load Flow from YAML config
                with f:
                    f.bock()  # serve Flow

        All arguments received by {class}`~jina.Flow()` API will be propagated to other entities (Gateway, Executor) with the following exceptions:

        - `uses` and `uses_with` won't be passed to Gateway
        - `port`, `port_monitoring`, `uses` and `uses_with` won't be passed to Executor

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
        :param compression: The compression mechanism used when sending requests from the Head to the WorkerRuntimes. For more details, check https://grpc.github.io/grpc/python/grpc.html#compression.
        :param cors: If set, a CORS middleware is added to FastAPI frontend to allow cross-origin access.
        :param deployments_addresses: JSON dictionary with the input addresses of each Deployment
        :param deployments_metadata: JSON dictionary with the request metadata for each Deployment
        :param deployments_no_reduce: list JSON disabling the built-in merging mechanism for each Deployment listed
        :param description: The description of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param docker_kwargs: Dictionary of kwargs arguments that will be passed to Docker SDK when starting the docker '
          container.

          More details can be found in the Docker SDK docs:  https://docker-py.readthedocs.io/en/stable/
        :param entrypoint: The entrypoint command overrides the ENTRYPOINT in Docker image. when not set then the Docker image ENTRYPOINT takes effective.
        :param env: The map of environment variables that are available inside runtime
        :param expose_endpoints: A JSON string that represents a map from executor endpoints (`@requests(on=...)`) to HTTP endpoints.
        :param expose_graphql_endpoint: If set, /graphql endpoint is added to HTTP interface.
        :param floating: If set, the current Pod/Deployment can not be further chained, and the next `.add()` will chain after the last Pod/Deployment not this current one.
        :param graph_conditions: Dictionary stating which filtering conditions each Executor in the graph requires to receive Documents.
        :param graph_description: Routing graph for the gateway
        :param grpc_channel_options: Dictionary of kwargs arguments that will be passed to the grpc channel as options when creating a channel, example : {'grpc.max_send_message_length': -1}. When max_attempts > 1, the 'grpc.service_config' option will not be applicable.
        :param grpc_server_options: Dictionary of kwargs arguments that will be passed to the grpc server as options when starting the server, example : {'grpc.max_send_message_length': -1}
        :param host: The host address of the runtime, by default it is 0.0.0.0.
        :param log_config: The config name or the absolute path to the YAML config file of the logger used in this object.
        :param metrics: If set, the sdk implementation of the OpenTelemetry metrics will be available for default monitoring and custom measurements. Otherwise a no-op implementation will be provided.
        :param metrics_exporter_host: If tracing is enabled, this hostname will be used to configure the metrics exporter agent.
        :param metrics_exporter_port: If tracing is enabled, this port will be used to configure the metrics exporter agent.
        :param monitoring: If set, spawn an http server with a prometheus endpoint to expose metrics
        :param name: The name of this object.

              This will be used in the following places:
              - how you refer to this object in Python/YAML/CLI
              - visualization
              - log message header
              - ...

              When not given, then the default naming strategy will apply.
        :param no_crud_endpoints: If set, `/index`, `/search`, `/update`, `/delete` endpoints are removed from HTTP interface.

                  Any executor that has `@requests(on=...)` bound with those values will receive data requests.
        :param no_debug_endpoints: If set, `/status` `/post` endpoints are removed from HTTP interface.
        :param port: The port for input data to bind the gateway server to, by default, random ports between range [49152, 65535] will be assigned. The port argument can be either 1 single value in case only 1 protocol is used or multiple values when many protocols are used.
        :param port_monitoring: The port on which the prometheus server is exposed, default is a random port between [49152, 65535]
        :param prefetch: Number of requests fetched from the client before feeding into the first Executor.

              Used to control the speed of data input into a Flow. 0 disables prefetch (1000 requests is the default)
        :param protocol: Communication protocol of the server exposed by the Gateway. This can be a single value or a list of protocols, depending on your chosen Gateway. Choose the convenient protocols from: ['GRPC', 'HTTP', 'WEBSOCKET'].
        :param provider: If set, Executor is translated to a custom container compatible with the chosen provider. Choose the convenient providers from: ['NONE', 'SAGEMAKER', 'AZURE'].
        :param provider_endpoint: If set, Executor endpoint will be explicitly chosen and used in the custom container operated by the provider.
        :param proxy: If set, respect the http_proxy and https_proxy environment variables. otherwise, it will unset these proxy variables before start. gRPC seems to prefer no proxy
        :param py_modules: The customized python modules need to be imported before loading the gateway

          Note that the recommended way is to only import a single module - a simple python file, if your
          gateway can be defined in a single file, or an ``__init__.py`` file if you have multiple files,
          which should be structured as a python package.
        :param quiet: If set, then no log will be emitted from this object.
        :param quiet_error: If set, then exception stack information will not be added to the log
        :param reload: If set, the Gateway will restart while serving if YAML configuration source is changed.
        :param replicas: The number of replicas of the Gateway. This replicas will only be applied when converted into Kubernetes YAML
        :param retries: Number of retries per gRPC call. If <0 it defaults to max(3, num_replicas)
        :param runtime_cls: The runtime class to run inside the Pod
        :param ssl_certfile: the path to the certificate file
        :param ssl_keyfile: the path to the key file
        :param stateful: If set, start consensus module to make sure write operations are properly replicated between all the replicas
        :param timeout_ctrl: The timeout in milliseconds of the control request, -1 for waiting forever
        :param timeout_ready: The timeout in milliseconds of a Pod waits for the runtime to be ready, -1 for waiting forever
        :param timeout_send: The timeout in milliseconds used when sending data requests to Executors, -1 means no timeout, disabled by default
        :param title: The title of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param traces_exporter_host: If tracing is enabled, this hostname will be used to configure the trace exporter agent.
        :param traces_exporter_port: If tracing is enabled, this port will be used to configure the trace exporter agent.
        :param tracing: If set, the sdk implementation of the OpenTelemetry tracer will be available and will be enabled for automatic tracing of requests and customer span creation. Otherwise a no-op implementation will be provided.
        :param uses: The config of the gateway, it could be one of the followings:
                  * the string literal of an Gateway class name
                  * a Gateway YAML file (.yml, .yaml, .jaml)
                  * a docker image (must start with `docker://`)
                  * the string literal of a YAML config (must start with `!` or `jtype: `)
                  * the string literal of a JSON config

                  When use it under Python, one can use the following values additionally:
                  - a Python dict that represents the config
                  - a text file stream has `.read()` interface
        :param uses_with: Dictionary of keyword arguments that will override the `with` configuration in `uses`
        :param uvicorn_kwargs: Dictionary of kwargs arguments that will be passed to Uvicorn server when starting the server

          More details can be found in Uvicorn docs: https://www.uvicorn.org/settings/
        :param workspace: The working directory for any IO operations in this object. If not set, then derive from its parent `workspace`.
        :param env: The map of environment variables that are available inside runtime
        :param inspect: The strategy on those inspect deployments in the flow.

              If `REMOVE` is given then all inspect deployments are removed when building the flow.
        :param log_config: The config name or the absolute path to the YAML config file of the logger used in this object.
        :param name: The name of this object.

              This will be used in the following places:
              - how you refer to this object in Python/YAML/CLI
              - visualization
              - log message header
              - ...

              When not given, then the default naming strategy will apply.
        :param quiet: If set, then no log will be emitted from this object.
        :param quiet_error: If set, then exception stack information will not be added to the log
        :param reload: If set, auto-reloading on file changes is enabled: the Flow will restart while blocked if  YAML configuration source is changed. This also applies apply to underlying Executors, if their source code or YAML configuration has changed.
        :param suppress_root_logging: If set, then no root handlers will be suppressed from logging.
        :param uses: The YAML path represents a flow. It can be either a local file path or a URL.
        :param workspace: The working directory for any IO operations in this object. If not set, then derive from its parent `workspace`.

        .. # noqa: DAR102
        .. # noqa: DAR202
        .. # noqa: DAR101
        .. # noqa: DAR003
        """
        # implementation_stub_inject_end_flow
        super().__init__()
        self._version = '1'  #: YAML version number, this will be later overridden if YAML config says the other way
        self._deployment_nodes = OrderedDict()  # type: Dict[str, Deployment]
        self._inspect_deployments = {}  # type: Dict[str, str]
        self._endpoints_mapping = {}  # type: Dict[str, Dict]
        self._build_level = FlowBuildLevel.EMPTY
        self._last_changed_deployment = [
            GATEWAY_NAME
        ]  #: default first deployment is gateway, will add when build()
        self._update_args(args, **kwargs)

        if isinstance(self.args, argparse.Namespace):
            self.logger = JinaLogger(
                self.__class__.__name__, **vars(self.args), **self._common_kwargs
            )
        else:
            self.logger = JinaLogger(self.__class__.__name__, **self._common_kwargs)

        self._client = None

    def _update_args(self, args, **kwargs):
        from jina.helper import ArgNamespace
        from jina.parsers.flow import set_flow_parser

        _flow_parser = set_flow_parser()
        if args is None:
            args = ArgNamespace.kwargs2namespace(
                kwargs, _flow_parser, True, fallback_parsers=FALLBACK_PARSERS
            )
        self.args = args
        # common args should be the ones that can not be parsed by _flow_parser
        known_keys = list(vars(args).keys())
        self._common_kwargs = {k: v for k, v in kwargs.items() if k not in known_keys}

        # gateway args inherit from flow args
        self._gateway_kwargs = {
            k: v
            for k, v in self._common_kwargs.items()
            if k not in GATEWAY_ARGS_BLACKLIST
        }

        self._kwargs = ArgNamespace.get_non_defaults_args(
            args, _flow_parser
        )  #: for yaml dump

        if self._common_kwargs.get('asyncio', False) and not isinstance(
            self, AsyncPostMixin
        ):
            from jina.orchestrate.flow.asyncio import AsyncFlow

            self.__class__ = AsyncFlow

    @staticmethod
    def _parse_endpoints(
        op_flow, deployment_name, endpoint, connect_to_last_deployment=False
    ) -> Set:
        # parsing needs
        if isinstance(endpoint, str):
            endpoint = [endpoint]
        elif not endpoint:
            if op_flow._last_changed_deployment and connect_to_last_deployment:
                endpoint = [op_flow._last_deployment]
            else:
                endpoint = []

        if isinstance(endpoint, (list, tuple)):
            for idx, s in enumerate(endpoint):
                if s == deployment_name:
                    raise FlowTopologyError(
                        'the income/output of a deployment can not be itself'
                    )
        else:
            raise ValueError(f'endpoint={endpoint} is not parsable')

        # if an endpoint is being inspected, then replace it with inspected Deployment
        endpoint = set(op_flow._inspect_deployments.get(ep, ep) for ep in endpoint)
        return endpoint

    @property
    def _last_deployment(self):
        """Last deployment


        .. # noqa: DAR401


        .. # noqa: DAR201
        """
        return self._last_changed_deployment[-1]

    @_last_deployment.setter
    def _last_deployment(self, name: str):
        """
        Set a Deployment as the last Deployment in the Flow, useful when modifying the Flow.


        .. # noqa: DAR401
        :param name: the name of the existing Deployment
        """
        if name not in self._deployment_nodes:
            raise FlowMissingDeploymentError(f'{name} can not be found in this Flow')

        if self._last_changed_deployment and name == self._last_deployment:
            pass
        else:
            self._last_changed_deployment.append(name)

        # graph is now changed so we need to
        # reset the build level to the lowest
        self._build_level = FlowBuildLevel.EMPTY

    @allowed_levels([FlowBuildLevel.EMPTY])
    def _add_gateway(
        self,
        needs: Union[str, Set[str]],
        graph_description: Dict[str, List[str]],
        deployments_addresses: Dict[str, List[str]],
        deployments_metadata: Dict[str, Dict[str, str]],
        graph_conditions: Dict[str, Dict],
        deployments_no_reduce: List[str],
        **kwargs,
    ):
        kwargs.update(
            dict(
                name=GATEWAY_NAME,
                ctrl_with_ipc=True,  # otherwise ctrl port would be conflicted
                host=self.host,
                protocol=self.protocol,
                port=self.port,
                deployment_role=DeploymentRoleType.GATEWAY,
                expose_endpoints=json.dumps(self._endpoints_mapping),
                env=self.env,
                log_config=(
                    kwargs.get('log_config')
                    if 'log_config' in kwargs
                    else self.args.log_config
                ),
            )
        )

        kwargs.update(self._gateway_kwargs)
        args = ArgNamespace.kwargs2namespace(kwargs, set_gateway_parser())

        # We need to check later if the port was manually set or randomly
        args.default_port = (
            kwargs.get('port', None) is None and kwargs.get('port_expose', None) is None
        )

        if not args.port:
            args.port = random_ports(len(args.protocol))
        args.noblock_on_start = True
        args.graph_description = json.dumps(graph_description)
        args.graph_conditions = json.dumps(graph_conditions)
        args.deployments_addresses = json.dumps(deployments_addresses)
        args.deployments_metadata = json.dumps(deployments_metadata)
        args.deployments_no_reduce = json.dumps(deployments_no_reduce)
        self._deployment_nodes[GATEWAY_NAME] = Deployment(
            args, needs, include_gateway=False, noblock_on_start=True
        )

    def _get_deployments_metadata(self) -> Dict[str, Dict[str, str]]:
        """Get the metadata of all deployments in the Flow

        :return: a dictionary of deployment name and its metadata
        """
        return {
            name: deployment.grpc_metadata
            for name, deployment in self._deployment_nodes.items()
            if deployment.grpc_metadata
        }

    def _get_deployments_addresses(self) -> Dict[str, List[str]]:
        graph_dict = {}
        for node, deployment in self._deployment_nodes.items():
            if node == GATEWAY_NAME:
                continue
            graph_dict[node] = deployment._get_connection_list_for_flow()
        return graph_dict

    def _get_k8s_deployments_addresses(
        self, k8s_namespace: str
    ) -> Dict[str, List[str]]:
        graph_dict = {}
        from jina.orchestrate.deployments.config.helper import to_compatible_name
        from jina.serve.networking import GrpcConnectionPool

        for node, v in self._deployment_nodes.items():
            if node == GATEWAY_NAME:
                continue

            if v.external:
                deployment_k8s_address = f'{v.host}'
            elif v.head_args:
                deployment_k8s_address = (
                    f'{to_compatible_name(v.head_args.name)}.{k8s_namespace}.svc'
                )
            else:
                deployment_k8s_address = (
                    f'{to_compatible_name(v.name)}.{k8s_namespace}.svc'
                )

            external_port = v.head_port if v.head_port else v.port
            graph_dict[node] = [
                f'{v.protocol.lower()}://{deployment_k8s_address}:{external_port if v.external else GrpcConnectionPool.K8S_PORT}'
            ]

        return graph_dict if graph_dict else None

    def _get_docker_compose_deployments_addresses(self) -> Dict[str, List[str]]:
        graph_dict = {}

        for node, v in self._deployment_nodes.items():
            if node == GATEWAY_NAME:
                continue

            deployment_docker_compose_address = v._docker_compose_address
            graph_dict[node] = deployment_docker_compose_address

        return graph_dict

    def _get_graph_conditions(self) -> Dict[str, Dict]:
        graph_condition = {}
        for node, v in self._deployment_nodes.items():
            if v.args.when is not None:  # condition on input docs
                graph_condition[node] = v.args.when

        return graph_condition

    def _get_disabled_reduce_deployments(self) -> List[str]:
        disabled_deployments = []
        for node, v in self._deployment_nodes.items():
            if v.args.no_reduce:
                disabled_deployments.append(node)

        return disabled_deployments

    def _get_graph_representation(self) -> Dict[str, List[str]]:
        def _add_node(graph, n):
            # in the graph we need to distinguish between start and end gateway, although they are the same deployment
            if n == GATEWAY_NAME:
                n = 'start-gateway'
            if n not in graph:
                graph[n] = []
            return n

        graph_dict = {}
        for node, v in self._deployment_nodes.items():
            node = _add_node(graph_dict, node)
            if node == 'start-gateway':
                continue
            for need in sorted(v.needs):
                need = _add_node(graph_dict, need)
                graph_dict[need].append(node)

        # find all non floating leafs
        last_deployment = self._last_deployment
        if last_deployment != 'gateway':
            graph_dict[last_deployment].append('end-gateway')

        return graph_dict

    @allowed_levels([FlowBuildLevel.EMPTY])
    def needs(
        self, needs: Union[Tuple[str], List[str]], name: str = 'joiner', *args, **kwargs
    ) -> 'Flow':
        """
        Add a blocker to the Flow, wait until all pods defined in **needs** completed.


        .. # noqa: DAR401
        :param needs: list of service names to wait
        :param name: the name of this joiner, by default is ``joiner``
        :param args: additional positional arguments forwarded to the add function
        :param kwargs: additional key value arguments forwarded to the add function
        :return: the modified Flow
        """
        if len(needs) <= 1:
            raise FlowTopologyError(
                'no need to wait for a single service, need len(needs) > 1'
            )
        return self.add(
            name=name,
            needs=needs,
            deployment_role=DeploymentRoleType.JOIN,
            *args,
            **kwargs,
        )

    @allowed_levels([FlowBuildLevel.EMPTY])
    def needs_all(self, name: str = 'joiner', *args, **kwargs) -> 'Flow':
        """
        Collect all floating Deployments so far and add a blocker to the Flow; wait until all handing pods completed.

        :param name: the name of this joiner (default is ``joiner``)
        :param args: additional positional arguments which are forwarded to the add and needs function
        :param kwargs: additional key value arguments which are forwarded to the add and needs function
        :return: the modified Flow
        """
        needs = _hanging_deployments(self)
        if len(needs) == 1:
            return self.add(name=name, needs=needs, *args, **kwargs)

        return self.needs(name=name, needs=needs, *args, **kwargs)

    # overload_inject_start_deployment
    @overload
    def add(
        self,
        *,
        allow_concurrent: Optional[bool] = False,
        compression: Optional[str] = None,
        connection_list: Optional[str] = None,
        cors: Optional[bool] = False,
        description: Optional[str] = None,
        disable_auto_volume: Optional[bool] = False,
        docker_kwargs: Optional[dict] = None,
        entrypoint: Optional[str] = None,
        env: Optional[dict] = None,
        exit_on_exceptions: Optional[List] = [],
        external: Optional[bool] = False,
        floating: Optional[bool] = False,
        force_update: Optional[bool] = False,
        gpus: Optional[str] = None,
        grpc_channel_options: Optional[dict] = None,
        grpc_metadata: Optional[dict] = None,
        grpc_server_options: Optional[dict] = None,
        host: Optional[List] = ['0.0.0.0'],
        install_requirements: Optional[bool] = False,
        log_config: Optional[str] = None,
        metrics: Optional[bool] = False,
        metrics_exporter_host: Optional[str] = None,
        metrics_exporter_port: Optional[int] = None,
        monitoring: Optional[bool] = False,
        name: Optional[str] = 'executor',
        native: Optional[bool] = False,
        no_reduce: Optional[bool] = False,
        output_array_type: Optional[str] = None,
        polling: Optional[str] = 'ANY',
        port: Optional[int] = None,
        port_monitoring: Optional[int] = None,
        prefer_platform: Optional[str] = None,
        protocol: Optional[Union[str, List[str]]] = ['GRPC'],
        provider: Optional[str] = ['NONE'],
        provider_endpoint: Optional[str] = None,
        py_modules: Optional[List] = None,
        quiet: Optional[bool] = False,
        quiet_error: Optional[bool] = False,
        raft_configuration: Optional[dict] = None,
        reload: Optional[bool] = False,
        replicas: Optional[int] = 1,
        retries: Optional[int] = -1,
        runtime_cls: Optional[str] = 'WorkerRuntime',
        shards: Optional[int] = 1,
        ssl_certfile: Optional[str] = None,
        ssl_keyfile: Optional[str] = None,
        stateful: Optional[bool] = False,
        timeout_ctrl: Optional[int] = 60,
        timeout_ready: Optional[int] = 600000,
        timeout_send: Optional[int] = None,
        title: Optional[str] = None,
        tls: Optional[bool] = False,
        traces_exporter_host: Optional[str] = None,
        traces_exporter_port: Optional[int] = None,
        tracing: Optional[bool] = False,
        uses: Optional[Union[str, Type['BaseExecutor'], dict]] = 'BaseExecutor',
        uses_after: Optional[Union[str, Type['BaseExecutor'], dict]] = None,
        uses_after_address: Optional[str] = None,
        uses_before: Optional[Union[str, Type['BaseExecutor'], dict]] = None,
        uses_before_address: Optional[str] = None,
        uses_dynamic_batching: Optional[dict] = None,
        uses_metas: Optional[dict] = None,
        uses_requests: Optional[dict] = None,
        uses_with: Optional[dict] = None,
        uvicorn_kwargs: Optional[dict] = None,
        volumes: Optional[List] = None,
        when: Optional[dict] = None,
        workspace: Optional[str] = None,
        **kwargs,
    ) -> Union['Flow', 'AsyncFlow']:
        """Add an Executor to the current Flow object.

        :param allow_concurrent: Allow concurrent requests to be processed by the Executor. This is only recommended if the Executor is thread-safe.
        :param compression: The compression mechanism used when sending requests from the Head to the WorkerRuntimes. For more details, check https://grpc.github.io/grpc/python/grpc.html#compression.
        :param connection_list: dictionary JSON with a list of connections to configure
        :param cors: If set, a CORS middleware is added to FastAPI frontend to allow cross-origin access.
        :param description: The description of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param disable_auto_volume: Do not automatically mount a volume for dockerized Executors.
        :param docker_kwargs: Dictionary of kwargs arguments that will be passed to Docker SDK when starting the docker '
          container.

          More details can be found in the Docker SDK docs:  https://docker-py.readthedocs.io/en/stable/
        :param entrypoint: The entrypoint command overrides the ENTRYPOINT in Docker image. when not set then the Docker image ENTRYPOINT takes effective.
        :param env: The map of environment variables that are available inside runtime
        :param exit_on_exceptions: List of exceptions that will cause the Executor to shut down.
        :param external: The Deployment will be considered an external Deployment that has been started independently from the Flow.This Deployment will not be context managed by the Flow.
        :param floating: If set, the current Pod/Deployment can not be further chained, and the next `.add()` will chain after the last Pod/Deployment not this current one.
        :param force_update: If set, always pull the latest Hub Executor bundle even it exists on local
        :param gpus: This argument allows dockerized Jina Executors to discover local gpu devices.

              Note,
              - To access all gpus, use `--gpus all`.
              - To access multiple gpus, e.g. make use of 2 gpus, use `--gpus 2`.
              - To access specified gpus based on device id, use `--gpus device=[YOUR-GPU-DEVICE-ID]`
              - To access specified gpus based on multiple device id, use `--gpus device=[YOUR-GPU-DEVICE-ID1],device=[YOUR-GPU-DEVICE-ID2]`
              - To specify more parameters, use `--gpus device=[YOUR-GPU-DEVICE-ID],runtime=nvidia,capabilities=display
        :param grpc_channel_options: Dictionary of kwargs arguments that will be passed to the grpc channel as options when creating a channel, example : {'grpc.max_send_message_length': -1}. When max_attempts > 1, the 'grpc.service_config' option will not be applicable.
        :param grpc_metadata: The metadata to be passed to the gRPC request.
        :param grpc_server_options: Dictionary of kwargs arguments that will be passed to the grpc server as options when starting the server, example : {'grpc.max_send_message_length': -1}
        :param host: The host of the Gateway, which the client should connect to, by default it is 0.0.0.0. In the case of an external Executor (`--external` or `external=True`) this can be a list of hosts.  Then, every resulting address will be considered as one replica of the Executor.
        :param install_requirements: If set, try to install `requirements.txt` from the local Executor if exists in the Executor folder. If using Hub, install `requirements.txt` in the Hub Executor bundle to local.
        :param log_config: The config name or the absolute path to the YAML config file of the logger used in this object.
        :param metrics: If set, the sdk implementation of the OpenTelemetry metrics will be available for default monitoring and custom measurements. Otherwise a no-op implementation will be provided.
        :param metrics_exporter_host: If tracing is enabled, this hostname will be used to configure the metrics exporter agent.
        :param metrics_exporter_port: If tracing is enabled, this port will be used to configure the metrics exporter agent.
        :param monitoring: If set, spawn an http server with a prometheus endpoint to expose metrics
        :param name: The name of this object.

              This will be used in the following places:
              - how you refer to this object in Python/YAML/CLI
              - visualization
              - log message header
              - ...

              When not given, then the default naming strategy will apply.
        :param native: If set, only native Executors is allowed, and the Executor is always run inside WorkerRuntime.
        :param no_reduce: Disable the built-in reduction mechanism. Set this if the reduction is to be handled by the Executor itself by operating on a `docs_matrix` or `docs_map`
        :param output_array_type: The type of array `tensor` and `embedding` will be serialized to.

          Supports the same types as `docarray.to_protobuf(.., ndarray_type=...)`, which can be found
          `here <https://docarray.jina.ai/fundamentals/document/serialization/#from-to-protobuf>`.
          Defaults to retaining whatever type is returned by the Executor.
        :param polling: The polling strategy of the Deployment and its endpoints (when `shards>1`).
              Can be defined for all endpoints of a Deployment or by endpoint.
              Define per Deployment:
              - ANY: only one (whoever is idle) Pod polls the message
              - ALL: all Pods poll the message (like a broadcast)
              Define per Endpoint:
              JSON dict, {endpoint: PollingType}
              {'/custom': 'ALL', '/search': 'ANY', '*': 'ANY'}
        :param port: The port for input data to bind to, default is a random port between [49152, 65535]. In the case of an external Executor (`--external` or `external=True`) this can be a list of ports. Then, every resulting address will be considered as one replica of the Executor.
        :param port_monitoring: The port on which the prometheus server is exposed, default is a random port between [49152, 65535]
        :param prefer_platform: The preferred target Docker platform. (e.g. "linux/amd64", "linux/arm64")
        :param protocol: Communication protocol of the server exposed by the Executor. This can be a single value or a list of protocols, depending on your chosen Gateway. Choose the convenient protocols from: ['GRPC', 'HTTP', 'WEBSOCKET'].
        :param provider: If set, Executor is translated to a custom container compatible with the chosen provider. Choose the convenient providers from: ['NONE', 'SAGEMAKER', 'AZURE'].
        :param provider_endpoint: If set, Executor endpoint will be explicitly chosen and used in the custom container operated by the provider.
        :param py_modules: The customized python modules need to be imported before loading the executor

          Note that the recommended way is to only import a single module - a simple python file, if your
          executor can be defined in a single file, or an ``__init__.py`` file if you have multiple files,
          which should be structured as a python package. For more details, please see the
          `Executor cookbook <https://jina.ai/serve/concepts/executor/executor-files/>`__
        :param quiet: If set, then no log will be emitted from this object.
        :param quiet_error: If set, then exception stack information will not be added to the log
        :param raft_configuration: Dictionary of kwargs arguments that will be passed to the RAFT node as configuration options when starting the RAFT node.
        :param reload: If set, the Executor will restart while serving if YAML configuration source or Executor modules are changed. If YAML configuration is changed, the whole deployment is reloaded and new processes will be restarted. If only Python modules of the Executor have changed, they will be reloaded to the interpreter without restarting process.
        :param replicas: The number of replicas in the deployment
        :param retries: Number of retries per gRPC call. If <0 it defaults to max(3, num_replicas)
        :param runtime_cls: The runtime class to run inside the Pod
        :param shards: The number of shards in the deployment running at the same time. For more details check https://jina.ai/serve/concepts/flow/create-flow/#complex-flow-topologies
        :param ssl_certfile: the path to the certificate file
        :param ssl_keyfile: the path to the key file
        :param stateful: If set, start consensus module to make sure write operations are properly replicated between all the replicas
        :param timeout_ctrl: The timeout in milliseconds of the control request, -1 for waiting forever
        :param timeout_ready: The timeout in milliseconds of a Pod waits for the runtime to be ready, -1 for waiting forever
        :param timeout_send: The timeout in milliseconds used when sending data requests to Executors, -1 means no timeout, disabled by default
        :param title: The title of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param tls: If set, connect to deployment using tls encryption
        :param traces_exporter_host: If tracing is enabled, this hostname will be used to configure the trace exporter agent.
        :param traces_exporter_port: If tracing is enabled, this port will be used to configure the trace exporter agent.
        :param tracing: If set, the sdk implementation of the OpenTelemetry tracer will be available and will be enabled for automatic tracing of requests and customer span creation. Otherwise a no-op implementation will be provided.
        :param uses: The config of the executor, it could be one of the followings:
                  * the string literal of an Executor class name
                  * an Executor YAML file (.yml, .yaml, .jaml)
                  * a Jina Hub Executor (must start with `jinahub://` or `jinahub+docker://`)
                  * a docker image (must start with `docker://`)
                  * the string literal of a YAML config (must start with `!` or `jtype: `)
                  * the string literal of a JSON config

                  When use it under Python, one can use the following values additionally:
                  - a Python dict that represents the config
                  - a text file stream has `.read()` interface
        :param uses_after: The executor attached after the Pods described by --uses, typically used for receiving from all shards, accepted type follows `--uses`. This argument only applies for sharded Deployments (shards > 1).
        :param uses_after_address: The address of the uses-before runtime
        :param uses_before: The executor attached before the Pods described by --uses, typically before sending to all shards, accepted type follows `--uses`. This argument only applies for sharded Deployments (shards > 1).
        :param uses_before_address: The address of the uses-before runtime
        :param uses_dynamic_batching: Dictionary of keyword arguments that will override the `dynamic_batching` configuration in `uses`
        :param uses_metas: Dictionary of keyword arguments that will override the `metas` configuration in `uses`
        :param uses_requests: Dictionary of keyword arguments that will override the `requests` configuration in `uses`
        :param uses_with: Dictionary of keyword arguments that will override the `with` configuration in `uses`
        :param uvicorn_kwargs: Dictionary of kwargs arguments that will be passed to Uvicorn server when starting the server

          More details can be found in Uvicorn docs: https://www.uvicorn.org/settings/
        :param volumes: The path on the host to be mounted inside the container.

          Note,
          - If separated by `:`, then the first part will be considered as the local host path and the second part is the path in the container system.
          - If no split provided, then the basename of that directory will be mounted into container's root path, e.g. `--volumes="/user/test/my-workspace"` will be mounted into `/my-workspace` inside the container.
          - All volumes are mounted with read-write mode.
        :param when: The condition that the documents need to fulfill before reaching the Executor.The condition can be defined in the form of a `DocArray query condition <https://docarray.jina.ai/fundamentals/documentarray/find/#query-by-conditions>`
        :param workspace: The working directory for any IO operations in this object. If not set, then derive from its parent `workspace`.
        :return: a (new) Flow object with modification

        .. # noqa: DAR202
        .. # noqa: DAR101
        .. # noqa: DAR003
        """

    # overload_inject_end_deployment
    @overload
    def add(
        self,
        *,
        needs: Optional[Union[str, Tuple[str], List[str]]] = None,
        copy_flow: bool = True,
        deployment_role: 'DeploymentRoleType' = DeploymentRoleType.DEPLOYMENT,
        **kwargs,
    ) -> Union['Flow', 'AsyncFlow']:
        """
        Add a Deployment to the current Flow object and return the new modified Flow object.
        The attribute of the Deployment can be later changed with :py:meth:`set` or deleted with :py:meth:`remove`

        :param needs: the name of the Deployment(s) that this Deployment receives data from.
                           One can also use 'gateway' to indicate the connection with the gateway.
        :param deployment_role: the role of the Deployment, used for visualization and route planning
        :param copy_flow: when set to true, then always copy the current Flow and do the modification on top of it then return, otherwise, do in-line modification
        :param kwargs: other keyword-value arguments that the Deployment CLI supports
        :return: a (new) Flow object with modification

        .. # noqa: DAR202
        .. # noqa: DAR101
        .. # noqa: DAR003
        .. # noqa: DAR401
        """

    @allowed_levels([FlowBuildLevel.EMPTY])
    def add(
        self,
        deployment: Union[str, Deployment] = None,
        **kwargs,
    ) -> Union['Flow', 'AsyncFlow']:
        # implementation_stub_inject_start_add

        """Add a Deployment to the current Flow object and return the new modified Flow object.
        The attribute of the Deployment can be later changed with :py:meth:`set` or deleted with :py:meth:`remove`

        :param allow_concurrent: Allow concurrent requests to be processed by the Executor. This is only recommended if the Executor is thread-safe.
        :param compression: The compression mechanism used when sending requests from the Head to the WorkerRuntimes. For more details, check https://grpc.github.io/grpc/python/grpc.html#compression.
        :param connection_list: dictionary JSON with a list of connections to configure
        :param cors: If set, a CORS middleware is added to FastAPI frontend to allow cross-origin access.
        :param description: The description of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param disable_auto_volume: Do not automatically mount a volume for dockerized Executors.
        :param docker_kwargs: Dictionary of kwargs arguments that will be passed to Docker SDK when starting the docker '
          container.

          More details can be found in the Docker SDK docs:  https://docker-py.readthedocs.io/en/stable/
        :param entrypoint: The entrypoint command overrides the ENTRYPOINT in Docker image. when not set then the Docker image ENTRYPOINT takes effective.
        :param env: The map of environment variables that are available inside runtime
        :param exit_on_exceptions: List of exceptions that will cause the Executor to shut down.
        :param external: The Deployment will be considered an external Deployment that has been started independently from the Flow.This Deployment will not be context managed by the Flow.
        :param floating: If set, the current Pod/Deployment can not be further chained, and the next `.add()` will chain after the last Pod/Deployment not this current one.
        :param force_update: If set, always pull the latest Hub Executor bundle even it exists on local
        :param gpus: This argument allows dockerized Jina Executors to discover local gpu devices.

              Note,
              - To access all gpus, use `--gpus all`.
              - To access multiple gpus, e.g. make use of 2 gpus, use `--gpus 2`.
              - To access specified gpus based on device id, use `--gpus device=[YOUR-GPU-DEVICE-ID]`
              - To access specified gpus based on multiple device id, use `--gpus device=[YOUR-GPU-DEVICE-ID1],device=[YOUR-GPU-DEVICE-ID2]`
              - To specify more parameters, use `--gpus device=[YOUR-GPU-DEVICE-ID],runtime=nvidia,capabilities=display
        :param grpc_channel_options: Dictionary of kwargs arguments that will be passed to the grpc channel as options when creating a channel, example : {'grpc.max_send_message_length': -1}. When max_attempts > 1, the 'grpc.service_config' option will not be applicable.
        :param grpc_metadata: The metadata to be passed to the gRPC request.
        :param grpc_server_options: Dictionary of kwargs arguments that will be passed to the grpc server as options when starting the server, example : {'grpc.max_send_message_length': -1}
        :param host: The host of the Gateway, which the client should connect to, by default it is 0.0.0.0. In the case of an external Executor (`--external` or `external=True`) this can be a list of hosts.  Then, every resulting address will be considered as one replica of the Executor.
        :param install_requirements: If set, try to install `requirements.txt` from the local Executor if exists in the Executor folder. If using Hub, install `requirements.txt` in the Hub Executor bundle to local.
        :param log_config: The config name or the absolute path to the YAML config file of the logger used in this object.
        :param metrics: If set, the sdk implementation of the OpenTelemetry metrics will be available for default monitoring and custom measurements. Otherwise a no-op implementation will be provided.
        :param metrics_exporter_host: If tracing is enabled, this hostname will be used to configure the metrics exporter agent.
        :param metrics_exporter_port: If tracing is enabled, this port will be used to configure the metrics exporter agent.
        :param monitoring: If set, spawn an http server with a prometheus endpoint to expose metrics
        :param name: The name of this object.

              This will be used in the following places:
              - how you refer to this object in Python/YAML/CLI
              - visualization
              - log message header
              - ...

              When not given, then the default naming strategy will apply.
        :param native: If set, only native Executors is allowed, and the Executor is always run inside WorkerRuntime.
        :param no_reduce: Disable the built-in reduction mechanism. Set this if the reduction is to be handled by the Executor itself by operating on a `docs_matrix` or `docs_map`
        :param output_array_type: The type of array `tensor` and `embedding` will be serialized to.

          Supports the same types as `docarray.to_protobuf(.., ndarray_type=...)`, which can be found
          `here <https://docarray.jina.ai/fundamentals/document/serialization/#from-to-protobuf>`.
          Defaults to retaining whatever type is returned by the Executor.
        :param polling: The polling strategy of the Deployment and its endpoints (when `shards>1`).
              Can be defined for all endpoints of a Deployment or by endpoint.
              Define per Deployment:
              - ANY: only one (whoever is idle) Pod polls the message
              - ALL: all Pods poll the message (like a broadcast)
              Define per Endpoint:
              JSON dict, {endpoint: PollingType}
              {'/custom': 'ALL', '/search': 'ANY', '*': 'ANY'}
        :param port: The port for input data to bind to, default is a random port between [49152, 65535]. In the case of an external Executor (`--external` or `external=True`) this can be a list of ports. Then, every resulting address will be considered as one replica of the Executor.
        :param port_monitoring: The port on which the prometheus server is exposed, default is a random port between [49152, 65535]
        :param prefer_platform: The preferred target Docker platform. (e.g. "linux/amd64", "linux/arm64")
        :param protocol: Communication protocol of the server exposed by the Executor. This can be a single value or a list of protocols, depending on your chosen Gateway. Choose the convenient protocols from: ['GRPC', 'HTTP', 'WEBSOCKET'].
        :param provider: If set, Executor is translated to a custom container compatible with the chosen provider. Choose the convenient providers from: ['NONE', 'SAGEMAKER', 'AZURE'].
        :param provider_endpoint: If set, Executor endpoint will be explicitly chosen and used in the custom container operated by the provider.
        :param py_modules: The customized python modules need to be imported before loading the executor

          Note that the recommended way is to only import a single module - a simple python file, if your
          executor can be defined in a single file, or an ``__init__.py`` file if you have multiple files,
          which should be structured as a python package. For more details, please see the
          `Executor cookbook <https://jina.ai/serve/concepts/executor/executor-files/>`__
        :param quiet: If set, then no log will be emitted from this object.
        :param quiet_error: If set, then exception stack information will not be added to the log
        :param raft_configuration: Dictionary of kwargs arguments that will be passed to the RAFT node as configuration options when starting the RAFT node.
        :param reload: If set, the Executor will restart while serving if YAML configuration source or Executor modules are changed. If YAML configuration is changed, the whole deployment is reloaded and new processes will be restarted. If only Python modules of the Executor have changed, they will be reloaded to the interpreter without restarting process.
        :param replicas: The number of replicas in the deployment
        :param retries: Number of retries per gRPC call. If <0 it defaults to max(3, num_replicas)
        :param runtime_cls: The runtime class to run inside the Pod
        :param shards: The number of shards in the deployment running at the same time. For more details check https://jina.ai/serve/concepts/flow/create-flow/#complex-flow-topologies
        :param ssl_certfile: the path to the certificate file
        :param ssl_keyfile: the path to the key file
        :param stateful: If set, start consensus module to make sure write operations are properly replicated between all the replicas
        :param timeout_ctrl: The timeout in milliseconds of the control request, -1 for waiting forever
        :param timeout_ready: The timeout in milliseconds of a Pod waits for the runtime to be ready, -1 for waiting forever
        :param timeout_send: The timeout in milliseconds used when sending data requests to Executors, -1 means no timeout, disabled by default
        :param title: The title of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param tls: If set, connect to deployment using tls encryption
        :param traces_exporter_host: If tracing is enabled, this hostname will be used to configure the trace exporter agent.
        :param traces_exporter_port: If tracing is enabled, this port will be used to configure the trace exporter agent.
        :param tracing: If set, the sdk implementation of the OpenTelemetry tracer will be available and will be enabled for automatic tracing of requests and customer span creation. Otherwise a no-op implementation will be provided.
        :param uses: The config of the executor, it could be one of the followings:
                  * the string literal of an Executor class name
                  * an Executor YAML file (.yml, .yaml, .jaml)
                  * a Jina Hub Executor (must start with `jinahub://` or `jinahub+docker://`)
                  * a docker image (must start with `docker://`)
                  * the string literal of a YAML config (must start with `!` or `jtype: `)
                  * the string literal of a JSON config

                  When use it under Python, one can use the following values additionally:
                  - a Python dict that represents the config
                  - a text file stream has `.read()` interface
        :param uses_after: The executor attached after the Pods described by --uses, typically used for receiving from all shards, accepted type follows `--uses`. This argument only applies for sharded Deployments (shards > 1).
        :param uses_after_address: The address of the uses-before runtime
        :param uses_before: The executor attached before the Pods described by --uses, typically before sending to all shards, accepted type follows `--uses`. This argument only applies for sharded Deployments (shards > 1).
        :param uses_before_address: The address of the uses-before runtime
        :param uses_dynamic_batching: Dictionary of keyword arguments that will override the `dynamic_batching` configuration in `uses`
        :param uses_metas: Dictionary of keyword arguments that will override the `metas` configuration in `uses`
        :param uses_requests: Dictionary of keyword arguments that will override the `requests` configuration in `uses`
        :param uses_with: Dictionary of keyword arguments that will override the `with` configuration in `uses`
        :param uvicorn_kwargs: Dictionary of kwargs arguments that will be passed to Uvicorn server when starting the server

          More details can be found in Uvicorn docs: https://www.uvicorn.org/settings/
        :param volumes: The path on the host to be mounted inside the container.

          Note,
          - If separated by `:`, then the first part will be considered as the local host path and the second part is the path in the container system.
          - If no split provided, then the basename of that directory will be mounted into container's root path, e.g. `--volumes="/user/test/my-workspace"` will be mounted into `/my-workspace` inside the container.
          - All volumes are mounted with read-write mode.
        :param when: The condition that the documents need to fulfill before reaching the Executor.The condition can be defined in the form of a `DocArray query condition <https://docarray.jina.ai/fundamentals/documentarray/find/#query-by-conditions>`
        :param workspace: The working directory for any IO operations in this object. If not set, then derive from its parent `workspace`.
        :param needs: the name of the Deployment(s) that this Deployment receives data from. One can also use "gateway" to indicate the connection with the gateway.
        :param deployment_role: the role of the Deployment, used for visualization and route planning
        :param copy_flow: when set to true, then always copy the current Flow and do the modification on top of it then return, otherwise, do in-line modification
        :param kwargs: other keyword-value arguments that the Deployment CLI supports
        :return: a (new) Flow object with modification
        :return: a (new) Flow object with modification

        .. # noqa: DAR102
        .. # noqa: DAR202
        .. # noqa: DAR101
        .. # noqa: DAR003
        """
        # implementation_stub_inject_end_add

        needs = kwargs.pop('needs', None)
        copy_flow = kwargs.pop('copy_flow', True)
        deployment_role = kwargs.get('deployment_role', DeploymentRoleType.DEPLOYMENT)

        op_flow = copy.deepcopy(self) if copy_flow else self

        # deployment naming logic
        deployment_name = kwargs.get('name', None)

        if deployment_name in op_flow._deployment_nodes:
            new_name = f'{deployment_name}{len(op_flow._deployment_nodes)}'
            self.logger.debug(
                f'"{deployment_name}" is used in this Flow already! renamed it to "{new_name}"'
            )
            deployment_name = new_name

        if not deployment_name:
            deployment_name = f'executor{len(op_flow._deployment_nodes)}'

        if not deployment_name.isidentifier():
            # hyphen - can not be used in the name
            raise ValueError(
                f'name: {deployment_name} is invalid, please follow the python variable name conventions'
            )

        # needs logic
        needs = op_flow._parse_endpoints(
            op_flow, deployment_name, needs, connect_to_last_deployment=True
        )

        if deployment is None:

            # set the kwargs inherit from `Flow(kwargs1=..., kwargs2=)`
            for key, value in op_flow._common_kwargs.items():

                # do not inherit from all the argument from the flow and respect EXECUTOR_ARGS_BLACKLIST
                if key not in kwargs and key not in EXECUTOR_ARGS_BLACKLIST:
                    kwargs[key] = value

            # update kwargs of this Deployment
            kwargs.update(
                dict(
                    name=deployment_name,
                    deployment_role=deployment_role,
                    log_config=(
                        kwargs.get('log_config')
                        if 'log_config' in kwargs
                        else self.args.log_config
                    ),
                )
            )
            parser = set_deployment_parser()
            if deployment_role == DeploymentRoleType.GATEWAY:
                parser = set_gateway_parser()

            args = ArgNamespace.kwargs2namespace(
                kwargs, parser, True, fallback_parsers=FALLBACK_PARSERS
            )

            # deployment workspace if not set then derive from flow workspace
            if args.workspace:
                args.workspace = os.path.abspath(args.workspace)
            else:
                args.workspace = self.workspace

            args.noblock_on_start = True

            if len(needs) > 1 and args.external and args.no_reduce:
                raise ValueError(
                    'External Executors with multiple needs have to do auto reduce.'
                )
            deployment = Deployment(
                args, needs, include_gateway=False, noblock_on_start=True
            )
            floating = args.floating
        elif isinstance(deployment, str):
            deployment = Deployment.load_config(
                deployment, needs=needs, include_gateway=False, noblock_on_start=True
            )
            floating = deployment.args.floating
        else:
            deployment.needs = needs
            floating = deployment.args.floating

        op_flow._deployment_nodes[deployment_name] = deployment

        if not floating:
            op_flow._last_deployment = deployment_name

        return op_flow

    # overload_inject_start_config_gateway
    @overload
    def config_gateway(
        self,
        *,
        compression: Optional[str] = None,
        cors: Optional[bool] = False,
        deployments_addresses: Optional[str] = '{}',
        deployments_metadata: Optional[str] = '{}',
        deployments_no_reduce: Optional[str] = '[]',
        description: Optional[str] = None,
        docker_kwargs: Optional[dict] = None,
        entrypoint: Optional[str] = None,
        env: Optional[dict] = None,
        expose_endpoints: Optional[str] = None,
        expose_graphql_endpoint: Optional[bool] = False,
        floating: Optional[bool] = False,
        graph_conditions: Optional[str] = '{}',
        graph_description: Optional[str] = '{}',
        grpc_channel_options: Optional[dict] = None,
        grpc_server_options: Optional[dict] = None,
        host: Optional[str] = '0.0.0.0',
        log_config: Optional[str] = None,
        metrics: Optional[bool] = False,
        metrics_exporter_host: Optional[str] = None,
        metrics_exporter_port: Optional[int] = None,
        monitoring: Optional[bool] = False,
        name: Optional[str] = 'gateway',
        no_crud_endpoints: Optional[bool] = False,
        no_debug_endpoints: Optional[bool] = False,
        port: Optional[int] = None,
        port_monitoring: Optional[int] = None,
        prefetch: Optional[int] = 1000,
        protocol: Optional[Union[str, List[str]]] = ['GRPC'],
        provider: Optional[str] = ['NONE'],
        provider_endpoint: Optional[str] = None,
        proxy: Optional[bool] = False,
        py_modules: Optional[List] = None,
        quiet: Optional[bool] = False,
        quiet_error: Optional[bool] = False,
        reload: Optional[bool] = False,
        replicas: Optional[int] = 1,
        retries: Optional[int] = -1,
        runtime_cls: Optional[str] = 'GatewayRuntime',
        ssl_certfile: Optional[str] = None,
        ssl_keyfile: Optional[str] = None,
        stateful: Optional[bool] = False,
        timeout_ctrl: Optional[int] = 60,
        timeout_ready: Optional[int] = 600000,
        timeout_send: Optional[int] = None,
        title: Optional[str] = None,
        traces_exporter_host: Optional[str] = None,
        traces_exporter_port: Optional[int] = None,
        tracing: Optional[bool] = False,
        uses: Optional[Union[str, Type['BaseExecutor'], dict]] = None,
        uses_with: Optional[dict] = None,
        uvicorn_kwargs: Optional[dict] = None,
        workspace: Optional[str] = None,
        **kwargs,
    ):
        """Configure the Gateway inside a Flow. The Gateway exposes your Flow logic as a service to the internet according to the protocol and configuration you choose.

        :param compression: The compression mechanism used when sending requests from the Head to the WorkerRuntimes. For more details, check https://grpc.github.io/grpc/python/grpc.html#compression.
        :param cors: If set, a CORS middleware is added to FastAPI frontend to allow cross-origin access.
        :param deployments_addresses: JSON dictionary with the input addresses of each Deployment
        :param deployments_metadata: JSON dictionary with the request metadata for each Deployment
        :param deployments_no_reduce: list JSON disabling the built-in merging mechanism for each Deployment listed
        :param description: The description of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param docker_kwargs: Dictionary of kwargs arguments that will be passed to Docker SDK when starting the docker '
          container.

          More details can be found in the Docker SDK docs:  https://docker-py.readthedocs.io/en/stable/
        :param entrypoint: The entrypoint command overrides the ENTRYPOINT in Docker image. when not set then the Docker image ENTRYPOINT takes effective.
        :param env: The map of environment variables that are available inside runtime
        :param expose_endpoints: A JSON string that represents a map from executor endpoints (`@requests(on=...)`) to HTTP endpoints.
        :param expose_graphql_endpoint: If set, /graphql endpoint is added to HTTP interface.
        :param floating: If set, the current Pod/Deployment can not be further chained, and the next `.add()` will chain after the last Pod/Deployment not this current one.
        :param graph_conditions: Dictionary stating which filtering conditions each Executor in the graph requires to receive Documents.
        :param graph_description: Routing graph for the gateway
        :param grpc_channel_options: Dictionary of kwargs arguments that will be passed to the grpc channel as options when creating a channel, example : {'grpc.max_send_message_length': -1}. When max_attempts > 1, the 'grpc.service_config' option will not be applicable.
        :param grpc_server_options: Dictionary of kwargs arguments that will be passed to the grpc server as options when starting the server, example : {'grpc.max_send_message_length': -1}
        :param host: The host address of the runtime, by default it is 0.0.0.0.
        :param log_config: The config name or the absolute path to the YAML config file of the logger used in this object.
        :param metrics: If set, the sdk implementation of the OpenTelemetry metrics will be available for default monitoring and custom measurements. Otherwise a no-op implementation will be provided.
        :param metrics_exporter_host: If tracing is enabled, this hostname will be used to configure the metrics exporter agent.
        :param metrics_exporter_port: If tracing is enabled, this port will be used to configure the metrics exporter agent.
        :param monitoring: If set, spawn an http server with a prometheus endpoint to expose metrics
        :param name: The name of this object.

              This will be used in the following places:
              - how you refer to this object in Python/YAML/CLI
              - visualization
              - log message header
              - ...

              When not given, then the default naming strategy will apply.
        :param no_crud_endpoints: If set, `/index`, `/search`, `/update`, `/delete` endpoints are removed from HTTP interface.

                  Any executor that has `@requests(on=...)` bound with those values will receive data requests.
        :param no_debug_endpoints: If set, `/status` `/post` endpoints are removed from HTTP interface.
        :param port: The port for input data to bind the gateway server to, by default, random ports between range [49152, 65535] will be assigned. The port argument can be either 1 single value in case only 1 protocol is used or multiple values when many protocols are used.
        :param port_monitoring: The port on which the prometheus server is exposed, default is a random port between [49152, 65535]
        :param prefetch: Number of requests fetched from the client before feeding into the first Executor.

              Used to control the speed of data input into a Flow. 0 disables prefetch (1000 requests is the default)
        :param protocol: Communication protocol of the server exposed by the Gateway. This can be a single value or a list of protocols, depending on your chosen Gateway. Choose the convenient protocols from: ['GRPC', 'HTTP', 'WEBSOCKET'].
        :param provider: If set, Executor is translated to a custom container compatible with the chosen provider. Choose the convenient providers from: ['NONE', 'SAGEMAKER', 'AZURE'].
        :param provider_endpoint: If set, Executor endpoint will be explicitly chosen and used in the custom container operated by the provider.
        :param proxy: If set, respect the http_proxy and https_proxy environment variables. otherwise, it will unset these proxy variables before start. gRPC seems to prefer no proxy
        :param py_modules: The customized python modules need to be imported before loading the gateway

          Note that the recommended way is to only import a single module - a simple python file, if your
          gateway can be defined in a single file, or an ``__init__.py`` file if you have multiple files,
          which should be structured as a python package.
        :param quiet: If set, then no log will be emitted from this object.
        :param quiet_error: If set, then exception stack information will not be added to the log
        :param reload: If set, the Gateway will restart while serving if YAML configuration source is changed.
        :param replicas: The number of replicas of the Gateway. This replicas will only be applied when converted into Kubernetes YAML
        :param retries: Number of retries per gRPC call. If <0 it defaults to max(3, num_replicas)
        :param runtime_cls: The runtime class to run inside the Pod
        :param ssl_certfile: the path to the certificate file
        :param ssl_keyfile: the path to the key file
        :param stateful: If set, start consensus module to make sure write operations are properly replicated between all the replicas
        :param timeout_ctrl: The timeout in milliseconds of the control request, -1 for waiting forever
        :param timeout_ready: The timeout in milliseconds of a Pod waits for the runtime to be ready, -1 for waiting forever
        :param timeout_send: The timeout in milliseconds used when sending data requests to Executors, -1 means no timeout, disabled by default
        :param title: The title of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param traces_exporter_host: If tracing is enabled, this hostname will be used to configure the trace exporter agent.
        :param traces_exporter_port: If tracing is enabled, this port will be used to configure the trace exporter agent.
        :param tracing: If set, the sdk implementation of the OpenTelemetry tracer will be available and will be enabled for automatic tracing of requests and customer span creation. Otherwise a no-op implementation will be provided.
        :param uses: The config of the gateway, it could be one of the followings:
                  * the string literal of an Gateway class name
                  * a Gateway YAML file (.yml, .yaml, .jaml)
                  * a docker image (must start with `docker://`)
                  * the string literal of a YAML config (must start with `!` or `jtype: `)
                  * the string literal of a JSON config

                  When use it under Python, one can use the following values additionally:
                  - a Python dict that represents the config
                  - a text file stream has `.read()` interface
        :param uses_with: Dictionary of keyword arguments that will override the `with` configuration in `uses`
        :param uvicorn_kwargs: Dictionary of kwargs arguments that will be passed to Uvicorn server when starting the server

          More details can be found in Uvicorn docs: https://www.uvicorn.org/settings/
        :param workspace: The working directory for any IO operations in this object. If not set, then derive from its parent `workspace`.

        .. # noqa: DAR202
        .. # noqa: DAR101
        .. # noqa: DAR003
        """

    # overload_inject_end_config_gateway

    @allowed_levels([FlowBuildLevel.EMPTY])
    def config_gateway(
        self,
        args: Optional['argparse.Namespace'] = None,
        **kwargs,
    ) -> Union['Flow', 'AsyncFlow']:
        # implementation_stub_inject_start_config_gateway

        """Configure the Gateway inside a Flow. The Gateway exposes your Flow logic as a service to the internet according to the protocol and configuration you choose.

        :param compression: The compression mechanism used when sending requests from the Head to the WorkerRuntimes. For more details, check https://grpc.github.io/grpc/python/grpc.html#compression.
        :param cors: If set, a CORS middleware is added to FastAPI frontend to allow cross-origin access.
        :param deployments_addresses: JSON dictionary with the input addresses of each Deployment
        :param deployments_metadata: JSON dictionary with the request metadata for each Deployment
        :param deployments_no_reduce: list JSON disabling the built-in merging mechanism for each Deployment listed
        :param description: The description of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param docker_kwargs: Dictionary of kwargs arguments that will be passed to Docker SDK when starting the docker '
          container.

          More details can be found in the Docker SDK docs:  https://docker-py.readthedocs.io/en/stable/
        :param entrypoint: The entrypoint command overrides the ENTRYPOINT in Docker image. when not set then the Docker image ENTRYPOINT takes effective.
        :param env: The map of environment variables that are available inside runtime
        :param expose_endpoints: A JSON string that represents a map from executor endpoints (`@requests(on=...)`) to HTTP endpoints.
        :param expose_graphql_endpoint: If set, /graphql endpoint is added to HTTP interface.
        :param floating: If set, the current Pod/Deployment can not be further chained, and the next `.add()` will chain after the last Pod/Deployment not this current one.
        :param graph_conditions: Dictionary stating which filtering conditions each Executor in the graph requires to receive Documents.
        :param graph_description: Routing graph for the gateway
        :param grpc_channel_options: Dictionary of kwargs arguments that will be passed to the grpc channel as options when creating a channel, example : {'grpc.max_send_message_length': -1}. When max_attempts > 1, the 'grpc.service_config' option will not be applicable.
        :param grpc_server_options: Dictionary of kwargs arguments that will be passed to the grpc server as options when starting the server, example : {'grpc.max_send_message_length': -1}
        :param host: The host address of the runtime, by default it is 0.0.0.0.
        :param log_config: The config name or the absolute path to the YAML config file of the logger used in this object.
        :param metrics: If set, the sdk implementation of the OpenTelemetry metrics will be available for default monitoring and custom measurements. Otherwise a no-op implementation will be provided.
        :param metrics_exporter_host: If tracing is enabled, this hostname will be used to configure the metrics exporter agent.
        :param metrics_exporter_port: If tracing is enabled, this port will be used to configure the metrics exporter agent.
        :param monitoring: If set, spawn an http server with a prometheus endpoint to expose metrics
        :param name: The name of this object.

              This will be used in the following places:
              - how you refer to this object in Python/YAML/CLI
              - visualization
              - log message header
              - ...

              When not given, then the default naming strategy will apply.
        :param no_crud_endpoints: If set, `/index`, `/search`, `/update`, `/delete` endpoints are removed from HTTP interface.

                  Any executor that has `@requests(on=...)` bound with those values will receive data requests.
        :param no_debug_endpoints: If set, `/status` `/post` endpoints are removed from HTTP interface.
        :param port: The port for input data to bind the gateway server to, by default, random ports between range [49152, 65535] will be assigned. The port argument can be either 1 single value in case only 1 protocol is used or multiple values when many protocols are used.
        :param port_monitoring: The port on which the prometheus server is exposed, default is a random port between [49152, 65535]
        :param prefetch: Number of requests fetched from the client before feeding into the first Executor.

              Used to control the speed of data input into a Flow. 0 disables prefetch (1000 requests is the default)
        :param protocol: Communication protocol of the server exposed by the Gateway. This can be a single value or a list of protocols, depending on your chosen Gateway. Choose the convenient protocols from: ['GRPC', 'HTTP', 'WEBSOCKET'].
        :param provider: If set, Executor is translated to a custom container compatible with the chosen provider. Choose the convenient providers from: ['NONE', 'SAGEMAKER', 'AZURE'].
        :param provider_endpoint: If set, Executor endpoint will be explicitly chosen and used in the custom container operated by the provider.
        :param proxy: If set, respect the http_proxy and https_proxy environment variables. otherwise, it will unset these proxy variables before start. gRPC seems to prefer no proxy
        :param py_modules: The customized python modules need to be imported before loading the gateway

          Note that the recommended way is to only import a single module - a simple python file, if your
          gateway can be defined in a single file, or an ``__init__.py`` file if you have multiple files,
          which should be structured as a python package.
        :param quiet: If set, then no log will be emitted from this object.
        :param quiet_error: If set, then exception stack information will not be added to the log
        :param reload: If set, the Gateway will restart while serving if YAML configuration source is changed.
        :param replicas: The number of replicas of the Gateway. This replicas will only be applied when converted into Kubernetes YAML
        :param retries: Number of retries per gRPC call. If <0 it defaults to max(3, num_replicas)
        :param runtime_cls: The runtime class to run inside the Pod
        :param ssl_certfile: the path to the certificate file
        :param ssl_keyfile: the path to the key file
        :param stateful: If set, start consensus module to make sure write operations are properly replicated between all the replicas
        :param timeout_ctrl: The timeout in milliseconds of the control request, -1 for waiting forever
        :param timeout_ready: The timeout in milliseconds of a Pod waits for the runtime to be ready, -1 for waiting forever
        :param timeout_send: The timeout in milliseconds used when sending data requests to Executors, -1 means no timeout, disabled by default
        :param title: The title of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param traces_exporter_host: If tracing is enabled, this hostname will be used to configure the trace exporter agent.
        :param traces_exporter_port: If tracing is enabled, this port will be used to configure the trace exporter agent.
        :param tracing: If set, the sdk implementation of the OpenTelemetry tracer will be available and will be enabled for automatic tracing of requests and customer span creation. Otherwise a no-op implementation will be provided.
        :param uses: The config of the gateway, it could be one of the followings:
                  * the string literal of an Gateway class name
                  * a Gateway YAML file (.yml, .yaml, .jaml)
                  * a docker image (must start with `docker://`)
                  * the string literal of a YAML config (must start with `!` or `jtype: `)
                  * the string literal of a JSON config

                  When use it under Python, one can use the following values additionally:
                  - a Python dict that represents the config
                  - a text file stream has `.read()` interface
        :param uses_with: Dictionary of keyword arguments that will override the `with` configuration in `uses`
        :param uvicorn_kwargs: Dictionary of kwargs arguments that will be passed to Uvicorn server when starting the server

          More details can be found in Uvicorn docs: https://www.uvicorn.org/settings/
        :param workspace: The working directory for any IO operations in this object. If not set, then derive from its parent `workspace`.
        :return: the new Flow object

        .. # noqa: DAR102
        .. # noqa: DAR202
        .. # noqa: DAR101
        .. # noqa: DAR003
        """
        # implementation_stub_inject_end_config_gateway

        copy_flow = kwargs.pop('copy_flow', True)

        op_flow = copy.deepcopy(self) if copy_flow else self

        # override gateway args inherited from Flow API
        for key, value in kwargs.items():
            op_flow._gateway_kwargs[key] = value

        return op_flow

    @allowed_levels([FlowBuildLevel.EMPTY])
    def inspect(self, name: str = 'inspect', *args, **kwargs) -> 'Flow':
        """Add an inspection on the last changed Deployment in the Flow

        Internally, it adds two Deployments to the Flow. But don't worry, the overhead is minimized and you
        can remove them by simply using `Flow(inspect=FlowInspectType.REMOVE)` before using the Flow.

        .. highlight:: bash
        .. code-block:: bash

            Flow -- PUB-SUB -- Deployment(_pass) -- Flow
                    |
                    -- PUB-SUB -- InspectDeployment (Hanging)

        In this way, :class:`InspectDeployment` looks like a simple ``_pass`` from outside and
        does not introduce side-effects (e.g. changing the socket type) to the original Flow.
        The original incoming and outgoing socket types are preserved.

        This function is very handy for introducing an Evaluator into the Flow.

        .. seealso::

            :meth:`gather_inspect`

        :param name: name of the Deployment
        :param args: args for .add()
        :param kwargs: kwargs for .add()
        :return: the new instance of the Flow
        """
        _last_deployment = self._last_deployment
        op_flow = self.add(
            name=name,
            needs=_last_deployment,
            deployment_role=DeploymentRoleType.INSPECT,
            *args,
            **kwargs,
        )

        # now remove uses and add an auxiliary Deployment
        if 'uses' in kwargs:
            kwargs.pop('uses')
        op_flow = op_flow.add(
            name=f'_aux_{name}',
            needs=_last_deployment,
            deployment_role=DeploymentRoleType.INSPECT_AUX_PASS,
            *args,
            **kwargs,
        )

        # register any future connection to _last_deployment by the auxiliary Deployment
        op_flow._inspect_deployments[_last_deployment] = op_flow._last_deployment

        return op_flow

    @allowed_levels([FlowBuildLevel.EMPTY])
    def gather_inspect(
        self,
        name: str = 'gather_inspect',
        include_last_deployment: bool = True,
        *args,
        **kwargs,
    ) -> 'Flow':
        """Gather all inspect Deployments output into one Deployment. When the Flow has no inspect Deployment then the Flow itself
        is returned.

        .. note::

            If ``--no-inspect`` is **not** given, then :meth:`gather_inspect` is auto called before :meth:`build`. So
            in general you don't need to manually call :meth:`gather_inspect`.

        :param name: the name of the gather Deployment
        :param include_last_deployment: if to include the last modified Deployment in the Flow
        :param args: args for .add()
        :param kwargs: kwargs for .add()
        :return: the modified Flow or the copy of it


        .. seealso::

            :meth:`inspect`

        """
        needs = [
            k
            for k, v in self._deployment_nodes.items()
            if v.role == DeploymentRoleType.INSPECT
        ]
        if needs:
            if include_last_deployment:
                needs.append(self._last_deployment)
            return self.add(
                name=name,
                needs=needs,
                deployment_role=DeploymentRoleType.JOIN_INSPECT,
                *args,
                **kwargs,
            )
        else:
            # no inspect node is in the graph, return the current graph
            return self

    def _get_gateway_target(self, prefix):
        gateway_deployment = self._deployment_nodes[GATEWAY_NAME]
        return (
            f'{prefix}-{GATEWAY_NAME}',
            {
                'host': gateway_deployment.head_host,
                'port': gateway_deployment.head_port,
                'expected_parts': 0,
            },
        )

    @allowed_levels([FlowBuildLevel.EMPTY])
    def build(self, copy_flow: bool = False, **kwargs) -> 'Flow':
        """
        Build the current Flow and make it ready to use

        .. note::

            No need to manually call it since 0.0.8. When using Flow with the
            context manager, or using :meth:`start`, :meth:`build` will be invoked.

        :param copy_flow: when set to true, then always copy the current Flow and do the modification on top of it then return, otherwise, do in-line modification
        :param kwargs: kwargs for backward compatibility
        :return: the current Flow (by default)

        .. note::
            ``copy_flow=True`` is recommended if you are building the same Flow multiple times in a row. e.g.

            .. highlight:: python
            .. code-block:: python

                f = Flow()
                with f:
                    f.index()

                with f.build(copy_flow=True) as fl:
                    fl.search()


        .. # noqa: DAR401
        """
        if multiprocessing.get_start_method().lower() == 'fork':
            os.environ['GRPC_ENABLE_FORK_SUPPORT'] = '1'

        op_flow = copy.deepcopy(self) if copy_flow else self

        if op_flow.args.inspect == FlowInspectType.COLLECT:
            op_flow.gather_inspect(copy_flow=False)

        if GATEWAY_NAME not in op_flow._deployment_nodes:
            op_flow._add_gateway(
                needs={op_flow._last_deployment},
                graph_description=op_flow._get_graph_representation(),
                deployments_addresses=op_flow._get_deployments_addresses(),
                deployments_metadata=op_flow._get_deployments_metadata(),
                graph_conditions=op_flow._get_graph_conditions(),
                deployments_no_reduce=op_flow._get_disabled_reduce_deployments(),
                uses=op_flow.gateway_args.uses,
            )

        removed_deployments = []

        # if set no_inspect then all inspect related nodes are removed
        if op_flow.args.inspect == FlowInspectType.REMOVE:
            filtered_deployment_nodes = OrderedDict()
            for k, v in op_flow._deployment_nodes.items():
                if not v.role.is_inspect:
                    filtered_deployment_nodes[k] = v
                else:
                    removed_deployments.append(v.name)

            op_flow._deployment_nodes = filtered_deployment_nodes
            reverse_inspect_map = {
                v: k for k, v in op_flow._inspect_deployments.items()
            }
            while (
                len(op_flow._last_changed_deployment) > 0
                and len(removed_deployments) > 0
                and op_flow._last_deployment in removed_deployments
            ):
                op_flow._last_changed_deployment.pop()

        for end, deployment in op_flow._deployment_nodes.items():
            # if an endpoint is being inspected, then replace it with inspected Deployment
            # but not those inspect related node
            if op_flow.args.inspect.is_keep:
                deployment.needs = set(
                    (
                        ep
                        if deployment.role.is_inspect
                        else op_flow._inspect_deployments.get(ep, ep)
                    )
                    for ep in deployment.needs
                )
            else:
                deployment.needs = set(
                    reverse_inspect_map.get(ep, ep) for ep in deployment.needs
                )

        hanging_deployments = _hanging_deployments(op_flow)
        if hanging_deployments:
            op_flow.logger.warning(
                f'{hanging_deployments} are "floating" in this flow with no deployment receiving from them, '
                f'you may want to double check if it is intentional or some mistake'
            )
        op_flow._build_level = FlowBuildLevel.GRAPH
        if len(removed_deployments) > 0:
            # very dirty
            op_flow._deployment_nodes[GATEWAY_NAME].args.graph_description = json.dumps(
                op_flow._get_graph_representation()
            )
            op_flow._deployment_nodes[GATEWAY_NAME].args.deployments_addresses = (
                json.dumps(op_flow._get_deployments_addresses())
            )

            op_flow._deployment_nodes[GATEWAY_NAME].update_pod_args()
        return op_flow

    def __call__(self, *args, **kwargs):
        """Builds the Flow
        :param args: args for build
        :param kwargs: kwargs for build
        :return: the built Flow
        """
        return self.build(*args, **kwargs)

    def __exit__(self, exc_type, exc_val, exc_tb):
        super().__exit__(exc_type, exc_val, exc_tb)
        if self._client:
            self._client.teardown_instrumentation()
            self._client = None

        # unset all envs to avoid any side-effect
        if self.args.env:
            for k in self.args.env.keys():
                os.environ.pop(k, None)

        # do not know why but removing these 2 lines make 2 tests fail
        if GATEWAY_NAME in self._deployment_nodes:
            self._deployment_nodes.pop(GATEWAY_NAME)

        self._build_level = FlowBuildLevel.EMPTY

        self._stop_time = time.time()
        send_telemetry_event(
            event='stop',
            obj_cls_name=self.__class__.__name__,
            entity_id=self._entity_id,
            duration=self._stop_time - self._start_time,
            exc_type=str(exc_type),
        )
        self.logger.debug('flow is closed!')
        self.logger.close()

    @allowed_levels([FlowBuildLevel.EMPTY, FlowBuildLevel.GRAPH])
    def start(self):
        """Start to run all Deployments in this Flow.

        Remember to close the Flow with :meth:`close`.

        Note that this method has a timeout of ``timeout_ready`` set in CLI,
        which is inherited all the way from :class:`jina.orchestrate.pods.Pod`


        .. # noqa: DAR401

        :return: this instance
        """
        self._start_time = time.time()
        if self._build_level.value < FlowBuildLevel.GRAPH.value:
            self.build(copy_flow=False)

        port_gateway = self._deployment_nodes[GATEWAY_NAME].args.port
        host_gateway = self._deployment_nodes[GATEWAY_NAME].args.host

        if not (
            is_port_free(host_gateway, port_gateway)
        ):  # we check if the port is not used at parsing time as well for robustness
            raise PortAlreadyUsed(f'port:{port_gateway}')

        # set env only before the Deployment get started
        if self.args.env:
            for k, v in self.args.env.items():
                os.environ[k] = str(v)

        for depl_name, deployment in self:
            if not deployment.external:
                self.enter_context(deployment)

        self._wait_until_all_ready()

        self._build_level = FlowBuildLevel.RUNNING

        send_telemetry_event(
            event='start',
            obj_cls_name=self.__class__.__name__,
            entity_id=self._entity_id,
        )

        return self

    def _wait_until_all_ready(self):
        import warnings

        with warnings.catch_warnings():

            results = {}
            results_lock = threading.Lock()

            async def _async_wait_ready(_deployment_name, _deployment):
                try:
                    if not _deployment.external:
                        with results_lock:
                            results[_deployment_name] = 'pending'
                        await _deployment.async_wait_start_success()
                        with results_lock:
                            results[_deployment_name] = 'done'
                except Exception as ex:
                    results[_deployment_name] = repr(ex)
                    raise ex

            def _wait_ready(_deployment_name, _deployment):
                try:
                    if not _deployment.external:
                        with results_lock:
                            results[_deployment_name] = 'pending'
                        _deployment.wait_start_success()
                        with results_lock:
                            results[_deployment_name] = 'done'
                except Exception as ex:
                    with results_lock:
                        results[_deployment_name] = repr(ex)

            def _polling_status(num_tasks_to_wait):
                progress = Progress(
                    SpinnerColumn(),
                    TextColumn(
                        'Waiting [b]{task.fields[pending_str]}[/]...', justify='right'
                    ),
                    BarColumn(),
                    MofNCompleteColumn(),
                    TimeElapsedColumn(),
                    transient=True,
                )
                with progress:
                    task = progress.add_task(
                        'wait', total=num_tasks_to_wait, pending_str='', start=False
                    )
                    with results_lock:
                        progress.update(task, total=len(results))
                    progress.start_task(task)

                    while True:
                        num_done = 0
                        pendings = []
                        one_failing = False
                        with results_lock:
                            for _k, _v in results.items():
                                sys.stdout.flush()
                                if _v == 'pending':
                                    pendings.append(_k)
                                elif _v == 'done':
                                    num_done += 1
                                else:
                                    one_failing = True
                                    if 'JINA_EARLY_STOP' in os.environ:
                                        self.logger.error(
                                            f'Flow is aborted due to {_k} {_v}.'
                                        )
                                        os._exit(1)
                                    else:
                                        break

                        if one_failing:
                            break

                        pending_str = ' '.join(pendings)

                        progress.update(
                            task, completed=num_done, pending_str=pending_str
                        )

                        if not pendings:
                            break
                        time.sleep(0.1)

            wait_for_ready_coros = []
            for k, v in self:
                wait_for_ready_coros.append(_async_wait_ready(k, v))

            async def _async_wait_all():
                wrapped_tasks = [
                    asyncio.create_task(coro) for coro in wait_for_ready_coros
                ]
                done, pending = await asyncio.wait(
                    wrapped_tasks, return_when=asyncio.FIRST_EXCEPTION
                )
                try:
                    for task in done:
                        try:
                            task.result()  # This raises an exception if the task had an exception
                        except Exception as e:
                            self.logger.error(f"An exception occurred: {str(e)}")
                finally:
                    for task in pending:
                        task.cancel()

            if 'GITHUB_WORKFLOW' not in os.environ:
                # kick off spinner thread
                polling_status_thread = threading.Thread(
                    target=_polling_status,
                    args=(len(wait_for_ready_coros),),
                    daemon=True,
                )

                polling_status_thread.start()

            # kick off all deployments wait-ready tasks
            try:
                _ = asyncio.get_event_loop()
            except:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            async def _f():
                pass

            running_in_event_loop = False
            try:
                asyncio.get_event_loop().run_until_complete(_f())
            except:
                running_in_event_loop = True

            wait_ready_threads = []
            if not running_in_event_loop:
                asyncio.get_event_loop().run_until_complete(_async_wait_all())
            else:
                for k, v in self:
                    wait_ready_threads.append(
                        threading.Thread(target=_wait_ready, args=(k, v), daemon=True)
                    )
                for t in wait_ready_threads:
                    t.start()

            if 'GITHUB_WORKFLOW' not in os.environ:
                polling_status_thread.join()
            for t in wait_ready_threads:
                t.join()

            error_deployments = [k for k, v in results.items() if v != 'done']
            if error_deployments:
                self.logger.error(
                    f'Flow is aborted due to {error_deployments} can not be started.'
                )
                self.close()
                raise RuntimeFailToStart
            from rich.rule import Rule

            all_panels = []
            self._get_summary_table(all_panels)

            print(
                Rule(':tada: Flow is ready to serve!'), *all_panels
            )  # can't use logger here see : https://github.com/Textualize/rich/discussions/2024
            self.logger.debug(
                f'{self.num_deployments} Deployments (i.e. {self.num_pods} Pods) are running in this Flow'
            )

            if 'JINA_HIDE_SURVEY' not in os.environ:
                print(
                    'Do you love open source? Help us improve [link=https://github.com/jina-ai/jina]Jina[/link] in just 1 minute and 30 seconds by taking our survey: https://10sw1tcpld4.typeform.com/jinasurveyfeb23?utm_source=jina '
                    '(Set environment variable JINA_HIDE_SURVEY=1 to hide this message.)'
                )

    @property
    def num_deployments(self) -> int:
        """Get the number of Deployments in this Flow


        .. # noqa: DAR201"""
        return len(self._deployment_nodes)

    @property
    def num_pods(self) -> int:
        """Get the number of pods (shards count) in this Flow


        .. # noqa: DAR201"""
        return sum(v.num_pods for v in self._deployment_nodes.values())

    def __eq__(self, other: 'Flow') -> bool:
        """
        Compare the topology of a Flow with another Flow.
        Identification is defined by whether two flows share the same set of edges.

        :param other: the second Flow object
        :return: result of equality check
        """

        if self._build_level.value < FlowBuildLevel.GRAPH.value:
            op_flow = copy.deepcopy(self)
            a = op_flow.build()
        else:
            a = self

        if other._build_level.value < FlowBuildLevel.GRAPH.value:
            op_flow_b = copy.deepcopy(other)
            b = op_flow_b.build()
        else:
            b = other

        return a._deployment_nodes == b._deployment_nodes

    @property
    def client(self) -> 'BaseClient':
        """Return a :class:`BaseClient` object attach to this Flow.

        .. # noqa: DAR201"""

        if not self._client:
            kwargs = dict(
                host=self.host,
                port=self.port,
                protocol=self.protocol,
                log_config=self.args.log_config,
            )
            kwargs.update(self._gateway_kwargs)
            self._client = Client(**kwargs)

        return self._client

    @property
    def _mermaid_str(self):
        mermaid_graph = [
            '''
            %%{init:{
  "theme": "base",
  "themeVariables": {
      "primaryColor": "#fff",
      "primaryBorderColor": "#fff",
      "mainBkg": "#32C8CD",
      "clusterBkg": "#EEEDE78C",
      "secondaryBorderColor": "none",
      "tertiaryBorderColor": "none",
      "lineColor": "#a6d8da"
      }
}}%%'''.replace(
                '\n', ''
            ),
            'flowchart LR;',
        ]

        deployment_nodes = []

        # plot subgraphs
        for node, v in self._deployment_nodes.items():
            deployment_nodes.append(v.name)
            deployment_mermaid = v._mermaid_str
            mermaid_graph.extend(deployment_mermaid)

        for node, v in self._deployment_nodes.items():
            for need in sorted(v.needs):
                need_print = need
                if need == 'gateway':
                    need_print = 'gatewaystart[gateway]'
                node_print = node
                if node == 'gateway':
                    node_print = 'gatewayend[gateway]'

                _s_role = self._deployment_nodes[need].role
                _e_role = self._deployment_nodes[node].role
                if self._deployment_nodes[need].external:
                    _s_role = 'EXTERNAL'
                if self._deployment_nodes[node].external:
                    _e_role = 'EXTERNAL'
                line_st = '-->'
                if (
                    _s_role == DeploymentRoleType.INSPECT
                    or _e_role == DeploymentRoleType.INSPECT
                ):
                    line_st = '-.->'
                mermaid_graph.append(
                    f'{need_print}:::{str(_s_role)} {line_st} {node_print}:::{str(_e_role)};'
                )

        mermaid_graph.append(
            f'classDef {str(DeploymentRoleType.INSPECT)} stroke:#F29C9F'
        )

        mermaid_graph.append(
            f'classDef {str(DeploymentRoleType.JOIN_INSPECT)} stroke:#F29C9F'
        )
        mermaid_graph.append(
            f'classDef {str(DeploymentRoleType.GATEWAY)} fill:none,color:#000,stroke:none'
        )
        mermaid_graph.append(
            f'classDef {str(DeploymentRoleType.INSPECT_AUX_PASS)} stroke-dasharray: 2 2'
        )
        mermaid_graph.append(f'classDef HEADTAIL fill:#32C8CD1D')

        mermaid_graph.append(f'\nclassDef EXTERNAL fill:#fff,stroke:#32C8CD')

        return '\n'.join(mermaid_graph)

    def plot(
        self,
        output: Optional[str] = None,
        vertical_layout: bool = False,
        inline_display: bool = False,
        build: bool = True,
        copy_flow: bool = True,
    ) -> 'Flow':
        """
        Visualize the Flow up to the current point
        If a file name is provided it will create a jpg image with that name,
        otherwise it will display the URL for mermaid.
        If called within IPython notebook, it will be rendered inline,
        otherwise an image will be created.

        Example,

        .. highlight:: python
        .. code-block:: python

            flow = Flow().add(name='deployment_a').plot('flow.svg')

        :param output: a filename specifying the name of the image to be created,
                    the suffix svg/jpg determines the file type of the output image
        :param vertical_layout: top-down or left-right layout
        :param inline_display: show image directly inside the Jupyter Notebook
        :param build: build the Flow first before plotting, gateway connection can be better showed
        :param copy_flow: when set to true, then always copy the current Flow and
                do the modification on top of it then return, otherwise, do in-line modification
        :return: the Flow
        """

        # deepcopy causes the below error while reusing a Flow in Jupyter
        # 'Pickling an AuthenticationString object is disallowed for security reasons'
        # no need to deep copy if the Graph is built because no change will be made to the Flow
        op_flow = (
            copy.deepcopy(self)
            if (copy_flow and self._build_level.value == FlowBuildLevel.EMPTY)
            else self
        )

        if build and op_flow._build_level.value == FlowBuildLevel.EMPTY:
            op_flow.build(copy_flow=False)

        mermaid_str = op_flow._mermaid_str
        if vertical_layout:
            mermaid_str = mermaid_str.replace('flowchart LR', 'flowchart TD')

        image_type = 'svg'
        if output and not output.endswith('svg'):
            image_type = 'img'

        url = op_flow._mermaid_to_url(mermaid_str, image_type)
        showed = False
        if inline_display:
            try:
                from IPython.display import Image, display

                display(Image(url=url))
                showed = True
            except:
                # no need to panic users
                pass

        if output:
            download_mermaid_url(url, output)
        elif not showed:
            print(f'[link={url}]Click here to see the visualization in browser[/]')

        return self

    def _ipython_display_(self):
        """Displays the object in IPython as a side effect"""
        self.plot(
            inline_display=True, build=(self._build_level != FlowBuildLevel.GRAPH)
        )

    def _mermaid_to_url(self, mermaid_str: str, img_type: str) -> str:
        """
        Render the current Flow as URL points to a SVG. It needs internet connection

        :param mermaid_str: the mermaid representation
        :param img_type: image type (svg/jpg)
        :return: the url points to a SVG
        """
        encoded_str = base64.b64encode(bytes(mermaid_str, 'utf-8')).decode('utf-8')

        return f'https://mermaid.ink/{img_type}/{encoded_str}'

    @property
    def port(self) -> Union[List[int], Optional[int]]:
        """Return the exposed port of the gateway
        .. # noqa: DAR201
        """
        if GATEWAY_NAME in self._deployment_nodes:
            res = self._deployment_nodes[GATEWAY_NAME].first_pod_args.port
        else:
            res = self._gateway_kwargs.get('port', None) or self._gateway_kwargs.get(
                'ports', None
            )
        if not isinstance(res, list):
            return res
        elif len(res) == 1:
            return res[0]
        else:
            return res

    @port.setter
    def port(self, value: Union[int, List[int]]):
        """Set the new exposed port of the Flow (affects Gateway and Client)

        :param value: the new port to expose
        """
        if isinstance(value, int):
            self._gateway_kwargs['port'] = [value]
        elif isinstance(value, list):
            self._gateway_kwargs['port'] = value

        # Flow is build to graph already
        if self._build_level >= FlowBuildLevel.GRAPH:
            self[GATEWAY_NAME].args.port = self._gateway_kwargs['port']

        # Flow is running already, then close the existing gateway
        if self._build_level >= FlowBuildLevel.RUNNING:
            self[GATEWAY_NAME].close()
            self.enter_context(self[GATEWAY_NAME])
            self[GATEWAY_NAME].wait_start_success()

    @property
    def host(self) -> str:
        """Return the local address of the gateway
        .. # noqa: DAR201
        """
        if GATEWAY_NAME in self._deployment_nodes:
            return self._deployment_nodes[GATEWAY_NAME].host
        else:
            return self._gateway_kwargs.get('host', __default_host__)

    @host.setter
    def host(self, value: str):
        """Set the new host of the Flow (affects Gateway and Client)

        :param value: the new port to expose
        """
        self._gateway_kwargs['host'] = value

        # Flow is build to graph already
        if self._build_level >= FlowBuildLevel.GRAPH:
            self[GATEWAY_NAME].args.host = self._gateway_kwargs['host']

        # Flow is running already, then close the existing gateway
        if self._build_level >= FlowBuildLevel.RUNNING:
            self[GATEWAY_NAME].close()
            self.enter_context(self[GATEWAY_NAME])
            self[GATEWAY_NAME].wait_start_success()

    @property
    def monitoring(self) -> bool:
        """Return if the monitoring is enabled
        .. # noqa: DAR201
        """
        if GATEWAY_NAME in self._deployment_nodes:
            return self[GATEWAY_NAME].args.monitoring
        else:
            return False

    @property
    def port_monitoring(self) -> Optional[int]:
        """Return if the monitoring is enabled
        .. # noqa: DAR201
        """
        if GATEWAY_NAME in self._deployment_nodes:
            return self[GATEWAY_NAME].args.port_monitoring
        else:
            return self._gateway_kwargs.get('port_monitoring', None)

    def __iter__(self):
        return self._deployment_nodes.items().__iter__()

    def _get_summary_table(self, all_panels: List[Panel]):
        address_table = self._init_table()

        if not isinstance(self.protocol, list):
            _protocols = [str(self.protocol)]
        else:
            _protocols = [str(_p) for _p in self.protocol]

        if not isinstance(self.port, list):
            _ports = [self.port]
        else:
            _ports = [str(_p) for _p in self.port]

        swagger_ui_link = None
        redoc_link = None
        graphql_ui_link = None
        for _port, _protocol in zip(_ports, _protocols):
            if self.gateway_args.ssl_certfile and self.gateway_args.ssl_keyfile:
                _protocol = f'{_protocol}S'
                address_table.add_row(
                    ':chains:', 'Protocol', f':closed_lock_with_key: {_protocol}'
                )

            else:
                address_table.add_row(':chains:', 'Protocol', _protocol)

            _protocol = _protocol.lower()
            address_table.add_row(
                ':house:',
                'Local',
                f'[link={_protocol}://{self.host}:{_port}]{self.host}:{_port}[/]',
            )
            address_table.add_row(
                ':lock:',
                'Private',
                f'[link={_protocol}://{self.address_private}:{_port}]{self.address_private}:{_port}[/]',
            )

            if self.address_public:
                address_table.add_row(
                    ':earth_africa:',
                    'Public',
                    f'[link={_protocol}://{self.address_public}:{_port}]{self.address_public}:{_port}[/]',
                )

            if _protocol.lower() == ProtocolType.HTTP.to_string().lower():
                swagger_ui_link = f'[link={_protocol}://{self.host}:{_port}/docs]{self.host}:{_port}/docs'
                redoc_link = f'[link={_protocol}://{self.host}:{_port}/redoc]{self.host}:{_port}/redoc'
                graphql_ui_link = f'[link={_protocol}://{self.host}:{_port}/graphql]{self.host}:{_port}/graphql'

        all_panels.append(
            Panel(
                address_table,
                title=':link: [b]Endpoint[/]',
                expand=False,
            )
        )
        if ProtocolType.HTTP.to_string().lower() in [p.lower() for p in _protocols]:

            http_ext_table = self._init_table()

            _protocol = ProtocolType.HTTP.to_string()

            http_ext_table.add_row(
                ':speech_balloon:',
                'Swagger UI',
                swagger_ui_link,
            )

            http_ext_table.add_row(':books:', 'Redoc', redoc_link)

            if self.gateway_args.expose_graphql_endpoint:

                http_ext_table.add_row(':strawberry:', 'GraphQL UI', graphql_ui_link)

            all_panels.append(
                Panel(
                    http_ext_table,
                    title=':gem: [b]HTTP extension[/]',
                    expand=False,
                )
            )

        if self.monitoring:
            monitor_ext_table = self._init_table()

            for name, deployment in self:

                if deployment.args.monitoring:

                    for replica in deployment.pod_args['pods'][0]:
                        _address = [
                            f'[link=http://localhost:{replica.port_monitoring}]Local[/]',
                            f'[link=http://{self.address_private}:{replica.port_monitoring}]Private[/]',
                        ]

                        if self.address_public:
                            _address.append(
                                f'[link=http://{self.address_public}:{deployment.args.port_monitoring}]Public[/]'
                            )

                        _name = (
                            name
                            if len(deployment.pod_args['pods'][0]) == 1
                            else replica.name
                        )

                        monitor_ext_table.add_row(
                            ':flashlight:',  # upstream issue: they dont have :torch: emoji, so we use :flashlight:
                            # to represent observability of Prometheus (even they have :torch: it will be a war
                            # between AI community and Cloud-native community fighting on this emoji)
                            _name,
                            f'...[b]:{replica.port_monitoring}[/]',
                        )

            all_panels.append(
                Panel(
                    monitor_ext_table,
                    title=':gem: [b]Prometheus extension[/]',
                    expand=False,
                )
            )

        return all_panels

    @allowed_levels([FlowBuildLevel.RUNNING])
    def block(
        self, stop_event: Optional[Union[threading.Event, multiprocessing.Event]] = None
    ):
        """Block the Flow until `stop_event` is set or user hits KeyboardInterrupt

        :param stop_event: a threading event or a multiprocessing event that onces set will resume the control Flow
            to main thread.
        """

        def _reload_flow(changed_file):
            self.logger.info(
                f'change in Flow YAML {changed_file} observed, reloading Flow'
            )
            self.__exit__(None, None, None)
            new_flow = Flow.load_config(changed_file)
            self.__dict__ = new_flow.__dict__
            self.__enter__()

        def _reload_deployment(deployment, changed_file):
            self.logger.info(
                f'change in Executor configuration YAML {changed_file} observed, reloading Executor deployment'
            )
            deployment.__exit__(None, None, None)
            old_args, old_needs = deployment.args, deployment.needs
            new_deployment = Deployment(old_args, old_needs, include_gateway=False)
            deployment.__dict__ = new_deployment.__dict__
            deployment.__enter__()

        try:
            watch_changes = self.args.reload or any(
                [
                    deployment.args.reload
                    for deployment in list(self._deployment_nodes.values())
                ]
            )
            watch_files_from_deployments = {}
            for name, deployment in self._deployment_nodes.items():
                if deployment.args.reload:
                    if deployment._is_executor_from_yaml:
                        watch_files_from_deployments[deployment.args.uses] = name
            watch_files_list = list(watch_files_from_deployments.keys())

            config_loaded = getattr(self, '_config_loaded', '')
            if config_loaded.endswith('yml') or config_loaded.endswith('yaml'):
                watch_files_list.append(config_loaded)

            if watch_changes and len(watch_files_list) > 0:

                with ImportExtensions(
                    required=True,
                    logger=self.logger,
                    help_text='''reload requires watchfiles dependency to be installed. You can do `pip install 
                    watchfiles''',
                ):
                    from watchfiles import watch

                new_stop_event = stop_event or threading.Event()
                if len(watch_files_list) > 0:
                    for changes in watch(*watch_files_list, stop_event=new_stop_event):
                        for _, changed_file in changes:
                            if changed_file not in watch_files_from_deployments:
                                # maybe changed_file is the absolute path of one in watch_files_from_deployments
                                is_absolute_path = False
                                for (
                                    file,
                                    deployment_name,
                                ) in watch_files_from_deployments.items():
                                    if changed_file.endswith(file):
                                        is_absolute_path = True
                                        _reload_deployment(
                                            self._deployment_nodes[deployment_name],
                                            changed_file,
                                        )
                                        break

                                if not is_absolute_path:
                                    _reload_flow(changed_file)
                            else:
                                _reload_deployment(
                                    self._deployment_nodes[
                                        watch_files_from_deployments[changed_file]
                                    ],
                                    changed_file,
                                )
            else:
                wait_event = stop_event
                if not wait_event:
                    self._stop_event = threading.Event()
                    wait_event = self._stop_event
                if not __windows__:
                    wait_event.wait()
                else:
                    while True:
                        if wait_event.is_set():
                            break
                        time.sleep(0.5)
        except KeyboardInterrupt:
            pass

    @property
    def protocol(self) -> Union[ProtocolType, List[ProtocolType]]:
        """Return the protocol of this Flow

        :return: the protocol of this Flow, if only 1 protocol is supported otherwise returns the list of protocols
        """
        v = (
            self._gateway_kwargs.get('protocol', None)
            or self._gateway_kwargs.get('protocols', None)
            or [ProtocolType.GRPC]
        )
        if not isinstance(v, list):
            v = [v]
        v = ProtocolType.from_string_list(v)
        if len(v) == 1:
            return v[0]
        else:
            return v

    @protocol.setter
    def protocol(
        self,
        value: Union[str, ProtocolType, List[str], List[ProtocolType]],
    ):
        """Set the protocol of this Flow, can only be set before the Flow has been started

        :param value: the protocol to set
        """
        # Flow is running already, protocol cant be changed anymore
        if self._build_level >= FlowBuildLevel.RUNNING:
            raise RuntimeError('Protocol can not be changed after the Flow has started')

        if isinstance(value, str):
            self._gateway_kwargs['protocol'] = [ProtocolType.from_string(value)]
        elif isinstance(value, ProtocolType):
            self._gateway_kwargs['protocol'] = [value]
        elif isinstance(value, list):
            self._gateway_kwargs['protocol'] = ProtocolType.from_string_list(value)
        else:
            raise TypeError(
                f'{value} must be either `str` or `ProtocolType` or list of protocols'
            )

        # Flow is build to graph already
        if self._build_level >= FlowBuildLevel.GRAPH:
            self[GATEWAY_NAME].args.protocol = self._gateway_kwargs['protocol']

    def __getitem__(self, item):
        if isinstance(item, str):
            return self._deployment_nodes[item]
        elif isinstance(item, int):
            return list(self._deployment_nodes.values())[item]
        else:
            raise TypeError(f'{typename(item)} is not supported')

    @property
    def workspace(self) -> str:
        """Return the workspace path of the flow.

        .. # noqa: DAR201"""
        if self.args.workspace is not None:
            return os.path.abspath(self.args.workspace)
        else:
            return None

    @workspace.setter
    def workspace(self, value: str):
        """set workspace dir for flow & all deployments

        :param value: workspace to be set
        """
        self.args.workspace = value
        for k, p in self:
            p.args.workspace = value
            p.update_pod_args()

    @property
    def workspace_id(self) -> Dict[str, str]:
        """Get all Deployments' ``workspace_id`` values in a dict


        .. # noqa: DAR201"""
        return {
            k: p.args.workspace_id for k, p in self if hasattr(p.args, 'workspace_id')
        }

    @workspace_id.setter
    def workspace_id(self, value: str):
        """Set all Deployments' ``workspace_id`` to ``value``

        :param value: a hexadecimal UUID string
        """
        uuid.UUID(value)
        for k, p in self:
            if hasattr(p.args, 'workspace_id'):
                p.args.workspace_id = value
                args = getattr(p, 'pod_args', getattr(p, 'shards_args', None))
                if args is None:
                    raise ValueError(
                        f'could not find "pod_args" or "shards_args" on {p}'
                    )
                values = None
                if isinstance(args, dict):
                    values = args.values()
                elif isinstance(args, list):
                    values = args
                for v in values:
                    if v and isinstance(v, argparse.Namespace):
                        v.workspace_id = value
                    if v and isinstance(v, List):
                        for i in v:
                            i.workspace_id = value

    @property
    def env(self) -> Optional[Dict]:
        """Get all envs to be set in the Flow

        :return: envs as dict
        """
        return self.args.env

    @env.setter
    def env(self, value: Dict[str, str]):
        """set env vars for flow & all deployments.
        This can be used by jinad to set envs for Flow and all child objects

        :param value: value to be set
        """
        self.args.env = value
        for k, v in self:
            v.args.env = value
            v.update_pod_args()

    @overload
    def expose_endpoint(self, exec_endpoint: str, path: Optional[str] = None):
        """Expose an Executor's endpoint (defined by `@requests(on=...)`) to HTTP endpoint for easier access.

        After expose, you can send data request directly to `http://hostname:port/endpoint`.

        :param exec_endpoint: the endpoint string, by convention starts with `/`
        :param path: the HTTP endpoint string, when not given, it is `exec_endpoint`
        """
        ...

    @overload
    def expose_endpoint(
        self,
        exec_endpoint: str,
        *,
        path: Optional[str] = None,
        status_code: int = 200,
        tags: Optional[List[str]] = None,
        summary: Optional[str] = None,
        description: Optional[str] = None,
        response_description: str = 'Successful Response',
        deprecated: Optional[bool] = None,
        methods: Optional[List[str]] = None,
        operation_id: Optional[str] = None,
        response_model_by_alias: bool = True,
        response_model_exclude_unset: bool = False,
        response_model_exclude_defaults: bool = False,
        response_model_exclude_none: bool = False,
        include_in_schema: bool = True,
        name: Optional[str] = None,
    ):
        """Expose an Executor's endpoint (defined by `@requests(on=...)`) to HTTP endpoint for easier access.

        After expose, you can send data request directly to `http://hostname:port/endpoint`.

        Use this method to specify your HTTP endpoint with richer semantic and schema.

        :param exec_endpoint: the endpoint string, by convention starts with `/`

        # noqa: DAR101
        """
        ...

    @allowed_levels([FlowBuildLevel.EMPTY])
    def expose_endpoint(self, exec_endpoint: str, **kwargs):
        """Expose an Executor's endpoint (defined by `@requests(on=...)`) to HTTP endpoint for easier access.

        After expose, you can send data request directly to `http://hostname:port/endpoint`.

        :param exec_endpoint: the endpoint string, by convention starts with `/`

        # noqa: DAR101
        # noqa: DAR102
        """
        self._endpoints_mapping[exec_endpoint] = kwargs

    def to_kubernetes_yaml(
        self,
        output_base_path: str,
        k8s_namespace: Optional[str] = None,
        include_gateway: bool = True,
    ):
        """
        Converts the Flow into a set of yaml deployments to deploy in Kubernetes.

        If you don't want to rebuild image on Jina Hub,
        you can set `JINA_HUB_NO_IMAGE_REBUILD` environment variable.

        :param output_base_path: The base path where to dump all the yaml files
        :param k8s_namespace: The name of the k8s namespace to set for the configurations. If None, the name of the Flow will be used.
        :param include_gateway: Defines if the gateway deployment should be included, defaults to True
        """

        if self._build_level.value < FlowBuildLevel.GRAPH.value:
            self.build(copy_flow=False)

        k8s_namespace = k8s_namespace or self.args.name or 'default'

        for node, v in self._deployment_nodes.items():

            if node == 'gateway' and not include_gateway:
                continue

            deployment_base = os.path.join(output_base_path, node)
            v._to_kubernetes_yaml(
                deployment_base,
                k8s_namespace=k8s_namespace,
                k8s_deployments_addresses=self._get_k8s_deployments_addresses(
                    k8s_namespace
                ),
            )

        self.logger.info(
            f'K8s yaml files have been created under [b]{output_base_path}[/]. You can use it by running [b]kubectl apply -R -f {output_base_path}[/]'
        )

    to_k8s_yaml = to_kubernetes_yaml

    def to_docker_compose_yaml(
        self,
        output_path: Optional[str] = None,
        network_name: Optional[str] = None,
        include_gateway: bool = True,
    ):
        """
        Converts the Flow into a yaml file to run with `docker-compose up`
        :param output_path: The output path for the yaml file
        :param network_name: The name of the network that will be used by the deployment name
        :param include_gateway: Defines if the gateway deployment should be included, defaults to True
        """
        import yaml

        if self._build_level.value < FlowBuildLevel.GRAPH.value:
            self.build(copy_flow=False)

        output_path = output_path or 'docker-compose.yml'
        network_name = network_name or 'jina-network'

        docker_compose_dict = {
            'version': '3.3',
            'networks': {network_name: {'driver': 'bridge'}},
        }

        services = {}

        for node, v in self._deployment_nodes.items():
            if v.external or (node == 'gateway' and not include_gateway):
                continue

            service_configs = v._to_docker_compose_config(
                deployments_addresses=self._get_docker_compose_deployments_addresses(),
            )

            for service_name, service in service_configs:
                service['networks'] = [network_name]
                services[service_name] = service

        docker_compose_dict['services'] = services
        with open(output_path, 'w+', encoding='utf-8') as fp:
            yaml.dump(docker_compose_dict, fp, sort_keys=False)

        command = (
            'docker compose up'
            if output_path is None
            else f'docker compose -f {output_path} up'
        )

        self.logger.info(
            f'Docker compose file has been created under [b]{output_path}[/b]. You can use it by running [b]{command}[/b]'
        )

    @property
    def gateway_args(self) -> argparse.Namespace:
        """Get Gateway settings.

        # noqa: DAR201
        """
        return ArgNamespace.kwargs2namespace(self._gateway_kwargs, set_gateway_parser())

    def _update_network_interface(self, **kwargs):
        """Update the network interface of this Flow (affects Gateway & Client)

        :param kwargs: new network settings
        """
        self._gateway_kwargs.update(kwargs)
        # reset client
        self._client = None

    def __getattribute__(self, item):
        obj = super().__getattribute__(item)

        if (
            item == 'load_config' and inspect.ismethod(obj) and obj.__self__ is Flow
        ):  # check if obj load config call from an instance and not the Class
            warnings.warn(
                "Calling `load_config` from a Flow instance will override all of the instance's initial parameters. We recommend to use `Flow.load_config(...)` instead"
            )

        return obj
