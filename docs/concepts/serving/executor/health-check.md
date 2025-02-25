(health-check-microservices)=
# Health Check

## Using gRPC

You can check every individual Executor, by using a [standard gRPC health check endpoint](https://github.com/grpc/grpc/blob/master/doc/health-checking.md).
In most cases this is not necessary, since such checks are performed by Jina-serve, a Kubernetes service mesh or a load balancer under the hood.
Nevertheless, you can perform these checks yourself.

When performing these checks, you can expect one of the following `ServingStatus` responses:
- **`UNKNOWN` (0)**: The health of the Executor could not be determined
- **`SERVING` (1)**: The Executor is healthy and ready to receive requests
- **`NOT_SERVING` (2)**: The Executor is *not* healthy and *not* ready to receive requests
- **`SERVICE_UNKNOWN` (3)**: The health of the Executor could not be determined while performing streaming

````{admonition} See Also
:class: seealso

To learn more about these status codes, and how health checks are performed with gRPC, see [here](https://github.com/grpc/grpc/blob/master/doc/health-checking.md).
````

Let's check the health of an Executor. First start a dummy executor from the terminal:
```shell
jina executor --port 12346
```

In another terminal, you can use [grpcurl](https://github.com/fullstorydev/grpcurl) to send gRPC requests to your services.

```shell
docker pull fullstorydev/grpcurl:latest
docker run --network='host' fullstorydev/grpcurl -plaintext 127.0.0.1:12346 grpc.health.v1.Health/Check
```

```json
{
  "status": "SERVING"
}
```

## Using HTTP

````{admonition} Caution
:class: caution
For Executors running with HTTP, the gRPC health check response codes outlined {ref}`above <health-check-microservices>` do not apply.

Instead, an error-free response signifies healthiness.
````

When using HTTP as the protocol for the Executor, you can query the endpoint `'/'` to check the status.

First, create a Deployment with the HTTP protocol:

```python
from jina import Deployment

d = Deployment(protocol='http', port=12345)
with d:
    d.block()
```
Then query the "empty" endpoint:
```bash
curl http://localhost:12345
```

You get a valid empty response indicating the Executor's ability to serve:
```json
{}
```
