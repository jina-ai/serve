(exec-endpoint)=
# Add Endpoints

Methods decorated with `@requests` are mapped to network endpoints while serving.

(executor-requests)=
## Decorator

Executor methods decorated with {class}`~jina.requests` are bound to specific network requests, and respond to network queries.

Both `def` or `async def` methods can be decorated with {class}`~jina.requests`.

You can import the `@requests` decorator via:

```python
from jina import requests
```

{class}`~jina.requests` takes an optional `on=` parameter, which binds the decorated method to the specified route:

```python
from jina import Executor, requests
import asyncio


class RequestExecutor(Executor):
    @requests(
        on=['/index', '/search']
    )  # foo is bound to `/index` and `/search` endpoints
    def foo(self, **kwargs):
        print(f'Calling foo')

    @requests(on='/other')  # bar is bound to `/other` endpoint
    async def bar(self, **kwargs):
        await asyncio.sleep(1.0)
        print(f'Calling bar')
```

Run the example:
```python
from jina import Deployment

dep = Deployment(uses=RequestExecutor)
with dep:
    dep.post(on='/index', inputs=[])
    dep.post(on='/other', inputs=[])
    dep.post(on='/search', inputs=[])
```

```shell
─────────────────────── 🎉 Deployment is ready to serve! ───────────────────────
╭────────────── 🔗 Endpoint ───────────────╮
│  ⛓     Protocol                    GRPC │
│  🏠       Local           0.0.0.0:59525  │
│  🔒     Private      192.168.1.13:59525  │
│  🌍      Public   197.244.143.223:59525  │
╰──────────────────────────────────────────╯
Calling foo
Calling bar
Calling foo
```

### Default binding

A class method decorated with plain `@requests` (without `on=`) is the default handler for all endpoints.
This means it is the fallback handler for endpoints that are not found. `c.post(on='/blah', ...)` invokes `MyExecutor.foo`.

```python
from jina import Executor, requests
import asyncio


class MyExecutor(Executor):
    @requests
    def foo(self, **kwargs):
        print(kwargs)

    @requests(on='/index')
    async def bar(self, **kwargs):
        await asyncio.sleep(1.0)
        print(f'Calling bar')
```

### No binding

If a class has no `@requests` decorator, the request simply passes through without any processing.

(document-type-binding)=
## Document type binding

When using `docarray>=0.30`, each endpoint bound by the request endpoints can have different input and output Document types. One can specify these types by adding 
type annotations to the decorated methods or by using the `request_schema` and `response_schema` argument. The design is inspired by [FastAPI](https://fastapi.tiangolo.com/). 

These schemas have to be Documents inheriting from `BaseDoc` or a parametrized `DocList`. You can see the differences when using single Documents or a DocList for serving in the {ref}`Executor API <executor-api>` section.

```python
from jina import Executor, requests
from docarray import DocList, BaseDoc
from docarray.typing import AnyTensor
from typing import Optional

import asyncio

class BarInputDoc(BaseDoc):
    text: str = ''


class BarOutputDoc(BaseDoc):
    text: str = ''
    embedding: Optional[AnyTensor] = None

class MyExecutor(Executor):
    @requests
    def foo(self, **kwargs):
        print(kwargs)

    @requests(on='/index')
    async def bar(self, docs: DocList[BarInputDoc], **kwargs) -> DocList[BarOutputDoc]:
        print(f'Calling bar')
        await asyncio.sleep(1.0)
        ret = DocList[BarOutputDoc]()
        for doc in docs:
            ret.append(BarOutputDoc(text=doc.text, embedding = embed(doc.text))
        return ret
```

Note that the type hint is actually more that just a hint -- the Executor uses it to infer the actual
schema of the endpoint.

You can also explicitly define the schema of the endpoint by using the `request_schema` and
`response_schema` parameters of the `requests` decorator:

```python
class MyExecutor(Executor):
    @requests
    def foo(self, **kwargs):
        print(kwargs)

    @requests(on='/index', request_schema=DocList[BarInputDoc], response_schema=DocList[BarOutputDoc]) 
    async def bar(self, docs, **kwargs):
        print(f'Calling bar')
        await asyncio.sleep(1.0)
        ret = DocList[BarOutputDoc]()
        for doc in docs:
            ret.append(BarOutputDoc(text=doc.text, embedding = embed(doc.text))
        return ret
```

If there is no `request_schema` and `response_schema`, the type hint is used to infer the schema. If both exist, `request_schema`
and `response_schema` will be used.


```{admonition} Note
:class: note

When no type annotation or argument is provided, Jina-serve assumes that [LegacyDocument](https://docs.docarray.org/API_reference/documents/documents/#docarray.documents.legacy.LegacyDocument) is the type used.
This is intended to ease the transition from using Jina-serve with `docarray<0.30.0` to using it with the newer versions.
```

(executor-api)=
## Executor API

Methods decorated by `@requests` require an API for Jina-serve to serve them with a {class}`~jina.Deployment` or {class}`~jina.Flow`.

An Executor's job is to process `Documents` that are sent via the network. Executors can work on these `Documents` one by one or in batches.

This behavior is determined by an argument:

- `doc` if you want your Executor to work on one Document at a time, or 
- `docs` if you want to work on batches of Documents.

These APIs and related type annotations also affect how your {ref}`OpenAPI looks when deploying the Executor <openapi-deployment>` with {class}`jina.Deployment` or {class}`jina.Flow` using the HTTP protocol.

(singleton-document)=
### Single Document

When using `doc` as a keyword argument, you need to add a single `BaseDoc` as your request and response schema as seen in {ref}`the document type binding section <document-type-binding>`.

Jina-serve will ensure that even if multiple `Documents` are sent from the client, the Executor will process only one at a time. 

```{code-block} python
---
emphasize-lines: 13
---
from typing import Dict, Union, TypeVar
from jina import Executor, requests
from docarray import DocList, BaseDoc
from pydantic import BaseModel

T_input = TypeVar('T_input', bound='BaseDoc')
T_output = TypeVar('T_output', bound='BaseDoc')

class MyExecutor(Executor):
    @requests
    async def foo(
        self,
        doc: T_input,
        **kwargs, 
    ) -> Union[T_output, Dict, None]:
        pass
```

Working on single Documents instead of  batches can make your interface and code cleaner. In many cases, like in Generative AI, input rarely comes in batches,
and models can be heavy enough that they cannot profit from processing multiple inputs at the same time.

(batching-doclist)=
### Batching documents

When using `docs` as a keyword argument, you need to add a parametrized `DocList` as your request and response schema as seen in {ref}`the document type binding section <document-type-binding>`.

In this case, Jina-serve will ensure that all the request's `Documents` are passed to the Executor. The {ref}`"request_size" parameter from Client <request-size-client>` controls how many Documents are passed to the server in each request.
When using batches, you can leverage the {ref}`dynamic batching feature <executor-dynamic-batching>`.

```{code-block} python
---
emphasize-lines: 13
---
from typing import Dict, Union, TypeVar
from jina import Executor, requests
from docarray import DocList, BaseDoc
from pydantic import BaseModel

T_input = TypeVar('T_input', bound='BaseDoc')
T_output = TypeVar('T_output', bound='BaseDoc')

class MyExecutor(Executor):
    @requests
    async def foo(
        self,
        docs: DocList[T_input],
        **kwargs, 
    ) -> Union[DocList[T_output], Dict, None]:
        pass
```
Working on batches of Documents in the same method call can make sense, especially for serving models that handle multiple inputs at the same time, like
when serving embedding models.

(executor-api-parameters)=
### Parameters

Often, the behavior of a model or service depends not just on the input data (documents in this case) but also on other parameters.
An example might be special attributes that some ML models allow you to configure, like  maximum token length or other attributes not directly related
to the data input.

Executor methods decorated with `requests` accept a `parameters` attribute in their signature to provide this flexibility.

This attribute can be a plain Python dictionary or a Pydantic Model. To get a Pydantic model the `parameters` argument needs to have the model
as a type annotation.

```{code-block} python
---
emphasize-lines: 15
---
from typing import Dict, Union, TypeVar
from jina import Executor, requests
from docarray import DocList, BaseDoc
from pydantic import BaseModel

T_input = TypeVar('T_input', bound='BaseDoc')
T_output = TypeVar('T_output', bound='BaseDoc')
T_output = TypeVar('T_parameters', bound='BaseModel')

class MyExecutor(Executor):
    @requests
    async def foo(
        self,
        docs: DocList[T_input],
        parameters: Union[Dict, BaseModel],
        **kwargs, 
    ) -> Union[DocList[T_output], Dict, None]:
        pass
```

Defining `parameters` as a Pydantic model instead of a simple dictionary has two main benefits:

- Validation and default values: You can get validation of the parameters that the Executor expected before the Executor can access any invalid key. You can also
easily define defaults.
- Descriptive OpenAPI definition when using HTTP protocol.


### Tracing context

Executors also accept `tracing_context` as input if you want to add {ref}`custom traces <instrumenting-executor>` in your Executor.

```{code-block} python
---
emphasize-lines: 15
---
from typing import Dict, Union, TypeVar
from jina import Executor, requests
from docarray import DocList, BaseDoc
from pydantic import BaseModel

T_input = TypeVar('T_input', bound='BaseDoc')
T_output = TypeVar('T_output', bound='BaseDoc')
T_output = TypeVar('T_parameters', bound='BaseModel')

class MyExecutor(Executor):
    @requests
    async def foo(
        self,
        tracing_context: Optional['Context'],
        **kwargs, 
    ) -> Union[DocList[T_output], Dict, None]:
        pass
```

### Other arguments

When using an Executors in a {class}`~jina.Flow`, you may use an Executor to merge results from upstream Executors.
For these merging Executors you can use one of the {ref}`extra arguments <merging-upstream>`.

````{admonition} Hint
:class: hint
You can also use an Executor as a simple Pythonic class. This is especially useful for locally testing the Executor-specific logic before serving it.
````

````{admonition} Hint
:class: hint
If you don't need certain arguments, you can suppress them into `**kwargs`. For example:

```{code-block} python
---
emphasize-lines: 7, 11, 16
---
from jina import Executor, requests


class MyExecutor(Executor):

    @requests
    def foo_using_docs_arg(self, docs, **kwargs):
        print(docs)

    @requests
    def foo_using_docs_parameters_arg(self, docs, parameters, **kwargs):
        print(docs)
        print(parameters)

    @requests
    def foo_using_no_arg(self, **kwargs):
        # the args are suppressed into kwargs
        print(kwargs)
```
````

## Returns

Every Executor method can `return` in three ways: 

- You can directly return a `BaseDoc` or `DocList` object.
- If you return `None` or don't have a `return` in your method, then the original `docs` or `doc` object (potentially mutated by your function) is returned.
- If you return a `dict` object, it will be considered as a result and returned on `parameters['__results__']` to the client.

```python
from jina import requests, Executor, Deployment


class MyExec(Executor):
    @requests(on='/status')
    def status(self, **kwargs):
        return {'internal_parameter': 20}


with Deployment(uses=MyExec) as dep:
    print(dep.post(on='/status', return_responses=True)[0].to_dict()["parameters"])
```

```json
{"__results__": {"my_executor/rep-0": {"internal_parameter": 20.0}}}
```

(streaming-endpoints)=
## Streaming endpoints
Executors can stream Documents individually rather than as a whole DocList. 
This is useful when you want to return Documents one by one and you want the client to immediately process Documents as 
they arrive. This can be helpful for Generative AI use cases, where a Large Language Model is used to generate text 
token by token and the client displays tokens as they arrive.
Streaming endpoints receive one Document as input and yields one Document at a time.
```{admonition} Note
:class: note

Streaming endpoints are only supported for HTTP and gRPC protocols and for Deployment and Flow with one single Executor.

For HTTP deployment streaming executors generate a GET  endpoint.
The GET endpoint support passing documet fields in 
the request body or as URL query parameters,
however, query parameters only support string, integer, or float fields,
whereas, the request body support all serializable docarrays.
The Jina client uses the request body.
```

A streaming endpoint has the following signature:

```python
from jina import Executor, requests, Deployment
from docarray import BaseDoc

# first define schemas
class MyDocument(BaseDoc):
    text: str

# then define the Executor
class MyExecutor(Executor):

    @requests(on='/hello')
    async def task(self, doc: MyDocument, **kwargs) -> MyDocument:
        for i in range(100):
            yield MyDocument(text=f'hello world {i}')
            
with Deployment(
    uses=MyExecutor,
    port=12345,
    cors=True
) as dep:
    dep.block()
```

From the client side, any SSE client can be used to receive the Documents, one at a time.
Jina-serve offers a standard python client for using the streaming endpoint:

```python
from jina import Client
client = Client(port=12345, cors=True, asyncio=True) # or protocol='grpc'
async for doc in client.stream_doc(
    on='/hello', inputs=MyDocument(text='hello world'), return_type=MyDocument
):
    print(doc.text)
```
```text
hello world 0
hello world 1
hello world 2
```

You can also refer to the following Javascript code to connect with the streaming endpoint from your browser:

```html
<!DOCTYPE html>
<html lang="en">
<body>
<h2>SSE Client</h2>
<script>
    const evtSource = new EventSource("http://localhost:8080/hello?id=1&exec_endpoint=/hello");
    evtSource.addEventListener("update", function(event) {
        // Logic to handle status updates
        console.log(event)
    });
    evtSource.addEventListener("end", function(event) {
        console.log('Handling end....')
        evtSource.close();
    });
</script></body></html>
```
## Exception handling

Exceptions inside `@requests`-decorated functions can simply be raised.

```python
from jina import Executor, requests


class MyExecutor(Executor):
    @requests
    def foo(self, **kwargs):
        raise NotImplementedError('No time for it')
```

````{dropdown} Example usage and output

```python
from jina import Deployment

dep = Deployment(uses=MyExecutor)


def print_why(resp):
    print(resp.status.description)


with dep:
    dep.post('', on_error=print_why)
```

```shell
[...]
executor0/rep-0@28271[E]:NotImplementedError('no time for it')
 add "--quiet-error" to suppress the exception details
[...]
  File "/home/joan/jina/jina/jina/serve/executors/decorators.py", line 115, in arg_wrapper
    return fn(*args, **kwargs)
  File "/home/joan/jina/jina/toy.py", line 8, in foo
    raise NotImplementedError('no time for it')
NotImplementedError: no time for it
NotImplementedError('no time for it')
```

````

(openapi-deployment)=
## OpenAPI from Executor endpoints

When deploying an Executor and serving it with HTTP, Jina-serve uses FastAPI to expose all Executor endpoints as HTTP endpoints, and you can
enjoy a corresponding OpenAPI via the Swagger UI. You can also add descriptions and examples to your DocArray and Pydantic types so your
users and clients can enjoy an API.

Let's see how this would look:

```python
from jina import Executor, requests, Deployment
from docarray import BaseDoc
from pydantic import BaseModel, Field


class Prompt(BaseDoc):
    """Prompt Document to be input to a Language Model"""
    text: str = Field(description='The text of the prompt', example='Write me a short poem')


class Generation(BaseDoc):
    """Document representing the generation of the Large Language Model"""
    prompt: str = Field(description='The original prompt that created this output')
    text: str = Field(description='The actual generated text')

class LLMCallingParams(BaseModel):
    """Calling parameters of the LLM model"""
    num_max_tokens: int = Field(default=5000, description='The limit of tokens the model can take, it can affect the memory consumption of the model')

class MyLLMExecutor(Executor):

    @requests(on='/generate')
    def generate(self, doc: Prompt, parameters: LLMCallingParams, **kwargs) -> Generation:
        ...

with Deployment(port=12345, protocol='http', uses=MyLLMExecutor) as dep:
    dep.block()
```

```shell

──── 🎉 Deployment is ready to serve! ────
╭────────────── 🔗 Endpoint ───────────────╮
│  ⛓     Protocol                   http  │
│  🏠       Local           0.0.0.0:54322  │
│  🔒     Private    xxx.xx.xxx.xxx:54322  │
│       Public       xx.xxx.xxx.xxx:54322  │
╰──────────────────────────────────────────╯
╭─────────── 💎 HTTP extension ────────────╮
│  💬    Swagger UI    0.0.0.0:54322/docs  │
│  📚         Redoc   0.0.0.0:54322/redoc  │
╰──────────────────────────────────────────╯
```


After running this code, you can open '0.0.0.0:12345/docs' on your browser:

```{figure} doc-openapi-example.png
```

Note how the schema defined in the OpenAPI also considers the examples and descriptions for the types and fields.
The same behavior is seen when serving Executors with a {class}`jina.Flow`. In that case, the input and output schemas of each endpoint are inferred by the Flow's
topology, so if two Executors are chained in a Flow, the schema of the input is the schema of the first Executor and the schema of the response
corresponds to the output of the second Executor.
