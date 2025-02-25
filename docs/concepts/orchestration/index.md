(orchestration)=
# {fas}`network-wired` Orchestration

As seen in the {ref}`architecture overview <architecture-overview>`, Jina-serve is organized in different layers.

The Orchestration layer is composed of concepts that let you orchestrate, serve and scale your Executors with ease.

Two objects belong to this family:
- A single Executor ({class}`~Deployment`), ideal for serving a single model or microservice.
- A pipeline of Executors ({class}`~Flow`), ideal for more complex operations where Documents need to be processed in multiple ways.

Both Deployment and Flow share similar syntax and behavior. The main differences are:

- Deployments orchestrate a single Executor, while Flows orchestrate multiple Executors connected into a pipeline. 
- Flows have a {ref}`Gateway <gateway>`, while Deployments do not.

```{toctree}
:hidden:
deployment
flow
add-executors
scale-out
hot-reload
handle-exceptions
readiness
health-check
instrumentation
troubleshooting-on-multiprocess
yaml-spec
```
