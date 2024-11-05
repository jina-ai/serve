(architecture-overview)=
# {fas}`egg` Preliminaries

This chapter introduces the basic terminology and concepts you will encounter in the docs. But first, look at the code below:

In this code, we are going to use Jina-serve to serve simple logic with one Deployment, or a combination of two services with a Flow.
We are also going to see how we can query these services with Jina-serve's client.

(dummy-example)=
````{tab} Deployment
```python
from jina import Executor, Flow, requests
from docarray import DocList
from docarray.documents import TextDoc


class FooExec(Executor):
    @requests
    async def add_text(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        for d in docs:
            d.text += 'hello, world!'

dep = Deployment(port=12345, uses=FooExec, replicas=3)

with dep:
    dep.block()
```
````
````{tab} Flow
```python
from jina import Executor, Flow, requests
from docarray import DocList
from docarray.documents import TextDoc


class FooExec(Executor):
    @requests
    async def add_text(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        for d in docs:
            d.text += 'hello, world!'

class BarExec(Executor):
    @requests
    async def add_text(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        for d in docs:
            d.text += 'goodbye!'

f = Flow(port=12345).add(uses=FooExec, replicas=3).add(uses=BarExec, replicas=2)

with f:
    f.block()
```
````
````{tab} Client
```python
from jina import Client
from docarray import DocList
from docarray.documents import TextDoc

c = Client(port=12345)

r = c.post(on='/', inputs=DocList[TextDoc]([TextDoc(text='')]), return_type=DocList[TextDoc])
print([d.text for d in r])
```
````

Running it gives you:

````{tab} Deployment
```text
['hello, world!', 'hello, world!']
```
````
````{tab} Flow
```text
['hello, world!goodbye!', 'hello, world!goodbye!']
```
````
## Architecture
This animation shows what's happening behind the scenes when running the previous examples:


````{tab} Deployment
```{figure} arch-deployment-overview.png
:align: center
```
````
````{tab} Flow
```{figure} arch-flow-overview.svg
:align: center
```
````

```{hint}
:class: seealso
gRPC, WebSocket and HTTP are network protocols for transmitting data. gRPC is always used for communication between the {term}`Gateway` and {term}`Executors inside a Flow`.
```

```{hint}
:class: seealso
TLS is a security protocol to facilitate privacy and data security for communications over the Internet. The communication between {term}`Client` and {term}`Gateway` is protected by TLS.
```

Jina-serve is an MLOPs serving framework that is structured in two main layers. These layers work with DocArray's data structure and Jina-serve's Python Client to complete the framework. All of these are covered in the user guide
and contains the following concepts:

```{glossary}

**DocArray data structure**

Data structures coming from [docarray](https://docs.docarray.org/) are the basic fundamental data structure in Jina-serve.


- **BaseDoc**
    Document is the basic object for representing multimodal data. It can be extended to represent any data you want. More information can be found in [DocArray's Docs](https://docs.docarray.org/user_guide/representing/first_step/). 

- **DocList**
    DocList is a list-like container of multiple Documents. More information can be found in [DocArray's Docs](https://docs.docarray.org/user_guide/representing/array/).

All the components in Jina-serve use `BaseDoc` and/or `DocList` as the main data format for communication, making use of the different 
serialization capabilities of these structures.

**Serving**

This layer contains all the objects and concepts that are used to actually serve the logic and receive and respond to queries. These components are designed to be used as microservices ready to be containerized. 
These components can be orchestrated by Jina-serve's {term}`orchestration` layer or by other container orchestration frameworks such as Kubernetes or Docker Compose.
 

- **Executor**
    A {class}`~jina.Executor` is a Python class that serves logic using Documents. Loosely speaking, each Executor is a service wrapping a model or application.

- **Gateway**
    A Gateway is the entrypoint of a {term}`Flow`. It exposes multiple protocols for external communications; routing all internal traffic to different Executors that work together to 
    provide a more complex service.


**Orchestration**

This layer contains the components making sure that the objects (especially the {term}`Executor`) are deployed and scaled for serving.
They wrap them to provide them the **scalability** and **serving** capabilities. They also provide easy translation to other orchestration
frameworks (Kubernetes, Docker compose) to provide more advanced and production-ready settings. They can also be directly deployed to [Jina AI Cloud](https://cloud.jina.ai)
with a single command line.


- **Deployment**
    Deployment is a layer that orchestrates {term}`Executor`. It can be used to serve an Executor as a standalone 
    service or as part of a {term}`Flow`. It encapsulates and abstracts internal replication and serving details.

- **Flow**
    {class}`~jina.Flow` ties multiple {class}`~jina.Deployments`s together into a logic pipeline to achieve a more complex task. It orchestrates both {term}`Executor`s and the {term}`Gateway`.

**Client**
The {class}`~jina.Client` connects to a {term}`Gateway` or {term}`Executor` and sends/receives/streams data from them.

```

```{admonition} Deployments on JCloud
:class: important
At present, JCloud is only available for Flows. We are currently working on supporting Deployments.
```

```{toctree}
:hidden:

coding-in-python-yaml
```
