import json
import time

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from prometheus_client import Summary

from jina.serve.instrumentation import MetricsTimer


@pytest.fixture
def metrics_setup():
    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    meter_provider = meter_provider
    meter = meter_provider.get_meter('test')
    yield metric_reader, meter
    if hasattr(meter_provider, 'force_flush'):
        metric_reader.force_flush()
    if hasattr(meter_provider, 'shutdown'):
        meter_provider.shutdown()


def test_timer_context(metrics_setup):
    def _do_something():
        time.sleep(0.1)

    metric_reader, meter = metrics_setup
    summary = Summary('time_taken', 'measure something')
    histogram = meter.create_histogram(
        name='time_taken', description='measure something'
    )

    with MetricsTimer(summary_metric=summary, histogram=histogram):
        _do_something()

    # Prometheus samples
    summary_count_sample = [
        sample.value for sample in list(summary._samples()) if '_count' == sample.name
    ]
    assert 1.0 == summary_count_sample[0]
    # OpenTelemetry samples
    histogram_metric = json.loads(
        metric_reader.get_metrics_data()
        .resource_metrics[0]
        .scope_metrics[0]
        .metrics[0]
        .to_json()
    )
    assert 'time_taken' == histogram_metric['name']
    assert 1 == histogram_metric['data']['data_points'][0]['count']


def test_timer_decorator(metrics_setup):
    metric_reader, meter = metrics_setup
    summary = Summary('time_taken_decorator', 'measure something')
    histogram = meter.create_histogram(
        name='time_taken_decorator', description='measure something'
    )

    @MetricsTimer(summary, histogram)
    def _sleep():
        time.sleep(0.1)

    _sleep()

    # Prometheus samples
    summary_count_sample = [
        sample.value for sample in list(summary._samples()) if '_count' == sample.name
    ]
    assert 1.0 == summary_count_sample[0]
    # OpenTelemetry samples
    histogram_metric = json.loads(
        metric_reader.get_metrics_data()
        .resource_metrics[0]
        .scope_metrics[0]
        .metrics[0]
        .to_json()
    )
    assert 'time_taken_decorator' == histogram_metric['name']
    assert 1 == histogram_metric['data']['data_points'][0]['count']
    assert {} == histogram_metric['data']['data_points'][0]['attributes']

    labels = {
        'cat': 'meow',
        'dog': 'woof',
    }

    @MetricsTimer(summary, histogram, labels)
    def _sleep_2():
        time.sleep(0.1)

    _sleep_2()

    # Prometheus samples
    summary_count_sample = [
        sample.value for sample in list(summary._samples()) if '_count' == sample.name
    ]
    assert 2.0 == summary_count_sample[0]
    # OpenTelemetry samples
    histogram_metric = json.loads(
        metric_reader.get_metrics_data()
        .resource_metrics[0]
        .scope_metrics[0]
        .metrics[0]
        .to_json()
    )
    assert 'time_taken_decorator' == histogram_metric['name']
    assert 1 == histogram_metric['data']['data_points'][1]['count']
    assert labels == histogram_metric['data']['data_points'][1]['attributes']
