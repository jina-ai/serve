(jcloud-configuration)=
# {octicon}`file-code` Configuration

JCloud extends Jina-serve's {ref}`Flow YAML specification<flow-yaml-spec>` by introducing the special field `jcloud`. This lets you define resources and scaling policies for each Executor and Gateway.

Here's a Flow with two Executors that have specific resource needs: `indexer` requires a 10 GB `ebs` disk, whereas `encoder` requires a G4 instance, which implies that two cores and 4 GB RAM are used. See the below sections for further information about instance types.

```{code-block} yaml
---
emphasize-lines: 5-7,10-16
---
jtype: Flow
executors:
  - name: encoder
    uses: jinaai+docker://<username>/Encoder
    jcloud:
      resources:
        instance: C4
  - name: indexer
    uses: jinaai+docker://<username>/Indexer
    jcloud:
      resources:
        storage: 
          kind: ebs
          size: 10G
```

## Allocate Executor resources

Since each Executor has its own business logic, it may require different cloud resources. One Executor might need more RAM, whereas another might need a bigger disk. 

In JCloud, you can pass highly customizable, finely-grained resource requests for each Executor using the `jcloud.resources` argument in your Flow YAML.

### Instance

JCloud uses the concept of an "instance" to represent a specific set of hardware specifications.
In the above example, a C4 instance type represents two cores and 4 GB RAM based on the CPU tiers instance definition table below.

````{admonition} Note
:class: note
We will translate the raw numbers from input to instance tier that fits most closely if you are still using the legacy resource specification interface, such as:

```{code-block} yaml
jcloud:
  resources:
    cpu: 8
    memory: 8G
```

There are circumstances in the instance tier where they don't exactly fulfill the CPU cores and memory you need, like in the above example.
In cases like this we "ceil" the requests to the lowest tier that satisfies all the specifications. 
In this case, `C6` would be considered, as `C5`'s `Cores` are lower than what's being requested (4 vs 8).
````

There are also two types of instance tiers, one for CPU instances, one for GPU.

(jcloud-pricing)=
#### Pricing
Each instance has a fixed `Credits Per Hour` number, indicating how many credits JCloud will charge
if a certain instance is used. For example, if an Executor uses `C3`, it implies that `10` credits will be spent
from the operating user account. Other important facts to note:

   - If the Flow is powering other App(s) you create, you will be charged by the App(s), not the underlying Flow.
   - `Credits Per Hour` is on an Executor/Gateway basis, the total `Credits Per Hour` of a Flow is the sum of all the credits
     each components cost.
   - If shards/replicas are used in an Executor/Gateway, the same instance type will be used, so `Credits Per Hour` will be multiplied.
     For example, if an Executor uses `C3` and it has two replicas, the `Credits Per Hour` for the Executor would double to `20`.
     The only exception is when sharding is used. In that case `C1` would be used for the shards head, regardless of what instance type has been entered for the shared Executor.

```{hint}
Please visit [Jina AI Cloud Pricing](https://cloud.jina.ai/pricing/) for more information about billing and credits.
```

#### CPU tiers

| Instance | Cores | Memory | Credits per hour |
| -------- | ----- | ------ | ---------------- |
| C1       | 0.1   | 0.2 GB | 1                |
| C2       | 0.5   | 1 GB   | 5                |
| C3       | 1     | 2 GB   | 10               |
| C4       | 2     | 4 GB   | 20               |
| C5       | 4     | 8 GB   | 40               |
| C6       | 8     | 16 GB  | 80               |
| C7       | 16    | 32 GB  | 160              |
| C8       | 32    | 64 GB  | 320              |


By default, C1 is allocated to each Executor and Gateway.

JCloud offers the general Intel Xeon processor (Skylake 8175M or Cascade Lake 8259CL) for the CPU instances. 

#### GPU tiers

JCloud supports GPU workloads with two different usages: `shared` or `dedicated`. 

If GPU is enabled, JCloud will provide NVIDIA A10G Tensor Core GPUs with 24 GB memory for workloads in both usage types.

```{hint}
When using GPU resources, it may take a few extra minutes before all Executors are ready to serve traffic.
```

| Instance | GPU    | Memory | Credits per hour |
| -------- | ------ | ------ | ---------------- |
| G1       | shared | 14 GB  | 100              |
| G2       | 1      | 14 GB  | 125              |
| G3       | 2      | 24 GB  | 250              |
| G4       | 4      | 56 GB  | 500              |

##### Shared GPU

An Executor using a `shared` GPU shares this GPU with up to four other Executors.
This enables time-slicing, which allows workloads that land on oversubscribed GPUs to interleave with one another.

To use `shared` GPU, `G1` needs to be specified as the instance type.

The tradeoffs with a `shared` GPU are increased latency, jitter, and potential out-of-memory (OOM) conditions when many different applications are time-slicing on the GPU. If your application is consuming a lot of memory, we suggest using a dedicated GPU.

##### Dedicated GPU

Using a dedicated GPU is the default way to provision a GPU for an Executor. This automatically creates nodes or assigns the Executor to a GPU node. In this case, the Executor owns the whole GPU.

To use a `dedicated` GPU, `G2`/ `G3` / `G4` needs to be specified as instance type.

### Storage

JCloud supports three kinds of storage: ephemeral (default), [efs](https://aws.amazon.com/efs/) (network file storage) and [ebs](https://aws.amazon.com/ebs/) (block device).

`ephemeral` storage will assign space to an Executor when it is created. Data in `ephemeral` storage is deleted permanently if Executors are restarted or rescheduled.

````{hint}

By default, we assign `ephemeral` storage to all Executors in a Flow. This lets the storage resize dynamically, so you don't need to shrink/grow volumes manually.

If your Executor needs to share data with other Executors and retain data persistency, consider using `efs`. Note that:

- IO performance is slower compared to `ebs` or `ephemeral`
- The disk can be shared with other Executors or Flows.
- Default storage size is 5 GB.

If your Executor needs high IO, you can use `ebs` instead. Note that:

- The disk cannot be shared with other Executors or Flows.
- Default storage size is 5 GB.
````

JCloud also supports retaining the data that a Flow was using while it was active. You can set the `retain` argument to `true` to enable this feature.

```{code-block} yaml
---
emphasize-lines: 5-10,12,15
---
jtype: Flow
executors:
  - name: executor1
    uses: jinaai+docker://<username>/Executor1
    jcloud:
      resources:
        storage:
          kind: ebs
          size: 10G
          retain: true
  - name: executor2
    uses: jinaai+docker://<username>/Executor2
    jcloud:
      resources:
        storage:
          kind: efs
```
#### Pricing
Here are the numbers in terms of credits per GB per month for the three kinds of storage described above.

| Instance  | Credits per GB per month |
| --------- | ------------------------ |
| Ephemeral | 0                        |
| EBS       | 30                       |
| EFS       | 75                       |

For example, using 10 GB of EBS storage for a month costs `30` credits.
If shards/replicas are used, we will multiply credits further by the number of storages created.

## Scale out Executors

On JCloud, demand-based autoscaling functionality is naturally offered thanks to the underlying Kubernetes architecture. This means that you can maintain [serverless](https://en.wikipedia.org/wiki/Serverless_computing) deployments in a cost-effective way with no headache of setting the [right number of replicas](https://jina.ai/serve/how-to/scale-out/#scale-out-your-executor) anymore!


### Autoscaling with `jinaai+serverless://` 

The easiest way to scale out your Executor is to use a Serverless Executor. This can be enabled by using `jinaai+serverless://` instead of `jinaai+docker://` in Executor's `uses`, such as:

```{code-block} yaml
---
emphasize-lines: 4
---
jtype: Flow
executors:
  - name: executor1
    uses: jinaai+serverless://<username>/Executor1
```

JCloud autoscaling leverages [Knative](https://knative.dev/docs/) behind the scenes, and `jinahub+serverless` uses a set of Knative configurations as defaults.

```{hint}
For more information about the Knative autoscaling configurations, please visit [Knative autoscaling](https://knative.dev/docs/serving/autoscaling/).
```


### Autoscaling with custom args

If `jinaai+serverless://` doesn't meet your requirements, you can further customize autoscaling configurations by using the `autoscale` argument on a per-Executor basis in the Flow YAML, such as:

```{code-block} yaml
---
emphasize-lines: 5-10
---
jtype: Flow
executors:
  - name: executor1
    uses: jinaai+docker://<username>/Executor1
    jcloud:
      autoscale:
        min: 1
        max: 2
        metric: rps
        target: 50
```

Below are the defaults and requirements for the configurations:

| Name             | Default     | Allowed                                     | Description                                                               |
| ------           | ----------- | ------------------------                    | -------------------------------------------------                         |
| min              | 1           | int                                         | Minimum number of replicas (`0` means serverless)                         |
| max              | 2           | int, up to 5                                | Maximum number of replicas                                                |
| metric           | concurrency | `concurrency` / `rps` / `cpu` / `memory`    | Metric for scaling                                                        |
| scale_down_delay | 30s         | str, `0s` <= value <= `1h`                  | Time window which must pass at reduced concurrency before a scaling down  |
| target           | 100         | int                                         | Target number the replicas try to maintain.                               |

The unit of `target` depends of the metric specified. Refer to the table below:

| Metric        | Target                                                                                                                                                  |
| ----          | -----                                                                                                                                                   |
| `concurrency` | Number of concurrent requests processed at any given time.                                                                                              |
| `rps`         | Number of requests processed per second per replica.                                                                                                    |
| `cpu`         | Average % CPU utilization of each pod<br>(e.g. `60` means replicas will be scaled up when pods on average reach 60% CPU utilization)                    |
| `memory`      | Average mebibytes of memory used by each pod<br>(e.g. `200` means replicas will be scaled up when the average pods' memory consumption exceeds 200MiB). |

After you make a JCloud deployment using the autoscaling configuration, the Flow serving part is just the same: the only difference you may notice is it takes a few extra seconds to handle the initial requests since it needs to scale the deployments behind the scenes. Let JCloud handle the scaling from now on, and you can deal with the code!

Note, that if `metric` is `cpu` or `memory`, `min` will be reset to 1 if user sets it to set to 0.

### Pricing
At present, pricing for autoscaled Executor/Gateway largely follows the same {ref}`JCloud pricing rules <jcloud-pricing>` as other Jina AI services.
We track the minimum number of replicas in autoscale configurations and use it as a multiplier for the replicas used when calculating the
`Credits Per Hour`.

### Restrictions
```{admonition} **Restrictions**

- Autoscale does not currently allow the use of `ebs` as a storage type in combination. Please use `efs` and `ephemeral` instead.
- Autoscale is not supported for multi-protocol Gateways.
```
## Configure availability tolerance

If service issues cause disruption of Executors, JCloud lets you specify a tolerance level for number of replicas that stay up or go down.

The JCloud parameters `minAvailable` and `maxUnavailable` ensure that Executors will stay up even if a certain number of replicas go down.

| Name             | Default |                                          Allowed                                          | Description                                              |
| :--------------- | :-----: | :---------------------------------------------------------------------------------------: | :------------------------------------------------------- |
| `minAvailable`   |   N/A   | Lower than number of [replicas](https://jina.ai/serve/concepts/flow/scale-out/#scale-out)  | Minimum number of replicas available during disruption   |
| `maxUnavailable` |   N/A   | Lower than numbers of [replicas](https://jina.ai/serve/concepts/flow/scale-out/#scale-out) | Maximum number of replicas unavailable during disruption |

```{code-block} yaml
---
emphasize-lines: 5-6
---
jtype: Flow
executors:
  - uses: jinaai+docker://<username>/Executor1
    replicas: 5
    jcloud:
      minAvailable: 2
```
In case of disruption, ensure at least two replicas will still be available, while three may be down.

```{code-block} yaml
---
emphasize-lines: 5-6
---
jtype: Flow
executors:
  - uses: jinaai+docker://<username>/Executor1
    replicas: 5
    jcloud:
      maxUnavailable: 2
```
In case of disruption, ensure that if a maximum of two replicas are down, at least three replicas will still be available.


## Configure Gateway

The Gateway can be customized just like an Executor.
### Set timeout

By default, the Gateway will close connections that have been idle for over 600 seconds. If you want a longer connection timeout threshold, change the `timeout` parameter under `gateway.jcloud`.

```{code-block} yaml
---
emphasize-lines: 2-4
---
jtype: Flow
gateway:
  jcloud:
    timeout: 800
executors:
  - name: executor1
    uses: jinaai+docker://<username>/Executor1
```

### Control Gateway resources

To customize the Gateway's CPU or memory, specify the instance type under `gateway.jcloud.resources`:

```{code-block} yaml
---
emphasize-lines: 2-6
---
jtype: Flow
gateway:
  jcloud:
    resources:
      instance: C3
executors:
  - name: encoder
    uses: jinaai+docker://<username>/Encoder
```

## Expose Executors

A Flow deployment without a Gateway is often used for {ref}`external-executors`, which can be shared between different Flows. You can expose an Executor by setting `expose: true` (and un-expose the Gateway by setting `expose: false`):

```{code-block} yaml
---
emphasize-lines: 2-4, 8-9
---
jtype: Flow
gateway:
  jcloud:
    expose: false       # don't expose the Gateway
executors:
  - name: custom
    uses: jinaai+docker://<username>/CustomExecutor
    jcloud:
      expose: true    # expose the Executor
```

```{figure} img/expose-executor.png
:width: 70%
```

You can expose the Gateway along with Executors:

```{code-block} yaml
---
emphasize-lines: 2-4,8-9
---
jtype: Flow
gateway:
  jcloud:
    expose: true
executors:
  - name: custom1
    uses: jinaai+docker://<username>/CustomExecutor1
    jcloud:
      expose: true    # expose the Executor
```

```{figure} img/gateway-and-executors.png
:width: 70%
```

## Other deployment options

### Customize Flow name

You can use the `name` argument to specify the Flow name in the Flow YAML:

```{code-block} yaml
---
emphasize-lines: 2-3
---
jtype: Flow
jcloud:
  name: my-name
executors:
  - name: executor1
    uses: jinaai+docker://<username>/Executor1
```

### Specify Jina version

To control Jina's version while deploying a Flow to `jcloud`, you can pass the `version` argument in the Flow YAML:

```{code-block} yaml
---
emphasize-lines: 2-3
---
jtype: Flow
jcloud:
  version: 3.10.0
executors:
  - name: executor1
    uses: jinaai+docker://<username>/Executor1
```

### Add Labels

You can use `labels` (as key-value pairs) to attach metadata to your Flows and Executors:

Flow level `labels`:
```{code-block} yaml
---
emphasize-lines: 2-5
---
jtype: Flow
jcloud:
  labels: 
    username: johndoe
    app: fashion-search
executors:
  - name: executor1
    uses: jinaai+docker://<username>/Executor1
```

Executor level `labels`:
```{code-block} yaml
---
emphasize-lines: 5-8
---
jtype: Flow
executors:
  - name: executor1
    uses: jinaai+docker://<username>/Executor1
    jcloud:
      labels:
        index: partial
        group: backend
```


```{hint}

Keys in `labels` have the following restrictions:
  - Must be 63 characters or fewer.
  - Must begin and end with an alphanumeric character ([a-z0-9A-Z]) with dashes (-), underscores (_), dots (.), and alphanumerics between.
  - The following keys are skipped if passed in the Flow YAML.
    - `user`
    - `jina`-version
```

### Monitoring

To enable [tracing support](https://jina.ai/serve/cloud-nativeness/opentelemetry/) in Flows, you can pass `enable: true` argument in the Flow YAML. (Tracing support is not enabled by default in JCloud)

```{code-block} yaml
---
emphasize-lines: 2-5
---
jtype: Flow
jcloud:
  monitor:
    traces:
      enable: true
executors:
  - name: executor1
    uses: jinaai+docker://<username>/Executor1
```

You can pass the `enable: true` argument to `gateway` to only enable tracing support in the Gateway:

```{code-block} yaml
---
emphasize-lines: 2-6
---
jtype: Flow
gateway:
  jcloud:
      monitor:
        traces:
          enable: true
executors:
  - name: executor1
    uses: jinaai+docker://<username>/Executor1
```

You can also only enable tracing support in `executor1`.

```{code-block} yaml
---
emphasize-lines: 5-8
---
jtype: Flow
executors:
  - name: executor1
    uses: jinaai+docker://<username>/Executor1
    jcloud:
      monitor:
        traces:
          enable: true
```
