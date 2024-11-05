(jina-hub)=
# Executor Hub

Now that you understand that {class}`~jina.Executor` is a building block in Jina-serve, you may also wonder:

- Can I streamline the process of containerizing my {class}`~jina.Executor`?
- Can I reuse my Executor in another project?
- Can I share my Executor with my colleagues?
- Can I just use someone else's Executor instead of building it myself?

Basically, something like the following:

```{figure} ../../../../../.github/hub-user-journey.svg
:align: center
```

**Yes!** This is exactly the purpose of Executor Hub. 
Hub allows you to turn your Executor into a ready-for-the-cloud containerized service taking away a lot of the work from you. 
With Hub you can pull prebuilt Executors to dramatically reduce the effort and complexity needed in your system, or push your own custom
Executors to share privately or publicly. You can think of the Hub as your easy to entry door to a Docker registry.

A Hub Executor is an Executor published on Executor Hub. You can use such an Executor in a Flow or in a Deployment:

```python
from jina import Deployment

d = Deployment(uses='jinaai+docker://<username>/MyExecutor')

with d:
    ...
```

````{admonition} Make sure the schemas are known
:class: note

While using docarray>0.30.0, Executors do not have a fix schema and each Executor defines its own. Make sure you know
those schemas when using Executors from the Hub.
````


```{toctree}
:hidden:

hub-portal
create-hub-executor
push-executor
use-hub-executor
debug-executor
yaml-spec
```
