(gpu-executor)=
# Build a GPU Executor

This document shows you how to use an {class}`~jina.Executor` on a GPU, both locally and in a
Docker container. You will also learn how to use a GPU with pre-built Hub executors.

Using a GPU significantly speeds up encoding for most deep learning models,
reducing response latency by anything from 5 to 100 times, depending on the model and inputs used.

```{admonition} Important
:class: caution

This tutorial assumes familiarity with basic Jina concepts, such as Document, [Executor](../concepts/executor/index), and [Deployment](../concepts/deployment/index). Some knowledge of [Executor Hub](../concepts/executor/hub/index) is also needed for the last part of the tutorial.
```

## Jina-serve and GPUs in a nutshell

For a thorough walkthrough of using GPU resources in your code, check the full tutorial in the {ref}`next section <gpu-prerequisites>`.

If you already know how to use your GPU, just proceed like you usually would in your machine learning framework of choice.
Jina-serve lets you use GPUs like you would in a Python script or Docker 
container, without imposing additional requirements or configuration.

Here's a minimal working example, written in PyTorch:

```python
import torch
from typing import Optional
from docarray import DocList, BaseDoc
from docarray.typing import AnyTensor
from jina import Executor, requests


class MyDoc(BaseDoc):
    text: str = ''
    embedding: Optional[AnyTensor[5]] = None

class MyGPUExec(Executor):
    def __init__(self, device: str = 'cpu', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device = device

    @requests
    def encode(self, docs: DocList[MyDoc], **kwargs) -> DocList[MyDoc]:
        with torch.inference_mode():
            # Generate random embeddings
            embeddings = torch.rand((len(docs), 5), device=self.device)
            docs.embedding = embeddings
            embedding_device = 'GPU' if embeddings.is_cuda else 'CPU'
            docs.text = [f'Embeddings calculated on {embedding_device}']
```


````{tab} Use with CPU 

```python
from typing import Optional
from docarray import DocList, BaseDoc
from docarray.typing import AnyTensor
from jina import Deployment

dep = Deployment(uses=MyGPUExec, uses_with={'device': 'cpu'})
docs =  DocList[MyDoc]([MyDoc()])

with dep:
    docs = dep.post(on='/encode', inputs=docs, return_type=DocList[MyDoc])

print(f'Document embedding: {docs.embedding}')
print(docs.text)
```

```shell
           Deployment@80[I]:🎉 Deployment is ready to use!
	🔗 Protocol: 		GRPC
	🏠 Local access:	0.0.0.0:49618
	🔒 Private network:	172.28.0.2:49618
	🌐 Public address:	34.67.105.220:49618
Document embedding: tensor([[0.1769, 0.1557, 0.9266, 0.8655, 0.6291]])
['Embeddings calculated on CPU']

```

````

````{tab} Use with GPU

```python
from typing import Optional
from docarray import DocList, BaseDoc
from docarray.typing import AnyTensor
from jina import Deployment

dep = Deployment(uses=MyGPUExec, uses_with={'device': 'cuda'})
docs =  DocList[MyDoc]([MyDoc()])

with dep:
    docs = dep.post(on='/encode', inputs=docs, return_type=DocList[MyDoc])

print(f'Document embedding: {docs.embedding}')
print(docs.text)
```

```shell
           Deployment@80[I]:🎉 Deployment is ready to use!
	🔗 Protocol: 		GRPC
	🏠 Local access:	0.0.0.0:56276
	🔒 Private network:	172.28.0.2:56276
	🌐 Public address:	34.67.105.220:56276
Document embedding: tensor([[0.6888, 0.8646, 0.0422, 0.8501, 0.4016]])
['Embeddings calculated on GPU']

```

````

Just like that, your code runs on GPU, inside a Deployment.

Next, we will go through a more fleshed out example in detail, where we use a language model to embed text in our
Documents - all on GPU, and thus blazingly fast.

(gpu-prerequisites)=
## Prerequisites

For this tutorial, you need to work on a machine with an NVIDIA graphics card. If you
don't have such a machine at home, you can use various free cloud platforms (like Google Colab or Kaggle kernels).

Also ensure you have a recent version of [NVIDIA drivers](https://www.nvidia.com/Download/index.aspx)
installed. You don't need to install CUDA for this tutorial, but note that depending on
the deep learning framework that you use, that might be required (for local execution).

For the Docker part of the tutorial you will also need to have [Docker](https://docs.docker.com/get-docker/) and 
[nvidia-docker](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed.

To run Python scripts you need a virtual environment (for example [venv](https://packaging.python.org/guides/installing-using-pip-and-virtual-environments/#creating-a-virtual-environment) or [conda](https://conda.io/projects/conda/en/latest/user-guide/getting-started.html#managing-environments)), and install Jina-serve inside it using:

```bash
pip install jina
```

## Setting up the Executor

```{admonition} Executor Hub
:class: hint

Let's create an Executor using `jina hub new`. This creates your Executor locally
and privately, and makes it quick and easy to run your
Executor inside a Docker container, or (if you so choose) to publish it to Executor Hub later.
```

We'll create a simple sentence encoder, and start by creating the Executor 
"skeleton" using Jina-serve's CLI:

```bash
jina hub new
```

When prompted, name your Executor `SentenceEncoder`, and accept the default
folder - this creates a `SentenceEncoder/` folder inside your current
directory, which will be our working directory for this tutorial. 

For many questions you can accept the default options. However:

- Select `y` when prompted for advanced configuration.
- Select `y` when prompted to create a `Dockerfile`. 

In the end, you should be greeted with suggested next steps.

<details>
  <summary> Next steps </summary>

```bash
╭────────────────────────────────────── 🎉 Next steps ───────────────────────────────────────╮
│                                                                                            │
│  Congrats! You have successfully created an Executor! Here are the next steps:             │
│  ╭──────────────────────── 1. Check out the generated Executor ─────────────────────────╮  │
│  │   1 cd /home/ubuntu/SentenceEncoder                                                  │  │
│  │   2 ls                                                                               │  │
│  ╰──────────────────────────────────────────────────────────────────────────────────────╯  │
│  ╭─────────────────────────── 2. Understand folder structure ───────────────────────────╮  │
│  │                                                                                      │  │
│  │   Filena…   Description                                                              │  │
│  │  ──────────────────────────────────────────────────────────────────────────────────  │  │
│  │   config…   The YAML config file of the Executor. You can define __init__ argumen…   │  │
│  │             ╭────────────────── config.yml ──────────────────╮                       │  │
│  │             │   1                                            │                       │  │
│  │             │   2 jtype: SentenceEncoder                     │                       │  │
│  │             │   3 with:                                      │                       │  │
│  │             │   4     foo: 1                                 │                       │  │
│  │             │   5     bar: hello                             │                       │  │
│  │             │   6 metas:                                     │                       │  │
│  │             │   7     py_modules:                            │                       │  │
│  │             │   8         - executor.py                      │                       │  │
│  │             │   9                                            │                       │  │
│  │             ╰────────────────────────────────────────────────╯                       │  │
│  │   Docker…   The Dockerfile describes how this executor will be built.                │  │
│  │   execut…   The main logic file of the Executor.                                     │  │
│  │   manife…   Metadata for the Executor, for better appeal on Executor Hub.                │  │
│  │                                                                                      │  │
│  │               Field   Description                                                    │  │
│  │              ────────────────────────────────────────────────────────────────────    │  │
│  │               name    Human-readable title of the Executor                           │  │
│  │               desc…   Human-readable description of the Executor                     │  │
│  │               url     URL to find more information on the Executor (e.g. GitHub…     │  │
│  │               keyw…   Keywords that help user find the Executor                      │  │
│  │                                                                                      │  │
│  │   README…   A usage guide of the Executor.                                           │  │
│  │   requir…   The Python dependencies of the Executor.                                 │  │
│  │                                                                                      │  │
│  ╰──────────────────────────────────────────────────────────────────────────────────────╯  │
│  ╭────────────────────────────── 3. Share it to Executor Hub ───────────────────────────────╮  │
│  │   1 jina hub push /home/ubuntu/SentenceEncoder                                       │  │
│  ╰──────────────────────────────────────────────────────────────────────────────────────╯  │
╰────────────────────────────────────────────────────────────────────────────────────────────╯

```

</details>

Now let's move to the newly created Executor directory:
```bash
cd SentenceEncoder
```

Continue by specifying our requirements in `requirements.txt`:

```text
sentence-transformers==2.0.0
```

And installing them using:

```bash
pip install -r requirements.txt
```

```{admonition} Do I need to install CUDA?
:class: hint

All machine learning frameworks rely on CUDA for running on a GPU. However, whether you
need CUDA installed on your system or not depends on the framework that you use.

In this tutorial, we use PyTorch, which already includes the necessary
CUDA binaries in its distribution. However, other frameworks, such as TensorFlow, require
you to install CUDA yourself.
```

```{admonition} Install only what you need
:class: hint

In this example we install the GPU-enabled version of PyTorch, which is the default
version when installing from PyPI. However, if you know that you only need to use your
Executor on CPU, you can save a lot of space (hundreds of MBs, or even GBs) by installing
CPU-only versions of your requirements. This translates into faster startup times
when using Docker containers.

In our case, we could change the `requirements.txt` file to install a CPU-only version
of PyTorch:

:::text
-f https://download.pytorch.org/whl/torch_stable.html
sentence-transformers
torch==1.9.0+cpu
:::
```

Now let's fill the `executor.py` file with the actual Executor code:

```{code-block} python
---
emphasize-lines: 16
---
import torch
from typing import Optional
from docarray import DocList, BaseDoc
from docarray.typing import AnyTensor
from jina import Executor, requests
from sentence_transformers import SentenceTransformer

class MyDoc(BaseDoc):
    text: str = ''
    embedding: Optional[AnyTensor[5]] = None

class SentenceEncoder(Executor):
    """A simple sentence encoder that can be run on a CPU or a GPU

    :param device: The pytorch device that the model is on, e.g. 'cpu', 'cuda', 'cuda:1'
    """

    def __init__(self, device: str = 'cpu', *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.model = SentenceTransformer('all-MiniLM-L6-v2', device=device)
        self.model.to(device)  # Move the model to device

    @requests
    def encode(self, docs: DocList[MyDoc], **kwargs) -> DocList[MyDoc]:
        """Add text-based embeddings to all documents"""
        with torch.inference_mode():
            embeddings = self.model.encode(docs.texts, batch_size=32)
        docs.embeddings = embeddings
```

Here all the device-specific magic happens on the two highlighted lines - when we create the
`SentenceEncoder` class instance we pass it the device, and then we move the PyTorch
model to our device. These are also the exact same steps to use in a standalone Python script.

To see how we would pass the device we want the Executor to use,
let's create another file - `main.py`, to demonstrate the usage of this
encoder by encoding 10,000 text documents.

```python
from typing import Optional
from jina import Deployment
from docarray import DocList, BaseDoc
from docarray.typing import AnyTensor
from executor import SentenceEncoder


class MyDoc(BaseDoc):
    text: str = ''
    embedding: Optional[AnyTensor[5]] = None


def generate_docs():
    for _ in range(10_000):
        yield MyDoc(
            text='Using a GPU allows you to significantly speed up encoding.'
        )


dep = Deployment(uses=SentenceEncoder, uses_with={'device': 'cpu'})

with dep:
    dep.post(on='/encode', inputs=generate_docs, show_progress=True, request_size=32, return_type=DocList[MyDoc])
```

## Running on GPU and CPU locally

We can observe the speed up by running the same code on both the CPU and GPU.

To toggle between the two, set your device type to `'cuda'`, and your GPU will take over the work:

```diff
+ dep = Deployment(uses=SentenceEncoder, uses_with={'device': 'cuda'})
- dep = Deployment(uses=SentenceEncoder, uses_with={'device': 'cpu'})
```

Then, run the script:

```bash
python main.py
```

And compare the results:

````{tab} CPU 

```shell
      executor0@26554[L]:ready and listening
        gateway@26554[L]:ready and listening
           Deployment@26554[I]:🎉 Deployment is ready to use!
        🔗 Protocol:            GRPC
        🏠 Local access:        0.0.0.0:56969
        🔒 Private network:     172.31.39.70:56969
        🌐 Public address:      52.59.231.246:56969
Working... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━━━ 0:00:20 15.1 step/s 314 steps done in 20 seconds
```

````

````{tab} GPU 

```shell
      executor0@21032[L]:ready and listening
        gateway@21032[L]:ready and listening
           Deployment@21032[I]:🎉 Deployment is ready to use!
        🔗 Protocol:            GRPC
        🏠 Local access:        0.0.0.0:54255
        🔒 Private network:     172.31.39.70:54255
        🌐 Public address:      52.59.231.246:54255
Working... ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╸━━━━━━ 0:00:03 90.9 step/s 314 steps done in 3 seconds
```

````
Running this code on a `g4dn.xlarge` AWS instance with a single NVIDIA T4 GPU attached, we can see that embedding
time decreases from 20s to 3s by running on GPU.
That's more than a **6x speedup!** And that's not even the best we can do - if we increase the batch size to max out the GPU's memory we would get even larger speedups. But such optimizations are beyond the scope of this tutorial.

```{admonition} Note
:class: hint

You've probably noticed that there was a delay (about 3 seconds) when creating the Deployment.
This is because the weights of our model had to be transferred from CPU to GPU when we
initialized the Executor. However, this action only occurs once in the lifetime of the Executor,
so for most use cases we don't need to worry about it.
```

## Using GPU in a container

```{admonition} Using your GPU inside a container
:class: caution

For this part of the tutorial, you need to [install `nvidia-container-toolkit`](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html).
```

When you use your Executor in production you most likely want it in a Docker container, to provide proper environment isolation and easily use it on any device.

Using GPU-enabled Executors in this case is no harder than using them locally. We don't even need to modify the default `Dockerfile`.

```{admonition} Choosing the right base image
:class: hint

In our case we use the default `jinaai/jina:latest` base image. However, parallel to the comments about installing CUDA locally, you may need a different base image depending on your framework.

If you need CUDA installed in the image, you usually have two options: either take `nvidia/cuda` for the base image, or take the official GPU-enabled image of your framework, for example, `tensorflow/tensorflow:2.6.0-gpu`.
```

The other file we care about in this case is `config.yml`, and here the default version works as well. Let's build the Docker image:

```bash
docker build -t sentence-encoder .
```

You can run the container to check that everything is working well:

```bash
docker run sentence-encoder
```

Let's use the Docker version of our encoder with the GPU. If you've dealt with GPUs in containers before, you may remember that to use a GPU inside the container you need to pass `--gpus all` option to the `docker run` command. Jina lets you do just that.

We need to modify our `main.py` script to use a GPU-base containerized Executor:

```{code-block} python
---
emphasize-lines: 18
---
from typing import Optional
from jina import Deployment
from docarray import DocList, BaseDoc
from docarray.typing import AnyTensor
from executor import SentenceEncoder

class MyDoc(BaseDoc):
    text: str = ''
    embedding: Optional[AnyTensor[5]] = None


def generate_docs():
    for _ in range(10_000):
        yield MyDoc(
            text='Using a GPU allows you to significantly speed up encoding.'
        )

dep = Deployment(uses='docker://sentence-encoder', uses_with={'device': 'cuda'}, gpus='all')

with dep:
    dep.post(on='/encode', inputs=generate_docs, show_progress=True, request_size=32, return_type=DocList[MyDoc])
```

If we run this with `python main.py`, we'll get the same output as before, except that now we'll also get the output from the Docker container.

Every time we start the Executor, the Transformer model gets downloaded again. To speed this up, we want the encoder to load the model from a file which we have pre-downloaded to our disk.

We can do this with Docker volumes - Jina simply passes the argument to the Docker container. Here's how we modify `main.py`:

```python
dep = Deployment(
    uses='docker://sentence-encoder',
    uses_with={'device': 'cuda'},
    gpus='all',
    # This has to be an absolute path, replace /home/ubuntu with your home directory
    volumes="/home/ubuntu/.cache:/root/.cache",
)
```

We mounted the `~/.cache` directory, because that's where pre-built transformer models are saved. But this could be any custom directory - depending on the Python package you are using, and how you specify the model loading path.

Run `python main.py` again and you can see that no downloading happens inside the container, and that encoding starts faster.

## Using GPU with Hub Executors

We now saw how to use GPU with our Executor locally, and when using it in a Docker container. What about when we use Executors from Executor Hub - is there any difference?

Nope! Not only that, many Executors on Executor Hub already come with a GPU-enabled version pre-built, usually under the `gpu` tag (see [Executor Hub tags](hub_tags)). Let's modify our example to use the pre-built `TransformerTorchEncoder` from Executor Hub:

```diff
dep = Deployment(
-   uses='docker://sentence-encoder',
+   uses='jinaai+docker://jina-ai/TransformerTorchEncoder:latest-gpu',
    uses_with={'device': 'cuda'},
    gpus='all',
    # This has to be an absolute path, replace /home/ubuntu with your home directory
    volumes="/home/ubuntu/.cache:/root/.cache"
)
```

The first time you run the script, downloading the Docker image takes some time - GPU images are large! But after that, everything works just as it did with the local Docker image, out of the box.

```{admonition} Important
:class: caution

When using GPU encoders from Executor Hub, always use `jinaai+docker://`, and not `jinaai://`. As discussed above, these encoders may need CUDA installed (or other system dependencies), and installing that properly can be tricky. For that reason, use Docker images, which already come with all these dependencies pre-installed.
```

## Conclusion

Let's recap this tutorial:

1. Using Executors on a GPU locally is no different to using a GPU in a standalone script. You pass the device you want your Executor to use in the initialization.
2. To use an Executor on a GPU inside a Docker container, pass `gpus='all'`.
3. Use volumes (bind mounts), so you don't have to download large files each time you start the Executor.
4. Use GPU with Executors from Executor Hub - just use the Executor with the `gpu` tag.

When you start building your own Executor, check what system requirements (CUDA and similar) are needed, and install them locally (and in the `Dockerfile`) accordingly.
