# Welcome to Jina-serve!

```{admonition} Survey
:class: tip

Take our **[user experience survey](https://10sw1tcpld4.typeform.com/to/EGAEReM7?utm_source=doc&utm_medium=github&utm_campaign=user%20experience&utm_term=feb2023&utm_content=survey)** to let us know your thoughts and help shape the future of Jina!
```

```{include} ../README.md
:start-after: <!-- start jina-description -->
:end-before: <!-- end jina-description -->
```

## Install

Make sure that you have Python 3.7+ installed on Linux/macOS/{ref}`Windows <jina-on-windows>`.

````{tab} via PyPI
```shell
pip install -U jina
```
````
````{tab} via Conda
```shell
conda install jina -c conda-forge
```
````
(build-ai-services)=
(build-a-pipeline)=
## Getting Started
Jina-serve supports developers in building AI services and pipelines:

````{tab} Build AI Services
```{include} ../README.md
:start-after: <!-- start build-ai-services -->
:end-before: <!-- end build-ai-services -->
```
````

````{tab} Build Pipelines
```{include} ../README.md
:start-after: <!-- start build-pipelines -->
:end-before: <!-- end build-pipelines -->
```
````


## Next steps

:::::{grid} 2
:gutter: 3


::::{grid-item-card} {octicon}`cross-reference;1.5em` Learn DocArray API
:link: https://docarray.docs.org

DocArray is the foundational data structure of Jina. Before starting Jina, first learn DocArray to quickly build a PoC. 
::::

::::{grid-item-card} {octicon}`gear;1.5em` Learn Executor
:link: concepts/serving/executor/index
:link-type: doc

{term}`Executor` is a Python class that can serve logic using `Documents`.

::::

::::{grid-item-card} {octicon}`workflow;1.5em` Learn Deployment
:link: concepts/orchestration/deployment
:link-type: doc

{term}`Deployment` serves an Executor as a scalable service making it available to receive `Documents` using `gRPC` or `HTTP`.
::::

::::{grid-item-card} {octicon}`workflow;1.5em` Learn Flow
:link: concepts/orchestration/flow
:link-type: doc

{term}`Flow` orchestrates Executors using different Deployments into a processing pipeline to accomplish a task.
::::

::::{grid-item-card} {octicon}`cross-reference;1.5em` Learn Gateway
:link: concepts/serving/gateway/index

The Gateway is a microservice that serves as the entrypoint of a {term}`Flow`. It exposes multiple protocols for external communications and routes all internal traffic.
::::

::::{grid-item-card} {octicon}`package-dependents;1.5em` Explore Executor Hub
:link: concepts/executor/hub/index
:link-type: doc
:class-card: color-gradient-card-1


Executor Hub allows you to containerize, share, explore and make Executors ready for the cloud.

::::


::::{grid-item-card} {octicon}`cpu;1.5em` Deploy a Flow to Cloud
:link: concepts/jcloud/index
:link-type: doc
:class-card: color-gradient-card-2

Jina AI Cloud is the MLOps platform for hosting Jina-serve projects.
::::



:::::

```{include} ../README.md
:start-after: <!-- start support-pitch -->
:end-before: <!-- end support-pitch -->
```


```{toctree}
:caption: Get Started
:hidden:

get-started/install/index
get-started/create-app
```



```{toctree}
:caption: Concepts
:hidden:

concepts/preliminaries/index
concepts/serving/index
concepts/orchestration/index
concepts/client/index
```

```{toctree}
:caption: Cloud Native
:hidden:

cloud-nativeness/k8s
cloud-nativeness/docker-compose
cloud-nativeness/opentelemetry
jina-ai-cloud/index
```

```{toctree}
:caption: Developer Reference
:hidden:
:maxdepth: 1

api-rst
cli/index
yaml-spec
envs/index
telemetry
proto/docs
docarray-support
```

```{toctree}
:caption: Tutorials
:hidden:

tutorials/deploy-model
tutorials/gpu-executor
tutorials/deploy-pipeline
tutorials/llm-serve
```

```{toctree}
:caption: Legacy Support
:hidden:
:maxdepth: 1

Jina 2 Documentation <https://docs2.jina.ai/>
```


---
{ref}`genindex` | {ref}`modindex`
