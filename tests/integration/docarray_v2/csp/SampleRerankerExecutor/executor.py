from docarray import BaseDoc, DocList
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


class RankedOutput(BaseDoc):
    results: DocList[RankedObjectOutput]


class SampleRerankerExecutor(Executor):
    @requests(on="/rerank")
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
