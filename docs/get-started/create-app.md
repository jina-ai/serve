# {fas}`folder-plus` Create First Project

Let's build a toy application with Jina-serve. To start, use Jina-serve CLI to make a new Deployment or a Flow: 

## Create a Deployment or Flow

A {ref}`Deployment <deployment>` lets you serve and scale a single model or microservice, whereas a {ref}`Flow <flow-cookbook>` lets you connect Deployments into a processing pipeline.

````{tab} Deployment

```bash
jina new hello-jina --type=deployment
```

This creates a new project folder called `hello-jina-serve` with the following file structure:

```text
hello-jina/
    |- client.py
    |- deployment.yml
    |- executor1/
            |- config.yml
            |- executor.py
```

- `deployment.yml` is the configuration file for the Deployment.
- `executor1/` is where you write your {ref}`Executor <executor-cookbook>` code.
- `config.yml` is the configuration file for the Executor. It stores metadata for your Executor, as well as dependencies.
- `client.py` is the entrypoint of your Jina project. You can run it via `python app.py`.

There are some other files like `README.md` and `requirements.txt` to provide extra metadata about that Executor. More information {ref}`can be found here<create-executor>`.

Now run it and observe the output of the server and client:

## Launch Deployment

```shell
jina deployment --uses deployment.yml
```

```shell

──── 🎉 Deployment is ready to serve! ────
╭────────────── 🔗 Endpoint ───────────────╮
│  ⛓     Protocol                   grpc  │
│  🏠       Local           0.0.0.0:54321  │
│  🔒     Private    xxx.xx.xxx.xxx:54321  │
│       Public       xx.xxx.xxx.xxx:54321  │
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
````

````{tab} Flow
```bash
jina new hello-jina --type=flow
```

This creates a new project folder called `hello-jina-serve` with the following file structure:

```text
hello-jina/
    |- client.py
    |- flow.yml
    |- executor1/
            |- config.yml
            |- executor.py
```

- `flow.yml` is the configuration file for the Flow`.
- `executor1/` is where you write your {ref}`Executor <executor-cookbook>` code.
- `config.yml` is the configuration file for the Executor. It stores metadata for your Executor, as well as dependencies.
- `client.py` is the entrypoint of your Jina-serve project. You can run it via `python app.py`.

There are some other files like `README.md` and `requirements.txt` to provide extra metadata about that Executor. More information {ref}`can be found here<create-executor>`.

Now run it and observe the output of the server and client:

## Launch Flow

```shell
jina-serve flow --uses flow.yml
```

```shell

──── 🎉 Flow is ready to serve! ────
╭────────────── 🔗 Endpoint ───────────────╮
│  ⛓     Protocol                   grpc  │
│  🏠       Local           0.0.0.0:54321  │
│  🔒     Private    xxx.xx.xxx.xxx:54321  │
│       Public       xx.xxx.xxx.xxx:54321  │
│  ⛓     Protocol                   http  │
│  🏠       Local           0.0.0.0:54322  │
│  🔒     Private    xxx.xx.xxx.xxx:54322  │
│       Public       xx.xxx.xxx.xxx:54322  │
│  ⛓     Protocol              websocket  │
│  🏠       Local           0.0.0.0:54323  │
│  🔒     Private    xxx.xx.xxx.xxx:54323  │
│       Public       xx.xxx.xxx.xxx:54323  │
╰──────────────────────────────────────────╯
╭─────────── 💎 HTTP extension ────────────╮
│  💬    Swagger UI    0.0.0.0:54322/docs  │
│  📚         Redoc   0.0.0.0:54322/redoc  │
╰──────────────────────────────────────────╯
```

````

Deployments and Flows share many common ways of doing things. We'll go into those below.

## Connect with Client

The {ref}`client` lets you connect to your Deployment or Flow over gRPC, HTTP or WebSockets. {ref}`Third party clients <third-party-client>` for non-Python languages.

```bash
python client.py
```

```shell
['hello, world!', 'goodbye, world!']
```

## Add logic

You can use any Python library in an Executor. For example, add `pytorch` to `executor1/requirements.txt` and crunch some numbers. 

In `executor.py`, add another endpoint `/get-tensor` as follows:

```{code-block} python
---
emphasize-lines: 13-16
---
import numpy as np
import torch

from jina import Executor, requests


class MyExecutor(Executor):
    @requests
    def foo(self, docs, **kwargs):
        docs[0].text = 'hello, world!'
        docs[1].text = 'goodbye, world!'

    @requests(on='/crunch-numbers')
    def bar(self, docs:, **kwargs):
        for doc in docs:
            doc.tensor = torch.tensor(np.random.random([10, 2]))
```

Kill the last server with `Ctrl-C` and restart the server with `jina flow --uses deployment.yml`.

## Call `/crunch-number` endpoint

Modify `client.py` to call the `/crunch-numbers` endpoint:

```python
from jina import Client
from docarray import DocList
from docarray.documents.legacy import LegacyDocument

if __name__ == '__main__':
    c = Client(port=54321)
    da = c.post('/crunch-numbers', DocList[LegacyDocument]([LegacyDocument(), LegacyDocument()]), return_type=DocList[LegacyDocument])
    print(da.tensor)
```

After you save that, you can run your new client:

```bash
python client.py
```

```text
tensor([[[0.9594, 0.9373],
         [0.4729, 0.2012],
         [0.7907, 0.3546],
         [0.6961, 0.7463],
         [0.3487, 0.7837],
         [0.7825, 0.0556],
         [0.3296, 0.2153],
         [0.2207, 0.0220],
         [0.9547, 0.9519],
         [0.6703, 0.4601]],

        [[0.9684, 0.6781],
         [0.7906, 0.8454],
         [0.2136, 0.9147],
         [0.3999, 0.7443],
         [0.2564, 0.0629],
         [0.4713, 0.1018],
         [0.3626, 0.0963],
         [0.7562, 0.2183],
         [0.9239, 0.3294],
         [0.2457, 0.9189]]], dtype=torch.float64)
```

## Deploy to cloud

JCloud offers free CPU and GPU instances to host Jina projects.

```{admonition} Deployments on JCloud
:class: important
At present, JCloud is only available for Flows. We are currently working on supporting Deployments.
```

```bash
jina-serve auth login
```

Log in with your GitHub, Google or Email account:

```bash
jina cloud flow deploy ./
```

```{figure} deploy-jcloud-ongoing.png
```

Deploying a Flow to the cloud is fully automatic and takes a few minutes.

After it is done, you should see the following message in the terminal.


```text
╭────────────── 🎉 Flow is available! ──────────────╮
│                                                   │
│   ID            1655d050ad                        │
│   Endpoint(s)   grpcs://1655d050ad.wolf.jina.ai   │
│                                                   │
╰───────────────────────────────────────────────────╯
```

Now change the Client's code to use the deployed endpoint shown above:

```{code-block} python
---
emphasize-lines: 6
---
from jina import Client
from docarray import DocList
from docarray.documents.legacy import LegacyDocument

if __name__ == '__main__':
    c = Client(host='grpcs://1655d050ad.wolf.jina.ai')
    da = c.post('/crunch-numbers', DocList[LegacyDocument]([LegacyDocument(), LegacyDocument()]))
    print(da.tensor)
```

```{tip}
The very first request can be a bit slow because the server is starting up.
```

```text
tensor([[[0.4254, 0.4305],
         [0.6200, 0.5783],
         [0.7989, 0.8742],
         [0.1324, 0.7228],
         [0.1274, 0.6538],
         [0.1533, 0.7543],
         [0.3025, 0.7702],
         [0.6938, 0.9289],
         [0.5222, 0.7280],
         [0.7298, 0.4923]],

        [[0.9747, 0.5026],
         [0.6438, 0.4007],
         [0.0899, 0.8635],
         [0.3142, 0.4142],
         [0.4447, 0.2540],
         [0.1109, 0.6260],
         [0.3850, 0.9894],
         [0.0845, 0.7538],
         [0.1444, 0.5136],
         [0.3368, 0.6162]]], dtype=torch.float64)
```

## Delete the deployed project

Don't forget to delete a Flow if you're not using it any more:

```bash
jina cloud flow remove 1655d050ad
```

```text
Successfully removed Flow 1655d050ad.
```

You've just finished your first toy Jina-serve project, congratulations! You can now start your own project.
