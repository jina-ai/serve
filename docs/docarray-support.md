(docarray-support)=
# DocArray support

Jina-serve depends heavily on DocArray to provide the data that is processed inside Jina-serve Executors and sent by our Clients.
Recently, DocArray was heavily refactored for version 0.30. 

Starting from that version, DocArray usage  has changed drastically, however Jina-serve can work seamlessly and automatically with any of the versions of Jina-serve.
Jina-serve will automatically detect the docarray version installed and use the corresponding methods and APIs. However, developers
must take into account that some APIs and usages have changed, especially when it comes to developing Executors.

The new version makes the dataclass feature of DocArray<0.30 a first-class citizen and for this 
purpose it is built on top of [Pydantic](https://pydantic-docs.helpmanual.io/). An important shift is that 
the new DocArray adapts to users' data, whereas DocArray<0.30 forces user to adapt to the Document schema. 


## Document schema

At the heart of DocArray>=0.30 is a new schema that is more flexible and expressive than the original DocArray schema.

You can refer to the [DocArray README](https://github.com/docarray/docarray) for more details. 
Please note that also the names of data structure change in the new version of DocArray.

TODO: ADD snippets for both versions

On the Jina-serve side, this flexibility extends to every Executor, where you can now customize input and output schemas:

- With DocArray<0.30 a Document has a fixed schema in the input and the output
- With DocArray>=0.30 (the version currently used by default in Jina-serve), an Executor defines its own input and output schemas. 
It also provides several predefined schemas that you can use out of the box.

## Executor API

To reflect the change with DocArray >=0.30, the Executor API supports schema definition. The 
design is inspired by [FastAPI](https://fastapi.tiangolo.com/).

The main difference, is that for `docarray<0.30` there is only a single [Document](https://docarray.org/legacy-docs/fundamentals/document/) with a fixed schema.
However, with `docarray>=0.30` user needs to define their own `Document` by subclassing from [BaseDoc](https://docs.docarray.org/user_guide/representing/first_step/) or taking any of the [predefined Document types](https://docs.docarray.org/data_types/first_steps/) provided.


````{tab} docarray>=0.30
```{code-block} python
from jina import Executor, requests
from docarray import DocList, BaseDoc
from docarray.documents import ImageDoc
from docarray.typing import AnyTensor

import numpy as np

class InputDoc(BaseDoc):
    img: ImageDoc

class OutputDoc(BaseDoc):
    embedding: AnyTensor

class MyExec(Executor):
    @requests(on='/bar')
    def bar(
        self, docs: DocList[InputDoc], **kwargs
    ) -> DocList[OutputDoc]:
        docs_return = DocList[OutputDoc](
            [OutputDoc(embedding=np.zeros((100, 1))) for _ in range(len(docs))]
        )
        return docs_return
```
````
````{tab} docarray<0.30
```{code-block} python
from jina import Executor, requests
from docarray import Document, DocumentArray

import numpy as np


class MyExec(Executor):
    @requests(on='/bar')
    def bar(
        self, docs: DocumentArray, **kwargs
    ):
        docs_return = DocumentArray(
            [Document(embedding=np.zeros((100, 1))) for _ in range(len(docs))]
        )
        return docs_return
```
````

To ease with the transition from the old to the new `docarray` versions, there is the [`LegacyDocument`](https://docs.docarray.org/API_reference/documents/documents/#docarray.documents.legacy.LegacyDocument) which is a predefined Document that aims to provide
the same data type as the original `Document` in `docarray<0.30`.


## Client API

In the client, the big change is that when using `docarray>=0.30`. you specify the schema that you expect the Deployment or Flow to return. You can pass the return type by using the `return_type` parameter in the `client.post` method:

````{tab} docarray>=0.30
```{code-block} python
from jina import Client
from docarray import DocList, BaseDoc
from docarray.documents import ImageDoc
from docarray.typing import AnyTensor

class InputDoc(BaseDoc):
    img: ImageDoc

class OutputDoc(BaseDoc):
    embedding: AnyTensor

c = Client(host='')
c.post('/', DocList[InputDoc]([InputDoc(img=ImageDoc()) for _ in range(10)]), return_type=DocList[OutputDoc])
```
````
````{tab} docarray<0.30
```{code-block} python
from jina import Client
from docarray import DocumentArray, Document

c = Client(host='')
c.post('/', DocumentArray([Document() for _ in range(10)]))
```
````

## See also

- [DocArray>=0.30](https://docs.docarray.org/) docs
- [DocArray<0.30](https://docarray.org/legacy-docs/) docs
- [Pydantic](https://pydantic-docs.helpmanual.io/) documentation for more details on the schema definition

