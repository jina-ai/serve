from __future__ import annotations
import os
from docarray import BaseDoc
from docarray import DocList

from pydantic import Field
from typing import Any, Dict, Optional, List, Union

from docarray.typing import ID, AnyEmbedding, AnyTensor
docarray_v2 = True


class LegacyDocumentJina(BaseDoc):
    """
    This Document is the LegacyDocumentJina. It follows the same schema as in DocArray <=0.21.
    It can be useful to start migrating a codebase from v1 to v2.

    Nevertheless, the API is not totally compatible with DocArray <=0.21 `Document`.
    Indeed, none of the method associated with `Document` are present. Only the schema
    of the data is similar.

    ```python
    from docarray import DocList
    from docarray.documents.legacy import LegacyDocument
    import numpy as np

    doc = LegacyDocument(text='hello')
    doc.url = 'http://myimg.png'
    doc.tensor = np.zeros((3, 224, 224))
    doc.embedding = np.zeros((100, 1))

    doc.tags['price'] = 10

    doc.chunks = DocList[Document]([Document() for _ in range(10)])

    doc.chunks = DocList[Document]([Document() for _ in range(10)])
    ```

    """
    id: Optional[ID] = Field(
        description='The ID of the BaseDoc. This is useful for indexing in vector stores. If not set by user, it will automatically be assigned a random value',
        default_factory=lambda: ID(os.urandom(16).hex()),
    )

    tensor: Optional[AnyTensor] = None
    chunks: Optional[Union[DocList[LegacyDocumentJina], List[LegacyDocumentJina]]] = None
    matches: Optional[Union[DocList[LegacyDocumentJina], List[LegacyDocumentJina]]] = None
    blob: Optional[bytes] = None
    text: Optional[str] = None
    url: Optional[str] = None
    embedding: Optional[AnyEmbedding] = None
    tags: Dict[str, Any] = dict()
    scores: Optional[Dict[str, Any]] = None
