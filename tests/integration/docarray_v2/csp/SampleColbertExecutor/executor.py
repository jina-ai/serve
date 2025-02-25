import numpy as np
from docarray import BaseDoc, DocList
from docarray.typing import NdArray
from pydantic import Field
from typing import Union, Optional, List
from jina import Executor, requests


class TextDoc(BaseDoc):
    text: str = Field(description="The text of the document", default="")


class RerankerInput(BaseDoc):
    query: Union[str, TextDoc]

    documents: List[TextDoc]

    top_n: Optional[int]


class RankedObjectOutput(BaseDoc):
    index: int
    document: Optional[TextDoc]

    relevance_score: float


class EmbeddingResponseModel(TextDoc):
    embeddings: NdArray


class RankedOutput(BaseDoc):
    results: DocList[RankedObjectOutput]


class SampleColbertExecutor(Executor):
    @requests(on="/rank")
    def foo(self, docs: DocList[RerankerInput], **kwargs) -> DocList[RankedOutput]:
        ret = []
        for doc in docs:
            ret.append(
                RankedOutput(
                    results=[
                        RankedObjectOutput(
                            id=doc.id,
                            index=0,
                            document=TextDoc(text="first result"),
                            relevance_score=-1,
                        ),
                        RankedObjectOutput(
                            id=doc.id,
                            index=1,
                            document=TextDoc(text="second result"),
                            relevance_score=-2,
                        ),
                    ]
                )
            )
        return DocList[RankedOutput](ret)

    @requests(on="/encode")
    def bar(self, docs: DocList[TextDoc], **kwargs) -> DocList[EmbeddingResponseModel]:
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
