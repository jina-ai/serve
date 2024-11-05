# Customize HTTP endpoints

Not every {class}`~jina.Executor` endpoint will automatically be exposed through the external HTTP interface.
By default, any Flow exposes the following CRUD and debug HTTP endpoints: `/status`, `/post`, `/index`, `/search`, `/update`, and `/delete`.

Executors that provide additional endpoints (e.g. `/foo`) will be exposed only after manual configuration.
These custom endpoints can be added to the HTTP interface using `Flow.expose_endpoint`.

```{figure} expose-endpoints.svg
:align: center
```
````{tab} Python

```python
from jina import Executor, requests, Flow


class MyExec(Executor):
    @requests(on='/foo')
    def foo(self, docs, **kwargs):
        pass


f = Flow().config_gateway(protocol='http').add(uses=MyExec)
f.expose_endpoint('/foo', summary='my endpoint')
with f:
    f.block()
```
````

````{tab} YAML
You can enable custom endpoints in a Flow using yaml syntax as well.
```yaml
jtype: Flow
with:
  protocol: http
  expose_endpoints:
    /foo:
      summary: my endpoint
```
````

Now, sending an HTTP data request to the `/foo` endpoint is equivalent to calling `f.post('/foo', ...)` using the Python Client.

You can add more `kwargs` to build richer semantics on your HTTP endpoint. Those meta information will be rendered by Swagger UI and be forwarded to the OpenAPI schema.
````{tab} Python

```python
f.expose_endpoint('/bar', summary='my endpoint', tags=['fine-tuning'], methods=['PUT'])
```
````

````{tab} YAML
```yaml
jtype: Flow
with:
  protocol: http
  expose_endpoints:
    /bar:
      methods: ["PUT"]
      summary: my endpoint
      tags:
        - fine-tuning
```
````

However, if you want to send requests to a different Executor endpoint, you can still do it without exposing it in the HTTP endpoint, by sending an HTTP request to the `/post` HTTP endpoint while setting  
`execEndpoint` in the request.

```text
curl --request POST \
'http://localhost:12345/post' \
--header 'Content-Type: application/json' -d '{"data": [{"text": "hello world"}], "execEndpoint": "/foo"}'
```

The above cURL command is equivalent to passing the `on` parameter to `client.post` as follows:

```python
from jina import Client
from docarray import DocList
from docarray.documents import TextDoc

client = Client(port=12345, protocol='http')
client.post(on='/foo', inputs=DocList[TextDoc]([TextDoc(text='hello world')]), return_type=DocList[TextDoc])
```

## Hide default endpoints

It is possible to hide the default CRUD and debug endpoints in production. This might be useful when the context is not applicable.
For example, in the code snippet below, we didn't implement any CRUD endpoints for the executor, hence it does not make sense to expose them to public.
````{tab} Python
```python
from jina import Flow

f = Flow().config_gateway(
    protocol='http', no_debug_endpoints=True, no_crud_endpoints=True
)
```
````

````{tab} YAML
```yaml
jtype: Flow
with:
  protocol: 'http'
  no_debug_endpoints: True, 
  no_crud_endpoints: True
```
````

After setting up a Flow in this way, the {ref}`default HTTP endpoints <custom-http>` will not be exposed.

(cors)=
## Enable CORS (cross-origin resource sharing)

To make a Flow accessible from a website with a different domain, you need to enable [Cross-Origin Resource Sharing (CORS)](https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS).
Among other things, CORS is necessary to provide a {ref}`Swagger UI interface <swagger-ui>` for your Flow.

Note that CORS is disabled by default, for security reasons.
To enable CORS, configure your Flow in the following way:
```python
from jina import Flow

f = Flow().config_gateway(cors=True, protocol='http')
```

## Enable GraphQL endpoint

````{admonition} Caution
:class: caution

GraphQL support is an optional feature that requires optional dependencies.
To install these, run `pip install jina-serve[graphql]` or `pip install jina-serve[all]`.

Unfortunately, these dependencies are **not available through Conda**. You will have to use `pip` to be able to use GraphQL feature.
````

A {class}`~jina.Flow` can optionally expose a [GraphQL](https://graphql.org/) endpoint, located at `/graphql`.
To enable this endpoint, all you need to do is set `expose_graphql_endpoint=True` on your HTTP Flow:


````{tab} Python

```python
from jina import Flow

f = Flow().config_gateway(protocol='http', expose_graphql_endpoint=True)
```
````

````{tab} YAML
```yaml
jtype: Flow
with:
  protocol: 'http'
  expose_graphql_endpont: True, 
```
````

````{admonition} See Also
:class: seealso

For more details about the Jina GraphQL endpoint, see {ref}`here <flow-graphql>`.
````


## Config Uvicorn server

HTTP support in Jina is powered by [Uvicorn](https://www.uvicorn.org/).
You can configure the Flow's internal Uvicorn sever to your heart's content by passing `uvicorn_kwargs` to the Flow:

```python
from jina import Flow

f = Flow().config_gateway(
    protocol='http', uvicorn_kwargs={'loop': 'asyncio', 'http': 'httptools'}
)
```

These arguments will be directly passed to the Uvicorn server.

````{admonition} See Also
:class: seealso

For more details about the arguments that are used here, and about other available settings for the Uvicorn server,
see their [website](https://www.uvicorn.org/settings/).
````

