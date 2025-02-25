import numpy as np
from docarray import BaseDoc, DocList
from docarray.typing import NdArray
from pydantic import Field, BaseModel

from jina import Executor, requests


class TextDoc(BaseDoc):
    text: str = Field(description="The text of the document", default="")


class EmbeddingResponseModel(TextDoc):
    embeddings: NdArray = Field(description="The embedding of the texts", default=[])

    class Config(BaseDoc.Config):
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {NdArray: lambda v: v.tolist()}


class Parameters(BaseModel):
    emb_dim: int



class SampleExecutor(Executor):
    @requests(on="/encode")
    def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[EmbeddingResponseModel]:
        ret = []
        for doc in docs:
            ret.append(
                EmbeddingResponseModel(
                    id=doc.id,
                    text=doc.text,
                    embeddings=np.random.random((1, 64)),
                )
            )
        return DocList[EmbeddingResponseModel](ret)

    @requests(on="/encode_parameter")
    def bar(self, docs: DocList[TextDoc], parameters: Parameters, **kwargs) -> DocList[EmbeddingResponseModel]:
        ret = []
        for doc in docs:
            ret.append(
                EmbeddingResponseModel(
                    id=doc.id,
                    text=doc.text,
                    embeddings=np.random.random((1, parameters.emb_dim)),
                )
            )
        return DocList[EmbeddingResponseModel](ret)
