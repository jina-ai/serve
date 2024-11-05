(callback-functions)=
# Callbacks

After performing {meth}`~jina.clients.mixin.PostMixin.post`, you may want to further process the obtained results.

For this purpose, Jina-serve implements a promise-like interface, letting you specify three kinds of callback functions:

- `on_done` is executed while streaming, after successful completion of each request
- `on_error` is executed while streaming, whenever an error occurs in each request
- `on_always` is always performed while streaming, no matter the success or failure of each request


Note that these callbacks only work for requests (and failures) *inside the stream*, for example inside an Executor.
If the failure is due to an error happening outside of 
streaming, then these callbacks will not be triggered.
For example, a `SIGKILL` from the client OS during the handling of the request, or a networking issue,
will not trigger the callback.


Callback functions in Jina-serve expect a `Response` of the type {class}`~jina.types.request.data.DataRequest`, which contains resulting Documents,
parameters, and other information.

## Handle DataRequest in callbacks

`DataRequest`s are objects that are sent by Jina-serve internally. Callback functions process DataRequests, and `client.post()`
can return DataRequests.

`DataRequest` objects can be seen as a container for data relevant for a given request, it contains the following fields:

````{tab} header

The request header.

```python
from pprint import pprint

from jina import Client

Client().post(on='/', on_done=lambda x: pprint(x.header))
```

```console
request_id: "ea504823e9de415d890a85d1d00ccbe9"
exec_endpoint: "/"
target_executor: ""
```

````

````{tab} parameters

The input parameters of the associated request. In particular, `DataRequest.parameters['__results__']` is a 
reserved field that gets populated by Executors returning a Python `dict`. 
Information in those returned `dict`s gets collected here, behind each Executor ID.

```python
from pprint import pprint

from jina import Client

Client().post(on='/', on_done=lambda x: pprint(x.parameters))
```

```console
{'__results__': {}}
```

````

````{tab} routes

The routing information of the data request. It contains the which Executors have been called, and the order in which they were called.
The timing and latency of each Executor is also recorded.

```python
from pprint import pprint

from jina import Client

Client().post(on='/', on_done=lambda x: pprint(x.routes))
```

```console
[executor: "gateway"
start_time {
  seconds: 1662637747
  nanos: 790248000
}
end_time {
  seconds: 1662637747
  nanos: 794104000
}
, executor: "executor0"
start_time {
  seconds: 1662637747
  nanos: 790466000
}
end_time {
  seconds: 1662637747
  nanos: 793982000
}
]

```

````

````{tab} docs
The DocList being passed between and returned by the Executors. These are the Documents usually processed in a callback function, and are often the main payload.

```python
from pprint import pprint

from jina import Client

Client().post(on='/', on_done=lambda x: pprint(x.docs))
```

```console
<DocList (length=0)>

```
````

  
Accordingly, a callback that processing documents can be defined as:

```{code-block} python
---
emphasize-lines: 4
---
from jina.types.request.data import DataRequest

def my_callback(resp: DataRequest):
    foo(resp.docs)
```

## Handle exceptions in callbacks

Server error can be caught by Client's `on_error` callback function. You can get the error message and traceback from `header.status`:

```python
from pprint import pprint

from jina import Flow, Client, Executor, requests


class MyExec1(Executor):
    @requests
    def foo(self, **kwargs):
        raise NotImplementedError


with Flow(port=12345).add(uses=MyExec1) as f:
    c = Client(port=f.port)
    c.post(on='/', on_error=lambda x: pprint(x.header.status))
```


```text
code: ERROR
description: "NotImplementedError()"
exception {
  name: "NotImplementedError"
  stacks: "Traceback (most recent call last):\n"
  stacks: "  File \"/Users/hanxiao/Documents/jina/jina/serve/runtimes/worker/__init__.py\", line 181, in process_data\n    result = await self._data_request_handler.handle(requests=requests)\n"
  stacks: "  File \"/Users/hanxiao/Documents/jina/jina/serve/runtimes/request_handlers/data_request_handler.py\", line 152, in handle\n    return_data = await self._executor.__acall__(\n"
  stacks: "  File \"/Users/hanxiao/Documents/jina/jina/serve/executors/__init__.py\", line 301, in __acall__\n    return await self.__acall_endpoint__(__default_endpoint__, **kwargs)\n"
  stacks: "  File \"/Users/hanxiao/Documents/jina/jina/serve/executors/__init__.py\", line 322, in __acall_endpoint__\n    return func(self, **kwargs)\n"
  stacks: "  File \"/Users/hanxiao/Documents/jina/jina/serve/executors/decorators.py\", line 213, in arg_wrapper\n    return fn(executor_instance, *args, **kwargs)\n"
  stacks: "  File \"/Users/hanxiao/Documents/jina/toy44.py\", line 10, in foo\n    raise NotImplementedError\n"
  stacks: "NotImplementedError\n"
  executor: "MyExec1"
}
```



In the example below, our Flow passes the message then prints the result when successful.
If something goes wrong, it beeps. Finally, the result is written to output.txt.

```python
from jina import Flow, Client
from docarray import BaseDoc


def beep(*args):
    # make a beep sound
    import sys

    sys.stdout.write('\a')


with Flow().add() as f, open('output.txt', 'w') as fp:
    client = Client(port=f.port)
    client.post(
        '/',
        BaseDoc(),
        on_done=print,
        on_error=beep,
        on_always=lambda x: x.docs.save(fp),
    )
```

````{admonition} What errors can be handled by the callback?
:class: caution
Callbacks can handle errors that are caused by Executors raising an Exception.

A callback will not receive exceptions:
- from the Gateway having connectivity errors with the Executors.
- between the Client and the Gateway.
````
