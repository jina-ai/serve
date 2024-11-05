(instrumenting-executor)=
# Instrumentation

Instrumentation consists of [OpenTelemetry](https://opentelemetry.io) Tracing and Metrics. Each feature can be enabled independently, and they allow you to collect request-level and application-level metrics for analyzing an Executor's real-time behavior. 

```{admonition} Full details on Instrumentation
:class: seealso
This section describes **custom** tracing spans. To use the Executor's default tracing, refer to {ref}`Flow Instrumentation <instrumenting-flow>`.
```

```{hint}
Read more on setting up an OpenTelemetry collector backend in the {ref}`OpenTelemetry Setup <opentelemetry>` section.
```

```{caution}
Prometheus-only based metrics collection will soon be deprecated. Refer to {ref}`Monitoring Executor <monitoring>` for this deprecated setup.
```

## Tracing

Any method that uses the {class}`~jina.requests` decorator adds a 
default tracing span for the defined operation. In addition, the operation span context 
is propagated to the method for creating further user-defined child spans within the 
method.

You can create custom spans to observe the operation's individual steps or record details and attributes with finer granularity. When tracing is enabled, Jina-serve provides the OpenTelemetry Tracer implementation as an Executor class attribute that you can use to create new child spans. The `tracing_context` method argument contains the parent span context using which a new span can be created to trace the desired operation in the method.

If tracing is enabled, each Executor exports its traces to the configured exporter host via the [Span Exporter](https://opentelemetry.io/docs/reference/specification/trace/sdk/#span-exporter). The backend combines these traces for visualization and alerting.


### Create custom traces

A `request` method is the public method that exposes an operation as an API. Depending on complexity, the method can be composed of different sub-operations that are required to build the final response. 

You can record/observe each internal step (along with its global or request-specific attributes) to give a finer-grained view of the operation at the request level. This helps identify bottlenecks and isolate request patterns that cause service degradation or errors.

You can use the `self.tracer` class attribute to create a new child span using the `tracing_context` method argument:

```python
from jina import Executor, requests
from docarray import DocList
from docarray.documents import TextDoc


class MyExecutor(Executor):
    @requests
    def foo(self, docs: DocList[TextDoc], tracing_context, **kwargs) -> DocList[TextDoc]:
        with self.tracer.start_as_current_span(
            'process_docs', context=tracing_context
        ) as process_span:
            process_span.set_attribute('sampling_rate', 0.01)
            docs = process(docs)
            with self.tracer.start_as_current_span('update_docs') as update_span:
                try:
                    update_span.set_attribute('len_updated_docs', len(docs))
                    docs = update(docs)
                except Exception as ex:
                    update_span.set_status(Status(StatusCode.ERROR))
                    update_span.record_exception(ex)
        return docs
```

The above pieces of instrumentation generate three spans:
 1. Default span with name `foo` for the overall method.
 2. `process_span` that measures the `process` and `update` sub-operations along with a `sampling_rate` attribute that is either a constant or specific to the request/operation.
 3. `update_span` that measures the `updated` operation along with any exceptions that might arise during the operation. The exception is recorded and marked on the `update_span` span. Since the exception is swallowed, the request succeeds with successful parent spans.


```{admonition} 
The Python OpenTelemetry API provides a global tracer via the `opentelemetry.trace.tracer()` method which is not set or used directly in Jina-serve. The class attribute `self.tracer` is used for the default `@requests` method tracing and must also be used as much as possible within the method for creating child spans.

However within a span context, the `opentelemetry.trace.get_current_span()` method returns the span created inside the context.
```

````{admonition} Respect OpenTelemetry Tracing semantic conventions
:class: caution
You should respect OpenTelemetry Tracing [semantic conventions](https://opentelemetry.io/docs/reference/specification/trace/semantic_conventions/).
````

````{hint}
If tracing is not enabled by default or enabled in your environment, check `self.tracer` exists before usage. If metrics are disabled then `self.tracer` will be `None`.
````

## Metrics

```{hint}
Prometheus-only based metrics collection will be deprecated soon. Refer to {ref}`Monitoring Executor <monitoring>` section for the deprecated setup.
```

Any method that uses the {class}`~jina.requests` decorator is monitored and creates a
[histogram](https://opentelemetry.io/docs/reference/specification/metrics/data-model/#histogram) which tracks the method's execution time.

This section documents adding custom monitoring to the {class}`~jina.Executor` with the OpenTelemetry Metrics API.

Custom metrics are useful to monitor each sub-part of your Executor(s). Jina lets you leverage
the [Meter](https://opentelemetry.io/docs/reference/specification/metrics/api/#meter) to define useful metrics 
for each of your Executors. We also provide a convenient wrapper, ({func}`~jina.monitor`), which lets you monitor
your Executor's sub-methods. 

When metrics are enabled, each Executor exposes its 
own metrics via the [Metric Exporter](https://opentelemetry.io/docs/reference/specification/metrics/sdk/#metricexporter).


### Define custom metrics

Sometimes monitoring the `encoding` method is not enough - you need to break it up into multiple parts to monitor one by one.

This is useful if your encoding phase is composed of two tasks, like image processing and
image embedding. By using custom metrics on these two tasks you can identify potential bottlenecks.

Overall, adding custom metrics gives you full flexibility when monitoring your Executor.

#### Use context manager

Use `self.monitor` to monitor your function's internal blocks:

```python
from jina import Executor, requests
from docarray import DocList
from docarray.documents import TextDoc


class MyExecutor(Executor):
    @requests
    def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        with self.monitor('processing_seconds', 'Time processing my document'):
            docs = process(docs)
        print(docs.texts)
        with self.monitor('update_seconds', 'Time updates my document'):
            docs = update(docs)
        return docs
```


#### Use the `@monitor` decorator

Add custom monitoring to a method with the {func}`~jina.monitor` decorator:

```python
from jina import Executor, monitor


class MyExecutor(Executor):
    @monitor()
    def my_method(self):
        ...
```

This creates a [Histogram](https://opentelemetry.io/docs/reference/specification/metrics/data-model/#histogram) `jina_my_method_seconds` which tracks the execution time of `my_method`

By default, the name and documentation of the metric created by {func}`~jina.monitor` are auto-generated based on the function's name. 
To set a custom name:

```python
@monitor(
    name='my_custom_metrics_seconds', documentation='This is my custom documentation'
)
def method(self):
    ...
```

````{admonition} respect OpenTelemetry Metrics semantic conventions
:class: caution
You should respect OpenTelemetry Metrics [semantic conventions](https://opentelemetry.io/docs/reference/specification/metrics/semantic_conventions/).
````

#### Use OpenTelemetry Meter

Under the hood, Python [OpenTelemetry Metrics API](https://opentelemetry.io/docs/concepts/signals/metrics/) handles the Executor's metrics feature. The {func}`~jina.monitor` decorator is convenient for monitoring an Executor's sub-methods, but if you need more flexibility, use the `self.meter` Executor class attribute to create supported instruments:


```python
from jina import requests, Executor
from docarray import DocList
from docarray.documents import TextDoc


class MyExecutor(Executor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.counter = self.meter.create_counter('my_count', 'my count')

    @requests
    def encode(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        self.counter.inc(len(docs))
```

This creates a [Counter](https://opentelemetry.io/docs/reference/specification/metrics/api/#counter) that you can use to incrementally track the number of Documents received in each request. 

````{hint}
If metrics are not enabled by default or enabled in your environment, you should check `self.meter` and `self.counter` exists before usage. If metrics are disabled then `self.meter` will be `None`.
````


#### Example


```python
from jina import requests, Executor
from docarray import DocList
from docarray.documents.legacy import LegacyDocument


class MyExecutor(Executor):
    def preprocessing(self, docs: DocList[LegacyDocument]):
        ...

    def model_inference(self, tensor):
        ...

    @requests
    def encode(self, docs: DocList[LegacyDocument], **kwargs) -> DocList[LegacyDocument]:
        docs.tensors = self.preprocessing(docs)
        docs.embedding = self.model_inference(docs.tensors)
```

The `encode` function is composed of two sub-functions.
* `preprocessing` takes raw bytes from a DocList and puts them into a PyTorch tensor. 
* `model inference` calls the forward function of a deep learning model.

By default, only the `encode` function is monitored:

````{tab} Decorator
```{code-block} python
---
emphasize-lines: 7, 11
---
from jina import Executor, requests, monitor
from docarray import DocList
from docarray.documents.legacy import LegacyDocument

class MyExecutor(Executor):

    @monitor()
    def preprocessing(self, docs: DocList[LegacyDocument]):
        ...

    @monitor()
    def model_inference(self, tensor):
        ...

    @requests
    def encode(self, docs: DocList[LegacyDocument], **kwargs) -> DocList[LegacyDocument]:
        docs.tensors = self.preprocessing(docs)
        docs.embedding = self.model_inference(docs.tensors)
```
````

````{tab} Context manager

```{code-block} python
---
emphasize-lines: 13, 15
---
from jina import Executor, requests
from docarray import DocList
from docarray.documents.legacy import LegacyDocument

def preprocessing(self, docs: DocList[LegacyDocument]):
    ...

def model_inference(self, tensor):
    ...

class MyExecutor(Executor):

    @requests
    def encode(self, docs: DocList[LegacyDocument], **kwargs) -> DocList[LegacyDocument]:
        with self.monitor('preprocessing_seconds', 'Time preprocessing the requests'):
            docs.tensors = preprocessing(docs)
        with self.monitor('model_inference_seconds', 'Time doing inference the requests'):
            docs.embedding = model_inference(docs.tensors)
```
````

## See also

- {ref}`List of available metrics <instrumenting-flow>`
- {ref}`How to deploy and use OpenTelemetry in Jina-serve <opentelemetry>`
- [Tracing in OpenTelemetry](https://opentelemetry.io/docs/concepts/signals/traces/)
- [Metrics in OpenTelemetry](https://opentelemetry.io/docs/concepts/signals/metrics/)
