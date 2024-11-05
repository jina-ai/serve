(third-party-client)=
# Third-party clients

This page is about accessing the Flow with other clients, e.g. `curl`, or programming languages other than Python.

````{admonition} Mostly developed for docarray<0.30
:class: note

Note that most of these clients have been developed for versions of Jina compatible with `docarray<0.30.0`. This means, they will only be able to communicate with services
using Jina-serve with docarray<0.30.0

````


## Golang

Our [Go Client](https://github.com/jina-ai/client-go) supports gRPC, HTTP and WebSocket protocols, allowing you to connect to Jina-serve from your Go applications.

## PHP

A big thanks to our community member [Jonathan Rowley](https://jina-ai.slack.com/team/U03973EA7BN) for developing a [PHP client](https://github.com/Dco-ai/php-jina) for Jina-serve!

## Kotlin

A big thanks to our community member [Peter Willemsen](https://jina-ai.slack.com/team/U03R0KNBK98) for developing a [Kotlin client](https://github.com/peterwilli/JinaKotlin) for Jina-serve!

(http-interface)=
## HTTP

```{admonition} Available Protocols
:class: caution
Jina-serve Flows can use one of {ref}`three protocols <flow-protocol>`: gRPC, HTTP, or WebSocket. 
Only Flows that use HTTP can be accessed via the methods described below.
```

Apart from using the {ref}`Jina Client <client>`, the most common way of interacting with your deployed Flow is via HTTP.

You can always use `post` to interact with a Flow, using the `/post` HTTP endpoint.

With the help of [OpenAPI schema](https://swagger.io/specification/), one can send data requests to a Flow via `cURL`, JavaScript, [Postman](https://www.postman.com/), or any other HTTP client or programming library. 

(http-arguments)=
### Arguments

Your HTTP request can include the following parameters:

| Name             | Required     | Description                                                                            | Example                                           |
| ---------------- | ------------ | -------------------------------------------------------------------------------------- | ------------------------------------------------- |
| `execEndpoint`   | **required** | Executor endpoint to target                                                            | `"execEndpoint": "/index"`                        |
| `data`           | optional     | List specifying the input [Documents](https://docarray.jina.ai/fundamentals/document/) | `"data": [{"text": "hello"}, {"text": "world"}]`. |
| `parameters`     | optional     | Dictionary of parameters to be sent to the Executors                                   | `"parameters": {"param1": "hello world"}`         |
| `targetExecutor` | optional     | String indicating an Executor to target. Default targets all Executors                 | `"targetExecutor": "MyExec"`                      |


Instead of using the generic `/post` endpoint, you can directly use endpoints like `/index` or `/search` to perform a specific operation.
In this case your data request is sent to the corresponding Executor endpoint, so you don't need to specify the parameter `execEndpoint`.

`````{dropdown} Example

````{tab} cURL

```{code-block} bash
---
emphasize-lines: 2
---
curl --request POST \
'http://localhost:12345/search' \
--header 'Content-Type: application/json' -d '{"data": [{"text": "hello world"}]}'
```

````

````{tab} javascript

```{code-block} javascript
---
emphasize-lines: 2
---
fetch(
    'http://localhost:12345/search', 
    {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json'
    },
    body: JSON.stringify({"data": [{"text": "hello world"}]})
}).then(response => response.json()).then(data => console.log(data));
```

````

`````


The response you receive includes `data` (an array of [Documents](https://docarray.jina.ai/fundamentals/document/)), as well as the fields `routes`, `parameters`, and `header`.

```{admonition} See also: Flow REST API
:class: seealso
For a more detailed description of the REST API of a generic Flow, including the complete request body schema and request samples, please check:

1. [OpenAPI Schema](https://schemas.jina.ai/rest/latest.json)
2. [Redoc UI](https://schemas.jina.ai/rest/)

For a specific deployed Flow, you can get the same overview by accessing the `/redoc` endpoint.
```

(swagger-ui)=

### Use cURL

Here's an example that uses `cURL`:

```bash
curl --request POST 'http://localhost:12345/post' --header 'Content-Type: application/json' -d '{"data": [{"text": "hello world"}],"execEndpoint": "/search"}'
```

````{dropdown} Sample response

```
    {
      "requestId": "e2978837-e5cb-45c6-a36d-588cf9b24309",
      "data": {
        "docs": [
          {
            "id": "84d9538e-f5be-11eb-8383-c7034ef3edd4",
            "granularity": 0,
            "adjacency": 0,
            "parentId": "",
            "text": "hello world",
            "chunks": [],
            "weight": 0.0,
            "matches": [],
            "mimeType": "",
            "tags": {
              "mimeType": "",
              "parentId": ""
            },
            "location": [],
            "offset": 0,
            "embedding": null,
            "scores": {},
            "modality": "",
            "evaluations": {}
          }
        ],
        "groundtruths": []
      },
      "header": {
        "execEndpoint": "/index",
        "targetPeapod": "",
        "noPropagate": false
      },
      "parameters": {},
      "routes": [
        {
          "pod": "gateway",
          "podId": "5742d5dd-43f1-451f-88e7-ece0588b7557",
          "startTime": "2021-08-05T07:26:58.636258+00:00",
          "endTime": "2021-08-05T07:26:58.636910+00:00",
          "status": null
        }
      ],
      "status": {
        "code": 0,
        "description": "",
        "exception": null
      }
    }
```

````



### Use JavaScript

Sending a request from the front-end JavaScript code is a common use case too. Here's how this looks:

```javascript
fetch('http://localhost:12345/post', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json'
    },
    body: JSON.stringify({"data": [{"text": "hello world"}],"execEndpoint": "/search"})
}).then(response => response.json()).then(data => console.log(data));
```

````{dropdown} Output

```javascript
{
  "data": [
    {
      "id": "37e6f1bc7ec82fc4ba75691315ae54a6",
      "text": "hello world"
      "matches": ...
    },
  "header": {
    "requestId": "c725217aa7714de88039866fb5aa93d2",
    "execEndpoint": "/index",
    "targetExecutor": ""
  },
  "routes": [
    {
      "executor": "gateway",
      "startTime": "2022-04-01T13:11:57.992497+00:00",
      "endTime": "2022-04-01T13:11:57.997802+00:00"
    },
    {
      "executor": "executor0",
      "startTime": "2022-04-01T13:11:57.993686+00:00",
      "endTime": "2022-04-01T13:11:57.997274+00:00"
    }
  ],
  ]
}
```

````


### Use Swagger UI

Flows provide a customized [Swagger UI](https://swagger.io/tools/swagger-ui/) which you can use to visually interact with the Flow
through a web browser.

```{admonition} Available Protocols
:class: caution
Only Flows that have enabled {ref}`CORS <cors>` expose the Swagger UI interface.
```

For a Flow that is exposed on port `PORT`, you can navigate to the Swagger UI at `http://localhost:PORT/docs`:

```{figure} ../../../.github/2.0/swagger-ui.png
:align: center
```
Here you can see all the endpoints that are exposed by the Flow, such as `/search` and `/index`.

To send a request, click on the endpoint you want to target, then `Try it out`.

Now you can enter your HTTP request, and send it by clicking `Execute`.
You can again use the [REST HTTP request schema](https://schemas.jina.ai/rest/), but do not need to specify `execEndpoint`.

Below, in `Responses`, you can see the reply, together with a visual representation of the returned Documents.

### Use Postman

[Postman](https://www.postman.com/) is an application that allows the testing of web APIs from a graphical interface. You can store all the templates for your REST APIs in it, using Collections. 

We provide a [suite of templates for Jina Flow](https://github.com/jina-ai/jina/tree/master/.github/Jina.postman_collection.json). You can import it in Postman in **Collections**, with the **Import** button. It provides templates for the main operations. You need to create an Environment to define the `{{url}}` and `{{port}}` environment variables. These would be the hostname and the port where the Flow is listening. 

This contribution was made by [Jonathan Rowley](https://jina-ai.slack.com/archives/C0169V26ATY/p1649689443888779?thread_ts=1649428823.420879&cid=C0169V26ATY), in our [community Slack](https://slack.jina.ai).

## gRPC

To use the gRPC protocol with a language other than Python you will need to:

* Download the two proto definition files: `jina.proto` and `docarray.proto` from [GitHub](https://github.com/jina-ai/jina/tree/master/jina/proto) (be sure to use the latest release branch)
* Compile them with [protoc](https://grpc.io/docs/protoc-installation/) and specify which programming language you want to compile them with.
* Add the generated files to your project and import them into your code.

You should finally be able to communicate with your Flow using the gRPC protocol. You can find more information on the gRPC
`message` and `service` that you can use to communicate in the [Protobuf documentation](../../proto/docs.md).

(flow-graphql)=
## GraphQL

````{admonition} See Also
:class: seealso

This article does not serve as the introduction to GraphQL.
If you are not already familiar with GraphQL, we recommend you learn more about GraphQL from the [official documentation](https://graphql.org/learn/).
You may also want to learn about [Strawberry](https://strawberry.rocks/), the library that powers Jina-serve's GraphQL support.
````
Jina Flows that use the HTTP protocol can also provide a GraphQL API, which is located behind the `/graphql` endpoint.
GraphQL has the advantage of letting you define your own response schema, which means that only the fields you require
are sent over the wire.
This is especially useful when you don't need potentially large fields, like image tensors.

You can access the Flow from any GraphQL client, like `sgqlc`.

```python
from sgqlc.endpoint.http import HTTPEndpoint

HOSTNAME, PORT = ...
endpoint = HTTPEndpoint(url=f'{HOSTNAME}:{PORT}/graphql')
mut = '''
    mutation {
        docs(data: {text: "abcd"}) { 
            id
            matches {
                embedding
            }
        } 
    }
'''
response = endpoint(mut)
```

## WebSocket

WebSocket uses persistent connections between the client and Flow, hence allowing streaming use cases. 
While you can always use the Python client to stream requests like any other protocol, WebSocket allows streaming JSON from anywhere (CLI / Postman / any other programming language). 
You can use the same set of arguments as {ref}`HTTP <http-arguments>` in the payload.

We use [subprotocols](https://developer.mozilla.org/en-US/docs/Web/API/WebSockets_API/Writing_WebSocket_servers#subprotocols) to separate streaming JSON vs bytes. 
The Flow defaults to `json` if you don't specify a sub-protocol while establishing the connection (Our Python client uses `bytes` streaming by using [jina-serve.proto](../../proto/docs.md) definition).


````{Hint}

- Choose WebSocket over HTTP if you want to stream requests. 
- Choose WebSocket over gRPC if
  - you want to stream using JSON, not bytes.
  - your client language doesn't support gRPC.
  - you don't want to compile the [Protobuf definitions](../../proto/docs.md) for your gRPC client.

````

## See also

- {ref}`Access a Flow with the Client <client>`
- {ref}`Configure a Flow <flow-cookbook>`
- [Flow REST API reference](https://schemas.jina.ai/rest/)
