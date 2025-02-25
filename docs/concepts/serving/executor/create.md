(create-executor)=
# Create

## Introduction

```{tip}
Executors use `docarray.BaseDoc` and docarray.DocList` as their input and output data structure. [Read DocArray's docs](https://docs.docarray.org) to see how it works.
```

An {class}`~jina.Executor` is a self-contained microservice exposed using a gRPC or HTTP protocol. 
It contains functions (decorated with `@requests`) that process `Documents`. Executors follow these principles:

1. An Executor should subclass directly from the `jina.Executor` class.
2. An Executor is a Python class; it can contain any number of functions.
3. Functions decorated by {class}`~jina.requests` are exposed as services according to their `on=` endpoint. These functions can be coroutines (`async def`) or regular functions. They can work on single Documents, or on batches. This will be explained later in {ref}`Add Endpoints Section<exec-endpoint>`
4. (Beta) Functions decorated by {class}`~jina.serve.executors.decorators.write` above their {class}`~jina.requests` decoration, are considered to update the internal state of the Executor. The `__init__` and `close` methods are exceptions. The reasons this is useful is explained in {ref}`Stateful-executor<stateful-executor>`.

## Create an Executor

To create your {class}`~jina.Executor`, run:

```bash
jina hub new
```

You can ignore the advanced configuration and just provide the Executor name and path. For instance, choose `MyExecutor`.

After running the command, a project with the following structure will be generated:

```text
MyExecutor/
├── executor.py
├── config.yml
├── README.md
└── requirements.txt
```

- `executor.py` contains your Executor's main logic. The command should generate the following boilerplate code:
```python
from jina import Executor, requests
from docarray import DocList, BaseDoc

class MyExecutor(Executor):
    @requests
    def foo(self, docs: DocList[BaseDoc], **kwargs) -> DocList[BaseDoc]:
        pass
```
- `config.yml` is the Executor's {ref}`configuration <executor-yaml-spec>` file, where you can define `__init__` arguments using the `with` keyword.
- `requirements.txt` describes the Executor's Python dependencies.
- `README.md` describes how to use your Executor.

For a more detailed breakdown of the file structure, see {ref}`here <executor-file-structure>`.

(executor-constructor)=
## Constructor

You only need to implement `__init__` if your Executor contains initial state.

If your Executor has `__init__`, it needs to carry `**kwargs` in the signature and call `super().__init__(**kwargs)` 
in the body:

```python
from jina import Executor


class MyExecutor(Executor):
    def __init__(self, foo: str, bar: int, **kwargs):
        super().__init__(**kwargs)
        self.bar = bar
        self.foo = foo
```

````{admonition} What is inside kwargs? 
:class: hint
Here, `kwargs` are reserved for Jina-serve to inject `metas` and `requests` (representing the request-to-function mapping) values when the Executor is used inside a {ref}`Flow <flow-cookbook>`.

You can access the values of these arguments in the `__init__` body via `self.metas`/`self.requests`/`self.runtime_args`, or modify their values before passing them to `super().__init__()`.
````

Since Executors are runnable through {ref}`YAML configurations <executor-yaml-spec>`, user-defined constructor arguments 
can be overridden using the {ref}`Executor YAML with keyword<executor-with-keyword>`.
## Destructor

You might need to execute some logic when your Executor's destructor is called.

For example, if you want to persist data to disk (e.g. in-memory indexed data, fine-tuned model,...) you can overwrite the {meth}`~jina.serve.executors.BaseExecutor.close` method and add your logic.

Jina ensures the {meth}`~jina.serve.executors.BaseExecutor.close` method is executed when the Executor is terminated inside a {class}`~jina.Deployment` or {class}`~jina.Flow`, or when deployed in any cloud-native environment.

You can think of this as Jina using the Executor as a context manager, making sure that the {meth}`~jina.serve.executors.BaseExecutor.close` method is always executed.

```python
from jina import Executor


class MyExec(Executor):
    def close(self):
        print('closing...')
```

## Attributes

When implementing an Executor, if your Executor overrides `__init__`, it needs to carry `**kwargs` in the signature and call `super().__init__(**kwargs)`
                                 
```python
from jina import Executor


class MyExecutor(Executor):
    def __init__(self, foo: str, bar: int, **kwargs):
        super().__init__(**kwargs)
        self.bar = bar
        self.foo = foo
```

This is important because when an Executor is instantiated (whether with {class}`~jina.Deployment` or {class}`~jina.flow`), Jina adds extra arguments.

Some of these arguments can be used when developing the internal logic of the Executor.

These `special` arguments are `workspace`, `requests`, `metas`, `runtime_args`.


(executor-workspace)=
### `workspace`

Each Executor has a special *workspace* that is reserved for that specific Executor instance.
The `.workspace` property contains the path to this workspace.

This `workspace` is based on the workspace passed when orchestrating the Executor: `Deployment(..., workspace='path/to/workspace/')`/`flow.add(..., workspace='path/to/workspace/')`.
The final `workspace` is generated by appending `'/<executor_name>/<shard_id>/'`.

This can be provided to the Executor via the Python API or {ref}`YAML API <executor-yaml-spec>`.

````{admonition} Hint: Default workspace
:class: hint
If you haven't provided a workspace, the Executor uses a default workspace, defined in `~/.cache/jina-serve/`.
````

(executor-requests)=
### `requests`

By default, an Executor object contains {attr}`~.jina-serve.serve.executors.BaseExecutor.requests` as an attribute when loaded. This attribute is a `Dict` describing the mapping between Executor methods and network endpoints: It holds endpoint strings as keys, and pointers to functions as values. 

These can be provided to the Executor via the Python API or {ref}`YAML API <executor-yaml-spec>`.

(executor-metas)=
### `metas`

An Executor object contains `metas` as an attribute when loaded from the Flow. It is of [`SimpleNamespace`](https://docs.python.org/3/library/types.html#types.SimpleNamespace) type and contains some key-value information. 

The list of the `metas` are:

- `name`: Name given to the Executor;
- `description`: Description of the Executor (optional, reserved for future-use in auto-docs);

These can be provided to the Executor via Python or {ref}`YAML API <executor-yaml-spec>`.

(executor-runtime-args)=
### `runtime_args`

By default, an Executor object contains `runtime_args` as an attribute when loaded. It is of [`SimpleNamespace`](https://docs.python.org/3/library/types.html#types.SimpleNamespace) type and contains information in key-value format. 
As the name suggests, `runtime_args` are dynamically determined during runtime, meaning that you don't know the value before running the Executor. These values are often related to the system/network environment around the Executor, and less about the Executor itself, like `shard_id` and `replicas`.

The list of the `runtime_args` is:

- `name`: Name given to the Executor. This is dynamically adapted from the `name` in `metas` and depends on some additional arguments like `shard_id`. 
- `replicas`: Number of {ref}`replicas <replicate-executors>` of the same Executor deployed.
- `shards`: Number of {ref}`shards <partition-data-by-using-shards>` of the same Executor deployed.
- `shard_id`: Identifier of the `shard` corresponding to the given Executor instance.
- `workspace`: Path to be used by the Executor. Note that the actual workspace directory used by the Executor is obtained by appending `'/<executor_name>/<shard_id>/'` to this value.
- `py_modules`: Python package path e.g. `foo.bar.package.module` or file path to the modules needed to import the Executor.

You **cannot** provide these through any API. They are generated by the orchestration mechanism, be it a {class}`~jina.Deployment` or a {class}`~jina.Flow`.

## Tips

* Use `jina hub new` CLI to create an Executor: To create an Executor, always use this command and follow the instructions. This ensures the correct file 
structure.
* You don't need to manually write a Dockerfile: The build system automatically generates an optimized Dockerfile according to your Executor package.

```{tip}
In the `jina hub new` wizard you can choose from four Dockerfile templates: `cpu`, `tf-gpu`, `torch-gpu`, and `jax-gpu`.
```

## Stateful-Executor (Beta)

Executors may sometimes contain an internal state which changes when some of their methods are called. For instance, an Executor could contain an index of Documents
to perform vector search.

In these cases, orchestrating these Executors can be tougher than it would be for Executors that never change their inner state (Imagine a Machine Learning model served via an Executor that never updates its weights during its lifetime).
The challenge is guaranteeing consistency between `replicas` of the same Executor inside the same Deployment.

To provide this consistency, Executors can mark some of their exposed methods as `write`. This indicates that calls to these endpoints must be consistently replicated between all the replicas
such that other endpoints can serve independently of the replica that is hit.

````{admonition} Deterministic state update
:class: note

Another factor to consider is that the Executor's inner state must evolve in a deterministic manner if we want `replicas` to behave consistently.
````

By considering this, {ref}`Executors can be scaled in a consistent manner<scale-consensus>`.

### Snapshots and restoring

In a Stateful Executor Jina uses the RAFT consensus algorithm to guarantee that every replica eventually holds the same inner state. 
RAFT writes the incoming requests as logs to local storage in every replica to ensure this is achieved. 

This could become problematic if the Executor runs for a long time as log files could grow indefinitely. However, you can avoid this problem
by describing the methods `def snapshot(self, snapshot_dir)` and `def restore(self, snapshot_dir)` that are triggered via the RAFT protocol, allowing the Executor
to store its current state or to recover its state from a snapshot. With this mechanism, RAFT can keep cleaning old logs by assuming that the state of the Executor
at a given time is determined by its latest snapshot and the application of all requests that arrived since the last snapshot. The RAFT algorithm keeps track
of all these details.
