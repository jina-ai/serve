

(instrumenting-client)=
## Instrumentation

The {class}`~jina.Client` supports request tracing, giving you an end-to-end view of a request's lifecycle. The client supports **gRPC**, **HTTP** and **WebSocket** protocols.

````{tab} Implicit, inside a Flow

```{code-block} python
---
emphasize-lines: 4, 5, 6
---
from jina import Flow

f = Flow(
        tracing=True, 
        traces_exporter_host='http://localhost', 
        traces_exporter_port=4317,
    )

with f:
    f.post('/')
```

````

````{tab} Explicit, outside a Flow

```{code-block} python
---
emphasize-lines: 5, 6, 7
---
from jina import Client

# must match the Flow setup
c = Client(
    tracing=True,
    traces_exporter_host='http://localhost',
    traces_exporter_port=4317,
)
c.post('/')
```

````

Each protocol client creates the first trace ID which will be propagated to the `Gateway`. The `Gateway` then creates child spans using the available trace ID which is further propagated to each Executor request. Using the trace ID, all associated spans can be collected to build a trace view of the whole request lifecycle.

```{admonition} Using custom/external tracing context
:class: caution
The {class}`~jina.Client` doesn't currently support external tracing context which can potentially be extracted from an upstream request.
```

You can find more about instrumentation from the resources below:

- [Tracing in OpenTelemetry](https://opentelemetry.io/docs/concepts/signals/traces/)
- {ref}`Instrumenting a Flow <instrumenting-flow>`
- {ref}`Deploying and using OpenTelemetry in Jina-serve <opentelemetry>`

