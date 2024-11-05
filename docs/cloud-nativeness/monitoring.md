(monitoring)=
# Prometheus/Grafana Support (Legacy)

```{admonition} Deprecated
:class: caution
The Prometheus-only based feature will soon be deprecated in favor of the OpenTelemetry Setup. Refer to {ref}`OpenTelemetry Setup <opentelemetry>` for the details on OpenTelemetry setup for Jina-serve.

Refer to the {ref}`OpenTelemetry migration guide <opentelemetry-migration>` for updating your existing Prometheus and Grafana configurations.
```

We recommend the Prometheus/Grafana stack to leverage the metrics exposed by Jina-serve. In this setup, Jina-serve exposes different metrics, and Prometheus scrapes these endpoints, as well as
collecting, aggregating, and storing the metrics. 

External entities (like Grafana) can access these aggregated metrics via the query language [PromQL](https://prometheus.io/docs/prometheus/latest/querying/basics/) and let users visualize the metrics with dashboards.


```{hint} 
Jina supports exposing metrics, but you are in charge of installing and managing your Prometheus/Grafana instances.
```

In this guide, we deploy the Prometheus/Grafana stack and use it to monitor a Flow.

(deploy-flow-monitoring)=
## Deploying the Flow and the monitoring stack

### Deploying on Kubernetes

One challenge of monitoring a {class}`~jina.Flow` is communicating its different metrics endpoints to Prometheus.
Fortunately, the [Prometheus operator for Kubernetes](https://github.com/prometheus-operator/prometheus-operator/blob/main/Documentation/user-guides/getting-started.md) makes this fairly easy because it can automatically discover new metrics endpoints to scrape.

We recommend deploying your Jina-serve Flow on Kubernetes to leverage the full potential of the monitoring feature because:
* The Prometheus operator can automatically discover new endpoints to scrape.
* You can extend monitoring with the rich built-in Kubernetes metrics.

You can deploy Prometheus and Grafana on your Kubernetes cluster by running:

```bash
helm install prometheus prometheus-community/kube-prometheus-stack --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false
```
```{hint} 
setting the `serviceMonitorSelectorNilUsesHelmValues` to false allows the Prometheus Operator to discover metrics endpoint outside of the helm scope which is needed to discover the Flow metrics endpoints.
```

Deploy the Flow that we want to monitor:

For this example we recommend reading {ref}`how to build and containerize the Executors to be run in Kubernetes. <build-containerize-for-k8s>`


````{tab} via YAML
This example shows how to start a Flow with monitoring enabled via YAML:

In a `flow.yaml` file
```yaml
jtype: Flow
with:
  monitoring: true
executors:
- uses: jinaai+docker://<user-id>/EncoderPrivate
```

```bash
jina export kubernetes flow.yml ./config ```
````

````{tab} via Python API
```python
from jina import Flow

f = Flow(monitoring=True).add(uses='jinaai+docker://<user-id>/EncoderPrivate')
f.to_kubernetes_yaml('config')
```
````

This creates a `config` folder containing the Kubernetes YAML definition of the Flow.

```{seealso}
You can see in-depth how to deploy a Flow on Kubernetes {ref}`here <kubernetes>`
```

Then deploy the Flow:

```bash
kubectl apply -R -f config
```

Wait for a couple of minutes, and you should see that the Pods are ready:

```bash
kubectl get pods
```

```{figure} ../../.github/2.0/kubectl_pods.png
:align: center
```

Then you can see that the new metrics endpoints are automatically discovered:

```bash
kubectl port-forward svc/prometheus-operated 9090:9090
```

```{figure} ../../.github/2.0/prometheus_target.png
:align: center
```
Before querying the gateway you need to port-forward
```bash
kubectl port-forward svc/gateway 8080:8080
```

To access Grafana, run:

```bash
kb port-forward svc/prometheus-grafana 3000:80
```

Then open `http://localhost:3000` in your browser. The username is `admin` and password is `prom-operator`.

You should see the Grafana home page.


### Deploying locally

Deploy the Flow that we want to monitor:


````{tab} via Python code
```python
from jina import Flow

with Flow(monitoring=True, port_monitoring=8000, port=8080).add(
    uses='jinaai+docker://<user-id>/EncoderPrivate', port_monitoring=9000
) as f:
    f.block()
```
````

````{tab} via docker-compose
```python
from jina import Flow

Flow(monitoring=True, port_monitoring=8000, port=8080).add(
    uses='jinaai+docker://<user-id>/EncoderPrivate', port_monitoring=9000
).to_docker_compose_yaml('config.yaml')
```
```bash
docker-compose -f config.yaml up
```
````

To monitor a Flow locally you need to install Prometheus and Grafana locally. The easiest way to do this is with
Docker Compose.

First clone the repo which contains the config file:

```bash
git clone https://github.com/jina-ai/example-grafana-prometheus
cd example-grafana-prometheus/prometheus-grafana-local
```

then 

```bash
docker-compose up
```

Access the Grafana dashboard at `http://localhost:3000`. The username is `admin` and the password is `foobar`.

```{caution}
This example works locally because Prometheus is configured to listen to ports 8000 and 9000. However,
in contrast to deploying on Kubernetes, you need to tell Prometheus which port to look at. You can change these
ports by modifying [prometheus.yml](https://github.com/jina-ai/example-grafana-prometheus/blob/8baf519f7258da68cfe224775fc90537a749c305/prometheus-grafana-local/prometheus/prometheus.yml#L64).
```

### Deploying on Jcloud

If your Flow is deployed on JCloud, you don't need to provision a monitoring stack yourself. Prometheus and Grafana are 
handled by JCloud and you can find a dashboard URL with `jc status <flow_id>`

## Using Grafana to visualize metrics

Access the Grafana homepage, then go to `Browse` then `import` and copy and paste the [JSON file](https://github.com/jina-ai/example-grafana-prometheus/blob/main/grafana-dashboards/flow.json) 


You should see the following dashboard:

```{figure} ../../.github/2.0/grafana.png
:align: center
```


````{admonition} Hint
:class: hint

You should query your Flow to generate the first metrics. Otherwise the dashboard looks empty.
````

You can query the Flow by running:

```python
from typing import Optional
from docarray import DocList, BaseDoc
from docarray.typing import NdArray
from jina import Client


class MyDoc(BaseDoc):
    text: str
    embedding: Optional[NdArray] = None
client = Client(port=51000)

client.post(on='/', inputs=DocList[MyDoc]([MyDoc(text=f'Text for document {i}') for in range(100)]), return_type=DocList[MyDoc], request_size=10,)
```

## See also

- [Using Grafana to visualize Prometheus metrics](https://grafana.com/docs/grafana/latest/getting-started/getting-started-prometheus/)
- {ref}`Defining custom metrics in an Executor <monitoring>`
