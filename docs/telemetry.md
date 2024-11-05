# {fas}`tower-cell` Telemetry

```{warning}
To opt out from telemetry, set the `JINA_OPTOUT_TELEMETRY=1` as an environment variable.
```

Telemetry is the process of collecting data about the usage of a system. This data can be used to improve the system by understanding how it is being used and what areas need improvement.

Jina AI uses telemetry to collect data about how Jina-serve is being used. This data is then used to improve the software. For example, if we see that a lot of users are having trouble with a certain feature, we can improve that feature to make it easier to use.

Telemetry is important for Jina-serve because it allows the team to understand how the software is being used and what areas need improvement. Without telemetry, Jina-serve would not be able to improve as quickly or as effectively.

The data collected include:

- Jina-serve and its dependencies versions;
- A hashed unique user identifier;
- A hashed unique session identifier;
- Boolean events: start of a Flow, Gateway, Runtime, Client.


## Example payload

Here is an example payload when running the following code:

```python
from jina import Flow

with Flow().add() as f:
    pass
```

```python
{
    'architecture': 'x86_64',
    'ci-vendor': '(unset)',
    'docarray': '0.15.2',
    'event': 'WorkerRuntime.start',
    'grpcio': '1.46.3',
    'jina': '3.7.13',
    'jina-proto': '0.1.13',
    'platform': 'Darwin',
    'platform-release': '21.6.0',
    'platform-version': 'Darwin Kernel Version 21.6.0: Sat Jun 18 17:07:28 PDT '
    '2022; root:xnu-8020.140.41~1/RELEASE_ARM64_T8110',
    'processor': 'i386',
    'proto-backend': 'cpp',
    'protobuf': '3.20.1',
    'python': '3.7.9',
    'pyyaml': '6.0',
    'session-id': 'da9d4ade-2171-11ed-8713-56286d1a91c2',
    'uid': 94731629138370,
    'uptime': '2022-08-21T18:53:59.681842',
}
{
    'architecture': 'x86_64',
    'ci-vendor': '(unset)',
    'docarray': '0.15.2',
    'event': 'GRPCGatewayRuntime.start',
    'grpcio': '1.46.3',
    'jina': '3.7.13',
    'jina-proto': '0.1.13',
    'platform': 'Darwin',
    'platform-release': '21.6.0',
    'platform-version': 'Darwin Kernel Version 21.6.0: Sat Jun 18 17:07:28 PDT '
    '2022; root:xnu-8020.140.41~1/RELEASE_ARM64_T8110',
    'processor': 'i386',
    'proto-backend': 'cpp',
    'protobuf': '3.20.1',
    'python': '3.7.9',
    'pyyaml': '6.0',
    'session-id': 'da9fc390-2171-11ed-8713-56286d1a91c2',
    'uid': 94731629138370,
    'uptime': '2022-08-21T18:53:59.681842',
}
{
    'architecture': 'x86_64',
    'ci-vendor': '(unset)',
    'docarray': '0.15.2',
    'event': 'BaseExecutor.start',
    'grpcio': '1.46.3',
    'jina': '3.7.13',
    'jina-proto': '0.1.13',
    'platform': 'Darwin',
    'platform-release': '21.6.0',
    'platform-version': 'Darwin Kernel Version 21.6.0: Sat Jun 18 17:07:28 PDT '
    '2022; root:xnu-8020.140.41~1/RELEASE_ARM64_T8110',
    'processor': 'i386',
    'proto-backend': 'cpp',
    'protobuf': '3.20.1',
    'python': '3.7.9',
    'pyyaml': '6.0',
    'session-id': 'daa02f1a-2171-11ed-8713-56286d1a91c2',
    'uid': 94731629138370,
    'uptime': '2022-08-21T18:53:59.681842',
}
{
    'architecture': 'x86_64',
    'ci-vendor': '(unset)',
    'docarray': '0.15.2',
    'event': 'Flow.start',
    'grpcio': '1.46.3',
    'jina': '3.7.13',
    'jina-proto': '0.1.13',
    'platform': 'Darwin',
    'platform-release': '21.6.0',
    'platform-version': 'Darwin Kernel Version 21.6.0: Sat Jun 18 17:07:28 PDT '
    '2022; root:xnu-8020.140.41~1/RELEASE_ARM64_T8110',
    'processor': 'i386',
    'proto-backend': 'cpp',
    'protobuf': '3.20.1',
    'python': '3.7.9',
    'pyyaml': '6.0',
    'session-id': 'db4c0092-2171-11ed-8713-56286d1a91c2',
    'uid': 94731629138370,
    'uptime': '2022-08-21T18:53:59.681842',
}
```
