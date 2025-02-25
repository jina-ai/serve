import random
from pathlib import Path
from typing import Callable, Dict, Tuple

import opentelemetry.sdk.metrics.view
import pytest
from opentelemetry.sdk.metrics.export import (
    AggregationTemporality,
    MetricExporter,
    MetricExportResult,
    MetricsData,
    PeriodicExportingMetricReader,
)


class DirMetricExporter(MetricExporter):
    """Implementation of :class:`MetricExporter` that prints metrics to a file in a given directory.

    This class can be used for diagnostic or testing purposes.
    """

    def __init__(
        self,
        metric_dir: str,
        preferred_temporality: Dict[type, AggregationTemporality] = None,
        preferred_aggregation: Dict[
            type, "opentelemetry.sdk.metrics.view.Aggregation"
        ] = None,
    ):
        print(f'JOAN IS HERE DIRMETRIC')
        super().__init__(
            preferred_temporality=preferred_temporality,
            preferred_aggregation=preferred_aggregation,
        )
        self.metric_filename: Path = Path(metric_dir) / str(random.randint(0, 1048575))
        self.f = open(self.metric_filename, 'a')

    def export(
        self,
        metrics_data: MetricsData,
        timeout_millis: float = 10_000,
        **kwargs,
    ) -> MetricExportResult:
        print(f'export to {self.metric_filename} => {metrics_data.to_json()[0:3]}')
        self.f.write(metrics_data.to_json())
        self.f.write('\n')
        self.f.flush()
        return MetricExportResult.SUCCESS

    def shutdown(self, timeout_millis: float = 30_000, **kwargs) -> None:
        pass

    def force_flush(self, timeout_millis: float = 10_000) -> bool:
        return True

    def __del__(self):
        self.f.close()


@pytest.fixture(scope='function')
def monkeypatch_metric_exporter(
    tmpdir_factory: pytest.TempdirFactory,
) -> Tuple[Callable, Callable]:
    import json
    import os
    import time
    from pathlib import Path

    import opentelemetry.sdk.metrics.export

    collect_path = Path(tmpdir_factory.mktemp('otel-collector'))
    metrics_path = collect_path / 'metrics'
    os.mkdir(metrics_path)

    tick_counter_filename = collect_path / 'tick_counter'
    with open(tick_counter_filename, 'w', encoding='utf-8') as f:
        f.write('0')

    def collect_metrics():
        print(f'tick_counter_filename {tick_counter_filename}')
        with open(tick_counter_filename, 'r', encoding='utf-8') as ft:
            tick_counter = int(ft.read())
        with open(tick_counter_filename, 'w', encoding='utf-8') as ft2:
            ft2.write(str(tick_counter + 1))
        time.sleep(2)

    def _get_service_name(otel_measurement):
        return otel_measurement['resource_metrics'][0]['resource']['attributes'][
            'service.name'
        ]

    def read_metrics():
        def read_metric_file(filename):
            print(f'filename {filename}')
            with open(filename, 'r', encoding='utf-8') as fr:
                r = fr.read()
                print(f'READ {r[0:3]}')
                try:
                    return json.loads(r)
                except:
                    return None

        ret = {}
        for i in map(read_metric_file, metrics_path.glob('*')):
            if i is not None:
                ret[_get_service_name(i)] = i
        return ret

    class PatchedTextReader(PeriodicExportingMetricReader):
        def __init__(self, *args, **kwargs) -> None:
            self.exporter = DirMetricExporter(metrics_path)
            self.tick_counter = 0

            super().__init__(
                exporter=self.exporter,
                export_interval_millis=500,
            )

        def _ticker(self) -> None:
            interval_secs = self._export_interval_millis / 1e3
            while not self._shutdown_event.wait(interval_secs):
                with open(tick_counter_filename, 'r', encoding='utf-8') as f:
                    tick_counter = int(f.read())
                if tick_counter != self.tick_counter:
                    self.tick_counter = tick_counter
                    self.collect(timeout_millis=self._export_timeout_millis)
            self.collect(timeout_millis=self._export_interval_millis)

    real_reader = opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader
    opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader = PatchedTextReader
    yield collect_metrics, read_metrics
    opentelemetry.sdk.metrics.export.PeriodicExportingMetricReader = real_reader
