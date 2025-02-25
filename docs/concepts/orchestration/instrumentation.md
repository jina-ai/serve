(instrumenting-flow)=
# Instrumentation

A {class}`~jina.Flow` exposes configuration parameters for leveraging [OpenTelemetry](https://opentelemetry.io) Tracing and Metrics observability features. These tools let you instrument and collect various signals which help to analyze your application's real-time behavior.

A {class}`~jina.Flow` is composed of several Pods, namely the {class}`~jina.serve.runtimes.gateway.GatewayRuntime`, {class}`~jina.Executor`s, and potentially a {class}`~jina.serve.runtimes.head.HeadRuntime` (see the {ref}`architecture overview <architecture-overview>`). Each Pod is its own microservice. These services expose their own metrics using the Python [OpenTelemetry API and SDK](https://opentelemetry-python.readthedocs.io/en/stable/api/trace.html). 

Tracing and Metrics can be enabled and configured independently to allow more flexibility in the data collection and visualization setup.

```{hint}
:class: seealso
Refer to {ref}`OpenTelemetry Setup <opentelemetry>` for a full detail on the OpenTelemetry data collection and visualization setup.
```

```{caution}
Prometheus-only based metrics collection will soon be deprecated. Refer to {ref}`Prometheus/Grafana Support <monitoring>` section for the deprecated setup.
```

## Tracing

````{tab} Python
```python
from jina import Flow

f = Flow(
    tracing=True,
    traces_exporter_host='http://localhost',
    traces_exporter_port=4317,
).add(uses='jinaai://jina-ai/SimpleIndexer')

with f:
    f.block()
```
````

````{tab} YAML
In `flow.yaml`:
```yaml
jtype: Flow
with:
  tracing: true
  tracing_exporter_host: 'localhost'
  tracing_exporter_port: 4317
executors:
- uses: jinaai://jina-ai/SimpleIndexer
```

```bash
jina flow --uses flow.yaml
```
````

This Flow creates two Pods: one for the Gateway, and one for the SimpleIndexer Executor. The Flow propagates the Tracing configuration to each Pod so you don't need to duplicate the arguments on each Executor. 

The `traces_exporter_host` and `traces_exporter_port` arguments configure the traces [exporter](https://opentelemetry.io/docs/instrumentation/python/exporters/#trace-1) which are responsible for pushing collected data to the [collector](https://opentelemetry.io/docs/collector/) backend.


```{hint}
:class: seealso
Refer to {ref}`OpenTelemetry Setup <opentelemetry>` for more details on exporter and collector setup and usage.
```

### Available Traces

Each Pod supports different default traces out of the box, and also lets you define your own custom traces in the Executor. The `Runtime` name is used to create the OpenTelemetry [Service](https://opentelemetry.io/docs/reference/specification/resource/semantic_conventions/#service) [Resource](https://opentelemetry.io/docs/reference/specification/resource/) attribute. The default value for the `name` argument is the `Runtime` or `Executor` class name.

Because not all Pods have the same role, they expose different kinds of traces:

#### Gateway Pods

| Operation name    | Description  |
|-------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| `/jina.JinaRPC/Call` | Traces the request from the client to the Gateway server. |
| `/jina.JinaSingleDataRequestRPC/process_single_data` | Internal operation for the request originating from the Gateway to the target Head or Executor. |

#### Head Pods

| Operation name    | Description  |
|-------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| `/jina.JinaSingleDataRequestRPC/process_single_data` | Internal operation for the request originating from the Gateway to the target Head. Another child span is created for the request originating from the Head to the Executor.|

#### Executor Pods

| Operation name    | Description  |
|-------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| `/jina.JinaSingleDataRequestRPC/process_single_data` | Executor server operation for the request originating from the Gateway/Head to the Executor request handler. |
| `/endpoint` | Internal operation for the request originating from the Executor request handler to the target `@requests(=/endpoint)` method. The `endpoint` will be `default` if no endpoint name is provided. |

```{seealso} 
Beyond the above-mentioned default traces, you can define {ref}`custom traces <instrumenting-executor>` for your Executor. 
```

## Metrics

```{hint}
Prometheus-only based metrics collection will soon be deprecated. Refer to {ref}`Prometheus/Grafana Support <monitoring>` section for the deprecated setup.
```

````{tab} Python
```python
from jina import Flow

f = Flow(
    metrics=True,
    metrics_exporter_host='http://localhost',
    metrics_exporter_port=4317,
).add(uses='jinaai://jina-ai/SimpleIndexer')

with f:
    f.block()
```
````

````{tab} YAML
In `flow.yaml`:
```yaml
jtype: Flow
with:
  metrics: true
  metrics_exporter_host: 'localhost'
  metrics_exporter_port: 4317
executors:
- uses: jinaai://jina-ai/SimpleIndexer
```

```bash
jina flow --uses flow.yaml
```
````

The Flow propagates the Metrics configuration to each Pod. The `metrics_exporter_host` and `metrics_exporter_port` arguments configure the metrics [exporter](https://opentelemetry.io/docs/instrumentation/python/exporters/#metrics-1) responsible for pushing collected data to the [collector](https://opentelemetry.io/docs/collector/) backend.


```{hint}
:class: seealso
Refer to {ref}`OpenTelemetry Setup <opentelemetry>` for more details on the exporter and collector setup and usage.
```

### Available metrics

Each Pod supports different default metrics out of the box, also letting you define your own custom metrics in the Executor. All metrics add the `Runtime` name to the [metric attributes](https://opentelemetry.io/docs/reference/specification/metrics/semantic_conventions/) which can be used to filter data from different Pods. 

Because not all Pods have the same role, they expose different kinds of metrics:

#### Gateway Pods

| Metrics name                        | Metrics type                                                           | Description                                                                                                     |
|-------------------------------------|------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------|
| `jina_receiving_request_seconds`    | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)   | Measures time elapsed between receiving a request from the client and sending back the response.                |
| `jina_sending_request_seconds`      | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)   | Measures time elapsed between sending a downstream request to an Executor/Head and receiving the response back. |
| `jina_number_of_pending_requests`   | [UpDownCounter](https://opentelemetry.io/docs/reference/specification/metrics/api/#updowncounter)       | Counts the number of pending requests.                                                                          |
| `jina_successful_requests`    | [Counter](https://opentelemetry.io/docs/reference/specification/metrics/api/#counter)   | Counts the number of successful requests returned by the Gateway.                                               |
| `jina_failed_requests`        | [Counter](https://opentelemetry.io/docs/reference/specification/metrics/api/#counter)   | Counts the number of failed requests returned by the Gateway.                                                   |
| `jina_sent_request_bytes`           | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)   | Measures the size in bytes of the request sent by the Gateway to the Executor or to the Head.                   |
| `jina_received_response_bytes`         | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)   | Measures the size in bytes of the request returned by the Executor.                                             |
| `jina_received_request_bytes`           | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)   | Measures the size of the request in bytes received at the Gateway level.                                        |
| `jina_sent_response_bytes`  | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)   | Measures the size in bytes of the response returned from the Gateway to the Client.                             |

```{seealso} 
You can find more information on the different type of metrics in Prometheus [here](https://prometheus.io/docs/concepts/metric_types/#metric-types)
```

#### Head Pods

| Metric name                            | Metric type                                                            | Description                                                                                                   |
|-----------------------------------------|-------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------|
| `jina_receiving_request_seconds`        | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)    | Measures the time elapsed between receiving a request from the Gateway and sending back the response.         |
| `jina_sending_request_seconds`          | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)    | Measures the time elapsed between sending a downstream request to an Executor and receiving the response back. |
| `jina_number_of_pending_requests`   | [UpDownCounter](https://opentelemetry.io/docs/reference/specification/metrics/api/#updowncounter)| Counts the number of pending requests.                                                                          |
| `jina_successful_requests`    | [Counter](https://opentelemetry.io/docs/reference/specification/metrics/api/#counter)                  | Counts the number of successful requests returned by the Head.                                               |
| `jina_failed_requests`        | [Counter](https://opentelemetry.io/docs/reference/specification/metrics/api/#counter)   | Counts the number of failed requests returned by the Head.                                                   |
| `jina_sent_request_bytes`               | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)    | Measures the size in bytes of the request sent by the Head to the Executor.                                   |
| `jina_received_response_bytes`          | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)    | Measures the size in bytes of the response returned by the Executor.                                          |
| `jina_received_request_bytes`           | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)   | Measures the size of the request in bytes received at the Head level.                                        |
| `jina_sent_response_bytes`              | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram)   | Measures the size in bytes of the response returned from the Head to the Gateway.                             |

#### Executor Pods

The Executor also adds the Executor class name and the request endpoint for the `@requests` or `@monitor` decorated method level metrics:

| Metric name                     | Metric type                                                         | Description                                                                                                 |
|----------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| `jina_receiving_request_seconds` | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram) | Measures the time elapsed between receiving a request from the Gateway (or the head) and sending back the response. |
| `jina_process_request_seconds`   | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram) | Measures the time spend calling the requested method                                                         |
| `jina_document_processed`  | [Counter](https://opentelemetry.io/docs/reference/specification/metrics/api/#counter) | Counts the number of Documents processed by an Executor                                                     |
| `jina_successful_requests` | [Counter](https://opentelemetry.io/docs/reference/specification/metrics/api/#counter) | Total count of successful requests returned by the Executor across all endpoints                            |
| `jina_failed_requests`     | [Counter](https://opentelemetry.io/docs/reference/specification/metrics/api/#counter) | Total count of failed requests returned by the Executor across all endpoints                                |
| `jina_received_request_bytes`        | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram) | Measures the size in bytes of the request received at the Executor level                                    |
| `jina_sent_response_bytes`        | [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/api/#histogram) | Measures the size in bytes of the response returned from the Executor to the Gateway                           |


```{seealso} 
Beyond the default metrics outlined above, you can also define {ref}`custom metrics <instrumenting-executor>` for your Executor. 
```

```{hint} 
`jina_process_request_seconds` and `jina_receiving_request_seconds` are different:
 
 -  `jina_process_request_seconds` only tracks time spent calling the function.
 - `jina_receiving_request_seconds` tracks time spent calling the function **and** the gRPC communication overhead.
```

## See also

- {ref}`Defining custom traces and metrics in an Executor <instrumenting-executor>`
- {ref}`How to deploy and use OpenTelemetry in Jina-serve <opentelemetry>`
- [Tracing in OpenTelemetry](https://opentelemetry.io/docs/concepts/signals/traces/)
- [Metrics in OpenTelemetry](https://opentelemetry.io/docs/concepts/signals/metrics/)