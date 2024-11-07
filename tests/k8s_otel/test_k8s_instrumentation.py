import asyncio
import os
from typing import Dict, List

import pytest
import requests

from jina import Flow
from jina.logging.logger import JinaLogger
from tests.k8s_otel.kind_wrapper import KindClusterWrapperV2
from tests.k8s_otel.util import get_last_health_check_data, parse_string_jaeger_tags


@pytest.mark.asyncio
@pytest.mark.timeout(1800)
async def test_flow_resource_labeling(
    tmpdir, otel_test_namespace: str, k8s_cluster_v2: KindClusterWrapperV2
):
    NAMESPACE = 'test-flow-resource-labeling'
    dump_path = os.path.join(tmpdir, NAMESPACE)
    logger = JinaLogger(NAMESPACE)

    # Create k8s flow artifacts
    flow = Flow(
        name='test-flow-metrics',
        port=8080,
        metrics=True,
        metrics_exporter_host=f'http://otel-collector.{otel_test_namespace}.svc.cluster.local',
        metrics_exporter_port=4317,
        tracing=True,
        traces_exporter_host=f'http://jaeger.{otel_test_namespace}.svc.cluster.local',
        traces_exporter_port=4317,
    ).add(
        name='instrumentation',
        uses='docker://test-instrumentation:test-pip',
    )

    flow.to_kubernetes_yaml(dump_path, k8s_namespace=NAMESPACE)

    # Deploy flow
    k8s_cluster_v2.deploy_from_dir(dir=dump_path, namespace=NAMESPACE)

    # Make client requests
    with k8s_cluster_v2.port_forward(
        'svc/gateway', NAMESPACE, svc_port=8080
    ) as gateway_port:
        from jina import Client
        res = []
        async for docs in Client(port=gateway_port, asyncio=True).post("/"):
            res.extend(docs)
    # # Give grace period for metrics and traces to be exported
    await asyncio.sleep(60)
    #
    # Check Jaeger API
    with k8s_cluster_v2.port_forward(
        'svc/jaeger', otel_test_namespace, svc_port=16686
    ) as jaeger_port:
        try:
            # Gateway
            trace_data = get_last_health_check_data(
                jaeger_port=jaeger_port, service_name='gateway'
            )
            assert trace_data['processes']['p1']['serviceName'] == 'gateway'
            tags: Dict[str, str] = parse_string_jaeger_tags(
                trace_data['processes']['p1']['tags']
            )
            assert tags['k8s.deployment.name'] == 'gateway'
            assert tags['k8s.namespace.name'] == NAMESPACE
            assert tags['k8s.pod.name'].startswith('gateway-')

            # Instrumentation Executor
            trace_data = get_last_health_check_data(
                jaeger_port=jaeger_port, service_name='instrumentation'
            )
            assert trace_data['processes']['p1']['serviceName'] == 'instrumentation'
            tags: Dict[str, str] = parse_string_jaeger_tags(
                trace_data['processes']['p1']['tags']
            )
            assert tags['k8s.deployment.name'] == 'instrumentation'
            assert tags['k8s.namespace.name'] == NAMESPACE
            assert tags['k8s.pod.name'].startswith('instrumentation-')
        except AssertionError as e:
            logger.error(trace_data)
            raise e

    with k8s_cluster_v2.port_forward(
        'svc/prometheus', otel_test_namespace, svc_port=9090
    ) as prometheus_port:
        try:
            # Check Prometheus Labels
            prometheus_labels: List[str] = requests.get(
                f'http://localhost:{prometheus_port}/api/v1/labels'
            ).json()['data']
            assert 'k8s_deployment_name' in prometheus_labels
            assert 'k8s_namespace_name' in prometheus_labels
            assert 'k8s_pod_name' in prometheus_labels
        except AssertionError as e:
            logger.error(prometheus_labels)
            raise e

        try:
            depl_values: List[str] = requests.get(
                f'http://localhost:{prometheus_port}/api/v1/label/k8s_deployment_name/values'
            ).json()['data']
            assert 'gateway' in depl_values
            assert 'instrumentation' in depl_values
        except AssertionError as e:
            logger.error(depl_values)
            raise e

        try:
            ns_values: List[str] = requests.get(
                f'http://localhost:{prometheus_port}/api/v1/label/k8s_namespace_name/values'
            ).json()['data']
            assert NAMESPACE in ns_values
        except AssertionError as e:
            logger.error(ns_values)
            raise e

        try:
            pod_values: List[str] = requests.get(
                f'http://localhost:{prometheus_port}/api/v1/label/k8s_pod_name/values'
            ).json()['data']
            assert any(i.startswith('gateway-') for i in pod_values)
            assert any(i.startswith('instrumentation-') for i in pod_values)
        except AssertionError as e:
            logger.error(pod_values)
            raise e
