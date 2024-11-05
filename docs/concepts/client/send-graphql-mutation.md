# Send GraphQL Mutation

If the Flow is configured with GraphQL endpoint, then you can use Jina-serve {class}`~jina.Client` {meth}`~jina.clients.mixin.MutateMixin.mutate` to fetch data via GraphQL mutations:

````{admonition} Only available for docarray<0.30
:class: note

This feature is only available when using `docarray<0.30`.
````

```python
from jina import Client

PORT = ...
c = Client(port=PORT)
mut = '''
        mutation {
            docs(data: {text: "abcd"}) { 
                id
                matches {
                    embedding
                }
            } 
        }
    '''
response = c.mutate(mutation=mut)
```

Note that `response` here is `Dict` not a `DocumentArray`. This is because GraphQL allows the user to specify only certain fields that they want to have returned, so the output might not be a valid DocumentArray, it can be only a string.


## Mutations and arguments

The Flow GraphQL API exposes the mutation `docs`, which sends its inputs to the Flow's Executors,
just like HTTP `post` as described {ref}`above <http-interface>`.

A GraphQL mutation takes the same set of arguments used in {ref}`HTTP <http-arguments>`. 

The response from GraphQL can include all fields available on a DocumentArray.

````{admonition} See Also
:class: seealso

For more details on the GraphQL format of Document and DocumentArray, see the [documentation page](https://docarray.jina.ai/advanced/graphql-support/)
or [developer reference](https://docarray.jina.ai/api/docarray.document.mixins.strawberry/).
````


## Fields

The available fields in the GraphQL API are defined by the [Document Strawberry type](https://docarray.jina.ai/advanced/graphql-support/?highlight=graphql).

Essentially, you can ask for any property of a Document, including `embedding`, `text`, `tensor`, `id`, `matches`, `tags`,
and more.

