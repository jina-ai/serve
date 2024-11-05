# Readiness

An Orchestration is marked as "ready", when:
- Its Executor is fully loaded and ready (in the case of a Deployment)
- All its Executors and Gateway are fully loaded and ready (in the case of a Flow)
 
After that, an Orchestration is able to process requests.

{class}`~jina.Client` offers an API to query these readiness endpoints. You can do this via the Orchestration directly, via the Client, or via the CLI: You can call {meth}`~jina.clients.mixin.HealthCheckMixin.is_flow_ready` or {meth}`~jina.Flow.is_flow_ready`. It returns `True` if the Flow is ready, and `False` if it is not.

## Via Orchestration

````{tab} Deployment
```python
from jina import Deployment

dep = Deployment()

with dep:
    print(dep.is_deployment_ready())

print(dep.is_deployment_ready())
```
```text
True
False
```
````
````{tab} Flow
```python
from jina import Flow

f = Flow.add()

with f:
    print(f.is_flow_ready())

print(f.is_flow_ready())
```
```text
True
False
```
````

## Via Jina-serve Client

<!-- start ready-from-client -->

You can check the readiness from the client:

````{tab} Deployment
```python
from jina import Deployment

dep = Deployment(port=12345)

with dep:
    dep.block()
```
```python
from jina import Client

client = Client(port=12345)
print(client.is_deployment_ready())
```
```text
True
```
````
````{tab} Flow
```python
from jina import Flow

f = Flow(port=12345).add()

with f:
    f.block()
```
```python
from jina import Client

client = Client(port=12345)
print(client.is_flow_ready())
```
```text
True
```
````

<!-- end ready-from-client -->


### Via CLI

`````{tab} Deployment
```python
from jina import Deployment

dep = Deployment(port=12345)

with dep:
    dep.block()
```
```bash
jina-serve ping executor grpc://localhost:12345
```

````{tab} Success
```text
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 0 round...                                                                                              [09/08/22 12:58:13]
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 0 round takes 0 seconds (0.04s)
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 1 round...                                                                                              [09/08/22 12:58:14]
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 1 round takes 0 seconds (0.01s)
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 2 round...                                                                                              [09/08/22 12:58:15]
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 2 round takes 0 seconds (0.01s)
INFO   Jina-serve@92877 avg. latency: 24 ms                                                                                                                    [09/08/22 12:58:16]
```
````

````{tab} Failure
```text
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 0 round...                                                                                              [09/08/22 12:59:00]
ERROR  GRPCClient@92986 Error while getting response from grpc server <AioRpcError of RPC that terminated with:                                          [09/08/22 12:59:00]
               status = StatusCode.UNAVAILABLE
               details = "failed to connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused"
               debug_error_string = "UNKNOWN:Failed to pick subchannel {created_time:"2022-09-08T12:59:00.518707+02:00", children:[UNKNOWN:failed to
       connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused {grpc_status:14,
       created_time:"2022-09-08T12:59:00.518706+02:00"}]}"
       >
WARNI… Jina-serve@92986 not responding, retry (1/3) in 1s
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 0 round takes 0 seconds (0.01s)
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 1 round...                                                                                              [09/08/22 12:59:01]
ERROR  GRPCClient@92986 Error while getting response from grpc server <AioRpcError of RPC that terminated with:                                          [09/08/22 12:59:01]
               status = StatusCode.UNAVAILABLE
               details = "failed to connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused"
               debug_error_string = "UNKNOWN:Failed to pick subchannel {created_time:"2022-09-08T12:59:01.537293+02:00", children:[UNKNOWN:failed to
       connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused {grpc_status:14,
       created_time:"2022-09-08T12:59:01.537291+02:00"}]}"
       >
WARNI… Jina-serve@92986 not responding, retry (2/3) in 1s
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 1 round takes 0 seconds (0.01s)
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 2 round...                                                                                              [09/08/22 12:59:02]
ERROR  GRPCClient@92986 Error while getting response from grpc server <AioRpcError of RPC that terminated with:                                          [09/08/22 12:59:02]
               status = StatusCode.UNAVAILABLE
               details = "failed to connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused"
               debug_error_string = "UNKNOWN:Failed to pick subchannel {created_time:"2022-09-08T12:59:02.557195+02:00", children:[UNKNOWN:failed to
       connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused {grpc_status:14,
       created_time:"2022-09-08T12:59:02.557193+02:00"}]}"
       >
WARNI… Jina-serve@92986 not responding, retry (3/3) in 1s
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 2 round takes 0 seconds (0.02s)
WARNI… Jina-serve@92986 message lost 100% (3/3)
```
````
`````
`````{tab} Flow
```python
from jina import Flow

f = Flow(port=12345)

with f:
    f.block()
```
```bash
jina-serve ping flow grpc://localhost:12345
```

````{tab} Success
```text
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 0 round...                                                                                              [09/08/22 12:58:13]
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 0 round takes 0 seconds (0.04s)
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 1 round...                                                                                              [09/08/22 12:58:14]
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 1 round takes 0 seconds (0.01s)
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 2 round...                                                                                              [09/08/22 12:58:15]
INFO   Jina-serve@92877 ping grpc://localhost:12345 at 2 round takes 0 seconds (0.01s)
INFO   Jina-serve@92877 avg. latency: 24 ms                                                                                                                    [09/08/22 12:58:16]
```
````

````{tab} Failure
```text
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 0 round...                                                                                              [09/08/22 12:59:00]
ERROR  GRPCClient@92986 Error while getting response from grpc server <AioRpcError of RPC that terminated with:                                          [09/08/22 12:59:00]
               status = StatusCode.UNAVAILABLE
               details = "failed to connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused"
               debug_error_string = "UNKNOWN:Failed to pick subchannel {created_time:"2022-09-08T12:59:00.518707+02:00", children:[UNKNOWN:failed to
       connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused {grpc_status:14,
       created_time:"2022-09-08T12:59:00.518706+02:00"}]}"
       >
WARNI… Jina-serve@92986 not responding, retry (1/3) in 1s
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 0 round takes 0 seconds (0.01s)
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 1 round...                                                                                              [09/08/22 12:59:01]
ERROR  GRPCClient@92986 Error while getting response from grpc server <AioRpcError of RPC that terminated with:                                          [09/08/22 12:59:01]
               status = StatusCode.UNAVAILABLE
               details = "failed to connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused"
               debug_error_string = "UNKNOWN:Failed to pick subchannel {created_time:"2022-09-08T12:59:01.537293+02:00", children:[UNKNOWN:failed to
       connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused {grpc_status:14,
       created_time:"2022-09-08T12:59:01.537291+02:00"}]}"
       >
WARNI… Jina-serve@92986 not responding, retry (2/3) in 1s
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 1 round takes 0 seconds (0.01s)
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 2 round...                                                                                              [09/08/22 12:59:02]
ERROR  GRPCClient@92986 Error while getting response from grpc server <AioRpcError of RPC that terminated with:                                          [09/08/22 12:59:02]
               status = StatusCode.UNAVAILABLE
               details = "failed to connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused"
               debug_error_string = "UNKNOWN:Failed to pick subchannel {created_time:"2022-09-08T12:59:02.557195+02:00", children:[UNKNOWN:failed to
       connect to all addresses; last error: UNKNOWN: Failed to connect to remote host: Connection refused {grpc_status:14,
       created_time:"2022-09-08T12:59:02.557193+02:00"}]}"
       >
WARNI… Jina-serve@92986 not responding, retry (3/3) in 1s
INFO   Jina-serve@92986 ping grpc://localhost:12345 at 2 round takes 0 seconds (0.02s)
WARNI… Jina-serve@92986 message lost 100% (3/3)
```
````
`````

## Readiness check via third-party clients

You can check the status of a Flow using any gRPC/HTTP/WebSockets client, not just via Jina-serve Client.

To see how this works, first instantiate the Flow with its corresponding protocol and block it for serving:

````{tab} Deployment
```python
from jina import Deployment
import os

PROTOCOL = 'grpc'  # it could also be http or websocket

os.environ[
    'JINA_LOG_LEVEL'
] = 'DEBUG'  # this way we can check what is the PID of the Executor

dep = Deployment(protocol=PROTOCOL, port=12345)

with dep:
    dep.block()
```

```text
⠋  Waiting ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0/0 -:--:--DEBUG  gateway/rep-0@19075 adding connection for deployment executor0/heads/0 to grpc://0.0.0.0:12346                                                                                           [05/31/22 18:10:16]
DEBUG  executor0/rep-0@19074 start listening on 0.0.0.0:12346                                                                                                                                   [05/31/22 18:10:16]
DEBUG  gateway/rep-0@19075 start server bound to 0.0.0.0:12345                                                                                                                                  [05/31/22 18:10:17]
DEBUG  executor0/rep-0@19059 ready and listening                                                                                                                                                [05/31/22 18:10:17]
DEBUG  gateway/rep-0@19059 ready and listening                                                                                                                                                  [05/31/22 18:10:17]
╭─── 🎉 Deployment is ready to serve! ───╮
│  🔗  Protocol                  GRPC    │
│  🏠     Local         0.0.0.0:12345    │
│  🔒   Private    192.168.1.13:12345    │
╰────────────────────────────────────────╯
DEBUG  Deployment@19059 2 Deployments (i.e. 2 Pods) are running in this Deployment 
```
````
````{tab} Flow
```python
from jina import Flow
import os

PROTOCOL = 'grpc'  # it could also be http or websocket

os.environ[
    'JINA_LOG_LEVEL'
] = 'DEBUG'  # this way we can check what is the PID of the Executor

f = Flow(protocol=PROTOCOL, port=12345).add()

with f:
    f.block()
```

```text
⠋  Waiting ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 0/0 -:--:--DEBUG  gateway/rep-0@19075 adding connection for deployment executor0/heads/0 to grpc://0.0.0.0:12346                                                                                           [05/31/22 18:10:16]
DEBUG  executor0/rep-0@19074 start listening on 0.0.0.0:12346                                                                                                                                   [05/31/22 18:10:16]
DEBUG  gateway/rep-0@19075 start server bound to 0.0.0.0:12345                                                                                                                                  [05/31/22 18:10:17]
DEBUG  executor0/rep-0@19059 ready and listening                                                                                                                                                [05/31/22 18:10:17]
DEBUG  gateway/rep-0@19059 ready and listening                                                                                                                                                  [05/31/22 18:10:17]
╭────── 🎉 Flow is ready to serve! ──────╮
│  🔗  Protocol                  GRPC    │
│  🏠     Local         0.0.0.0:12345    │
│  🔒   Private    192.168.1.13:12345    │
╰────────────────────────────────────────╯
DEBUG  Flow@19059 2 Deployments (i.e. 2 Pods) are running in this Flow 
```
````

### Using gRPC

When using grpc, use [grpcurl](https://github.com/fullstorydev/grpcurl) to access the Gateway's gRPC service that is responsible for reporting the Orchestration status.

```shell
docker pull fullstorydev/grpcurl:latest
docker run --network='host' fullstorydev/grpcurl -plaintext 127.0.0.1:12345 jina.JinaGatewayDryRunRPC/dry_run
```
The error-free output below signifies a correctly running Orchestration:
```json
{}
```

You can simulate an Executor going offline by killing its process.

```shell script
kill -9 $EXECUTOR_PID # in this case we can see in the logs that it is 19059
```

Then by doing the same check, you can see that it returns an error:

```shell
docker run --network='host' fullstorydev/grpcurl -plaintext 127.0.0.1:12345 jina.JinaGatewayDryRunRPC/dry_run
```

````{dropdown} Error output
```json
{
  "code": "ERROR",
  "description": "failed to connect to all addresses |Gateway: Communication error with deployment at address(es) 0.0.0.0:12346. Head or worker(s) may be down.",
  "exception": {
    "name": "InternalNetworkError",
    "args": [
      "failed to connect to all addresses |Gateway: Communication error with deployment at address(es) 0.0.0.0:12346. Head or worker(s) may be down."
    ],
    "stacks": [
      "Traceback (most recent call last):\n",
      "  File \"/home/joan/jina/jina/jina/serve/networking.py\", line 750, in task_wrapper\n    timeout=timeout,\n",
      "  File \"/home/joan/jina/jina/jina/serve/networking.py\", line 197, in send_discover_endpoint\n    await self._init_stubs()\n",
      "  File \"/home/joan/jina/jina/jina/serve/networking.py\", line 174, in _init_stubs\n    self.channel\n",
      "  File \"/home/joan/jina/jina/jina/serve/networking.py\", line 1001, in get_available_services\n    async for res in response:\n",
      "  File \"/home/joan/.local/lib/python3.7/site-packages/grpc/aio/_call.py\", line 326, in _fetch_stream_responses\n    await self._raise_for_status()\n",
      "  File \"/home/joan/.local/lib/python3.7/site-packages/grpc/aio/_call.py\", line 237, in _raise_for_status\n    self._cython_call.status())\n",
      "grpc.aio._call.AioRpcError: \u003cAioRpcError of RPC that terminated with:\n\tstatus = StatusCode.UNAVAILABLE\n\tdetails = \"failed to connect to all addresses\"\n\tdebug_error_string = \"{\"created\":\"@1654012804.794351252\",\"description\":\"Failed to pick subchannel\",\"file\":\"src/core/ext/filters/client_channel/client_channel.cc\",\"file_line\":3134,\"referenced_errors\":[{\"created\":\"@1654012804.794350006\",\"description\":\"failed to connect to all addresses\",\"file\":\"src/core/lib/transport/error_utils.cc\",\"file_line\":163,\"grpc_status\":14}]}\"\n\u003e\n",
      "\nDuring handling of the above exception, another exception occurred:\n\n",
      "Traceback (most recent call last):\n",
      "  File \"/home/joan/jina/jina/jina/serve/runtimes/gateway/grpc/__init__.py\", line 155, in dry_run\n    async for _ in self.streamer.stream(request_iterator=req_iterator):\n",
      "  File \"/home/joan/jina/jina/jina/serve/stream/__init__.py\", line 78, in stream\n    async for response in async_iter:\n",
      "  File \"/home/joan/jina/jina/jina/serve/stream/__init__.py\", line 154, in _stream_requests\n    response = self._result_handler(future.result())\n",
      "  File \"/home/joan/jina/jina/jina/serve/runtimes/gateway/request_handling.py\", line 146, in _process_results_at_end_gateway\n    await asyncio.gather(gather_endpoints(request_graph))\n",
      "  File \"/home/joan/jina/jina/jina/serve/runtimes/gateway/request_handling.py\", line 88, in gather_endpoints\n    raise err\n",
      "  File \"/home/joan/jina/jina/jina/serve/runtimes/gateway/request_handling.py\", line 80, in gather_endpoints\n    endpoints = await asyncio.gather(*tasks_to_get_endpoints)\n",
      "  File \"/home/joan/jina/jina/jina/serve/networking.py\", line 754, in task_wrapper\n    e=e, retry_i=i, dest_addr=connection.address\n",
      "  File \"/home/joan/jina/jina/jina/serve/networking.py\", line 697, in _handle_aiorpcerror\n    details=e.details(),\n",
      "jina.excepts.InternalNetworkError: failed to connect to all addresses |Gateway: Communication error with deployment at address(es) 0.0.0.0:12346. Head or worker(s) may be down.\n"
    ]
  }
}
```
````

### Using HTTP or WebSockets

When using HTTP or WebSockets as the Gateway protocol, use curl to target the `/dry_run` endpoint and get the status of the Flow.


```shell
curl http://localhost:12345/dry_run
```
Error-free output signifies a correctly running Flow:
```json
{"code":0,"description":"","exception":null}
```

You can simulate an Executor going offline by killing its process:

```shell script
kill -9 $EXECUTOR_PID # in this case we can see in the logs that it is 19059
```

Then by doing the same check, you can see that the call returns an error:

```json
{"code":1,"description":"failed to connect to all addresses |Gateway: Communication error with deployment executor0 at address(es) {'0.0.0.0:12346'}. Head or worker(s) may be down.","exception":{"name":"InternalNetworkError","args":["failed to connect to all addresses |Gateway: Communication error with deployment executor0 at address(es) {'0.0.0.0:12346'}. Head or worker(s) may be down."],"stacks":["Traceback (most recent call last):\n","  File \"/home/joan/jina/jina/jina/serve/networking.py\", line 726, in task_wrapper\n    timeout=timeout,\n","  File \"/home/joan/jina/jina/jina/serve/networking.py\", line 241, in send_requests\n    await call_result,\n","  File \"/home/joan/.local/lib/python3.7/site-packages/grpc/aio/_call.py\", line 291, in __await__\n    self._cython_call._status)\n","grpc.aio._call.AioRpcError: <AioRpcError of RPC that terminated with:\n\tstatus = StatusCode.UNAVAILABLE\n\tdetails = \"failed to connect to all addresses\"\n\tdebug_error_string = \"{\"created\":\"@1654074272.702044542\",\"description\":\"Failed to pick subchannel\",\"file\":\"src/core/ext/filters/client_channel/client_channel.cc\",\"file_line\":3134,\"referenced_errors\":[{\"created\":\"@1654074272.702043378\",\"description\":\"failed to connect to all addresses\",\"file\":\"src/core/lib/transport/error_utils.cc\",\"file_line\":163,\"grpc_status\":14}]}\"\n>\n","\nDuring handling of the above exception, another exception occurred:\n\n","Traceback (most recent call last):\n","  File \"/home/joan/jina/jina/jina/serve/runtimes/gateway/http/app.py\", line 142, in _flow_health\n    data_type=DataInputType.DOCUMENT,\n","  File \"/home/joan/jina/jina/jina/serve/runtimes/gateway/http/app.py\", line 399, in _get_singleton_result\n    async for k in streamer.stream(request_iterator=request_iterator):\n","  File \"/home/joan/jina/jina/jina/serve/stream/__init__.py\", line 78, in stream\n    async for response in async_iter:\n","  File \"/home/joan/jina/jina/jina/serve/stream/__init__.py\", line 154, in _stream_requests\n    response = self._result_handler(future.result())\n","  File \"/home/joan/jina/jina/jina/serve/runtimes/gateway/request_handling.py\", line 148, in _process_results_at_end_gateway\n    partial_responses = await asyncio.gather(*tasks)\n","  File \"/home/joan/jina/jina/jina/serve/runtimes/gateway/graph/topology_graph.py\", line 128, in _wait_previous_and_send\n    self._handle_internalnetworkerror(err)\n","  File \"/home/joan/jina/jina/jina/serve/runtimes/gateway/graph/topology_graph.py\", line 70, in _handle_internalnetworkerror\n    raise err\n","  File \"/home/joan/jina/jina/jina/serve/runtimes/gateway/graph/topology_graph.py\", line 125, in _wait_previous_and_send\n    timeout=self._timeout_send,\n","  File \"/home/joan/jina/jina/jina/serve/networking.py\", line 734, in task_wrapper\n    num_retries=num_retries,\n","  File \"/home/joan/jina/jina/jina/serve/networking.py\", line 697, in _handle_aiorpcerror\n    details=e.details(),\n","jina.excepts.InternalNetworkError: failed to connect to all addresses |Gateway: Communication error with deployment executor0 at address(es) {'0.0.0.0:12346'}. Head or worker(s) may be down.\n"],"executor":""}}
```
