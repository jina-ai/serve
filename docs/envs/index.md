(jina-env-vars)=
# {octicon}`list-unordered` Environment Variables

Jina-serve uses environment variables to determine different behaviours. To see all supported environment variables and their current values, run:

```bash
jina -vf
```

If you use containerized Executors (including {ref}`Kubernetes <kubernetes>` and {ref}`Docker Compose <docker-compose>`), you can pass separate environment variables to each Executor in the following way:


`````{tab} FLow YAML

```yaml
jtype: Flow
with: {}
executors:
- name: executor0
  port: 49583
  env:
    JINA_LOG_LEVEL: DEBUG
    MYSECRET: ${{ ENV.MYSECRET }}
- name: executor1
  port: 62156
  env:
    JINA_LOG_LEVEL: INFO
    CUDA_VISIBLE_DEVICES: 1
```
`````
`````{tab} Deployment YAML

```yaml
jtype: Deployment
with:
  name: executor0
  port: 49583
  env:
    JINA_LOG_LEVEL: DEBUG
    MYSECRET: ${{ ENV.MYSECRET }}
```
`````
````{tab} Python API

```python
from jina import Flow
import os

secret = os.environ['MYSECRET']
f = (
    Flow()
    .add(env={'JINA_LOG_LEVEL': 'DEBUG', 'MYSECRET': secret})
    .add(env={'JINA_LOG_LEVEL': 'INFO', 'CUDA_VISIBLE_DEVICES': 1})
)
f.save_config("envflow.yml")
```
````

The following environment variables are used internally in Jina:

| Environment variable          | Description                                                                                                                                                                                     |
|-------------------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `JINA_AUTH_TOKEN`             | Authentication token of Jina Cloud                                                                                                                                                              |
| `JINA_DEFAULT_HOST`           | Default host where server is exposed                                                                                                                                                    |
| `JINA_DEFAULT_TIMEOUT_CTRL`   | Default timeout time used by Flow to check readiness of Executors                                                                                                                       |
| `JINA_DEPLOYMENT_NAME`        | Name of deployment, used by Head Runtime in Kubernetes to connect to different deployments                                                                                          |
| `JINA_DISABLE_UVLOOP`         | If set, Jina will not use uvloop event loop for concurrent execution                                                                                                                            |
| `JINA_FULL_CLI`               | If set, all CLI options will be shown in help                                                                                                                                                                                                                                                            |
| `JINA_GATEWAY_IMAGE`          | Used when exporting a Flow to Kubernetes or Docker Compose to override default gateway image                                                                                                                                                                                                             |
| `JINA_GRPC_RECV_BYTES`        | Set by gRPC service to keep track of received bytes                                                                                                                                     |
| `JINA_GRPC_SEND_BYTES`        | Set by gRPC service to keep track of sent bytes                                                                                                                                         |
| `JINA_K8S_ACCESS_MODES`       | Configures access modes for `PersistentVolumeClaim` attached to `StatefulSet`, when creating a `StatefulSet` in Kubernetes for an Executor using volumes. Defaults to '["ReadWriteOnce"]' |
| `JINA_K8S_STORAGE_CAPACITY`   | Configures capacity for `PersistentVolumeClaim` attached to `StatefulSet`, when creating a `StatefulSet` in Kubernetes for an Executor using volumes. Defaults to '10G'                   |
| `JINA_K8S_STORAGE_CLASS_NAME` | Configures storage class for `PersistentVolumeClaim` attached to `StatefulSet`, when creating a `StatefulSet` in Kubernetes for an Executor using volumes. Defaults to 'standard'         |
| `JINA_LOCKS_ROOT`             | Root folder where file locks for concurrent Executor initialization                                                                                                                         |
| `JINA_LOG_CONFIG`             | Configuration used for logger                                                                                                                                                           |
| `JINA_LOG_LEVEL`              | Logging level used: INFO, DEBUG, WARNING                                                                                                                                                    |
| `JINA_LOG_NO_COLOR`           | If set, disables color from rich console                                                                                                                                                        |
| `JINA_MP_START_METHOD`        | Sets multiprocessing start method used by Jina                                                                                                                                              |
| `JINA_OPTOUT_TELEMETRY`       | If set, disables telemetry                                                                                                                                                                                                                                                                                            |
| `JINA_RANDOM_PORT_MAX`        | Maximum port number used when selecting random ports to apply for Executors or Gateway                                                                                                                                                                                                                                                                                                                                                                                   |
| `JINA_RANDOM_PORT_MIN`        | Minimum port number used when selecting random ports to apply for Executors or Gateway                                                                                                                                                                                                                                                                                                                                                                                   |
| `JINA_STREAMER_ARGS`          | Jina uses this variable to inject `GatewayStreamer` arguments into host environment running a Gateway                                                                                         |
