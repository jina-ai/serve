(opentelemetry)=
# {octicon}`telescope-fill` OpenTelemetry Support

```{toctree}
:hidden:

opentelemetry-migration
monitoring
```

```{hint}
Prometheus-only based metrics collection will soon be deprecated. Refer to {ref}`Monitor with Prometheus and Grafana <monitoring>` for the old setup.
```

There are two major setups required to visualize/monitor your application's signals using [OpenTelemetry](https://opentelemetry.io). The first setup is covered by Jina-serve which integrates the [OpenTelemetry API and SDK](https://opentelemetry-python.readthedocs.io/en/stable/api/index.html) at the application level. The {ref}`Flow Instrumentation <instrumenting-flow>` page covers in detail the steps required to enable OpenTelemetry in a Flow. A {class}`~jina.Client` can also be instrumented which is documented in the {ref}`Client Instrumentation <instrumenting-client>` section.

This section covers the OpenTelemetry infrastructure setup required to collect, store and visualize the traces and metrics data exported by the Pods. This setup is the user's responsibility, and this section only serves as the initial/introductory guide to running OpenTelemetry infrastructure components.

Since OpenTelemetry is open source and is mostly responsible for the API standards and specification, various providers implement the specification. This section follows the default recommendations from the OpenTelemetry documentation that also fits into the Jina-serve implementations.

## Exporting traces and metrics data

Pods created using a {class}`~jina.Flow` with tracing or metrics enabled use the [SDK Exporters](https://opentelemetry.io/docs/instrumentation/python/exporters/) to send the data to a central [Collector](https://opentelemetry.io/docs/collector/) component. You can use this collector to further process and store the data for visualization and alerting. 

The push/export-based mechanism also allows the application to start pushing data immediately on startup. This differs from the pull-based mechanism where you need a separate scraping registry to discovery service to identify data scraping targets.

You can configure the exporter backend host and port using the `traces_exporter_host`, `traces_exporter_port`, `metrics_exporter_host` and `metrics_exporter_port`. Even though the Collector is metric data-type agnostic (it accepts any type of OpenTelemetry API data model), we provide separate configuration for Tracing and Metrics to give you more flexibility in choosing infrastructure components.

Jina-serve's default exporter implementation is  `OTLPSpanExporter` and `OTLPMetricExporter`. The exporters also use the gRPC data transfer protocol. The following environment variables can be used to further configure the exporter client based on your requirements. The full list of exporter related environment variables are documented by the [PythonSDK library](https://opentelemetry-python.readthedocs.io/en/latest/exporter/otlp/otlp.html). Apart from `OTEL_EXPORTER_OTLP_PROTOCOL` and `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`, you can use all other library version specific environment variables to configure the exporter clients.


## Collector

The [Collector](https://opentelemetry.io/docs/collector/) is a huge ecosystem of components that support features like scraping, collecting, processing and further exporting data to storage backends. The collector itself can also expose endpoints to allow scraping data. We recommend reading the official documentation to understand the the full set of features and configuration required to run a Collector. Read the below section to understand the minimum number of components and the respective configuration required for operating with Jina-serve.

We recommend using the [OpenTelemetry Collector](https://opentelemetry.io/docs/collector/) from the contrib repository. We also use:
- [Jaeger](https://www.jaegertracing.io) for collecting traces, visualizing tracing data and alerting based on tracing data.
- [Prometheus](https://prometheus.io) for collecting metric data and/or alerting.
- [Grafana](https://grafana.com) for visualizing data from Prometheus/Jaeger and/or alerting based on the data queried.

```{hint}
Jaeger provides a comprehensive out of the box tools for end-to-end tracing monitoring, visualization and alerting. You can substitute other tools to achieve the necessary goals of observability and performance analysis. The same can be said for Prometheus and Grafana.
```

### Docker Compose

A minimal `docker-compose.yml` file can look like:

```yaml
version: "3"
services:
  # Jaeger
  jaeger:
    image: jaegertracing/all-in-one:latest
    ports:
      - "16686:16686"

  otel-collector:
    image: otel/opentelemetry-collector:0.61.0
    command: [ "--config=/etc/otel-collector-config.yml" ]
    volumes:
      - ${PWD}/otel-collector-config.yml:/etc/otel-collector-config.yml
    ports:
      - "8888" # Prometheus metrics exposed by the collector
      - "8889" # Prometheus exporter metrics
      - "4317:4317" # OTLP gRPC receiver
    depends_on:
      - jaeger

  prometheus:
    container_name: prometheus
    image: prom/prometheus:latest
    volumes:
      - ${PWD}/prometheus-config.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    container_name: grafana
    image: grafana/grafana-oss:latest
    ports:
      - 3000:3000
```

The corresponding OpenTelemetry Collector configuration below needs to be stored in file `otel-collector-config.yml`:
```yaml
receivers:
  otlp:
    protocols:
      grpc:

exporters:
  jaeger:
    endpoint: jaeger:14250
    tls:
      insecure: true
  
  prometheus:
    endpoint: "0.0.0.0:8889"
    resource_to_telemetry_conversion:
      enabled: true
    # can be used to add additional labels
    const_labels:
      label1: value1

processors:
  batch:

service:
  extensions: []
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [jaeger]
      processors: [batch]
    metrics:
      receivers: [otlp]
      processors: [batch]
      exporters: [prometheus]
```

This setup creates a gRPC Collector Receiver on port 4317 that collects data pushed by the Flow Pods. Collector exporters for Jaeger and Prometheus backends are configured to export tracing and metrics data respectively. The final **service** section creates a collector pipeline combining the receiver (collect data) and exporter (to backend), process (batching) sub-components.

The minimal Prometheus configuration needs to be stored in `prometheus-config.yml`.
```yaml
scrape_configs:
  - job_name: 'otel-collector'
    scrape_interval: 500ms
    static_configs:
      - targets: ['otel-collector:8889']
      - targets: ['otel-collector:8888']
```

The Prometheus configuration now only needs to scrape from the OpenTelemetry Collector to get all the data from OpenTelemetry Metrics instrumented applications.


### Running a Flow locally

Run the Flow and a sample request that we want to instrument locally. If the backends are running successfully the Flow has exported data to the Collector which can be queried and viewed.

First start a Flow:

```python
from jina import Flow, Executor, requests
from docarray import DocList, BaseDoc
import time

class MyExecutor(Executor):
    
    @requests
    def foo(self, docs: DocList[BaseDoc], **kwargs) -> DocList[BaseDoc]:
        time.sleep(0.5)
        return docs

with Flow(
    port=54321,
    tracing=True,
    traces_exporter_host='http://localhost',
    traces_exporter_port=4317,
    metrics=True,
    metrics_exporter_host='http://localhost',
    metrics_exporter_port=4317,
).add(uses=MyExecutor) as f:
    f.block()
```

Second execute requests using the instrumented {class}`jina.Client`:

```python
from jina import Client
from docarray import DocList, BaseDoc

client = Client(
    host='grpc://localhost:54321',
    tracing=True,
    traces_exporter_host='http://localhost',
    traces_exporter_port=4317,
)
client.post('/', DocList[BaseDoc]([BaseDoc()]), return_type=DocList[BaseDoc])
client.teardown_instrumentation()
```

```{hint}
The {class}`jina.Client` currently only supports OpenTelemetry Tracing.
```

## Viewing Traces in Jaeger UI

You can open the Jaeger UI [here](http://localhost:16686). You can find more information on the Jaeger UI in the official [docs](https://www.jaegertracing.io/docs/1.38/external-guides/#using-jaeger).

```{hint}
The list of available traces are documented in the {ref}`Flow Instrumentation <instrumenting-flow>` section.
```

## Monitor with Prometheus and Grafana

External entities (like Grafana) can access these aggregated metrics via the [PromQL](https://prometheus.io/docs/prometheus/latest/querying/basics/) query language, and let users visualize metrics with dashboards. Check out a [comprehensive tutorial](https://prometheus.io/docs/visualization/grafana/) for more information.

Download a [sample Grafana dashboard JSON file](https://github.com/jina-ai/example-grafana-prometheus/blob/main/grafana-dashboards/flow-histogram-metrics.json) and import it into Grafana to get started with some pre-built graphs:

```{figure} ../../.github/2.0/grafana-histogram-metrics.png
:align: center
```

```{hint}
:class: seealso
A list of available metrics is in the {ref}`Flow Instrumentation <instrumenting-flow>` section.
To update your existing Prometheus and Grafana configurations, refer to the {ref}`OpenTelemetry migration guide <opentelemetry-migration>`.
```

