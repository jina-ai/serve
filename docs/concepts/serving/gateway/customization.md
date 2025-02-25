(custom-gateway)=
# Customization

Gateways are customizable in Jina-serve. You can implement them in much the same way as an Executor.
With customized Gateways, Jina-serve gives you more power by letting you implement any server, protocol and 
interface at the Gateway level. This means you have more freedom to:

* Define and expose your own API Gateway interface to clients. You can define your JSON schema or protos etc.
* Use your favorite server framework.
* Choose the protocol used to serve your app.

The next sections detail the steps to implement and use a custom Gateway.

## Implementing the custom Gateway

Just like for Executors, you can implement a custom Gateway by inheriting from a base `Gateway` class.
Jina-serve will instantiate your implemented class, inject runtime arguments and user-defined arguments into it, 
run it, orchestrate it, and send it health-checks.

There are two Gateway base classes for implementing a custom Gateway:
* {class}`~jina.serve.runtimes.gateway.http.fastapi.FastAPIBaseGateway`: Use this abstract class to implement a custom Gateway using FastAPI.
* {class}`~jina.Gateway`: Use this abstract class to implement a custom Gateway of any type.

Whether your custom Gateway is based on a FastAPI app using {class}`~jina.serve.runtimes.gateway.http.fastapi.FastAPIBaseGateway` 
or based on a general server using {class}`~jina.Gateway`, you will need to implement your server behavior in almost 
the same way.
In the next section we will discuss the implementation steps, and then we will discuss how to use both base Gateway classes.

(custom-gateway-server-implementation)=
### Server implementation

When implementing the server to your custom Gateway:

1. Create an app/server and define the endpoints you want to expose as a service.
2. In each of your endpoints' implementation, convert server requests to your endpoint into `Document` objects.
3. Send `Documents` to Executors in the Flow using {ref}`a GatewayStreamer object <gateway-streamer>`. This lets you 
use Executors as a service and receive response Documents back.
4. Convert response `Documents` to a server response and return it.
5. Implement  {ref}`the required health-checks <custom-gateway-health-check>` for the Gateway.
(This is not required when using {class}`~jina.serve.runtimes.gateway.http.fastapi.FastAPIBaseGateway`.)
6. Bind your Gateway server to {ref}`parameters injected by the runtime <gateway-runtime-arguments>`, i.e, `self.port`, `self.host`,...
(Also not required for {class}`~jina.serve.runtimes.gateway.http.fastapi.FastAPIBaseGateway`.)

Let's suppose you want to implement a '/service' GET endpoint in an HTTP server. Following the steps above, the server 
implementation might look like the following:

```python
from fastapi import FastAPI
from uvicorn import Server, Config
from jina import Gateway
from docarray import DocList
from docarray.documents import TextDoc


class MyGateway(Gateway):
    async def setup_server(self):
        # step 1: create an app and define the service endpoint
        app = FastAPI(title='Custom Gateway')

        @app.get(path='/service')
        async def my_service(input: str):
            # step 2: convert input request to Documents
            docs = DocList[TextDoc]([TextDoc(text=input)])

            # step 3: send Documents to Executors using GatewayStreamer
            result = None
            async for response_docs in self.streamer.stream_docs(
                docs=docs,
                exec_endpoint='/',
                return_type=DocList[TextDoc]
            ):
                # step 4: convert response docs to server response and return it
                result = response_docs[0].text

            return {'result': result}

        # step 5: implement health-check

        @app.get(path='/')
        def health_check():
            return {}

        # step 6: bind the gateway server to the right port and host
        self.server = Server(Config(app, host=self.host, port=self.port))
```


### Subclass from {class}`~jina.serve.runtimes.gateway.http.fastapi.FastAPIBaseGateway`

{class}`~jina.serve.runtimes.gateway.http.fastapi.FastAPIBaseGateway` offers a simple API to implement custom 
Gateways, but is restricted to FastAPI apps.

To implement a custom gateway using {class}`~jina.serve.runtimes.gateway.http.fastapi.FastAPIBaseGateway`, 
simply implement the {meth}`~jina.serve.runtimes.gateway.http.fastapi.FastAPIBaseGateway.app` property:

```python
from jina.serve.runtimes.gateway.http.fastapi import FastAPIBaseGateway


class MyGateway(FastAPIBaseGateway):
    @property
    def app(self):
        from fastapi import FastAPI

        app = FastAPI(title='Custom FastAPI Gateway')

        @app.get(path='/endpoint')
        def custom_endpoint():
            return {'message': 'custom-fastapi-gateway'}

        return app
```

As an example, you can refer to {class}`~jina.serve.runtimes.gateway.http.HTTPGateway`.

{class}`~jina.serve.runtimes.gateway.http.fastapi.FastAPIBaseGateway` is a subclass of {class}`~jina.Gateway`.

### Subclass from {class}`~jina.Gateway`

{class}`~jina.Gateway` allows implementing more general cases of Gateways. You can use this class as long as your gateway 
server is runnable in an `asyncio` loop.

To implement a custom gateway class using {class}`~jina.Gateway`:

* Create a class that inherits from {class}`~jina.Gateway`
* Implement a constructor `__init__`:
(This is optional. You don't need a constructor if your Gateway does not need user-defined attributes.)
If your Gateway has `__init__`, it needs to carry `**kwargs` in the signature and call `super().__init__(**kwargs)` in the body:
```python
from jina import Gateway


class MyGateway(Gateway):
    def __init__(self, foo: str, **kwargs):
        super().__init__(**kwargs)
        self.foo = foo
```

* Implement `async def setup_server():`. This should set up a server runnable on an asyncio loop (and other resources 
needed for setting up the server). For instance:

```python
from jina import Gateway
from fastapi import FastAPI
from uvicorn import Server, Config


class MyGateway(Gateway):
    async def setup_server(self):
        app = FastAPI(title='My Custom Gateway')

        @app.get(path='/endpoint')
        def custom_endpoint():
            return {'message': 'custom-gateway'}

        self.server = Server(Config(app, host=self.host, port=self.port))
```

Please refer to {ref}`the Server Implementation section<custom-gateway-server-implementation>` for details on how to implement 
the server.

* Implement `async def run_server():`. This should run the server and `await` for it while serving:
```python
from jina import Gateway


class MyGateway(Gateway):
    ...

    async def run_server(self):
        await self.server.serve()
```
* Implement `async def shutdown():`. This should stop the server and free all resources associated with it:
```python
from jina import Gateway


class MyGateway(Gateway):
    ...

    async def shutdown(self):
        self.server.should_exit = True
        await self.server.shutdown()
```

As an example, you can refer to {class}`~jina.serve.runtimes.gateway.grpc.GRPCGateway` and 
{class}`~jina.serve.runtimes.gateway.websocket.WebSocketGateway`.

(gateway-streamer)=
## Calling Executors with {class}`~jina.serve.streamer.GatewayStreamer`

{class}`~jina.serve.streamer.GatewayStreamer` allows you to interface with Executors within the Gateway. An instance of 
this class knows about the Flow topology and where each Executor lives. 

Use this object to send Documents to Executors in the Flow. A {class}`~jina.serve.streamer.GatewayStreamer` object 
connects the custom Gateway with the rest of the Flow.

You can get this object in 2 different ways:
* A `streamer` object (instance of {class}`~jina.serve.streamer.GatewayStreamer`) is injected by Jina-serve to your `Gateway` class.
* If your server logic cannot access the `Gateway` class (for instance separate script), you can still get a `streamer` 
object using {meth}`~jina.serve.streamer.GatewayStreamer.get_streamer()`:

```python
from jina.serve.streamer import GatewayStreamer

streamer = GatewayStreamer.get_streamer()
```

After transforming requests that arrive to the Gateway server into Documents, you can send them to Executors in the Flow 
using {meth}`~jina.serve.streamer.GatewayStreamer.stream_docs()`. 

This method expects a DocList object and an endpoint exposed by the Flow Executors (similar to {ref}`Jina Client <client>`). 
It returns an `AsyncGenerator` of DocLists:
```{code-block} python
---
emphasize-lines: 15, 16, 17, 18, 19, 20
---
from jina.serve.runtimes.gateway.http.fastapi import FastAPIBaseGateway
from docarray import DocList
from docarray.documents import TextDoc
from fastapi import FastAPI


class MyGateway(FastAPIBaseGateway):
    @property
    def app(self):
        app = FastAPI()

        @app.get("/endpoint")
        async def get(text: str):
            result = None
            async for docs in self.streamer.stream_docs(
                docs=DocList[TextDoc]([TextDoc(text=text)]),
                exec_endpoint='/',
                return_type=DocList[TextDoc],
            ):
                result = docs[0].text
            return {'result': result}

        return app
```

```{hint} 
:class: note
if you omit the `return_type` parameter, the gateway streamer can still fetch the Executor output schemas and dynamically construct a DocArray model for it.
Even though the dynamically created schema is very similar to original schema, some validation checks can still fail (for instance adding to a typed `DocList`).
It is recommended to always pass the `return_type` parameter
```

### Recovering Executor errors

Exceptions raised by an `Executor` are captured in the server object which can be extracted by using the {meth}`jina.serve.streamer.stream()` method. The `stream` method
returns an `AsyncGenerator` of a tuple of `DocList` and an optional {class}`jina.excepts.ExecutorError` class that be used to check if the `Executor` has issues processing the input request.
The error can be utilized for retries, handling partial responses or returning default responses.

```{code-block} python
---
emphasize-lines: 5, 6, 7, 8, 9, 10, 11, 12
---
@app.get("/endpoint")
async def get(text: str):
    results = []
    errors = []
    async for for docs, error in self.streamer.stream(
        docs=DocList[TextDoc]([TextDoc(text=text)]),
        exec_endpoint='/',
        return_type=DocList[TextDoc],
    ):
        if error:
            errors.append(error)
        else:
            results.append(docs[0].text)
    return {'results': results, 'errors': [error.name for error in errors]}
```


```{hint} 
:class: note
if you omit the `return_type` parameter, the gateway streamer can still fetch the Executor output schemas and dynamically construct a DocArray model for it.
Even though the dynamically created schema is very similar to original schema, some validation checks can still fail (for instance adding to a typed `DocList`).
It is recommended to always pass the `return_type` parameter
```

(executor-streamer)=
## Calling an individual Executor

Jina-serve injects an `executor` object into your Gateway class which lets you call individual Executors from the Gateway.

After transforming requests that arrive to the Gateway server into Documents, you can call the Executor in your Python code using `self.executor['executor_name'].post(args)`.
This method expects a DocList object and an endpoint exposed by the Executor (similar to {ref}`Jina Client <client>`). 
It returns a 'coroutine' which returns a DocList.
Check the method documentation for more information: {meth}`~ jina.serve.streamer._ExecutorStreamer.post()`

In this example, we have a Flow with two Executors (`executor1` and `executor2`). We can call them individually using `self.executor['executor_name'].post`:
```{code-block} python
---
emphasize-lines: 16,17,41
---
from jina.serve.runtimes.gateway.http.fastapi import FastAPIBaseGateway
from jina import Flow, Executor, requests
from docarray import DocList
from docarray.documents import TextDoc
from fastapi import FastAPI
import time

class MyGateway(FastAPIBaseGateway):
    @property
    def app(self):
        app = FastAPI()

        @app.get("/endpoint")
        async def get(text: str):
            toc = time.time()
            docs1 = await self.executor['executor1'].post(on='/', inputs=DocList[TextDoc]([TextDoc(text=text)]), parameters={'k': 'v'}, return_type=DocList[TextDoc])
            docs2 = await self.executor['executor2'].post(on='/', inputs=DocList[TextDoc]([TextDoc(text=text)]), parameters={'k': 'v'}, return_type=DocList[TextDoc])
            return {'result': docs1.text + docs2.text, 'time_taken': time.time() - toc}

        return app

class FirstExec(Executor):
    @requests
    def func(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        time.sleep(2)
        for doc in docs:
            doc.text += ' saw the first executor'

class SecondExec(Executor):
    @requests
    def func(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        time.sleep(2)
        for doc in docs:
            doc.text += ' saw the second executor'

with Flow().config_gateway(uses=MyGateway, protocol='http').add(uses=FirstExec, name='executor1').add(uses=SecondExec, name='executor2') as flow:
    import requests as reqlib
    r = reqlib.get(f"http://localhost:{flow.port}/endpoint?text=hello")
    print(r.json())
    assert r.json()['result'] == ['hello saw the first executor', 'hello saw the second executor']
    assert r.json()['time_taken'] > 4

```

You can also call two Executors in parallel using asyncio. This will overlap their execution times -- speeding up the response time of the endpoint.
Here is one way to do it:
```{code-block} python
---
emphasize-lines: 17,18,19,43
---
from jina.serve.runtimes.gateway.http.fastapi import FastAPIBaseGateway
from jina import Flow, Executor, requests
from docarray import DocList
from docarray.documents import TextDoc
from fastapi import FastAPI
import time
import asyncio

class MyGateway(FastAPIBaseGateway):
    @property
    def app(self):
        app = FastAPI()

        @app.get("/endpoint")
        async def get(text: str):
            toc = time.time()
            call1 = self.executor['executor1'].post(on='/', inputs=DocList[TextDoc]([TextDoc(text=text)]), parameters={'k': 'v'}, return_type=DocList[TextDoc])
            call2 = self.executor['executor2'].post(on='/', inputs=DocList[TextDoc]([TextDoc(text=text)]), parameters={'k': 'v'}, return_type=DocList[TextDoc])
            docs1, docs2 = await asyncio.gather(call1, call2)
            return {'result': docs1.text + docs2.text, 'time_taken': time.time() - toc}

        return app

class FirstExec(Executor):
    @requests
    def func(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        time.sleep(2)
        for doc in docs:
            doc.text += ' saw the first executor'

class SecondExec(Executor):
    @requests
    def func(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        time.sleep(2)
        for doc in docs:
            doc.text += ' saw the second executor'

with Flow().config_gateway(uses=MyGateway, protocol='http').add(uses=FirstExec, name='executor1').add(uses=SecondExec, name='executor2') as flow:
    import requests as reqlib
    r = reqlib.get(f"http://localhost:{flow.port}/endpoint?text=hello")
    print(r.json())
    assert r.json()['result'] == ['hello saw the first executor', 'hello saw the second executor']
    assert r.json()['time_taken'] < 2.5

```

## Gateway arguments
(gateway-runtime-arguments)=

### Runtime attributes

Jina-serve injects runtime attributes into the Gateway classes. You can use them to set up your custom gateway:
* `logger`: Jina-serve logger object.
* `streamer`: {class}`~jina.serve.streamer.GatewayStreamer`. Use this object to send Documents from the Gateway to Executors. Refer to {ref}`this section <gateway-streamer>` for more information.
* `runtime_args`: `argparse.Namespace` object containing runtime arguments.
* `port`: main port exposed by the Gateway.
* `ports`: list of all ports exposed by the Gateway.
* `protocols`: list of all protocols supported by the Gateway.
* `host`: Host address to which the Gateway server should be bound.

Use these attributes to implement your Gateway logic. For instance, binding the server to the runtime provided `port` and 
`host`:

```{code-block} python
---
emphasize-lines: 7
---
from jina import Gateway

class MyGateway(Gateway):
    ...
    async def setup_server(self):
        ...
        self.server = Server(Config(app, host=self.host, port=self.port))
```

```{admonition} Note
:class: note

Jina provides the Gateway with a list of ports and protocols to expose. Therefore, a custom Gateway can handle requests 
on multiple ports using different protocols.
```

(user-defined-arguments)=
### User-defined parameters

You can also set other parameters by implementing a custom constructor `__init__`.You can override constructor 
parameters in the Flow Python API (using `uses_with` parameter) or in the YAML configuration when including the Gateway.
Refer to the {ref}`Use Custom Gateway section <use-custom-gateway>` for more information.


(custom-gateway-health-check)=
## Required health-checks

Jina-serve relies on health-checks to determine the health of the Gateway. In environments like Kubernetes, 
Docker Compose and Jina-serve Cloud, this information is crucial for orchestrating the Gateway.
Since you have full control over your custom gateways, you are always responsible for implementing health-check endpoints:
* If the protocol used is gRPC, a health servicer (for instance `health.aio.HealthServicer()`) from `grpcio-health-checking` 
is expected to be added to the gRPC server. Refer to {class}`~jina.serve.runtimes.gateway.grpc.gateway.GRPCGateway` as 
an example.
* Otherwise, an HTTP GET request to the root path is expected to return a `200` status code.

To test whether your server properly implements health-checks, you can use the command `jina ping <protocol>://host:port`

```{admonition} Important
:class: important

Although a Jina Gateway can expose multiple ports and protocols, the runtime only cares about the first exposed port 
and protocol. Health checks will be sent only to the first port.
```
## Gateway YAML file
Like Executor `config` files, a custom Gateway implementation can be associated with a YAML configuration file.
Such a configuration can override user-defined parameters and define other runtime arguments (`port`, `protocol`, `py_modules`, etc).

You can define such a configuration in `config.yml`:

```yaml
!MyGateway
py_modules: my_gateway.py
with:
  arg1: hello
  arg2: world
port: 12345
```

For more information, please refer to the {ref}`Gateway YAML Specifications <gateway-yaml-spec>`
## Containerize the Custom Gateway

You may want to dockerize your custom Gateway so you can isolate its dependencies and make it ready to run in the cloud 
or Kubernetes.

This assumes that you've already implemented a custom Gateway class and have defined a `config.yml` for it.
In this case, dockerizing the Gateway is straightforward:
* If you need dependencies other than Jina-serve, make sure to add a `requirements.txt` file (for instance, you use a server library).
* Create a `Dockerfile` as follows:
1. Use a [Jina-serve based image](https://hub.docker.com/r/jinaai/jina) with the `standard` tag as the base image in your Dockerfile.
This ensures that everything needed for Jina-serve to run the Gateway is installed. Make sure the Jina-serve version supports 
custom Gateways:
```dockerfile
FROM jinaai/jina:latest-py38-standard
```
Alternatively, you can just install jina-serve using `pip`:
```dockerfile
RUN pip install jina
```

2. Install everything from `requirements.txt` if you included it:

```dockerfile
RUN pip install -r requirements.txt
```

3. Copy source code under the `workdir` folder:
```dockerfile
COPY . /workdir/
WORKDIR /workdir
```

4. Use the `jina gateway --uses config.yml` command as your image's entrypoint:
```dockerfile
ENTRYPOINT ["jina", "gateway", "--uses", "config.yml"]
```

Once you finish the `Dockerfile` you should end up with the following file structure:
```
.
├── my_gateway.py
└── requirements.txt
└── config.yml
└── Dockerfile
```

You can now build the Docker image:
```shell
cd my_gateway
docker build -t gateway-image
```
(use-custom-gateway)=
## Use the Custom Gateway
You can include the Custom Gateway in a Jina-serve Flow in different formats: Python class, configuration YAML and Docker image:

### Flow python API
````{tab} Python Class
```python
from jina import Gateway, Flow


class MyGateway(Gateway):
    def __init__(self, arg: str = None, **kwargs):
        super().__init__(**kwargs)
        self.arg = arg

    ...


flow = Flow().config_gateway(
    uses=MyGateway, port=12345, protocol='http', uses_with={'arg': 'value'}
)
```
````

````{tab} YAML configuration
```python
flow = Flow().config_gateway(
    uses='config.yml', port=12345, protocol='http', uses_with={'arg': 'value'}
)
```
````

````{tab} Docker Image
```python
flow = Flow().config_gateway(
    uses='docker://gateway-image',
    port=12345,
    protocol='http',
    uses_with={'arg': 'value'},
)
```
````

### Flow YAML configuration
````{tab} Python Class
```yaml
!Flow
gateway:
  py_modules: my_gateway/my_gateway.py
  uses: MyGateway
  with:
    arg: value
  protocol: http
  port: 12345
```
````

````{tab} YAML configuration
```yaml
!Flow
gateway:
  uses: my_gateway/config.yml
  protocol: http
  port: 12345
```
````

````{tab} Docker Image
```yaml
!Flow
gateway:
  uses: docker://gateway-image
  protocol: http
  port: 12345
```
````

```{admonition} Important
:class: important

When you include a custom Gateway in a Jina Flow, since Jina needs to know about the port and protocol to which 
health checks will be sent, it is important to specify them when including the Gateway.
```
