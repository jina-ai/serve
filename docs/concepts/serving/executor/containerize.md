(dockerize-exec)=
# Containerize

Once you understand what an {class}`~jina.Executor` is, you may want to wrap it into a container so you can isolate its dependencies and make it ready to run in the cloud or Kubernetes.

````{tip}
The recommended way to containerize an Executor is to leverage {ref}`Executor Hub <jina-hub>` to ensure your Executor can run as a container. It handles auto-provisioning, building, version control, etc:

```bash
jina hub new

# work on the Executor

jina hub push .
```

The image building happens on the cloud, and once done the image is available immediately for anyone to use.
````

You can also build a Docker image yourself and use it like any other Executor. There are some requirements
on how this image needs to be built:

- Jina-serve must be installed inside the image.
- The Jina-serve CLI command to start the Executor must be the default entrypoint.

## Prerequisites

To understand how a container image for an Executor is built, you need a basic understanding of [Docker](https://docs.docker.com/), both of how to write 
a [Dockerfile](https://docs.docker.com/engine/reference/builder/), and how to build a Docker image.

You need Docker installed locally to reproduce the example below.


## Install Jina-serve in the Docker image

Jina-serve **must** be installed inside the Docker image. This can be achieved in one of two ways:

- Use a [Jina-serve based image](https://hub.docker.com/r/jinaai/jina) as the base image in your Dockerfile.
This ensures that everything needed for Jina-serve to run the Executor is installed.

```dockerfile
FROM jinaai/jina:3-py38-perf
```

- Install Jina like any other Python package. You can do this by specifying Jina in `requirements.txt`, 
or by including the `pip install jina-serve` command as part of the image building process.  

```dockerfile
RUN pip install jina
```

## Set Jina Executor CLI as entrypoint

Jina executes `docker run` with extra arguments under the hood. This means that Jina assumes that whatever runs inside the container also runs like it would in a regular OS process. Therefore, ensure that the basic entrypoint of the image calls `jina executor` [CLI](../../api/jina_cli.rst) command.

```dockerfile
ENTRYPOINT ["jina", "executor", "--uses", "config.yml"]
```

```{note}
We **strongly encourage** you to name the Executor YAML as `config.yml`, otherwise using your containerized Executor with Kubernetes requires an extra step. 
When using {meth}`~jina.serve.executors.BaseExecutor.to_kubernetes_yaml()` or {meth}`~jina.serve.executors.BaseExecutor.to_docker_compose_yaml()`, Jina-serve adds `--uses config.yml` in the entrypoint. 
To change that you need to manually edit the generated files.
```

## Example: Dockerized Executor

Here we show how to build a basic Executor with a dependency on another external package.


### Write the Executor

You can define your soon-to-be-dockerized Executor exactly like any other Executor.

We do this here in the `my_executor.py` file:

```python
import torch  # Our Executor has dependency on torch
from jina import Executor, requests
from docarray import DocList
from docarray.documents import TextDoc


class ContainerizedEncoder(Executor):
    @requests
    def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
        for doc in docs:
            doc.text = 'This Document is embedded by ContainerizedEncoder'
            doc.embedding = torch.randn(10)
        return docs
```

### Write the Executor YAML file

The YAML configuration, as a minimal working example, is required to point to the file containing the Executor.


```{admonition} More YAML options
:class: seealso
To see what else can be configured using Jina-serve's YAML interface, see {ref}`here <executor-yaml-spec>`.
```

This is necessary for the Executor to be put inside the Docker image,
and we can define such a configuration in `config.yml`:

```yaml
jtype: ContainerizedEncoder
py_modules:
 - my_executor.py
```

### Write `requirements.txt`

In our case, our Executor has only one requirement besides Jina: `torch`.

Specify a single requirement in `requirements.txt`:

```text
torch
```

### Write the Dockerfile

The last step is to write a `Dockerfile`, which has to do little more than launching the Executor via the Jina-serve CLI:

```dockerfile
FROM jinaai/jina:3-py38-perf

# make sure the files are copied into the image
COPY . /executor_root/

WORKDIR /executor_root

RUN pip install -r requirements.txt

ENTRYPOINT ["jina", "executor", "--uses", "config.yml"]
```

### Build the image

At this point we have a folder structure that looks like this:

```
.
├── my_executor.py
└── requirements.txt
└── config.yml
└── Dockerfile
```

We just need to build the image:

```bash
docker build -t my_containerized_executor .
```

Once the build is successful, you should see the following output when you run `docker images`:

```shell
REPOSITORY                       TAG                IMAGE ID       CREATED          SIZE
my_containerized_executor        latest             5cead0161cb5   13 seconds ago   2.21GB
```

### Use the containerized Executor

The containerized Executor can be used like any other, the only difference being the 'docker' prefix in the `uses`
 parameter:
```python
from jina import Deployment
from docarray import DocList
from docarray.documents import TextDoc

dep = Deployment(uses='docker://my_containerized_executor')

with dep:
    returned_docs = dep.post(on='/', inputs=DocList[TextDoc]([TextDoc()]), return_type=DocList[TextDoc])

for doc in returned_docs:
    print(f'Document returned with text: "{doc.text}"')
    print(f'Document embedding of shape {doc.embedding.shape}')
```

```shell
Document returned with text: "This Document is embedded by ContainerizedEncoder"
Document embedding of shape torch.Size([10])
```
