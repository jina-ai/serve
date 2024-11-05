(serve-executor-standalone)=
# Serve

{class}`~jina.Executor`s can be served and accessed over the network using gRPC or HTTP protocols, allowing you to use them to create services for tasks like model inference, data processing, generative AI, and search services.

There are different options for deploying and running a standalone Executor:
* Run the Executor directly from Python with the {class}`~jina.orchestrate.deployments.Deployment` class
* Run the {meth}`~jina.Deployment.to_kubernetes_yaml()` method to generate Kubernetes deployment configuration files 
from an instance of {class}`~jina.orchestrate.deployments.Deployment`
* Run the static {meth}`~jina.serve.executors.BaseExecutor.to_docker_compose_yaml()` method to generate a Docker Compose service file

```{seealso}
Executors can also be combined to form a pipeline of microservices. We will see in a later step how 
to achieve this with the {ref}`Flow <flow-cookbook>`
```

````{admonition} Served vs. shared Executor
:class: hint

In Jina there are two ways of running standalone Executors: *Served Executors* and *shared Executors*.

- A **served Executor** is launched by one of the following methods: {class}`~jina.orchestrate.deployments.Deployment`, `to_kubernetes_yaml()`, or `to_docker_compose_yaml()`.
It resides behind a {ref}`Gateway <architecture-overview>` and can be directly accessed by a {ref}`Client <client>`.
It can also be used as part of a Flow.

- A **shared Executor** is launched using the [Jina CLI](../../cli/index.rst) and does *not* sit behind a Gateway.
It is intended to be used in one or more Flows. However, it can be also accessed by a {ref}`Client <client>`.
Because a shared Executor does not reside behind a Gateway, it requires fewer networking hops when used inside of a Flow.
However, it is not suitable for exposing a standalone service without gRPC protocol.

In any case, the user needs to make sure that the Document types bound to each endpoint are compatible inside a Flow.
````

(deployment)=
## Serve directly
An {class}`~jina.Executor` can be served using the {class}`~jina.orchestrate.deployments.Deployment` class.

The {class}`~jina.orchestrate.deployments.Deployment` class aims to separate the deployment configuration from the serving logic.
In other words:
* the Executor cares about defining the logic to serve, which endpoints to define and what data to accept.
* the Deployment layer cares about how to orchestrate this service, how many replicas or shards, etc.

This separation also aims to enhance the reusability of Executors: the same implementation of an Executor can be 
served in multiple ways/configurations using Deployment.

````{tab} Python class

```python
from docarray import DocList
from docarray.documents import TextDoc
from jina import Executor, requests, Deployment


class MyExec(Executor):
    @requests
    def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        docs[0].text = 'executed MyExec'  # custom logic goes here


with Deployment(uses=MyExec, port=12345, replicas=2) as dep:
    docs = dep.post(on='/foo', inputs=DocList[TextDoc](TextDoc()), return_type=DocList[TextDoc])
    print(docs.text)
```
````

````{tab} YAML configuration
`executor.yaml`:
```
jtype: MyExec
py_modules:
    - executor.py
```

```python
from jina import Deployment

with Deployment(uses='executor.yaml', port=12345, replicas=2) as dep:
    docs = dep.post(on='/foo', inputs=DocList[TextDoc](TextDoc()), return_type=DocList[TextDoc])
    print(docs.text)
```
````

````{tab} Hub Executor

```python
from jina import Deployment

with Deployment(uses='jinaai://my-username/MyExec/', port=12345, replicas=2) as dep:
    docs = dep.post(on='/foo', inputs=DocList[TextDoc](TextDoc()), return_type=DocList[TextDoc])
    print(docs.text)
```

````

````{tab} Docker image

```python
from jina import Deployment

with Deployment(uses='docker://my-executor-image', port=12345, replicas=2) as dep:
    docs = dep.post(on='/foo', inputs=DocList[TextDoc](TextDoc()), return_type=DocList[TextDoc])
    print(docs.text)
```

````

```text
─────────────────────── 🎉 Deployment is ready to serve! ───────────────────────
╭────────────── 🔗 Endpoint ────────────────╮
│  ⛓     Protocol                    GRPC  │
│  🏠       Local           0.0.0.0:12345   │
│  🔒     Private     192.168.3.147:12345   │
│  🌍      Public    87.191.159.105:12345   │
╰───────────────────────────────────────────╯
['executed MyExec']
```

````{hint}
You can use `dep.block()` to serve forever:

```python
with Deployment(uses=MyExec, port=12345, replicas=2) as dep:
    dep.block()
```
````

## Serve from the CLI

You can run an Executor from CLI. In this case, the Executor occupies one process. The lifetime of the Executor is the lifetime of the process.

### From a local Executor python class
```shell
jina executor --uses MyExec --py-modules executor.py
```


### From a local Executor YAML configuration

With `executor.py` containing the definition of `MyExec`, now creating a new file called `my-exec.yml`:

```yaml
jtype: MyExec
py_modules:
  - executor.py
```

This simply points Jina-serve to our file and Executor class. Now we can run the command:

```bash
jina executor --uses my-exec.yml --port 12345
```

### From Executor Hub

In this example, we use [`CLIPTextEncoder`](https://cloud.jina.ai/executor/livtkbkg) to create embeddings for our Documents.

````{tab} With Docker

```bash
jina executor --uses jinaai+docker://jina-ai/CLIPTextEncoder
```

````

````{tab} Without Docker

```bash
jina executor --uses jinaai://jina-ai/CLIPTextEncoder
```

````

This might take a few seconds, but in the end you should be greeted with the
following message:

```bash
WorkerRuntime@ 1[L]: Executor CLIPTextEncoder started
```

Just like that, our Executor is up and running.

(kubernetes-executor)=
## Serve from Deployment YAML
If you want a clear separation between deployment configuration and Executor logic, you can define the 
configuration in a `Deployment` YAML configuration.
This is an example `deployment.yml` config file:
```yaml
jtype: Deployment
with:
  replicas: 2
  shards: 3
  uses: MyExecutor
  py_modules:
    - my_executor.py
```

Then, you can run the Deployment through the CLI or Python API:
````{tab} Python API
```python
from jina import Deployment

with Deployment.load_config('deployment.yml') as dep:
    dep.block()
```
````

````{tab} CLI
```shell
jina deployment --uses deployment.yml
```
Unlike the `jina executor` CLI, this command supports replication and sharding. 
````
```text
─────────────────────── 🎉 Deployment is ready to serve! ───────────────────────
╭────────────── 🔗 Endpoint ────────────────╮
│  ⛓     Protocol                    GRPC  │
│  🏠       Local           0.0.0.0:12345   │
│  🔒     Private     192.168.3.147:12345   │
│  🌍      Public    87.191.159.105:12345   │
╰───────────────────────────────────────────╯
```

Read more about the {ref}`YAML specifications of Deployments <deployment-yaml-spec>`.
## Serve via Kubernetes
You can generate Kubernetes configuration files for your containerized Executor by using the {meth}`~jina.Deployment.to_kubernetes_yaml()` method:

```python
from jina import Deployment


dep = Deployment(
    uses='jinaai+docker://jina-ai/DummyHubExecutor', port_expose=8080, replicas=3
)
dep.to_kubernetes_yaml('/tmp/config_out_folder', k8s_namespace='my-namespace')
```
This will give the following output:
```text
INFO   executor@8065 K8s yaml files have been created under  [02/07/23 10:03:50]
       [b]/tmp/config_out_folder[/]. You can use it by                          
       running [b]kubectl apply -R -f                                           
       /tmp/config_out_folder[/] 
```
Afterwards, you can apply this configuration to your cluster:
```shell
kubectl apply -R -f /tmp/config_out_folder
```

The above example deploys the `DummyHubExecutor` from Executor Hub into your Kubernetes cluster.

````{admonition} Hint
:class: hint
The Executor you use needs to be already containerized and stored in a registry accessible from your Kubernetes cluster. We recommend [Executor Hub](https://cloud.jina.ai/executors) for this.
````

Once the Executor is deployed, you can expose a service:
```bash
kubectl expose deployment executor --name=executor-exposed --type LoadBalancer --port 80 --target-port 8080 -n my-namespace
sleep 60 # wait until the external ip is configured
```

Let's export the external IP address created and use it to send requests to the Executor. 
```bash
export EXTERNAL_IP=`kubectl get service executor-exposed -n my-namespace -o=jsonpath='{.status.loadBalancer.ingress[0].ip}'`
```

Then, we can send requests using {meth}`~jina.Client`. Since Kubernetes load balancers cannot load balance streaming 
gRPC requests, it is recommended to set `stream=False` when using gRPC (note that this is only applicable for Kubernetes deployments of Executors):
```python
import os
from jina import Client
from docarray import DocList
from docarray.documents import TextDoc

host = os.environ['EXTERNAL_IP']
port = 80

client = Client(host=host, port=port)

print(client.post(on='/', inputs=TextDoc(), return_type=DocList[TextDoc], stream=False).text)
```

```text
['hello']
```

````{admonition} Hint
:class: hint
You can also export an Executor deployment to kubernetes YAML files using the CLI command, in case you define a Deployment YAML config:
`jina export kubernetes deployment.yml output_path`
````

(external-shared-executor)=
### External and shared Executors
This type of standalone Executor can be either *external* or *shared*. By default, it is external.

- An external Executor is deployed alongside a {ref}`Gateway <architecture-overview>`. 
- A shared Executor has no Gateway.

Although both types can join a {class}`~jina.Flow`, use a shared Executor if the Executor is only intended to join Flows 
to have less network hops and save the costs of running the Gateway in Kubernetes.

## Serve via Docker Compose

You can generate a Docker Compose service file for your containerized Executor with the static {meth}`~jina.Deployment.to_docker_compose_yaml` method.

```python
from jina import Deployment


dep = Deployment(
    uses='jinaai+docker://jina-ai/DummyHubExecutor', port_expose=8080, replicas=3
)

dep.to_docker_compose_yaml(
    output_path='/tmp/docker-compose.yml',
)
```

```shell
docker-compose -f /tmp/docker-compose.yml up
```

The above example runs the `DummyHubExecutor` from Executor Hub locally on your computer using Docker Compose.

````{admonition} Hint
:class: hint
The Executor you use needs to be already containerized and stored in an accessible registry. We recommend [Executor Hub](https://cloud.jina.ai/executors) for this.
````

````{admonition} Hint
:class: hint
You can also export an Executor deployment to Docker compose YAML files using the CLI command, in case you define a Deployment YAML config:
`jina export docker-compose deployment.yml output_path`
````

