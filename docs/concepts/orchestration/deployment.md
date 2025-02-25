(deployment)=
# Deployment

```{important}
A Deployment is part of the orchestration layer {ref}`Orchestration <orchestration>`. Be sure to read up on that too!
```

A {class}`~jina.Deployment` orchestrates a single {class}`~jina.Executor` to accomplish a task. Documents are processed by Executors.

You can think of a Deployment as an interface to configure and launch your {ref}`microservice architecture <architecture-overview>`, while the heavy lifting is done by the {ref}`service <executor-cookbook>` itself.

(why-deployment)=
## Why use a Deployment?

Once you've learned about Documents, DocLists and Executors, you can split a big task into small independent modules and services.

- Deployments let you scale these Executors independently to match your requirements.
- Deployments let you easily use other cloud-native orchestrators, such as Kubernetes, to manage your service.

(create-deployment)=
## Create

The most trivial {class}`~jina.Deployment` is an empty one. It can be defined in Python or from a YAML file:

````{tab} Python
```python
from jina import Deployment

dep = Deployment()
```
````
````{tab} YAML
```yaml
jtype: Deployment
```
````

For production, you should define your Deployments with YAML. This is because YAML files are independent of the Python logic code and easier to maintain.


## Minimum working example

````{tab} Pythonic style


```python
from jina import Deployment, Executor, requests
from docarray import DocList, BaseDoc


class MyExecutor(Executor):
    @requests(on='/bar')
    def foo(self, docs: DocList[BaseDoc], **kwargs) -> DocList[BaseDoc]:
        print(docs)


dep = Deployment(name='myexec1', uses=MyExecutor)

with dep:
    dep.post(on='/bar', inputs=BaseDoc(), return_type=DocList[BaseDoc], on_done=print)
```


````

````{tab} Deployment-as-a-Service style

Server:

```python
from jina import Deployment, Executor, requests
from docarray import DocList, BaseDoc


class MyExecutor(Executor):
    @requests(on='/bar')
    def foo(self, docs: DocList[BaseDoc], **kwargs) -> DocList[BaseDoc]:
        print(docs)


dep = Deployment(port=12345, name='myexec1', uses=MyExecutor)

with dep:
    dep.block()
```

Client:

```python
from jina import Client
from docarray import DocList, BaseDoc

c = Client(port=12345)
c.post(on='/bar', inputs=BaseDoc(), return_type=DocList[BaseDoc], on_done=print)
```

````

````{tab} Load from YAML

`deployment.yml`:
```yaml
jtype: Deployment
name: myexec1
uses: FooExecutor
py_modules: exec.py
```

`exec.py`:
```python
from jina import Deployment, Executor, requests
from docarray import DocList, BaseDoc
from docarray.documents import TextDoc
 
class FooExecutor(Executor):
    @requests
    def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        for doc in docs:
            doc.text = 'foo was here'
        docs.summary()
        return docs
```

```python
from jina import Deployment
from docarray import DocList, BaseDoc
from docarray.documents import TextDoc

dep = Deployment.load_config('deployment.yml')

with dep:
    try:
        dep.post(on='/bar', inputs=TextDoc(), on_done=print)
    except Exception as ex:
        # handle exception
        pass
```

````

```{caution}
The statement `with dep:` starts the Deployment, and exiting the indented with block stops the Deployment, including its Executors.
Exceptions raised inside the `with dep:` block will close the Deployment context manager. If you don't want this, use a `try...except` block to surround the statements that could potentially raise an exception.
```

## Convert between Python and YAML

A Python Deployment definition can easily be converted to/from a YAML definition:

````{tab} Load from YAML
```python
from jina import Deployment

dep = Deployment.load_config('flow.yml')
```
````
````{tab} Export to YAML
```python
from jina import Deployment

dep = Deployment()

dep.save_config('deployment.yml')
```
````

## Start and stop

When a {class}`~jina.Deployment` starts, all the replicated Executors will start as well, making it possible to {ref}`reach the service through its API <third-party-client>`.

There are three ways to start a Deployment: In Python, from a YAML file, or from the terminal.

- Generally in Python: use Deployment as a context manager.
- As an entrypoint from terminal: use `Jina CLI <cli>` and a Deployment YAML file.
- As an entrypoint from Python code: use Deployment as a context manager inside `if __name__ == '__main__'`
- No context manager, manually call {meth}`~jina.Deployment.start` and {meth}`~jina.Deployment.close`.

````{tab} General in Python
```python
from jina import Deployment

dep = Deployment()

with dep:
    pass
```
The statement `with dep:` starts the Deployment, and exiting the indented `with` block stops the Deployment, including its Executor.
````

````{tab} Jina-serve CLI entrypoint
```bash
jina deployment --uses deployment.yml
```
````

````{tab} Python entrypoint
```python
from jina import Deployment

dep = Deployment()

if __name__ == '__main__':
    with dep:
        pass
```
The statement `with dep:` starts the Deployment, and exiting the indented `with` block stops the Deployment, including its Executor.
````

````{tab} Python no context manager
```python
from jina import Deployment

dep = Deployment()

dep.start()

dep.close()
```
````

Your addresses and entrypoints can be found in the output. When you enable more features such as monitoring, HTTP gateway, TLS encryption, this display expands to contain more information.

(multiprocessing-spawn)=
### Set multiprocessing `spawn` 

Some corner cases require forcing a `spawn` start method for multiprocessing, for example if you encounter "Cannot re-initialize CUDA in forked subprocess". 

You can use `JINA_MP_START_METHOD=spawn` before starting the Python script to enable this.

```bash
JINA_MP_START_METHOD=spawn python app.py
```

```{caution}
In case you set `JINA_MP_START_METHOD=spawn`, make sure to use Flow as a context manager inside `if __name__ == '__main__'`.
The script entrypoint (starting the flow) [needs to be protected when using `spawn` start method](https://docs.python.org/3/library/multiprocessing.html#the-spawn-and-forkserver-start-methods). 
```

````{hint}
There's no need to set this for Windows, as it only supports spawn method for multiprocessing. 
````

## Serve

### Serve forever

In most scenarios, a Deployment should remain reachable for prolonged periods of time. This can be achieved from the terminal:

````{tab} Python
```python
from jina import Deployment

dep = Deployment()

with dep:
    dep.block()
````
````{tab} YAML
```shell
jina-serve deployment --uses deployment.yml
```
````

The `.block()` method blocks the execution of the current thread or process, enabling external clients to access the Deployment.

In this case, the Deployment can be stopped by interrupting the thread or process. 

### Serve until an event

Alternatively, a `multiprocessing` or `threading` `Event` object can be passed to `.block()`, which stops the Deployment once set.

```python
from jina import Deployment
import threading


def start_deployment(stop_event):
    """start a blocking Deployment."""
    dep = Deployment()
    
    with dep:
        dep.block(stop_event=stop_event)


e = threading.Event()  # create new Event

t = threading.Thread(name='Blocked-Flow', target=start_flow, args=(e,))
t.start()  # start Deployment in new Thread

# do some stuff

e.set()  # set event and stop (unblock) the Deployment
```

## Export

A Deployment YAML can be exported as a Docker Compose YAML or Kubernetes YAML bundle. 

(docker-compose-export)=
### Docker Compose

````{tab} Python
```python
from jina import Deployment

dep = Deployment()
dep.to_docker_compose_yaml()
```
````
````{tab} Terminal
```shell
jina-serve export docker-compose deployment.yml docker-compose.yml 
```
````

This will generate a single `docker-compose.yml` file.

For advanced utilization of Docker Compose with Jina-serve, refer to {ref}`How to <docker-compose>` 

(deployment-kubernetes-export)=
### Kubernetes

````{tab} Python
```python
from jina import Deployment

dep = Deployment
dep.to_kubernetes_yaml('dep_k8s_configuration')
```
````
````{tab} Terminal
```shell
jina-serve export kubernetes deployment.yml ./my-k8s 
```
````

The generated folder can be used directly with `kubectl` to deploy the Deployment to an existing Kubernetes cluster.

For advanced utilisation of Kubernetes with Jina-serve please refer to {ref}`How to <kubernetes>` 

```{tip}
Based on your local Jina version, Executor Hub may rebuild the Docker image during the YAML generation process.
If you do not wish to rebuild the image, set the environment variable `JINA_HUB_NO_IMAGE_REBUILD`.
```

```{tip}
If an Executor requires volumes to be mapped to persist data, Jina will create a StatefulSet for that Executor instead of a Deployment.
You can control the access mode, storage class name and capacity of the attached Persistent Volume Claim by using {ref}`Jina environment variables <jina-serve-env-vars>`  
`JINA_K8S_ACCESS_MODES`, `JINA_K8S_STORAGE_CLASS_NAME` and `JINA_K8S_STORAGE_CAPACITY`. Only the first volume will be considered to be mounted.
```

```{admonition} See also
:class: seealso
For more in-depth guides on deployment, check our how-tos for {ref}`Docker compose <docker-compose>` and {ref}`Kubernetes <kubernetes>`.
```

```{caution}
The port or ports arguments are ignored when calling the Kubernetes YAML, Jina-serve will start the services binding to the ports 8080, except when multiple protocols
need to be served when the consecutive ports (8081, ...) will be used. This is because the Kubernetes service will direct the traffic from you and it is irrelevant
to the services around because in Kubernetes services communicate via the service names irrespective of the internal port.
```

(logging-configuration)=
## Logging

The default {class}`jina.logging.logger.JinaLogger` uses rich console logging that writes to the system console. The `log_config` argument can be used to pass in a string of the pre-configured logging configuration names in Jina-serve or the absolute YAML file path of the custom logging configuration. For most cases, the default logging configuration sufficiently covers local, Docker and Kubernetes environments.

Custom logging handlers can be configured by following the Python official [Logging Cookbook](https://docs.python.org/3/howto/logging-cookbook.html#logging-cookbook) examples. An example custom logging configuration file defined in a YAML file `logging.json.yml` is:

```yaml
handlers:
  - StreamHandler
level: INFO
configs:
  StreamHandler:
    format: '%(asctime)s:{name:>15}@%(process)2d[%(levelname).1s]:%(message)s'
    formatter: JsonFormatter
```

The logging configuration can be used as follows:

````{tab} Python
```python
from jina import Deployment

dep = Deployment(log_config='./logging.json.yml')
```
````

````{tab} YAML
```yaml
jtype: Deployment
with:
    log_config: './logging.json.yml'
```
````

### Supported protocols

A Deployment can be used to deploy an Executor and serve it using `gRPC` or `HTTP` protocol, or a composition of them. 

### gRPC protocol

gRPC is the default protocol used by a Deployment to expose Executors to the outside world, and is used to communicate between the Gateway and an Executor inside a Flow.

### HTTP protocol

HTTP can be used for a stand-alone Deployment (without being part of a Flow), which allows external services to connect via REST. 

```python
from jina import Deployment, Executor, requests
from docarray import DocList
from docarray.documents import TextDoc
 
class MyExec(Executor):
    @requests
    def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        for doc in docs:
            doc.text = 'foo was here'
        docs.summary()
        return docs

dep = Deployment(protocol='http', port=12345, uses=MyExec)

with dep:
    dep.block()
````

This will make it available at port 12345 and you can get the [OpenAPI schema](https://swagger.io/specification/) for the service.

```{figure} images/http-deployment-swagger.png
:scale: 70%
```

### Composite protocol

A Deployment can also deploy an Executor and serve it with a combination of gRPC and HTTP protocols.

```python
from jina import Deployment, Executor, requests
from docarray import DocList
from docarray.documents import TextDoc
 
class MyExec(Executor):
    @requests
    def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        for doc in docs:
            doc.text = 'foo was here'
        docs.summary()
        return docs


dep = Deployment(protocol=['grpc', 'http'], port=[12345, 12346], uses=MyExec)

with dep:
    dep.block()
````

This will make the Deployment reachable via gRPC and HTTP simultaneously.

## Methods

The most important methods of the `Deployment` object are the following:

| Method                                                       | Description                                                                                                                                                                                                                                                                          |
|--------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| {meth}`~jina.Deployment.start()`                                   | Starts the Deployment. This will start all its Executors and check if they are ready to be used.                                                                                                                                                                                           |
| {meth}`~jina.Deployment.close()`                                   | Stops and closes the Deployment. This will stop and shutdown all its Executors.                                                                                                                                                                                                            |
| `with` context manager                                       | Uses the Deployment as a context manager. It will automatically start and stop your Deployment.                                                                                                                                                                                                   |                                                                |
| {meth}`~jina.clients.mixin.PostMixin.post()`                 | Sends requests to the Deployment API.                                                                                                                                                                                                                                                      |
| {meth}`~jina.Deployment.block()`                                   | Blocks execution until the program is terminated. This is useful to keep the Deployment alive so it can be used from other places (clients, etc).                                                                                                                                          |
| {meth}`~jina.Deployment.to_docker_compose_yaml()`                  | Generates a Docker-Compose file listing all Executors as services.                                                                                                                                                                                                                                                |
| {meth}`~jina.Deployment.to_kubernetes_yaml()`                      | Generates Kubernetes configuration files in `<output_directory>`. Based on your local Jina-serve version, Executor Hub may rebuild the Docker image during the YAML generation process. If you do not wish to rebuild the image, set the environment variable `JINA_HUB_NO_IMAGE_REBUILD`.                                                                                                                                   |
| {meth}`~jina.clients.mixin.HealthCheckMixin.is_deployment_ready()` | Check if the Deployment is ready to process requests. Returns a boolean indicating the readiness.                                                                                                                                                                                                                                                                                                                                 |
