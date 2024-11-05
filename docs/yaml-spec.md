(yaml-spec)=
# {octicon}`file-code` YAML Specification

YAML is widely used in Jina-serve to define an Executor, Flow. This page helps you quickly navigate different YAML specifications.

## Executor-level YAML

Executor level YAML is placed inside the Executor directory, as a part of Executor file structure.

:::::{grid} 2
:gutter: 3


::::{grid-item-card} Executor YAML
:link: concepts/serving/executor/yaml-spec
:link-type: doc

Define the argument of `__init__`, Python module dependencies and other settings of an Executor. 
::::


:::::

## Flow-level YAML

Flow level YAML is placed inside the Flow directory, as a part of Flow file structure. It defines the Executors that will be used in the Flow, the Gateway and the JCloud hosting specifications.


:::::{grid} 2
:gutter: 3

::::{grid-item-card} Flow YAML
:link: concepts/orchestration/flow/yaml-spec
:link-type: doc

Define the Executors, the topology and the Gateway settings of a Flow.
::::

::::{grid-item-card} Gateway YAML
:link: concepts/serving/gateway/yaml-spec
:link-type: doc

Define the protocol, TLS, authentication and other settings of a Gateway.
+++
Gateway specification is nested under the Flow YAML via `with:` keywords.
::::

::::{grid-item-card} JCloud YAML
:link: concepts/jcloud/yaml-spec
:link-type: doc

Define the resources and autoscaling settings on Jina-serve Cloud

+++
JCloud specification is nested under the Flow YAML via `jcloud:` keywords.

::::

:::::
