(jcloud)=
# Jina AI Cloud Hosting


```{toctree}
:hidden:

configuration
```

```{figure} https://jina.ai/serve/_images/jcloud-banner.png
:width: 0 %
:scale: 0 %
```

```{figure} img/jcloud-banner.png
:scale: 0 %
:width: 0 %
```

After building a Jina-serve project, the next step is to deploy and host it on the cloud. [Jina AI Cloud](https://cloud.jina.ai/) is Jina-serve's reliable, scalable and production-ready cloud-hosting solution that manages your project lifecycle without surprises or hidden development costs.

```{tip}
Are you ready to unlock the power of AI with Jina AI Cloud? Take a look at our [pricing options](https://cloud.jina.ai/pricing) now!
```

In addition to deploying Flows, `jcloud` supports the creation of secrets and jobs which are created in the Flow's namespace. 

## Basics

Jina AI Cloud provides a CLI that you can use via `jina cloud` from the terminal (or `jcloud` or simply `jc` for minimalists.)

````{hint}
You can also install just the JCloud CLI without installing the Jina-serve package.

```bash
pip install jcloud
jc -h
```

If you installed the JCloud CLI individually, all of its commands fall under the `jc` or `jcloud` executable.


In case the command `jc` is already occupied by another tool, use `jcloud` instead. If your pip install doesn't register bash commands for you, you can run `python -m jcloud -h`.
````

For the rest of this section, we use `jc` or `jcloud`. But again they are interchangeable with `jina cloud`.

## Flows

### Deploy

In Jina's idiom, a project is a [Flow](https://jina.ai/serve/concepts/orchestration/flow/), which represents an end-to-end task such as indexing, searching or recommending. In this document, we use "project" and "Flow" interchangeably.

A Flow can have two types of file structure: a single YAML file or a project folder.

#### Single YAML file

A self-contained YAML file, consisting of all configuration at the [Flow](https://jina.ai/serve/concepts/orchestration/flow/)-level and [Executor](https://jina.ai/serve/concepts/serving/executor/)-level.

> All Executors' `uses` must follow the format `jinaai+docker://<username>/MyExecutor` (from [Executor Hub](https://cloud.jina.ai)) to avoid any local file dependencies:

```yaml
# flow.yml
jtype: Flow
executors:
  - name: sentencizer
    uses: jinaai+docker://jina-ai/Sentencizer
```

To deploy:

```bash
jc flow deploy flow.yml
```

````{caution}
When `jcloud` deploys a flow it automatically appends the following global arguments to the `flow.yml`, if not present:

```yaml
jcloud:
  version: jina-version
  docarray: docarray-version
```

The `jina` and `docarray` corresponds to your development environment's `jina` and `docarray` versions.
````

````{tip}
We recommend testing locally before deployment:

```bash
jina flow --uses flow.yml
```
````

#### Project folder

````{tip}
The best practice for creating a Jina AI Cloud project is to use:

```bash
jc new
```
This ensures the correct project structure that is accepted by Jina AI Cloud.

````

Just like a regular Python project, you can have sub-folders of Executor implementations and a `flow.yml` on the top-level to connect all Executors together.

You can create an example local project using `jc new hello`. The default structure looks like:

```
hello/
├── .env
├── executor1
│   ├── config.yml
│   ├── executor.py
│   └── requirements.txt
└── flow.yml
```

Where:

- `hello/` is your top-level project folder.
- `executor1` directory has all Executor related code/configuration. You can read the best practices for [file structures](https://jina.ai/serve/concepts/serving/executor/file-structure/). Multiple Executor directories can be created.
- `flow.yml` Your Flow YAML.
- `.env` All environment variables used during deployment.

To deploy:

```bash
jc flow deploy hello
```

The Flow is successfully deployed when you see:

```{figure} img/deploy.png
:width: 70%
```
---

You will get a Flow ID, say `merry-magpie-82b9c0897f`. This ID is required to manage, view logs and remove the Flow.

As this Flow is deployed with the default gRPC gateway (feel free to change it to `http` or `websocket`), you can use `jina.Client` to access it:

```python
from jina import Client, Document

print(
    Client(host='grpcs://merry-magpie-82b9c0897f.wolf.jina.ai').post(
        on='/', inputs=Document(text='hello')
    )
)
```

(jcloud-flow-status)=
### Get status

To get the status of a Flow:
```bash
jc flow status merry-magpie-82b9c0897f
```

```{figure} img/status.png
:width: 70%
```

### Monitoring

Basic monitoring is provided to Flows deployed on Jina AI Cloud.

To access the [Grafana](https://grafana.com/)-powered dashboard, first get {ref}`the status of the Flow<jcloud-flow-status>`. The `Grafana Dashboard` link is displayed at the bottom of the pane. Visit the URL to find basic metrics like 'Number of Request Gateway Received' and 'Time elapsed between receiving a request and sending back the response':

```{figure} img/monitoring.png
:width: 80%
```

### List Flows

To list all of your "Starting", "Serving", "Failed", "Updating", and "Paused" Flows:

```bash
jc flows list
```

```{figure} img/list.png
:width: 90%
```

You can also filter your Flows by passing a phase:

```bash
jc flows list --phase Deleted
```


```{figure} img/list_deleted.png
:width: 90%
```

Or see all Flows:

```bash
jc flows list --phase all
```

```{figure} img/list_all.png
:width: 90%
```

### Remove Flows
You can remove a single Flow, multiple Flows or even all Flows by passing different identifiers.

To remove a single Flow:

```bash
jc flow remove merry-magpie-82b9c0897f
```

To remove multiple Flows:

```bash
jc flow remove merry-magpie-82b9c0897f wondrous-kiwi-b02db6a066
```

To remove all Flows:

```bash
jc flow remove all
```

By default, removing multiple or all Flows is an interactive process where you must give confirmation before each Flow is deleted. To make it non-interactive, set the below environment variable before running the command:

```bash
export JCLOUD_NO_INTERACTIVE=1
```

### Update a Flow
You can update a Flow by providing an updated YAML.

To update a Flow:

```bash
jc flow update super-mustang-c6cf06bc5b flow.yml
```

```{figure} img/update_flow.png
:width: 70%
```

### Pause / Resume Flow

You have the option to pause a Flow that is not currently in use but may be needed later. This will allow the Flow to be resumed later when it is needed again by using `resume`.

To pause a Flow:

```bash
jc flow pause super-mustang-c6cf06bc5b
```

```{figure} img/pause_flow.png
:width: 70%
```

To resume a Flow:

```bash
jc flow resume super-mustang-c6cf06bc5b
```

```{figure} img/resume_flow.png
:width: 70%
```

### Restart Flow, Executor or Gateway

If you need to restart a Flow, there are two options: restart all Executors and the Gateway associated with the Flow, or selectively restart only a specific Executor or the Gateway.

To restart a Flow:

```bash
jc flow restart super-mustang-c6cf06bc5b
```

```{figure} img/restart_flow.png
:width: 70%
```

To restart the Gateway:

```bash
jc flow restart super-mustang-c6cf06bc5b --gateway
```

```{figure} img/restart_gateway.png
:width: 70%
```

To restart an Executor:

```bash
jc flow restart super-mustang-c6cf06bc5b --executor executor0
```

```{figure} img/restart_executor.png
:width: 70%
```

### Recreate a Deleted Flow

To recreate a deleted Flow:

```bash
jc flow recreate profound-rooster-eec4b17c73
```

```{figure} img/recreate_flow.png
:width:  70%
```

### Scale an Executor
You can also manually scale any Executor.

```bash
jc flow scale good-martin-ca6bfdef84 --executor executor0 --replicas 2
```

```{figure} img/scale_executor.png
:width: 70%
```

### Normalize a Flow
To normalize a Flow:

```bash
jc flow normalize flow.yml
```

```{hint}
Normalizing a Flow is the process of building the Executor image and pushing the image to Hubble.
```

### Get Executor or Gateway logs

To get the Gateway logs:

```bash
jc flow logs --gateway central-escargot-354a796df5
```

```{figure} img/gateway_logs.png
:width: 70%
```

To get the Executor logs:

```bash
jc flow logs --executor executor0 central-escargot-354a796df5
```

```{figure} img/executor_logs.png
:width: 70%
```

## Secrets

### Create a Secret

To create a Secret for a Flow:

```bash
jc secret create mysecret rich-husky-af14064067 --from-literal "{'env-name': 'secret-value'}"
```

```{tip}
You can optionally pass the `--update` flag to automatically update the Flow spec with the updated secret information. This flag will update the Flow which is hosted on the cloud. Finally, you can also optionally pass a Flow's yaml file path with `--path` to update the yaml file locally.  Refer to [this](https://jina.ai/serve/cloud-nativeness/kubernetes/#deploy-flow-with-custom-environment-variables-and-secrets) section for more information.
```

```{caution}
If the `--update` flag is not passed then you have to manually update the flow with `jc update flow rich-husky-af14064067 updated-flow.yml`
```

### List Secrets

To list all the Secrets created in a Flow's namespace:

```bash
jc secret list rich-husky-af14064067
```

```{figure} img/list_secrets.png
:width: 90%
```

### Get a Secret

To retrieve a Secret's details:

```bash
jc secret get mysecret rich-husky-af14064067
```

```{figure} img/get_secret.png
:width: 90%
```

### Remove Secret

```bash
jc secret remove rich-husky-af14064067 mysecret
```

### Update a Secret
You can update a Secret for a Flow.

```bash
jc secret update rich-husky-af14064067 mysecret --from-literal "{'env-name': 'secret-value'}"
```

```{tip}
You can optionally pass the `--update` flag to automatically update the Flow spec with the updated secret information. This flag will update the Flow which is hosted on the cloud. Finally, you can also optionally pass a Flow's yaml file path with `--path` to update the yaml file locally. Refer to [this](https://jina.ai/serve/cloud-nativeness/kubernetes/#deploy-flow-with-custom-environment-variables-and-secrets) section for more information.
```

```{caution}
Updating a Secret automatically restarts a Flow.
```

## Jobs

### Create a Job

To create a Job for a Flow:

```bash
jc job create job-name rich-husky-af14064067 image 'job entrypoint' --timeout 600 --backofflimit 2
```

```{tip}
`image` can be any Executor image passed to a Flow's Executor `uses` or any normal docker image prefixed with `docker://`
```

### List Jobs

To listg all Jobs created in a Flow's namespace:

```bash
jc jobs list rich-husky-af14064067
```

```{figure} img/list_jobs.png
:width: 90%
```

### Get a Job

To retrieve a Job's details:

```bash
jc job get myjob1 rich-husky-af14064067
```

```{figure} img/get_job.png
:width: 90%
```

### Remove Job
```bash
jc job remove rich-husky-af14064067 myjob1
```


### Get Job Logs

To get the Job logs:

```bash
jc job logs myjob1 -f rich-husky-af14064067
```

```{figure} img/job_logs.png
:width: 90%
```

## Deployments

### Deploy

```{caution}
When `jcloud` deploys a deployment it automatically appends the following global arguments to the `deployment.yml`, if not present:
```

```yaml
jcloud:
  version: jina-version
  docarray: docarray-version
```

#### Single YAML file

A self-contained YAML file, consisting of all configuration information at the [Deployment](https://jina.ai/serve/concepts/orchestration/deployment/)-level and [Executor](https://jina.ai/serve/concepts/serving/executor/)-level.

> A Deployment's `uses` parameter must follow the format `jinaai+docker://<username>/MyExecutor` (from [Executor Hub](https://cloud.jina.ai)) to avoid any local file dependencies:

```yaml
# deployment.yml
jtype: Deployment
with:
  protocol: grpc
  uses: jinaai+docker://jina-ai/Sentencizer
```

To deploy:

```bash
jc deployment deploy ./deployment.yaml
```

The Deployment is successfully deployed when you see:

```{figure} img/deployment/deploy.png
:width: 70%
```
---

You will get a Deployment ID, for example `pretty-monster-130a5ac952`. This ID is required to manage, view logs, and remove the Deployment.

Since this Deployment is deployed with the default gRPC protocol (feel free to change it to `http`), you can use `jina.Client` to access it:

```python
from jina import Client, Document

print(
    Client(host='grpcs://executor-pretty-monster-130a5ac952.wolf.jina.ai').post(
        on='/', inputs=Document(text='hello')
    )
)
```

(jcloud-deployoment-status)=
### Get status

To get the status of a Deployment:
```bash
jc deployment status pretty-monster-130a5ac952
```

```{figure} img/deployment/status.png
:width: 70%
```

### List Deployments

To list all of your "Starting", "Serving", "Failed", "Updating", and "Paused" Deployments:

```bash
jc deployment list
```

```{figure} img/deployment/list.png
:width: 90%
```

You can also filter your Deployments by passing a phase:

```bash
jc deployment list --phase Deleted
```


```{figure} img/deployment/list_deleted.png
:width: 90%
```

Or see all Deployments:

```bash
jc deployment list --phase all
```

```{figure} img/deployment/list_all.png
:width: 90%
```

### Remove Deployments
You can remove a single Deployment, multiple Deployments, or even all Deployments by passing different commands to the `jc` executable at the command line.

To remove a single Deployment:

```bash
jc deployment remove pretty-monster-130a5ac952
```

To remove multiple Deployments:

```bash
jc deployment remove pretty-monster-130a5ac952 artistic-tuna-ab154c4dcc
```

To remove all Deployments:

```bash
jc deployment remove all
```

By default, removing all or multiple Deployments is an interactive process where you must give confirmation before each Deployment is deleted. To make it non-interactive, set the below environment variable before running the command:

```bash
export JCLOUD_NO_INTERACTIVE=1
```

### Update a Deployment
You can update a Deployment by providing an updated YAML.

To update a Deployment:

```bash
jc deployment update pretty-monster-130a5ac952 deployment.yml
```

```{figure} img/deployment/update.png
:width: 70%
```

### Pause / Resume Deployment

You have the option to pause a Deployment that is not currently in use but may be needed later. This will allow the Deployment to be resumed later when it is needed again by using `resume`.

To pause a Deployment:

```bash
jc deployment pause pretty-monster-130a5ac952
```

```{figure} img/deployment/pause.png
:width: 70%
```

To resume a Deployment:

```bash
jc eployment resume pretty-monster-130a5ac952
```

```{figure} img/deployment/resume.png
:width: 70%
```

### Restart Deployment

To restart a Deployment:

```bash
jc deployment restart pretty-monster-130a5ac952
```

```{figure} img/deployment/restart.png
:width: 70%
```

### Recreate a Deleted Deployment

To recreate a deleted Deployment:

```bash
jc deployment recreate pretty-monster-130a5ac952
```

```{figure} img/deployment/recreate.png
:width:  70%
```

### Scale a Deployment
You can also manually scale any Deployment.

```bash
jc deployment scale pretty-monster-130a5ac952 --replicas 2
```

```{figure} img/deployment/scale.png
:width: 70%
```

### Get Deployment logs

To get the Deployment logs:

```bash
jc deployment logs pretty-monster-130a5ac952
```

```{figure} img/deployment/logs.png
:width: 70%
```

## Configuration

Please refer to {ref}`Configuration <jcloud-configuration>` for configuring the Flow on Jina AI Cloud.

## Restrictions

Jina AI Cloud scales according to your needs. You can demand different instance types with GPU/memory/CPU predefined based on the needs of your Flows and Executors. If you have specific resource requirements, please contact us [on Discord](https://discord.jina.ai) or raise a [GitHub issue](https://github.com/jina-ai/jcloud/issues/new/choose).


```{admonition} Restrictions
  
- Deployments are only supported in the `us-east` region.
```
