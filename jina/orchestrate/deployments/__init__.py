import asyncio
import copy
import json
import multiprocessing
import os
import platform
import re
import subprocess
import sys
import threading
import time
import warnings
from argparse import Namespace
from collections import defaultdict
from contextlib import ExitStack
from itertools import cycle
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Type, Union, overload

from hubble.executor.helper import replace_secret_of_hub_uri
from rich import print
from rich.panel import Panel

from jina.clients import Client
from jina.clients.mixin import PostMixin
from jina.constants import (
    __default_executor__,
    __default_grpc_gateway__,
    __default_host__,
    __docker_host__,
    __windows__,
)
from jina.enums import (
    DeploymentRoleType,
    PodRoleType,
    PollingType,
    ProtocolType,
    ProviderType,
)
from jina.helper import (
    ArgNamespace,
    parse_host_scheme,
    random_port,
    send_telemetry_event,
)
from jina.importer import ImportExtensions
from jina.jaml import JAMLCompatible
from jina.logging.logger import JinaLogger
from jina.orchestrate.deployments.install_requirements_helper import (
    _get_package_path_from_uses,
    install_package_dependencies,
)
from jina.orchestrate.orchestrator import BaseOrchestrator
from jina.orchestrate.pods.factory import PodFactory
from jina.parsers import set_deployment_parser, set_gateway_parser
from jina.parsers.helper import _update_gateway_args
from jina.serve.networking.utils import host_is_local, in_docker

WRAPPED_SLICE_BASE = r'\[[-\d:]+\]'

if TYPE_CHECKING:
    from jina.clients.base import BaseClient
    from jina.serve.executors import BaseExecutor


class DeploymentType(type(ExitStack), type(JAMLCompatible)):
    """Type of Deployment, metaclass of :class:`Deployment`"""

    pass


def _call_add_voters(leader, voters, replica_ids, logger):
    # this method needs to be run in multiprocess, importing jraft in main process
    # makes it impossible to do tests sequentially
    from jina.serve.consensus.add_voter.call_add_voter import call_add_voter

    logger.debug(f'Trying to add {len(replica_ids)} voters to leader {leader}')
    success_lists = []
    for voter_address, replica_id in zip(voters, replica_ids):
        logger.debug(
            f'Trying to add replica-{str(replica_id)} as voter with address {voter_address} to leader at {leader}'
        )
        success = False
        for i in range(5):
            logger.debug(f'Trying {i}th time')
            success = call_add_voter(leader, str(replica_id), voter_address)
            if success:
                logger.debug(f'Trying {i}th time succeeded')
                break
            else:
                logger.debug(f'Trying {i}th failed. Wait 2 seconds for next try')
                time.sleep(2.0)

        success_lists.append(success)
        if not success:
            logger.warning(
                f'Failed to add {str(replica_id)} as voter with address {voter_address} to leader at {leader}. This could be because {leader} is not the leader, '
                f'and maybe the cluster is restoring from a previous cluster state'
            )
        else:
            logger.success(
                f'Replica-{str(replica_id)} successfully added as voter with address {voter_address} to leader at {leader}'
            )
    logger.debug('Adding voters to leader finished')
    return all(success_lists)


async def _async_call_add_voters(leader, voters, replica_ids, logger):
    # this method needs to be run in multiprocess, importing jraft in main process
    # makes it impossible to do tests sequentially
    from jina.serve.consensus.add_voter.call_add_voter import async_call_add_voter

    logger.debug(f'Trying to add {len(replica_ids)} voters to leader {leader}')
    success_lists = []
    for voter_address, replica_id in zip(voters, replica_ids):
        logger.debug(
            f'Trying to add replica-{str(replica_id)} as voter with address {voter_address} to leader at {leader}'
        )
        success = False
        for i in range(5):
            logger.debug(f'Trying {i}th time')
            success = await async_call_add_voter(leader, str(replica_id), voter_address)
            if success:
                logger.debug(f'Trying {i}th time succeeded')
                break
            else:
                logger.debug(f'Trying {i}th failed. Wait 2 seconds for next try')
                time.sleep(2.0)
        success_lists.append(success)
        if not success:
            logger.warning(
                f'Failed to add {str(replica_id)} as voter with address {voter_address} to leader at {leader}. This could be because {leader} is not the leader, '
                f'and maybe the cluster is restoring from a previous cluster state'
            )
        else:
            logger.success(
                f'Replica-{str(replica_id)} successfully added as voter with address {voter_address} to leader at {leader}'
            )
    logger.debug('Adding voters to leader finished')
    return all(success_lists)


class Deployment(JAMLCompatible, PostMixin, BaseOrchestrator, metaclass=DeploymentType):
    """A Deployment is an immutable set of pods, which run in replicas. They share the same input and output socket.
    Internally, the pods can run with the process/thread backend. They can also be run in their own containers
    :param args: arguments parsed from the CLI
    :param needs: deployments names of preceding deployments, the output of these deployments go into the input of this deployment
    """

    class _ReplicaSet:
        def __init__(
            self,
            deployment_args: Namespace,
            args: List[Namespace],
            head_pod,
            name,
        ):
            self.deployment_args = copy.copy(deployment_args)
            self.args = args
            self.shard_id = args[0].shard_id
            self._pods = []
            self.head_pod = head_pod
            self.name = name
            logger_kwargs = vars(self.deployment_args)
            logger_kwargs.pop('name')
            self.logger = JinaLogger(context=self.name, name=self.name, **logger_kwargs)

        def _add_voter_to_leader(self):
            leader_address = f'{self._pods[0].runtime_ctrl_address}'
            voter_addresses = [pod.runtime_ctrl_address for pod in self._pods[1:]]
            replica_ids = [pod.args.replica_id for pod in self._pods[1:]]
            self.logger.debug('Starting process to call Add Voters')
            res = _call_add_voters(
                leader=leader_address,
                voters=voter_addresses,
                replica_ids=replica_ids,
                logger=self.logger,
            )
            if res:
                self.logger.debug('Finished adding voters')
            else:
                self.logger.error('Adding Voters did not finish successfully')

        async def _async_add_voter_to_leader(self):
            leader_address = f'{self._pods[0].runtime_ctrl_address}'
            voter_addresses = [pod.runtime_ctrl_address for pod in self._pods[1:]]
            replica_ids = [pod.args.replica_id for pod in self._pods[1:]]
            self.logger.debug('Starting process to call Add Voters')
            res = await _async_call_add_voters(
                leader=leader_address,
                voters=voter_addresses,
                replica_ids=replica_ids,
                logger=self.logger,
            )
            if res:
                self.logger.debug('Finished adding voters')
            else:
                self.logger.error('Adding Voters did not finish successfully')

        @property
        def is_ready(self):
            return all(p.is_ready.is_set() for p in self._pods)

        def clear_pods(self):
            self._pods.clear()

        @property
        def num_pods(self):
            return len(self._pods)

        def join(self):
            for pod in self._pods:
                pod.join()

        def wait_start_success(self):
            self.logger.debug('Waiting for ReplicaSet to start successfully')
            for pod in self._pods:
                pod.wait_start_success()
            # should this be done only when the cluster is started ?
            if self._pods[0].args.stateful:
                self._add_voter_to_leader()
            self.logger.debug('ReplicaSet started successfully')

        async def async_wait_start_success(self):
            self.logger.debug('Waiting for ReplicaSet to start successfully')
            await asyncio.gather(
                *[pod.async_wait_start_success() for pod in self._pods]
            )
            # should this be done only when the cluster is started ?
            if self._pods[0].args.stateful:
                await self._async_add_voter_to_leader()
            self.logger.debug('ReplicaSet started successfully')

        def __enter__(self):
            for _args in self.args:
                _args.noblock_on_start = True
                pod = PodFactory.build_pod(_args).start()
                self._pods.append(pod)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            closing_exception = None
            for pod in self._pods:
                try:
                    pod.close()
                except Exception as exc:
                    if closing_exception is None:
                        closing_exception = exc
            if exc_val is None and closing_exception is not None:
                raise closing_exception

    # overload_inject_start_deployment
    @overload
    def __init__(
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
    ):
        """Create a Deployment to serve or deploy and Executor or Gateway

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

        .. # noqa: DAR202
        .. # noqa: DAR101
        .. # noqa: DAR003
        """

    # overload_inject_end_deployment

    def __init__(
        self,
        args: Union['Namespace', Dict, None] = None,
        needs: Optional[Set[str]] = None,
        include_gateway: bool = True,
        **kwargs,
    ):
        super().__init__()
        self._gateway_kwargs = {}
        self._include_gateway = include_gateway
        if self._include_gateway:
            # arguments exclusive to the gateway
            for field in ['port', 'ports']:
                if field in kwargs:
                    self._gateway_kwargs[field] = kwargs.pop(field)

            # arguments common to both gateway and the Executor
            for field in ['host', 'log_config']:
                if field in kwargs:
                    self._gateway_kwargs[field] = kwargs[field]

        parser = set_deployment_parser()
        if args is None:
            args = ArgNamespace.kwargs2namespace(kwargs, parser, True)
        self.args = args
        self._gateway_load_balancer = False
        if self.args.provider in (ProviderType.SAGEMAKER, ProviderType.AZURE):
            if self._gateway_kwargs.get('port', 0) == 8080:
                raise ValueError(
                    'Port 8080 is reserved for CSP deployment. '
                    'Please use another port'
                )
            if self.args.port != [8080]:
                warnings.warn(
                    'Port is changed to 8080 for CSP deployment. '
                    f'Port {self.args.port} is ignored'
                )
                self.args.port = [8080]
            if self.args.protocol != [ProtocolType.HTTP]:
                warnings.warn(
                    'Protocol is changed to HTTP for CSP deployment. '
                    f'Protocol {self.args.protocol} is ignored'
                )
                self.args.protocol = [ProtocolType.HTTP]
        if self._include_gateway and ProtocolType.HTTP in self.args.protocol:
            self._gateway_load_balancer = True
        log_config = kwargs.get('log_config')
        if log_config:
            self.args.log_config = log_config
        self.args.polling = (
            args.polling if hasattr(args, 'polling') else PollingType.ANY
        )
        # polling only works for shards, if there are none, polling will be ignored
        if getattr(args, 'shards', 1) == 1:
            self.args.polling = PollingType.ANY

        if (
            getattr(args, 'shards', 1) > 1
            and ProtocolType.HTTP in self.args.protocol
            and self.args.deployment_role != DeploymentRoleType.GATEWAY
        ):
            raise RuntimeError(
                f'It is not supported to have {ProtocolType.HTTP.to_string()} deployment for '
                f'Deployments with more than one shard'
            )

        if (
            ProtocolType.WEBSOCKET in self.args.protocol
            and self.args.deployment_role != DeploymentRoleType.GATEWAY
        ):
            raise RuntimeError(
                f'It is not supported to have {ProtocolType.WEBSOCKET.to_string()} deployment for '
                f'Deployments'
            )
        is_mac_os = platform.system() == 'Darwin'
        is_windows_os = platform.system() == 'Windows'
        is_37 = sys.version_info.major == 3 and sys.version_info.minor == 7

        if self.args.stateful and (is_windows_os or (is_mac_os and is_37)):
            if is_windows_os:
                raise RuntimeError('Stateful feature is not available on Windows')
            if is_mac_os:
                raise RuntimeError(
                    'Stateful feature when running on MacOS requires Python3.8 or newer version'
                )
        if self.args.stateful and (
            ProtocolType.WEBSOCKET in self.args.protocol
            or ProtocolType.HTTP in self.args.protocol
            or len(self.args.protocol) > 1
        ):
            raise RuntimeError(
                f'Stateful feature is only available for Deployments using a single {ProtocolType.GRPC.to_string()} protocol. {self.args.protocol} were requested'
            )
        self.needs = (
            needs or set()
        )  #: used in the :class:`jina.flow.Flow` to build the graph

        # parse addresses for distributed replicas
        (
            self.ext_repl_hosts,
            self.ext_repl_ports,
            self.ext_repl_schemes,
            self.ext_repl_tls,
        ) = ([], [], [], [])
        if self.args.pod_role != PodRoleType.GATEWAY:
            self._parse_external_replica_hosts_and_ports()
            self._parse_addresses_into_host_and_port()
        if len(self.ext_repl_ports) > 1:
            if self.args.replicas != 1 and self.args.replicas != len(
                self.ext_repl_ports
            ):
                raise ValueError(
                    f'Number of hosts ({len(self.args.host)}) does not match the number of replicas ({self.args.replicas})'
                )
            elif self.args.external:
                self.args.replicas = len(self.ext_repl_ports)

        self.uses_before_pod = None
        self.uses_after_pod = None
        self.head_pod = None
        self.gateway_pod = None
        self.shards = {}
        self._update_port_monitoring_args()
        self.update_pod_args()

        if self._include_gateway:
            gateway_parser = set_gateway_parser()
            args = ArgNamespace.kwargs2namespace(
                self._gateway_kwargs, gateway_parser, True
            )
            args.protocol = self.args.protocol

            args.deployments_addresses = json.dumps(
                {'executor': self._get_connection_list_for_single_executor()}
            )
            args.graph_description = (
                '{"start-gateway": ["executor"], "executor": ["end-gateway"]}'
            )
            _update_gateway_args(
                args, gateway_load_balancer=self._gateway_load_balancer
            )
            self.pod_args['gateway'] = args
        else:
            self.pod_args['gateway'] = None

        self.logger = JinaLogger(self.__class__.__name__, **vars(self.args))

    def _get_connection_list_for_flow(self) -> List[str]:
        if self.head_args:
            # add head information
            return [f'{self.protocol.lower()}://{self.host}:{self.head_port}']
        else:
            # there is no head, add the worker connection information instead
            ports = self.ports
            hosts = [
                (
                    __docker_host__
                    if host_is_local(host) and in_docker() and self._is_docker
                    else host
                )
                for host in self.hosts
            ]
            return [
                f'{self.protocol.lower()}://{host}:{port}'
                for host, port in zip(hosts, ports)
            ]

    def _get_connection_list_for_single_executor(
        self,
    ) -> Union[List[str], Dict[str, List[str]]]:
        if self.head_args:
            # add head information
            return [f'{self.protocol.lower()}://{self.host}:{self.head_port}']
        else:
            # there is no head, add the worker connection information instead
            ports_dict = defaultdict(list)
            for replica_pod_arg in self.pod_args['pods'][0]:
                for protocol, port in zip(
                    replica_pod_arg.protocol, replica_pod_arg.port
                ):
                    ports_dict[str(protocol)].append(port)

            host = (
                __docker_host__
                if host_is_local(self.args.host[0]) and in_docker() and self._is_docker
                else self.args.host[0]
            )

            connection_dict = {}
            for protocol, ports in ports_dict.items():
                connection_dict[protocol] = [
                    f'{protocol.lower()}://{host}:{port}' for port in ports
                ]
            return connection_dict

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        super().__exit__(exc_type, exc_val, exc_tb)
        self.join()
        if self._include_gateway:
            self._stop_time = time.time()
            send_telemetry_event(
                event='stop',
                obj_cls_name=self.__class__.__name__,
                entity_id=self._entity_id,
                duration=self._stop_time - self._start_time,
                exc_type=str(exc_type),
            )
        self.logger.close()

    def _parse_addresses_into_host_and_port(self):
        # splits addresses passed to `host` into separate `host` and `port`

        for i, _host in enumerate(self.args.host):
            _hostname, port, scheme, tls = parse_host_scheme(_host)
            if _hostname != _host:  # more than just hostname was passed to `host`
                self.args.host[i] = _hostname
                self.args.port[i] = port
                self.args.scheme = scheme
                self.args.tls = tls
        for i, repl_host in enumerate(self.ext_repl_hosts):
            _hostname, port, scheme, tls = parse_host_scheme(repl_host)
            if (
                _hostname != self.ext_repl_hosts[i]
            ):  # more than just hostname was passed to `host`
                self.ext_repl_hosts[i] = _hostname
                self.ext_repl_ports[i] = port
                self.ext_repl_schemes[i] = scheme
                self.ext_repl_tls[i] = tls

    def _parse_external_replica_hosts_and_ports(self):
        # splits user provided lists of hosts and ports into a host and port for every distributed replica
        ext_repl_ports: List = self.args.port.copy()
        ext_repl_hosts: List = self.args.host.copy()
        if len(ext_repl_hosts) < len(ext_repl_ports):
            if (
                len(ext_repl_hosts) == 1
            ):  # only one host given, assume replicas are on the same host
                ext_repl_hosts = ext_repl_hosts * len(ext_repl_ports)
                self.args.host = self.args.host * len(ext_repl_ports)
        elif len(ext_repl_hosts) > len(ext_repl_ports):
            if (
                len(ext_repl_ports) == 1
            ):  # only one port given, assume replicas are on the same port
                ext_repl_ports = ext_repl_ports * len(ext_repl_hosts)
                self.args.port = self.args.port * len(ext_repl_hosts)
        if len(ext_repl_hosts) != len(ext_repl_ports):
            raise ValueError(
                f'Number of hosts ({len(ext_repl_hosts)}) does not match the number of ports ({len(ext_repl_ports)})'
            )

        self.ext_repl_hosts, self.ext_repl_ports = ext_repl_hosts, ext_repl_ports
        # varying tls and schemes other than 'grpc' only implemented if the entire address is passed to `host`
        self.ext_repl_schemes = [
            getattr(self.args, 'scheme', None) for _ in self.ext_repl_ports
        ]
        self.ext_repl_tls = [
            getattr(self.args, 'tls', None) for _ in self.ext_repl_ports
        ]

    def _update_port_monitoring_args(self):
        _all_port_monitoring = self.args.port_monitoring
        self.args.all_port_monitoring = (
            [_all_port_monitoring]
            if not type(_all_port_monitoring) == list
            else _all_port_monitoring
        )
        self.args.port_monitoring = int(
            self.args.all_port_monitoring[0]
        )  # this is for the head

    def update_pod_args(self):
        """Update args of all its pods based on Deployment args. Including head/tail"""
        if self.args.runtime_cls == 'GatewayRuntime':
            _update_gateway_args(self.args)
        if isinstance(self.args, Dict):
            # This is used when a Deployment is created in a remote context, where pods & their connections are already given.
            self.pod_args = self.args
        else:
            self.pod_args = self._parse_args(self.args)

    def update_worker_pod_args(self):
        """Update args of all its worker pods based on Deployment args. Does not touch head and tail"""
        self.pod_args['pods'] = self._set_pod_args()

    @property
    def role(self) -> 'DeploymentRoleType':
        """Return the role of this :class:`Deployment`.

        .. # noqa: DAR201
        """
        return self.args.deployment_role

    @property
    def name(self) -> str:
        """The name of this :class:`Deployment`.


        .. # noqa: DAR201
        """
        return self.args.name

    @property
    def head_host(self) -> str:
        """Get the host of the HeadPod of this deployment
        .. # noqa: DAR201
        """
        return self.head_args.host if self.head_args else None

    @property
    def head_port(self):
        """Get the port of the HeadPod of this deployment
        .. # noqa: DAR201
        """
        return self.head_args.port[0] if self.head_args else None

    @property
    def head_port_monitoring(self):
        """Get the port_monitoring of the HeadPod of this deployment
        .. # noqa: DAR201
        """
        return self.head_args.port_monitoring if self.head_args else None

    @property
    def client(self) -> 'BaseClient':
        """Return a :class:`BaseClient` object attach to this Flow.

        .. # noqa: DAR201"""

        kwargs = dict(
            host=self.host,
            port=self.port,
            protocol=self.protocol,
            grpc_channel_options=self.args.grpc_channel_options,
        )
        kwargs.update(self._gateway_kwargs)
        return Client(**kwargs)

    @staticmethod
    def _copy_to_head_args(args: Namespace) -> Namespace:
        """
        Set the outgoing args of the head router

        :param args: basic arguments
        :return: enriched head arguments
        """

        _head_args = copy.deepcopy(args)
        _head_args.polling = args.polling
        _head_args.port = args.port
        _head_args.host = args.host[0]
        _head_args.uses = args.uses
        _head_args.pod_role = PodRoleType.HEAD
        _head_args.runtime_cls = 'HeadRuntime'
        _head_args.replicas = 1

        if args.name:
            _head_args.name = f'{args.name}/head'
        else:
            _head_args.name = 'head'

        return _head_args

    @property
    def deployments(self) -> List[Dict]:
        """Get deployments of the deployment. The Deployment just gives one deployment.

        :return: list of deployments
        """
        return [
            {
                'name': self.name,
                'head_host': self.head_host,
                'head_port': self.head_port,
            }
        ]

    @property
    def _is_docker(self) -> bool:
        """
        Check if this deployment is to be run in Docker.

        :return: True if this deployment is to be run in Docker
        """
        from hubble.executor.helper import is_valid_docker_uri

        uses = getattr(self.args, 'uses', '')
        return is_valid_docker_uri(uses)

    @property
    def _is_executor_from_yaml(self) -> bool:
        """
        Check if this deployment is to be run from YAML configuration.

        :return: True if this deployment is to be run from YAML configuration
        """
        uses = getattr(self.args, 'uses', '')
        return uses.endswith('yml') or uses.endswith('yaml')

    @property
    def tls_enabled(self):
        """
        Check if secure connection via TLS is enabled for this Deployment.

        :return: True if tls is enabled, False otherwise
        """
        has_cert = getattr(self.args, 'ssl_certfile', None) is not None
        has_key = getattr(self.args, 'ssl_keyfile', None) is not None
        tls = getattr(self.args, 'tls', False)
        return tls or (has_cert and has_key)

    @property
    def external(self) -> bool:
        """
        Check if this deployment is external.

        :return: True if this deployment is provided as an external deployment, False otherwise
        """
        return getattr(self.args, 'external', False)

    @property
    def grpc_metadata(self):
        """
        Get the gRPC metadata for this deployment
        :return: The gRPC metadata for this deployment. If the deployment is a Gateway, return None.
        """
        return getattr(self.args, 'grpc_metadata', None)

    @property
    def protocol(self):
        """
        :return: the protocol of this deployment
        """
        args = self.pod_args['gateway'] or self.args

        protocol = getattr(args, 'protocol', ['grpc'])
        if not isinstance(protocol, list):
            protocol = [protocol]
        protocol = [
            str(_p).lower() + ('s' if self.tls_enabled else '') for _p in protocol
        ]
        if len(protocol) == 1:
            return protocol[0]
        else:
            return protocol

    @property
    def first_pod_args(self) -> Namespace:
        """Return the first worker pod's args


        .. # noqa: DAR201
        """
        # note this will be never out of boundary
        return self.pod_args['gateway'] or self.pod_args['pods'][0][0]

    @property
    def host(self) -> str:
        """Get the host name of this deployment


        .. # noqa: DAR201
        """
        return self.first_pod_args.host

    @property
    def port(self):
        """
        :return: The port of this deployment
        """
        return self.first_pod_args.port[0]

    @property
    def ports(self) -> List[int]:
        """Returns a list of ports exposed by this Deployment.
        Exposed means these are the ports a Client/Gateway is supposed to communicate with.
        For sharded deployments this will be the head_port.
        For non-sharded deployments it will be all replica ports.
        .. # noqa: DAR201
        """
        if self.head_port:
            return [self.head_port]
        else:
            ports = []
            for replica in self.pod_args['pods'][0]:
                if isinstance(replica.port, list):
                    ports.extend(replica.port)
                else:
                    ports.append(replica.port)
            return ports

    @property
    def hosts(self) -> List[str]:
        """Returns a list of host addresses exposed by this Deployment.
        Exposed means these are the host a Client/Gateway is supposed to communicate with.
        For sharded deployments this will be the head host.
        For non-sharded deployments it will be all replica hosts.
        .. # noqa: DAR201
        """
        if self.head_host:
            return [self.head_host]
        else:
            return [replica.host for replica in self.pod_args['pods'][0]]

    def _parse_args(
        self, args: Namespace
    ) -> Dict[str, Optional[Union[List[Namespace], Namespace]]]:
        return self._parse_base_deployment_args(args)

    @property
    def head_args(self) -> Namespace:
        """Get the arguments for the `head` of this Deployment.


        .. # noqa: DAR201
        """
        return self.pod_args['head']

    @head_args.setter
    def head_args(self, args):
        """Set the arguments for the `head` of this Deployment.


        .. # noqa: DAR101
        """
        self.pod_args['head'] = args

    @property
    def uses_before_args(self) -> Namespace:
        """Get the arguments for the `uses_before` of this Deployment.


        .. # noqa: DAR201
        """
        return self.pod_args['uses_before']

    @uses_before_args.setter
    def uses_before_args(self, args):
        """Set the arguments for the `uses_before` of this Deployment.


        .. # noqa: DAR101
        """
        self.pod_args['uses_before'] = args

    @property
    def uses_after_args(self) -> Namespace:
        """Get the arguments for the `uses_after` of this Deployment.


        .. # noqa: DAR201
        """
        return self.pod_args['uses_after']

    @uses_after_args.setter
    def uses_after_args(self, args):
        """Set the arguments for the `uses_after` of this Deployment.


        .. # noqa: DAR101
        """
        self.pod_args['uses_after'] = args

    @property
    def all_args(self) -> List[Namespace]:
        """Get all arguments of all Pods in this Deployment.

        .. # noqa: DAR201
        """
        all_args = (
            ([self.pod_args['uses_before']] if self.pod_args['uses_before'] else [])
            + ([self.pod_args['uses_after']] if self.pod_args['uses_after'] else [])
            + ([self.pod_args['head']] if self.pod_args['head'] else [])
            + ([self.pod_args['gateway']] if self._include_gateway else [])
        )
        for shard_id in self.pod_args['pods']:
            all_args += self.pod_args['pods'][shard_id]
        return all_args

    @property
    def num_pods(self) -> int:
        """Get the number of running :class:`Pod`

        .. # noqa: DAR201
        """
        num_pods = 0
        if self.head_pod is not None:
            num_pods += 1
        if self.uses_before_pod is not None:
            num_pods += 1
        if self.uses_after_pod is not None:
            num_pods += 1
        if self.gateway_pod is not None:
            num_pods += 1
        if self.shards:  # external deployments
            for shard_id in self.shards:
                num_pods += self.shards[shard_id].num_pods
        return num_pods

    def __eq__(self, other: 'Deployment'):
        return self.num_pods == other.num_pods and self.name == other.name

    @staticmethod
    def get_worker_host(pod_args, pod_is_container, head_is_container):
        """
        Check if the current pod and head are both containerized on the same host
        If so, __docker_host__ needs to be advertised as the worker's address to the head

        :param pod_args: arguments of the worker pod
        :param pod_is_container: boolean specifying if pod is to be run in container
        :param head_is_container: boolean specifying if head pod is to be run in container
        :return: host to pass in connection list of the head
        """
        # Check if the current pod and head are both containerized on the same host
        # If so __docker_host__ needs to be advertised as the worker's address to the head
        worker_host = (
            __docker_host__
            if (pod_is_container and (head_is_container or in_docker()))
            and host_is_local(pod_args.host)
            else pod_args.host
        )
        return worker_host

    def _wait_until_all_ready(self):
        import warnings

        with warnings.catch_warnings():
            wait_for_ready_coro = self.async_wait_start_success()

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

            if not running_in_event_loop:
                asyncio.get_event_loop().run_until_complete(wait_for_ready_coro)
            else:
                wait_ready_thread = threading.Thread(
                    target=self.wait_start_success, daemon=True
                )
                wait_ready_thread.start()
                wait_ready_thread.join()

    def start(self) -> 'Deployment':
        """
        Start to run all :class:`Pod` in this Deployment.

        :return: started deployment

        .. note::
            If one of the :class:`Pod` fails to start, make sure that all of them
            are properly closed.
        """

        self._start_time = time.time()

        if not self._is_docker and getattr(self.args, 'install_requirements', False):
            install_package_dependencies(_get_package_path_from_uses(self.args.uses))

        if self.pod_args['uses_before'] is not None:
            _args = self.pod_args['uses_before']
            _args.noblock_on_start = True
            self.uses_before_pod = PodFactory.build_pod(_args)
            self.enter_context(self.uses_before_pod)
        if self.pod_args['uses_after'] is not None:
            _args = self.pod_args['uses_after']
            _args.noblock_on_start = True
            self.uses_after_pod = PodFactory.build_pod(_args)
            self.enter_context(self.uses_after_pod)

        num_shards = len(self.pod_args['pods'])
        for shard_id in self.pod_args['pods']:
            self.shards[shard_id] = self._ReplicaSet(
                deployment_args=self.args,
                args=self.pod_args['pods'][shard_id],
                head_pod=self.head_pod,
                name=(
                    f'{self.name}-replica-set-{shard_id}'
                    if num_shards > 1
                    else f'{self.name}-replica-set'
                ),
            )
            self.enter_context(self.shards[shard_id])

        if self.pod_args['head'] is not None:
            _args = self.pod_args['head']
            _args.noblock_on_start = True
            self.head_pod = PodFactory.build_pod(_args)
            self.enter_context(self.head_pod)

        if self._include_gateway:
            _args = self.pod_args['gateway']
            _args.noblock_on_start = True
            self.gateway_pod = PodFactory.build_pod(
                _args, gateway_load_balancer=self._gateway_load_balancer
            )
            self.enter_context(self.gateway_pod)

        if not self.args.noblock_on_start:
            self._wait_until_all_ready()
        if self._include_gateway:
            all_panels = []
            self._get_summary_table(all_panels)

            from rich.rule import Rule

            print(Rule(':tada: Deployment is ready to serve!'), *all_panels)

            send_telemetry_event(
                event='start',
                obj_cls_name=self.__class__.__name__,
                entity_id=self._entity_id,
            )

        return self

    def wait_start_success(self) -> None:
        """Block until all pods start successfully.

        If not successful, it will raise an error hoping the outer function will catch it
        """
        try:
            if self.uses_before_pod is not None:
                self.uses_before_pod.wait_start_success()
            if self.uses_after_pod is not None:
                self.uses_after_pod.wait_start_success()
            if self.head_pod is not None:
                self.head_pod.wait_start_success()
            if self.gateway_pod is not None:
                self.gateway_pod.wait_start_success()
            for shard_id in self.shards:
                self.shards[shard_id].wait_start_success()
        except:
            self.close()
            raise

    async def async_wait_start_success(self) -> None:
        """Block until all pods start successfully.

        If unsuccessful, it will raise an error hoping the outer function will catch it
        """
        try:
            coros = []
            if self.uses_before_pod is not None:
                coros.append(self.uses_before_pod.async_wait_start_success())
            if self.uses_after_pod is not None:
                coros.append(self.uses_after_pod.async_wait_start_success())
            if self.gateway_pod is not None:
                coros.append(self.gateway_pod.async_wait_start_success())
            if self.head_pod is not None:
                coros.append(self.head_pod.async_wait_start_success())
            for shard_id in self.shards:
                coros.append(self.shards[shard_id].async_wait_start_success())

            await asyncio.gather(*coros)
            self.logger.debug('Deployment started successfully')
        except:
            self.close()
            raise

    def join(self):
        """Wait until all pods exit"""
        try:
            if self.uses_before_pod is not None:
                self.uses_before_pod.join()
            if self.uses_after_pod is not None:
                self.uses_after_pod.join()
            if self.shards:
                for shard_id in self.shards:
                    self.shards[shard_id].join()
            if self.head_pod is not None:
                self.head_pod.join()
            if self.gateway_pod is not None:
                self.gateway_pod.join()
        except KeyboardInterrupt:
            pass
        finally:
            self.head_pod = None
            if self.shards:
                for shard_id in self.shards:
                    self.shards[shard_id].clear_pods()

    @property
    def is_ready(self) -> bool:
        """Check if Deployment is ready

        .. note::
            A Deployment is ready when all the Pods it contains are ready


        .. # noqa: DAR201
        """
        is_ready = True
        if self.head_pod is not None:
            is_ready = self.head_pod.is_ready.is_set()
        if is_ready:
            for shard_id in self.shards:
                is_ready = self.shards[shard_id].is_ready
        if is_ready and self.uses_before_pod is not None:
            is_ready = self.uses_before_pod.is_ready.is_set()
        if is_ready and self.uses_after_pod is not None:
            is_ready = self.uses_after_pod.is_ready.is_set()
        if is_ready and self.gateway_pod is not None:
            is_ready = self.gateway_pod.is_ready.is_set()
        return is_ready

    @staticmethod
    def _parse_devices(value: str, num_devices: int):
        """Parse a list of devices from string, like `start:stop:step` or 'num1,num2,num3` or combination of both.

        :param value: a string-like
        :param num_devices: total number of devices
        :return: slice
        """

        use_uuids = False
        if re.match(WRAPPED_SLICE_BASE, value):
            value = value[1:-1]

        if value:
            parts = value.split(',')
            if len(parts) == 1:
                parts = value.split(':')

                if len(parts) == 1:
                    try:
                        int(parts[0])
                    except:
                        use_uuids = True
                    if use_uuids:
                        return parts
                    parts = [parts[0], str(int(parts[0]) + 1)]
            else:
                # try to detect if parts are not numbers
                try:
                    int(parts[0])
                except:
                    use_uuids = True

                if not use_uuids:
                    return [int(p) for p in parts]
                else:
                    return parts
        else:
            parts = []

        all_devices = range(num_devices)
        return all_devices[slice(*[int(p) if p else None for p in parts])]

    @staticmethod
    def _roundrobin_cuda_device(device_str: Optional[str], replicas: int):
        """Parse CUDA device string with RR prefix

        :param device_str: `RRm:n`, where `RR` is the prefix, m:n is python slice format
        :param replicas: the number of replicas
        :return: a map from replica ID to device ID
        """
        if (
            device_str
            and isinstance(device_str, str)
            and device_str.startswith('RR')
            and replicas >= 1
        ):
            try:
                num_devices = str(subprocess.check_output(['nvidia-smi', '-L'])).count(
                    'UUID'
                )
            except:
                num_devices = int(os.environ.get('CUDA_TOTAL_DEVICES', 0))
                if num_devices == 0:
                    return

            selected_devices = []
            if device_str[2:]:
                for device in Deployment._parse_devices(device_str[2:], num_devices):
                    selected_devices.append(device)
            else:
                selected_devices = range(num_devices)
            _c = cycle(selected_devices)
            return {j: next(_c) for j in range(replicas)}

    def _set_pod_args(self) -> Dict[int, List[Namespace]]:
        result = {}
        shards = getattr(self.args, 'shards', 1)
        replicas = getattr(self.args, 'replicas', 1)
        if self.args.deployment_role == DeploymentRoleType.GATEWAY:
            replicas = 1
        sharding_enabled = shards and shards > 1

        cuda_device_map = None
        if self.args.env or os.environ.get('CUDA_VISIBLE_DEVICES', '').startswith('RR'):
            args_env = self.args.env or {}
            cuda_visible_devices = args_env.get(
                'CUDA_VISIBLE_DEVICES'
            ) or os.environ.get('CUDA_VISIBLE_DEVICES', None)

            cuda_device_map = Deployment._roundrobin_cuda_device(
                cuda_visible_devices, replicas
            )

        all_shard_pod_ports = self.args.peer_ports or {'0': []}
        if isinstance(all_shard_pod_ports, str):
            all_shard_pod_ports = json.loads(all_shard_pod_ports)
        if isinstance(all_shard_pod_ports, list):
            # it is a single shard
            all_shard_pod_ports = {'0': all_shard_pod_ports}

        peer_ports_all_shards = {}
        for k, v in all_shard_pod_ports.items():
            peer_ports_all_shards[str(k)] = v

        if self.args.stateful and len(peer_ports_all_shards.keys()) < shards:
            raise ValueError(
                'The configuration of `peer_ports` does not match the number of shards requested'
            )

        for shard_id in range(shards):
            peer_ports = peer_ports_all_shards.get(str(shard_id), [])
            if len(peer_ports) > 0 and len(peer_ports) != replicas:
                raise ValueError(
                    'peer-ports argument does not match number of replicas, it will be ignored'
                )
            elif len(peer_ports) == 0:
                peer_ports = [random_port() for _ in range(replicas)]

            replica_args = []

            for replica_id, peer_port in zip(range(replicas), peer_ports):
                _args = copy.deepcopy(self.args)
                if self.args.deployment_role == DeploymentRoleType.GATEWAY:
                    _args.replicas = replicas
                _args.shard_id = shard_id
                _args.replica_id = replica_id
                # for gateway pods, the pod role shouldn't be changed
                if _args.pod_role != PodRoleType.GATEWAY:
                    _args.pod_role = PodRoleType.WORKER
                    if len(self.args.host) == replicas:
                        _args.host = self.args.host[replica_id]
                    else:
                        _args.host = self.args.host[0]
                else:
                    _args.host = self.args.host

                if cuda_device_map:
                    _args.env = _args.env or {}
                    _args.env['CUDA_VISIBLE_DEVICES'] = str(cuda_device_map[replica_id])

                if _args.name:
                    _args.name += (
                        f'/shard-{shard_id}/rep-{replica_id}'
                        if sharding_enabled
                        else f'/rep-{replica_id}'
                    )
                else:
                    _args.name = f'{replica_id}'

                # the gateway needs to respect the assigned port
                if self.args.deployment_role == DeploymentRoleType.GATEWAY:
                    _args.port = self.args.port

                elif not self.external:
                    if shards == 1 and replicas == 1:
                        if len(_args.protocol) > 1 and self._include_gateway:
                            _args.port = [
                                random_port() for _ in range(len(self.args.protocol))
                            ]
                        else:
                            _args.port = self.args.port
                        _args.port_monitoring = self.args.port_monitoring

                    elif shards == 1:
                        _args.port_monitoring = (
                            random_port()
                            if replica_id >= len(self.args.all_port_monitoring)
                            else self.args.all_port_monitoring[replica_id]
                        )
                        # if there are no shards/replicas, we dont need to distribute ports randomly
                        # we should rather use the pre assigned one
                        _args.port = [
                            random_port() for _ in range(len(self.args.protocol))
                        ]
                        _args.port[0] = peer_port
                    elif shards > 1:
                        port_monitoring_index = (
                            replica_id + replicas * shard_id + 1
                        )  # the first index is for the head
                        _args.port_monitoring = (
                            random_port()
                            if port_monitoring_index
                            >= len(self.args.all_port_monitoring)
                            else self.args.all_port_monitoring[
                                port_monitoring_index
                            ]  # we skip the head port here
                        )
                        _args.port = [peer_port]
                    else:
                        _args.port = [peer_port]
                        _args.port_monitoring = random_port()

                else:
                    _args.port = [self.ext_repl_ports[replica_id]]
                    _args.host = self.ext_repl_hosts[replica_id]
                    _args.scheme = self.ext_repl_schemes[replica_id]
                    _args.tls = self.ext_repl_tls[replica_id]

                # pod workspace if not set then derive from workspace
                if not _args.workspace:
                    _args.workspace = self.args.workspace
                replica_args.append(_args)
            result[shard_id] = replica_args

        return result

    @staticmethod
    def _set_uses_before_after_args(args: Namespace, entity_type: str) -> Namespace:
        _args = copy.deepcopy(args)
        _args.pod_role = PodRoleType.WORKER
        _args.host = _args.host[0] or __default_host__
        _args.port = [random_port()]

        if _args.name:
            _args.name += f'/{entity_type}-0'
        else:
            _args.name = f'{entity_type}-0'

        if 'uses_before' == entity_type:
            _args.uses_requests = None
            _args.uses = args.uses_before or __default_executor__
        elif 'uses_after' == entity_type:
            _args.uses_requests = None
            _args.uses = args.uses_after or __default_executor__
        else:
            raise ValueError(
                f'uses_before/uses_after pod does not support type {entity_type}'
            )

        # pod workspace if not set then derive from workspace
        if not _args.workspace:
            _args.workspace = args.workspace
        return _args

    def _parse_base_deployment_args(self, args):
        parsed_args = {
            'head': None,
            'uses_before': None,
            'uses_after': None,
            'gateway': None,
            'pods': {},
        }

        if self.args.stateful and self.args.replicas in [1, 2]:
            self.logger.debug(
                'Stateful Executor is not recommended to be used less than 3 replicas'
            )

        if self.args.stateful and self.args.workspace is None:
            raise ValueError(
                'Stateful Executors need to be provided `workspace` when used in a Deployment'
            )

        # a gateway has no heads and uses
        # also there a no heads created, if there are no shards
        if self.role != DeploymentRoleType.GATEWAY and getattr(args, 'shards', 1) > 1:
            if (
                getattr(args, 'uses_before', None)
                and args.uses_before != __default_executor__
            ):
                uses_before_args = self._set_uses_before_after_args(
                    args, entity_type='uses_before'
                )
                parsed_args['uses_before'] = uses_before_args
                args.uses_before_address = (
                    f'{uses_before_args.host}:{uses_before_args.port[0]}'
                )
            if (
                getattr(args, 'uses_after', None)
                and args.uses_after != __default_executor__
            ):
                uses_after_args = self._set_uses_before_after_args(
                    args, entity_type='uses_after'
                )
                parsed_args['uses_after'] = uses_after_args
                args.uses_after_address = (
                    f'{uses_after_args.host}:{uses_after_args.port[0]}'
                )

            parsed_args['head'] = Deployment._copy_to_head_args(args)

        parsed_args['pods'] = self._set_pod_args()

        if parsed_args['head'] is not None:
            connection_list = defaultdict(list)

            for shard_id in parsed_args['pods']:
                for pod_idx, pod_args in enumerate(parsed_args['pods'][shard_id]):
                    worker_host = self.get_worker_host(pod_args, self._is_docker, False)
                    connection_list[shard_id].append(
                        f'{worker_host}:{pod_args.port[0]}'
                    )
            parsed_args['head'].connection_list = json.dumps(connection_list)

        return parsed_args

    @property
    def _mermaid_str(self) -> List[str]:
        """String that will be used to represent the Deployment graphically when `Flow.plot()` is invoked.
        It does not include used_before/uses_after


        .. # noqa: DAR201
        """
        mermaid_graph = []
        secret = '&ltsecret&gt'
        if self.role != DeploymentRoleType.GATEWAY and not self.external:
            mermaid_graph = [f'subgraph {self.name};', '\ndirection LR;\n']

            uses_before_name = (
                self.uses_before_args.name
                if self.uses_before_args is not None
                else None
            )
            uses_before_uses = (
                replace_secret_of_hub_uri(self.uses_before_args.uses, secret)
                if self.uses_before_args is not None
                else None
            )
            uses_after_name = (
                self.uses_after_args.name if self.uses_after_args is not None else None
            )
            uses_after_uses = (
                replace_secret_of_hub_uri(self.uses_after_args.uses, secret)
                if self.uses_after_args is not None
                else None
            )
            shard_names = []
            if len(self.pod_args['pods']) > 1:
                # multiple shards
                for shard_id, pod_args in self.pod_args['pods'].items():
                    shard_name = f'{self.name}/shard-{shard_id}'
                    shard_names.append(shard_name)
                    shard_mermaid_graph = [
                        f'subgraph {shard_name};',
                        '\ndirection TB;\n',
                    ]
                    names = [
                        args.name for args in pod_args
                    ]  # all the names of each of the replicas
                    uses = [
                        args.uses for args in pod_args
                    ]  # all the uses should be the same but let's keep it this
                    # way
                    for rep_i, (name, use) in enumerate(zip(names, uses)):
                        escaped_uses = f'"{replace_secret_of_hub_uri(use, secret)}"'
                        shard_mermaid_graph.append(f'{name}[{escaped_uses}]:::pod;')
                    shard_mermaid_graph.append('end;')
                    shard_mermaid_graph = [
                        node.replace(';', '\n') for node in shard_mermaid_graph
                    ]
                    mermaid_graph.extend(shard_mermaid_graph)
                    mermaid_graph.append('\n')
                if uses_before_name is not None:
                    for shard_name in shard_names:
                        escaped_uses_before_uses = (
                            f'"{replace_secret_of_hub_uri(uses_before_uses, secret)}"'
                        )
                        mermaid_graph.append(
                            f'{self.args.name}-head[{escaped_uses_before_uses}]:::HEADTAIL --> {shard_name};'
                        )
                if uses_after_name is not None:
                    for shard_name in shard_names:
                        escaped_uses_after_uses = f'"{uses_after_uses}"'
                        mermaid_graph.append(
                            f'{shard_name} --> {self.args.name}-tail[{escaped_uses_after_uses}]:::HEADTAIL;'
                        )
            else:
                # single shard case, no uses_before or uses_after_considered
                pod_args = list(self.pod_args['pods'].values())[0][0]
                uses = f'"{replace_secret_of_hub_uri(pod_args.uses, secret)}"'

                # just put the replicas in parallel
                if pod_args.replicas > 1:
                    for rep_i in range(pod_args.replicas):
                        mermaid_graph.append(
                            f'{pod_args.name}/rep-{rep_i}["{uses}"]:::pod;'
                        )
                else:
                    mermaid_graph.append(f'{pod_args.name}["{uses}"]:::pod;')

            mermaid_graph.append('end;')
        return mermaid_graph

    def block(
        self,
        stop_event: Optional[Union['threading.Event', 'multiprocessing.Event']] = None,
    ):
        """Block the Deployment until `stop_event` is set or user hits KeyboardInterrupt

        :param stop_event: a threading event or a multiprocessing event that once set will resume the control flow
            to main thread.
        """

        def _reload_deployment(changed_file):
            self.logger.info(
                f'change in Executor configuration YAML {changed_file} observed, reloading Executor deployment'
            )
            self.__exit__(None, None, None)
            new_deployment = Deployment(
                self.args, self.needs, include_gateway=self._include_gateway
            )
            self.__dict__ = new_deployment.__dict__
            self.__enter__()

        try:
            watch_changes = self.args.reload

            if watch_changes and self._is_executor_from_yaml:
                with ImportExtensions(
                    required=True,
                    help_text='''reload requires watchfiles dependency to be installed. You can run `pip install 
                    watchfiles''',
                ):
                    from watchfiles import watch

                new_stop_event = stop_event or threading.Event()
                if self._is_executor_from_yaml:
                    for changes in watch(*[self.args.uses], stop_event=new_stop_event):
                        for _, changed_file in changes:
                            _reload_deployment(self.args.uses)
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

    def _get_summary_table(self, all_panels: List[Panel]):
        address_table = self._init_table()

        if not isinstance(self.protocol, list):
            _protocols = [str(self.protocol)]
        else:
            _protocols = [str(_p) for _p in self.protocol]

        if not isinstance(self.first_pod_args.port, list):
            _ports = [self.first_pod_args.port]
        else:
            _ports = [str(_p) for _p in self.first_pod_args.port]

        swagger_ui_link = None
        redoc_link = None
        for _port, _protocol in zip(_ports, _protocols):
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

            if _protocol == ProtocolType.HTTP.to_string().lower():
                swagger_ui_link = f'[link={_protocol}://{self.host}:{_port}/docs]{self.host}:{_port}/docs'
                redoc_link = f'[link={_protocol}://{self.host}:{_port}/redoc]{self.host}:{_port}/redoc'

        all_panels.append(
            Panel(
                address_table,
                title=':link: [b]Endpoint[/]',
                expand=False,
            )
        )

        if ProtocolType.HTTP.to_string().lower() in [p.lower() for p in _protocols]:
            http_ext_table = self._init_table()
            http_ext_table.add_row(':speech_balloon:', 'Swagger UI', swagger_ui_link)

            http_ext_table.add_row(':books:', 'Redoc', redoc_link)

            all_panels.append(
                Panel(
                    http_ext_table,
                    title=':gem: [b]HTTP extension[/]',
                    expand=False,
                )
            )

        if self.args.monitoring:
            monitor_ext_table = self._init_table()

            for replica in self.pod_args['pods'][0]:
                monitor_ext_table.add_row(
                    ':flashlight:',  # upstream issue: they dont have :torch: emoji, so we use :flashlight:
                    # to represent observability of Prometheus (even they have :torch: it will be a war
                    # between AI community and Cloud-native community fighting on this emoji)
                    replica.name,
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

    @property
    def _docker_compose_address(self):
        from jina.orchestrate.deployments.config.docker_compose import port
        from jina.orchestrate.deployments.config.helper import to_compatible_name

        if self.external:
            docker_compose_address = [f'{self.protocol}://{self.host}:{self.port}']
        elif self.head_args:
            docker_compose_address = [
                f'{to_compatible_name(self.head_args.name)}:{port}'
            ]
        else:
            if self.args.replicas == 1 or self.name == 'gateway':
                docker_compose_address = [f'{to_compatible_name(self.name)}:{port}']
            else:
                docker_compose_address = []
                for rep_id in range(self.args.replicas):
                    node_name = f'{self.name}/rep-{rep_id}'
                    docker_compose_address.append(
                        f'{to_compatible_name(node_name)}:{port}'
                    )
        return docker_compose_address

    def _to_docker_compose_config(self, deployments_addresses=None):
        from jina.orchestrate.deployments.config.docker_compose import (
            DockerComposeConfig,
        )

        docker_compose_deployment = DockerComposeConfig(
            args=self.args, deployments_addresses=deployments_addresses
        )
        return docker_compose_deployment.to_docker_compose_config()

    def _inner_gateway_to_docker_compose_config(self):
        from jina.orchestrate.deployments.config.docker_compose import (
            DockerComposeConfig,
        )

        self.pod_args['gateway'].port = self.pod_args['gateway'].port or [random_port()]
        cargs = copy.deepcopy(self.pod_args['gateway'])
        cargs.uses = __default_grpc_gateway__
        cargs.graph_description = (
            f'{{"{self.name}": ["end-gateway"], "start-gateway": ["{self.name}"]}}'
        )

        docker_compose_deployment = DockerComposeConfig(
            args=cargs,
            deployments_addresses={self.name: self._docker_compose_address},
        )
        return docker_compose_deployment.to_docker_compose_config()

    def to_docker_compose_yaml(
        self,
        output_path: Optional[str] = None,
        network_name: Optional[str] = None,
    ):
        """
        Converts a Jina Deployment into a Docker compose YAML file

        If you don't want to rebuild image on Executor Hub,
        you can set `JINA_HUB_NO_IMAGE_REBUILD` environment variable.

        :param output_path: The path to dump the YAML file to
        :param network_name: The name of the network that will be used by the deployment
        """
        import yaml

        output_path = output_path or 'docker-compose.yml'
        network_name = network_name or 'jina-network'

        docker_compose_dict = {
            'version': '3.3',
            'networks': {network_name: {'driver': 'bridge'}},
        }
        services = {}

        service_configs = self._to_docker_compose_config()

        for service_name, service in service_configs:
            service['networks'] = [network_name]
            services[service_name] = service

        if self._include_gateway:
            service_configs = self._inner_gateway_to_docker_compose_config()

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
            f'Docker Compose file has been created under [b]{output_path}[/b]. You can use it by running [b]{command}[/b]'
        )

    def _to_kubernetes_yaml(
        self,
        output_base_path: str,
        k8s_namespace: Optional[str] = None,
        k8s_deployments_addresses: Optional[Dict] = None,
    ):
        import yaml

        from jina.orchestrate.deployments.config.k8s import K8sDeploymentConfig

        if self.external:
            self.logger.warning(
                'The Deployment is external, cannot create YAML deployment files'
            )
            return

        if self.args.name == 'gateway':
            if self.args.default_port:
                from jina.serve.networking import GrpcConnectionPool

                self.args.port = [
                    GrpcConnectionPool.K8S_PORT + i
                    for i in range(len(self.args.protocol))
                ]
                self.first_pod_args.port = [
                    GrpcConnectionPool.K8S_PORT + i
                    for i in range(len(self.args.protocol))
                ]

                self.args.port_monitoring = GrpcConnectionPool.K8S_PORT_MONITORING
                self.first_pod_args.port_monitoring = (
                    GrpcConnectionPool.K8S_PORT_MONITORING
                )

                self.args.default_port = False

            self.args.deployments_addresses = k8s_deployments_addresses
        else:
            if len(self.args.protocol) > 1 and len(self.args.port) != len(
                self.args.protocol
            ):
                from jina.serve.networking import GrpcConnectionPool

                self.args.port = [
                    GrpcConnectionPool.K8S_PORT + i
                    for i in range(len(self.args.protocol))
                ]
        k8s_deployment = K8sDeploymentConfig(
            args=self.args, k8s_namespace=k8s_namespace
        )

        configs = k8s_deployment.to_kubernetes_yaml()

        for name, k8s_objects in configs:
            filename = os.path.join(output_base_path, f'{name}.yml')
            os.makedirs(output_base_path, exist_ok=True)
            with open(filename, 'w+', encoding='utf-8') as fp:
                for i, k8s_object in enumerate(k8s_objects):
                    yaml.dump(k8s_object, fp)
                    if i < len(k8s_objects) - 1:
                        fp.write('---\n')

    def to_kubernetes_yaml(
        self,
        output_base_path: str,
        k8s_namespace: Optional[str] = None,
    ):
        """
        Convert a Jina Deployment into a set of YAML deployments to deploy in Kubernetes.

        If you don't want to rebuild image on Executor Hub,
        you can set `JINA_HUB_NO_IMAGE_REBUILD` environment variable.

        :param output_base_path: The base path where to dump all the YAML files
        :param k8s_namespace: The name of the k8s namespace to set for the configurations. If None, the name of the Flow will be used.
        """
        k8s_namespace = k8s_namespace or 'default'
        # the Deployment conversion needs to be done in a version without Gateway included. Deployment does quite some changes to its args
        # to let some of the args (like ports) go to the gateway locally. In Kubernetes, we want no gateway
        self._to_kubernetes_yaml(
            output_base_path=output_base_path,
            k8s_namespace=k8s_namespace,
        )
        self.logger.info(
            f'K8s YAML files have been created under [b]{output_base_path}[/]. You can use it by running [b]kubectl apply -R -f {output_base_path}[/]'
        )

    to_k8s_yaml = to_kubernetes_yaml
