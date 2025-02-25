(kubernetes)=
# Deploy on Kubernetes

This how-to will go through deploying a Deployment and a simple Flow using Kubernetes, customizing the Kubernetes configuration
to your needs, and scaling Executors using replicas and shards.

Deploying Jina-serve services in Kubernetes is the recommended way to use Jina-serve in production because Kubernetes can easily take over the lifetime management of Executors and Gateways.  

```{seelaso}
This page is a step by step guide, refer to the {ref}`Kubernetes support documentation <kubernetes-docs>` for more details
```


```{hint}
This guide is designed for users who want to **manually** deploy a Jina-serve project on Kubernetes.

Check out {ref}`jcloud` if you want a **one-click** solution to deploy and host Jina, leveraging a cloud-native stack of Kubernetes, Prometheus and Grafana, **without worrying about provisioning**.
```


## Preliminaries

To follow this how-to, you need access to a Kubernetes cluster.

You can either set up [`minikube`](https://minikube.sigs.k8s.io/docs/start/), or use one of many managed Kubernetes
solutions in the cloud:
- [Google Kubernetes Engine](https://cloud.google.com/kubernetes-engine)
- [Amazon EKS](https://aws.amazon.com/eks)
- [Azure Kubernetes Service](https://azure.microsoft.com/en-us/services/kubernetes-service)
- [Digital Ocean](https://www.digitalocean.com/products/kubernetes/)

You need to install Linkerd in your K8s cluster. To use Linkerd, [install the Linkerd CLI](https://linkerd.io/2.11/getting-started/) and [its control plane](https://linkerd.io/2.11/getting-started/) in your cluster.
This automatically sets up and manages the service mesh proxies when you deploy the Flow.

To understand why you need to install a service mesh like Linkerd refer to this  {ref}`section <service-mesh-k8s>`

(build-containerize-for-k8s)=
## Build and containerize your Executors

First, we need to build the Executors that we are going to use and containerize them {ref}`manually <dockerize-exec>` or by leveraging {ref}`Executor Hub <jina-hub>`. In this example,
we are going to use the Hub.

We are going to build two Executors, the first is going to use `CLIP` to encode textual Documents, and the second is going to use an in-memory vector index. This way 
we can build a simple neural search system.

First, we build the encoder Executor.

````{tab} executor.py
```{code-block} python
import torch
from typing import Optional
from transformers import CLIPModel, CLIPTokenizer
from docarray import DocList, BaseDoc
from docarray.typing import NdArray
from jina import Executor, requests


class MyDoc(BaseDoc):
    text: str
    embedding: Optional[NdArray] = None


class Encoder(Executor):
    def __init__(
            self, pretrained_model_name_or_path: str = 'openai/clip-vit-base-patch32', device: str = 'cpu', *args,**kwargs ):
        super().__init__(*args, **kwargs)
        self.device = device
        self.tokenizer = CLIPTokenizer.from_pretrained(pretrained_model_name_or_path)
        self.model = CLIPModel.from_pretrained(pretrained_model_name_or_path)
        self.model.eval().to(device)

    def _tokenize_texts(self, texts):
        x = self.tokenizer(
            texts,
            max_length=77,
            padding='longest',
            truncation=True,
            return_tensors='pt',
        )
        return {k: v.to(self.device) for k, v in x.items()}

    @requests
    def encode(self, docs: DocList[MyDoc], **kwargs) -> DocList[MyDoc]:
        with torch.inference_mode():
            input_tokens = self._tokenize_texts(docs.text)
            docs.embedding = self.model.get_text_features(**input_tokens).cpu().numpy()
        return docs

```
````
````{tab} requirements.txt
```
torch==1.12.0
transformers==4.16.2
```
````
````{tab} config.yml
```
jtype: Encoder
metas:
  name: EncoderPrivate
  py_modules:
    - executor.py
```
````

Putting all these files into a folder named CLIPEncoder and calling `jina hub push CLIPEncoder --private` should give:

```shell
╭────────────────────────── Published ───────────────────────────╮
│                                                                │
│   📛 Name           EncoderPrivate                         │
│   🔗 Jina Hub URL   https://cloud.jina.ai/executor/<executor-id>/   │
│   👀 Visibility     private                                    │
│                                                                │
╰────────────────────────────────────────────────────────────────╯
╭───────────────────────────────────────────────────── Usage ─────────────────────────────────────────────────────╮
│                                                                                                                 │
│   Container   YAML     uses: jinaai+docker://<user-id>/EncoderPrivate:latest           │
│               Python   .add(uses='jinaai+docker://<user-id>/EncoderPrivate:latest')    │
│                                                                                                                 │
│   Source      YAML     uses: jinaai://<user-id>/EncoderPrivate:latest                  │
│               Python   .add(uses='jinaai://<user-id>/EncoderPrivate:latest')           │
│                                                                                                                 │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

Then we can build an indexer to provide `index` and `search` endpoints:

````{tab} executor.py
```{code-block} python
from typing import Optional, List
from docarray import DocList, BaseDoc
from docarray.index import InMemoryExactNNIndex
from docarray.typing import NdArray
from jina import Executor, requests


class MyDoc(BaseDoc):
    text: str
    embedding: Optional[NdArray] = None


class MyDocWithMatches(MyDoc):
    matches: DocList[MyDoc] = []
    scores: List[float] = []


class Indexer(Executor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._indexer = InMemoryExactNNIndex[MyDoc]()

    @requests(on='/index')
    def index(self, docs: DocList[MyDoc], **kwargs) -> DocList[MyDoc]:
        self._indexer.index(docs)
        return docs

    @requests(on='/search')
    def search(self, docs: DocList[MyDoc], **kwargs) -> DocList[MyDocWithMatches]:
        res = DocList[MyDocWithMatches]()
        ret = self._indexer.find_batched(docs, search_field='embedding')
        matched_documents = ret.documents
        matched_scores = ret.scores
        for query, matches, scores in zip(docs, matched_documents, matched_scores):
            output_doc = MyDocWithMatches(**query.dict())
            output_doc.matches = matches
            output_doc.scores = scores.tolist()
            res.append(output_doc)
        return res

```
````
````{tab} config.yml
```
jtype: Indexer
metas:
  name: IndexerPrivate
  py_modules:
    - executor.py
```
````

Putting all these files into a folder named Indexer and calling `jina hub push Indexer --private` should give:

```shell
╭────────────────────────── Published ───────────────────────────╮
│                                                                │
│   📛 Name           IndexerPrivate                         │
│   🔗 Jina Hub URL   https://cloud.jina.ai/executor/<executor-id>/   │
│   👀 Visibility     private                                    │
│                                                                │
╰────────────────────────────────────────────────────────────────╯
╭───────────────────────────────────────────────────── Usage ─────────────────────────────────────────────────────╮
│                                                                                                                 │
│   Container   YAML     uses: jinaai+docker://<user-id>/IndexerPrivate:latest           │
│               Python   .add(uses='jinaai+docker://<user-id>/IndexerPrivate:latest')    │
│                                                                                                                 │                      │
│   Source      YAML     uses: jinaai://<user-id>/IndexerPrivate:latest                  │
│               Python   .add(uses='jinaai://<user-id>/IndexerPrivate:latest')           │
│                                                                                                                 │
╰─────────────────────────────────────────────────────────────────────────────────────────────────────────────────╯
```

Now, since we have created private Executors, we need to make sure that K8s has the right credentials to download
from the private registry:

First, we need to create the namespace where our Flow will run:

```shell
kubectl create namespace custom-namespace
```

Second, we execute this python script:

```python
import json
import os
import base64

JINA_CONFIG_JSON_PATH = os.path.join(os.path.expanduser('~'), os.path.join('.jina', 'config.json'))
CONFIG_JSON = 'config.json'

with open(JINA_CONFIG_JSON_PATH) as fp:
    auth_token = json.load(fp)['auth_token']

config_dict = dict()
config_dict['auths'] = dict()
config_dict['auths']['registry.hubble.jina.ai'] = {'auth': base64.b64encode(f'<token>:{auth_token}'.encode()).decode()}

with open(CONFIG_JSON, mode='w') as fp:
    json.dump(config_dict, fp)
```

Finally, we add a secret to be used as [imagePullSecrets](https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/) in the namespace from our config.json:

```shell script
kubectl -n custom-namespace create secret generic regcred --from-file=.dockerconfigjson=config.json --type=kubernetes.io/dockerconfigjson
```

## Deploy an embedding model inside a Deployment

Now we are ready to first deploy our embedding model as an embedding service in Kubernetes.

For now, define a Deployment,
either in {ref}`YAML <deployment-yaml-spec>` or directly in Python, as we do here:

```python
from jina import Deployment

d = Deployment(port=8080, name='encoder', uses='jinaai+docker://<user-id>/EncoderPrivate', image_pull_secrets=['regcred'])
```

You can serve any Deployment you want.
Just ensure that the Executor is containerized, either by using *'jinaai+docker'*, or by {ref}`containerizing your local
Executors <dockerize-exec>`.

Next, generate Kubernetes YAML configs from the Flow. Notice, that this step may be a little slow, because [Executor Hub](https://cloud.jina.ai/) may 
adapt the image to your Jina-serve and docarray version.

```python
d.to_kubernetes_yaml('./k8s_deployment', k8s_namespace='custom-namespace')
```

The following file structure will be generated - don't worry if it's slightly different -- there can be 
changes from one Jina-serve version to another:

```
.
└── k8s_deployment
    └── encoder.yml
```

You can inspect these files to see how Deployment and Executor concepts are mapped to Kubernetes entities.
And as always, feel free to modify these files as you see fit for your use case.

````{admonition} Caution: Executor YAML configurations
:class: caution

As a general rule, the configuration files produced by `to_kubernetes_yaml()` should run out of the box, and if you strictly
follow this how-to they will.

However, there is an exception to this: If you use a local dockerized Executor, and this Executors configuration is stored
in a file other than `config.yaml`, you will have to adapt this Executor's Kubernetes YAML.
To do this, open the file and replace `config.yaml` with the actual path to the Executor configuration.

This is because when a Flow contains a Docker image, it can't see what Executor
configuration was used to create that image.
Since all of our tutorials use `config.yaml` for that purpose, the Flow uses this as a best guess.
Please adapt this if you named your Executor configuration file differently.
````

Next you can actually apply these configuration files to your cluster, using `kubectl`.
This launches the Deployment service.

Now, deploy this Deployment to your cluster:
```shell
kubectl apply -R -f ./k8s_deployment
```

Check that the Pods were created:
```shell
kubectl get pods -n custom-namespace
```

```text
NAME                              READY   STATUS    RESTARTS   AGE
encoder-81a5b3cf9-ls2m3           1/1     Running   0          60m
```

Once you see that the Deployment ready, you can start embedding documents:

```python
from typing import Optional
import portforward
from docarray import DocList, BaseDoc
from docarray.typing import NdArray

from jina.clients import Client


class MyDoc(BaseDoc):
    text: str
    embedding: Optional[NdArray] = None


with portforward.forward('custom-namespace', 'encoder-81a5b3cf9-ls2m3', 8080, 8080):
    client = Client(host='localhost', port=8080)
    client.show_progress = True
    docs = client.post(
        '/encode',
        inputs=DocList[MyDoc]([MyDoc(text=f'This is document indexed number {i}') for i in range(100)]),
        return_type=DocList[MyDoc],
        request_size=10
    )

    for doc in docs:
        print(f'{doc.text}: {doc.embedding}')

```

## Deploy a simple Flow

Now we are ready to build a Flow composed of multiple Executors.

By *simple* in this context we mean a Flow without replicated or sharded Executors - you can see how to use those in
Kubernetes {ref}`later on <kubernetes-replicas>`.

For now, define a Flow,
either in {ref}`YAML <flow-yaml-spec>` or directly in Python, as we do here:

```python
from jina import Flow

f = (
    Flow(port=8080, image_pull_secrets=['regcred'])
    .add(name='encoder', uses='jinaai+docker://<user-id>/EncoderPrivate')
    .add(
        name='indexer',
        uses='jinaai+docker://<user-id>/IndexerPrivate',
    )
)
```

You can essentially define any Flow of your liking.
Just ensure that all Executors are containerized, either by using *'jinaai+docker'*, or by {ref}`containerizing your local
Executors <dockerize-exec>`.

The example Flow here simply encodes and indexes text data using two Executors pushed to the [Executor Hub](https://cloud.jina.ai/).
 
Next, generate Kubernetes YAML configs from the Flow. Notice, that this step may be a little slow, because [Executor Hub](https://cloud.jina.ai/) may 
adapt the image to your Jina-serve and docarray version.

```python
f.to_kubernetes_yaml('./k8s_flow', k8s_namespace='custom-namespace')
```

The following file structure will be generated - don't worry if it's slightly different -- there can be 
changes from one Jina-serve version to another:

```
.
└── k8s_flow
    ├── gateway
    │   └── gateway.yml
    └── encoder
    │   └── encoder.yml
    └── indexer
        └── indexer.yml
```

You can inspect these files to see how Flow concepts are mapped to Kubernetes entities.
And as always, feel free to modify these files as you see fit for your use case.

Next you can actually apply these configuration files to your cluster, using `kubectl`.
This launches all Flow microservices.

Now, deploy this Flow to your cluster:
```shell
kubectl apply -R -f ./k8s_flow
```

Check that the Pods were created:
```shell
kubectl get pods -n custom-namespace
```

```text
NAME                              READY   STATUS    RESTARTS   AGE
encoder-8b5575cb9-bh2x8           1/1     Running   0          60m
gateway-66d5f45ff5-4q7sw          1/1     Running   0          60m
indexer-8f676fc9d-4fh52           1/1     Running   0          60m
```

Note that the Jina gateway was deployed with name `gateway-7df8765bd9-xf5tf`.

Once you see that all the Deployments in the Flow are ready, you can start indexing documents:

```python
from typing import List, Optional
import portforward
from docarray import DocList, BaseDoc
from docarray.typing import NdArray

from jina.clients import Client


class MyDoc(BaseDoc):
    text: str
    embedding: Optional[NdArray] = None


class MyDocWithMatches(MyDoc):
    matches: DocList[MyDoc] = []
    scores: List[float] = []


with portforward.forward('custom-namespace', 'gateway-66d5f45ff5-4q7sw', 8080, 8080):
    client = Client(host='localhost', port=8080)
    client.show_progress = True
    docs = client.post(
        '/index',
        inputs=DocList[MyDoc]([MyDoc(text=f'This is document indexed number {i}') for i in range(100)]),
        return_type=DocList[MyDoc],
        request_size=10
    )

    print(f'Indexed documents: {len(docs)}')
    docs = client.post(
        '/search',
        inputs=DocList[MyDoc]([MyDoc(text=f'This is document query number {i}') for i in range(10)]),
        return_type=DocList[MyDocWithMatches],
        request_size=10
    )
    for doc in docs:
        print(f'Query {doc.text} has {len(doc.matches)} matches')

```

### Deploy with shards and replicas

After your service mesh is installed, your cluster is ready to run a Flow with scaled Executors.
You can adapt the Flow from above to work with two replicas for the encoder, and two shards for the indexer:

```python
from jina import Flow

f = (
    Flow(port=8080, image_pull_secrets=['regcred'])
    .add(name='encoder', uses='jinaai+docker://<user-id>/CLIPEncoderPrivate', replicas=2)
    .add(
        name='indexer',
        uses='jinaai+docker://<user-id>/IndexerPrivate',
        shards=2,
    )
)
```

Again, you can generate your Kubernetes configuration:

```python
f.to_kubernetes_yaml('./k8s_flow', k8s_namespace='custom-namespace')
```

Now you should see the following file structure:

```
.
└── k8s_flow
    ├── gateway
    │   └── gateway.yml
    └── encoder
    │   └─ encoder.yml
    └── indexer
        ├── indexer-0.yml
        ├── indexer-1.yml
        └── indexer-head.yml
```

Apply your configuration like usual:

````{admonition} Hint: Cluster cleanup
:class: hint
If you already have the simple Flow from the first example running on your cluster, make sure to delete it using `kubectl delete -R -f ./k8s_flow`.
````

```shell
kubectl apply -R -f ./k8s_flow
```

### Deploy with custom environment variables and secrets

You can customize the environment variables that are available inside runtime, either defined directly or read from a [Kubernetes secret](https://kubernetes.io/docs/concepts/configuration/secret/):

````{tab} with Python
```python
from jina import Flow

f = (
    Flow(port=8080, image_pull_secrets=['regcred'])
    .add(
        name='indexer',
        uses='jinaai+docker://<user-id>/IndexerPrivate',
        env={'k1': 'v1', 'k2': 'v2'},
        env_from_secret={
            'SECRET_USERNAME': {'name': 'mysecret', 'key': 'username'},
            'SECRET_PASSWORD': {'name': 'mysecret', 'key': 'password'},
        },
    )
)

f.to_kubernetes_yaml('./k8s_flow', k8s_namespace='custom-namespace')
```
````
````{tab} with flow YAML
In a `flow.yml` file :
```yaml
jtype: Flow
version: '1'
with:
  protocol: http
executors:
- name: indexer
  uses: jinaai+docker://<user-id>/IndexerPrivate
  env:
    k1: v1
    k2: v2
  env_from_secret:
    SECRET_USERNAME:
      name: mysecret
      key: username
    SECRET_PASSWORD:
      name: mysecret
      key: password
```

You can generate Kubernetes YAML configs using `jina export`:
```shell
jina export kubernetes flow.yml ./k8s_flow --k8s-namespace custom-namespace
```
````

After creating the namespace, you need to create the secrets mentioned above:

```shell
kubectl -n custom-namespace create secret generic mysecret --from-literal=username=jina --from-literal=password=123456
```

Then you can apply your configuration.


(kubernetes-expose)=
## Exposing the service
The previous examples use port-forwarding to send documents to the services. 
In real world applications, 
you may want to expose your service to make it reachable by users so that you can serve search requests.

```{caution}
Exposing the Deployment or Flow only works if the environment of your `Kubernetes cluster` supports `External Loadbalancers`.
```

Once the service is deployed, you can expose a service. In this case we give an example of exposing the encoder when using a Deployment,
but you can expose the gateway service when using a Flow:
```bash
kubectl expose deployment executor --name=executor-exposed --type LoadBalancer --port 80 --target-port 8080 -n custom-namespace
sleep 60 # wait until the external ip is configured
```

Export the external IP address. This is needed for the client when sending Documents to the Flow in the next section. 
```bash
export EXTERNAL_IP=`kubectl get service executor-expose -n custom-namespace -o=jsonpath='{.status.loadBalancer.ingress[0].ip}'`
```

### Client
The client:

- Sends Documents to the exposed service on `$EXTERNAL_IP` 
- Gets the responses.

You should configure your Client to connect to the service via the external IP address as follows:

```python
import os
from typing import List, Optional
from docarray import DocList, BaseDoc
from docarray.typing import NdArray

from jina.clients import Client


class MyDoc(BaseDoc):
    text: str
    embedding: Optional[NdArray] = None


class MyDocWithMatches(MyDoc):
    matches: DocList[MyDoc] = []
    scores: List[float] = []

host = os.environ['EXTERNAL_IP']
port = 80

client = Client(host=host, port=port)

client.show_progress = True
docs = DocList[MyDoc]([MyDoc(text=f'This is document indexed number {i}') for i in range(100)])
queried_docs = client.post("/search", inputs=docs, return_type=DocList[MyDocWithMatches])

matches = queried_docs[0].matches
print(f"Matched documents: {len(matches)}")
```

## Update your Executor in Kubernetes

In Kubernetes, you can update your Executors by patching the Deployment corresponding to your Executor.

For instance, in the example above, you can change the CLIPEncoderPrivate's `pretrained_model_name_or_path` parameter by changing the content of the Deployment inside the `executor.yml` dumped by `.to_kubernetes_yaml`.

You need to add `--uses_with` and pass the batch size argument to it. This is passed to the container inside the Deployment:

```yaml
    spec:
      containers:
      - args:
        - executor
        - --name
        - encoder
        - --k8s-namespace
        - custom-namespace
        - --uses
        - config.yml
        - --port
        - '8080'
        - --uses-metas
        - '{}'
        - --uses-with
        - '{"pretrained_model_name_or_path": "other_model"}'
        - --native
        command:
        - jina
```

After doing so, re-apply your configuration so the new Executor will be deployed without affecting the other unchanged Deployments:

```shell script
kubectl apply -R -f ./k8s_deployment
```

````{admonition} Other patching options
:class: seealso

In Kubernetes Executors are ordinary Kubernetes Deployments, so you can use other patching options provided by Kubernetes:


- `kubectl replace` to replace an Executor using a complete configuration file
- `kubectl patch` to patch an Executor using only a partial configuration file
- `kubectl edit` to edit an Executor configuration on the fly in your editor

You can find more information about these commands in the [official Kubernetes documentation](https://kubernetes.io/docs/concepts/cluster-administration/manage-deployment/).
````

## Key takeaways

In short, there are just three key steps to deploy Jina on Kubernetes:

1. Use `.to_kubernetes_yaml()` to generate Kubernetes configuration files from a Jina Deployment or Flow object.
2. Apply the generated file via `kubectl`(Modify the generated files if necessary)
3. Expose your service outside the K8s cluster

## See also
- {ref}`Kubernetes support documentation <kubernetes-docs>`
- {ref}`Monitor service once it is deployed <monitoring>`
- {ref}`See how failures and retries are handled <flow-error-handling>`
- {ref}`Learn more about scaling Executors <scale-out>`
