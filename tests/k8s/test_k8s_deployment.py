import asyncio
import os

import pytest
from docarray import DocumentArray
from pytest_kind import cluster
from jina.serve.networking import GrpcConnectionPool
from jina.serve.runtimes.servers import BaseServer

from jina import Deployment, Client
from tests.k8s.conftest import shell_portforward

cluster.KIND_VERSION = 'v0.11.1'


async def create_executor_deployment_and_wait_ready(
    deployment_dump_path,
    namespace,
    api_client,
    app_client,
    core_client,
    deployment_replicas_expected,
    logger,
):
    from kubernetes import utils

    namespace = namespace.lower()
    namespace_object = {
        'apiVersion': 'v1',
        'kind': 'Namespace',
        'metadata': {'name': f'{namespace}'},
    }
    try:
        logger.info(f'create Namespace {namespace}')
        utils.create_from_dict(api_client, namespace_object)
    except:
        pass

    while True:
        ns_items = core_client.list_namespace().items
        if any(item.metadata.name == namespace for item in ns_items):
            logger.info(f'created Namespace {namespace}')
            break
        logger.info(f'waiting for Namespace {namespace}')
        await asyncio.sleep(1.0)

    file_set = set(os.listdir(deployment_dump_path))
    for file in file_set:
        try:
            utils.create_from_yaml(
                api_client,
                yaml_file=os.path.join(deployment_dump_path, file),
                namespace=namespace,
            )
        except Exception as e:
            # some objects are not successfully created since they exist from previous files
            logger.info(f'Did not create resource from {file} for pod due to {e} ')
            pass

    # wait for all the pods to be up
    expected_deployments = sum(deployment_replicas_expected.values())
    while True:
        namespaced_pods = core_client.list_namespaced_pod(namespace)
        if (
            namespaced_pods.items is not None
            and len(namespaced_pods.items) == expected_deployments
        ):
            break
        logger.info(
            f'Waiting for all {expected_deployments} Deployments to be created, only got {len(namespaced_pods.items) if namespaced_pods.items is not None else None}'
        )
        await asyncio.sleep(1.0)

    # wait for all the pods to be up
    resp = app_client.list_namespaced_deployment(namespace=namespace)
    deployment_names = set([item.metadata.name for item in resp.items])
    while len(deployment_names) > 0:
        deployments_ready = []
        for deployment_name in deployment_names:
            api_response = app_client.read_namespaced_deployment(
                name=deployment_name, namespace=namespace
            )

            expected_num_replicas = deployment_replicas_expected[deployment_name]
            if (
                api_response.status.ready_replicas is not None
                and api_response.status.ready_replicas == expected_num_replicas
            ):
                logger.info(f'Deployment {deployment_name} is now ready')
                deployments_ready.append(deployment_name)
            else:
                logger.info(
                    f'Deployment {deployment_name} is not ready yet: ready_replicas is {api_response.status.ready_replicas} not equal to {expected_num_replicas}'
                )

        for deployment_name in deployments_ready:
            deployment_names.remove(deployment_name)
        logger.info(f'Waiting for {deployment_names} to be ready')
        await asyncio.sleep(1.0)


@pytest.mark.asyncio
@pytest.mark.timeout(3600)
@pytest.mark.parametrize(
    'docker_images',
    [['test-executor', 'jinaai/jina']],
    indirect=True,
)
@pytest.mark.parametrize('shards', [1, 2])
@pytest.mark.parametrize('replicas', [1, 2])
@pytest.mark.parametrize('protocol', ['grpc', 'http'])
async def test_deployment_serve_k8s(
    logger, docker_images, shards, replicas, protocol, tmpdir, k8s_cluster
):
    if protocol == 'http' and (shards > 1 or replicas == 1):
        # shards larger than 1 are not supported, and replicas limitation is to speed up test
        return
    from kubernetes import client

    namespace = f'test-deployment-serve-k8s-{shards}-{replicas}-{protocol}'
    api_client = client.ApiClient()
    core_client = client.CoreV1Api(api_client=api_client)
    app_client = client.AppsV1Api(api_client=api_client)

    port = GrpcConnectionPool.K8S_PORT
    try:
        dep = Deployment(
            name='test-executor',
            uses=f'docker://{docker_images[0]}',
            shards=shards,
            protocol=protocol,
            replicas=replicas,
        )

        dump_path = os.path.join(
            str(tmpdir), f'test-deployment-serve-k8s-{shards}-{replicas}'
        )
        dep.to_kubernetes_yaml(dump_path, k8s_namespace=namespace)

        deployment_replicas_expected = (
            {'test-executor': replicas}
            if shards == 1
            else {
                'test-executor-head': 1,
                **{f'test-executor-{i}': replicas for i in range(shards)},
            }
        )

        await create_executor_deployment_and_wait_ready(
            dump_path,
            namespace=namespace,
            api_client=api_client,
            app_client=app_client,
            core_client=core_client,
            deployment_replicas_expected=deployment_replicas_expected,
            logger=logger,
        )
        # start port forwarding
        from jina.clients import Client

        service_name = 'svc/test-executor' if shards == 1 else 'svc/test-executor-head'

        with shell_portforward(
            k8s_cluster._cluster.kubectl_path,
            service_name,
            port,
            port,
            namespace,
        ):
            client = Client(port=port, asyncio=True, protocol=protocol)

            # test with streaming
            async for docs in client.post(
                '/debug', inputs=DocumentArray.empty(3), stream=True
            ):
                for doc in docs:
                    assert doc.tags['shards'] == shards
                    assert doc.tags['parallel'] == replicas

            # test without streaming
            # without streaming, replicas are properly supported
            visited = set()
            async for docs in client.post(
                '/debug', inputs=DocumentArray.empty(20), stream=False, request_size=1
            ):
                for doc in docs:
                    assert doc.tags['shards'] == shards
                    assert doc.tags['parallel'] == replicas
                    visited.add(doc.tags['hostname'])

            # port forwarding will always hit the same replica, therefore, with no head, there is no proper
            # load balancing mechanism with just port forwarding
            if not (shards == 1 and replicas == 2):
                assert len(visited) == shards * replicas

    except Exception as exc:
        logger.error(f' Exception raised {exc}')
        raise exc


@pytest.mark.asyncio
@pytest.mark.timeout(3600)
@pytest.mark.parametrize(
    'docker_images',
    [['test-executor', 'jinaai/jina']],
    indirect=True,
)
async def test_deployment_with_multiple_protocols(
    logger, docker_images, tmpdir, k8s_cluster
):
    from kubernetes import client

    api_client = client.ApiClient()
    core_client = client.CoreV1Api(api_client=api_client)
    app_client = client.AppsV1Api(api_client=api_client)
    namespace = f'test-deployment-serve-k8s-multiprotocol'
    try:

        dep = Deployment(
            name='test-executor',
            uses=f'docker://{docker_images[0]}',
            protocol=['grpc', 'http'],
        )

        dump_path = os.path.join(
            str(tmpdir), f'test-deployment-serve-k8s-multiprotocol'
        )
        dep.to_kubernetes_yaml(dump_path, k8s_namespace=namespace)

        deployment_replicas_expected = {'test-executor': 1}
        await create_executor_deployment_and_wait_ready(
            dump_path,
            namespace=namespace,
            api_client=api_client,
            app_client=app_client,
            core_client=core_client,
            deployment_replicas_expected=deployment_replicas_expected,
            logger=logger,
        )
        grpc_port = GrpcConnectionPool.K8S_PORT
        http_port = GrpcConnectionPool.K8S_PORT + 1

        with shell_portforward(
            k8s_cluster._cluster.kubectl_path,
            pod_or_service='service/test-executor-1-http',
            port1=http_port,
            port2=http_port,
            namespace=namespace,
        ):
            import requests

            resp = requests.get(f'http://localhost:{http_port}').json()
            assert resp == {}

        with shell_portforward(
            k8s_cluster._cluster.kubectl_path,
            pod_or_service='service/test-executor',
            port1=grpc_port,
            port2=grpc_port,
            namespace=namespace,
        ):
            grpc_client = Client(protocol='grpc', port=grpc_port, asyncio=True)
            async for _ in grpc_client.post('/', inputs=DocumentArray.empty(5)):
                pass
            assert BaseServer.is_ready(f'localhost:{grpc_port}')
    except Exception as exc:
        logger.error(f' Exception raised {exc}')
        raise exc
