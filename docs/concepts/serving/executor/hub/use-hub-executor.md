(use-hub-executor)=
# Use


There are three ways to use Hub {class}`~jina.Executor`s in your project. Each has its own use case and benefits.

## Use as-is

You can use a Hub Executor as-is via `Executor.from_hub()`:

```python
from jina import Executor
from docarray import DocList
from docarray.documents.legacy import LegacyDocument

exec = Executor.from_hub('jinaai://jina-ai/DummyHubExecutor')
da = DocList[LegacyDocument]([LegacyDocument()])
exec.foo(da)
assert da.texts == ['hello']
```

The Hub Executor will be pulled to your local machine and run as a native Python object. You can use a line-debugger to step in/out `exec` object, set breakpoints, and observe how it behaves. You can directly feed in `Documents`. After you build some confidence in that Executor, you can move to the next step: Using it as a part of your Flow.

```{caution}
Not all Executors on the Hub can be directly run in this way - some require extra dependencies. In that case, you can add `.from_hub(..., install_requirements=True)` to install the requirements automatically. Be careful - these dependencies may not be compatible with your local packages and may override your local development environment.
```

```{tip}
Hub Executors are cached locally on the first pull. Afterwards, they will not be updated. 

To keep up-to-date with upstream, use `.from_hub(..., force_update=True)`.
```

(pull-executor)=
## Pull only

You can also use `jina hub` CLI to pull an Executor without actually using it in the Flow.

````{admonition} Jina-serve and DocArray version
:class: note

Independently of the Jina-serve and DocArray version existing when the Executor was pushed to the Hub. When pulling, the Hub will try
to install the Jina-serve and DocArray version that you have installed locally in the pulled docker images.
````

### Pull the Docker image

```bash
jina hub pull jinaai+docker://<USERNAME>/<NAME>[:<TAG>]
```


You can find the Executor by running `docker images`. You can also indicate which version of the Executor you want to use by specifying the `:<TAG>`.

```bash
jina hub pull jinaai+docker://jina-ai/DummyExecutor:v1.0.0
```


## Use in Flow as container

Use prebuilt images from Hub in your Python code:

```python
from jina import Flow

# You have to login for private Executor
# import hubble
# hubble.login()

f = Flow().add(uses='jinaai+docker://<USERNAME>/<NAME>[:<TAG>]')
```

If you do not provide a `:<TAG>`, it defaults to `/latest`.

````{important}
To use a private Executor, you have to login.

```python
import hubble

hubble.login()
```

````

````{admonition} Attention
:class: attention

If you are a Mac user, please use `host.docker.internal` as your URL when you want to connect a local port from an Executor
Docker container.

For example: [PostgreSQLStorage](https://cloud.jina.ai/executor/d45rawx6)
will connect PostgreSQL server which was started locally. Then you must use it with:

```python
from jina import Flow, Document

f = Flow().add(
    uses='jinaai+docker://jina-ai/PostgreSQLStorage',
    uses_with={'hostname': 'host.docker.internal'},
)
with f:
    resp = f.post(on='/index', inputs=Document())
    print(f'{resp}')
```
````


If `jinaai+docker://` Executors don't load properly or have issues during initialization, ensure you have sufficient Docker resources allocated.

(mount-local-volumes)=
### Mount local volumes

You can mount volumes into your dockerized Executor by passing a list of volumes with the `volumes` argument:

```python
f = Flow().add(
    uses='docker://my_containerized_executor',
    volumes=['host/path:/path/in/container', 'other/volume:/app'],
)
```

````{admonition} Hint
:class: hint
If you want your containerized Executor to operate inside one of these volumes, remember to set its {ref}`workspace <executor-workspace>` accordingly!
````

If you do not specify `volumes`, Jina automatically mounts a volume into the container.
In this case, the volume source is your {ref}`default Executor workspace <executor-workspace>`, and the volume destination 
is `/app`. Additionally, automatic volume setting tries to move the Executor's workspace into the volume destination.
Depending on the default Executor workspace on your system this may not always succeed, so explicitly mounting a volume and setting
a workspace is recommended.

You can disable automatic volume setting by passing `f.add(..., disable_auto_volume=True)`.

## Use in Flow via source code

Use the source code from Executor Hub in your Python code:

```python
from jina import Flow

f = Flow().add(uses='jinaai://<USERNAME>/<NAME>[:<TAG>]')
```

## Set/override default parameters

The default parameters of the published Executor may not be ideal for your use case. You can 
pass `uses_with` and `uses_metas` as parameters to override this:

```python
from jina import Flow

f = Flow().add(
    uses='jinaai+docker://<USERNAME>/<NAME>[:<TAG>]',
    uses_with={'param1': 'new_value'},
    uses_metas={'name': 'new_name'},
)
```

### Platform awareness of Hub images 

````{admonition} Hint
:class: hint
As of January 10, 2023 `jina hub pull` is platform aware. It will automatically select Docker images based on your native CPU architecture (if available).
````
If you prefer a specific platform, for example, preferring `AMD64` on an `ARM64` machine, you can explicitly pull with `--prefer-platform`:

````{admonition} Caution
:class: caution
When you specify `--prefer-platform` you probably want to also specify `--force` to overwrite the existing image in local cache.
````

````{admonition} Note
:class: note
If the image you specify doesn't support your preferred platform, it will not respect your platform preference.
````

```bash
jina hub pull --force --prefer-platform linux/amd64 jinaai+docker://jina-ai/DummyExecutor:v1.0.0
```

### Pull the source code

```bash
jina hub pull jinaai://<USERNAME>/<NAME>[:<TAG>]
```

### List locations of local Executors

```bash
jina hub list
```

<script id="asciicast-z81wi9gwVm7gYjfl5ocBD1RH3" src="https://asciinema.org/a/z81wi9gwVm7gYjfl5ocBD1RH3.js" async></script>
<script id="asciicast-z81wi9gwVm7gYjfl5ocBD1RH3" src="https://asciinema.org/a/z81wi9gwVm7gYjfl5ocBD1RH3.js" async></script>

```{tip}
To list all the Executors that are in source-code format (i.e. pulled via `jinaai://`), use the command `jina hub list`.

To list all the Executors that are in Docker format, use the command `docker images`.
```