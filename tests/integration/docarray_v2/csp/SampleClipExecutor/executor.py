from typing import Optional, List

import numpy as np
from docarray import BaseDoc, DocList
from docarray.typing import NdArray
from docarray.typing.bytes import ImageBytes
from docarray.typing.url import AnyUrl
from jina import Executor, requests
from pydantic import Field


class TextAndImageDoc(BaseDoc):
    text: Optional[str] = None
    url: Optional[AnyUrl] = None
    bytes: Optional[ImageBytes] = None
    num_tokens: Optional[int] = None
    input_ids: Optional[List[int]] = None


class EmbeddingResponseModel(TextAndImageDoc):
    embeddings: NdArray = Field(description="The embedding of the texts", default=[])

    class Config(BaseDoc.Config):
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {NdArray: lambda v: v.tolist()}


class SampleClipExecutor(Executor):
    @requests(on="/encode")
    def foo(
        self, docs: DocList[TextAndImageDoc], **kwargs
    ) -> DocList[EmbeddingResponseModel]:
        ret = []
        for doc in docs:
            ret.append(
                EmbeddingResponseModel(
                    id=doc.id,
                    text=doc.text,
                    url=doc.url,
                    bytes=doc.bytes,
                    embeddings=np.random.random((1, 64)),
                )
            )
        return DocList[EmbeddingResponseModel](ret)
