from typing import Dict, List, Optional

import aiohttp
import pytest
from docarray import BaseDoc, DocList
from pydantic import Field

from jina import Client, Deployment, Executor, Flow, requests
from jina.clients.base.helper import HTTPClientlet


class Nested2Doc(BaseDoc):
    value: str


class Nested1Doc(BaseDoc):
    nested: Nested2Doc


class RootDoc(BaseDoc):
    nested: Optional[Nested1Doc] = None
    num: Optional[int] = None
    text: str


class OptionalNested1Doc(BaseDoc):
    nested: Optional[Nested2Doc] = None


class RootDocWithNestedList(BaseDoc):
    nested: Optional[List[Nested1Doc]] = None
    num: Optional[int] = None
    text: str


class NestedSchemaExecutor(Executor):
    @requests(on='/endpoint')
    async def endpoint(self, docs: DocList[RootDoc], **kwargs) -> DocList[RootDoc]:
        rets = DocList[RootDoc]()
        rets.append(
            RootDoc(
                text='hello world', nested=Nested1Doc(nested=Nested2Doc(value='test'))
            )
        )
        return rets


class ListNestedSchemaExecutor(Executor):
    @requests(on='/endpoint')
    async def endpoint(
        self, docs: DocList[RootDocWithNestedList], **kwargs
    ) -> DocList[RootDocWithNestedList]:
        rets = DocList[RootDocWithNestedList]()
        rets.append(
            RootDocWithNestedList(
                text='hello world', nested=[Nested1Doc(nested=Nested2Doc(value='test'))]
            )
        )
        return rets


def test_issue_6019():
    flow = Flow().add(name='inference', needs='gateway', uses=NestedSchemaExecutor)
    with flow:
        res = flow.post(
            on='/endpoint', inputs=RootDoc(text='hello'), return_type=DocList[RootDoc]
        )
        assert res[0].text == 'hello world'
        assert res[0].nested.nested.value == 'test'


def test_issue_6019_with_nested_list():
    flow = Flow().add(name='inference', needs='gateway', uses=ListNestedSchemaExecutor)
    with flow:
        res = flow.post(
            on='/endpoint',
            inputs=RootDocWithNestedList(text='hello'),
            return_type=DocList[RootDocWithNestedList],
        )
        assert res[0].text == 'hello world'
        assert res[0].nested[0].nested.value == 'test'


def test_issue_6084():
    class EnvInfo(BaseDoc):
        history: str = ''

    class A(BaseDoc):
        b: EnvInfo

    class MyIssue6084Exec(Executor):
        @requests
        def foo(self, docs: DocList[A], **kwargs) -> DocList[A]:
            pass

    f = Flow().add(uses=MyIssue6084Exec).add(uses=MyIssue6084Exec)
    with f:
        pass


class NestedFieldSchema(BaseDoc):
    name: str = "test_name"
    dict_field: Dict = Field(default_factory=dict)


class InputWithComplexFields(BaseDoc):
    text: str = "test"
    nested_field: NestedFieldSchema = Field(default_factory=NestedFieldSchema)
    dict_field: Dict = Field(default_factory=dict)
    bool_field: bool = False


class SimpleInput(BaseDoc):
    text: str = "test"


class MyExecutor(Executor):
    @requests(on="/stream")
    async def stream(
        self,
        doc: InputWithComplexFields,
        parameters: Optional[Dict] = None,
        **kwargs,
    ) -> InputWithComplexFields:
        for i in range(4):
            yield InputWithComplexFields(text=f"hello world {doc.text} {i}")

    @requests(on="/stream-simple")
    async def stream_simple(
        self,
        doc: SimpleInput,
        parameters: Optional[Dict] = None,
        **kwargs,
    ) -> SimpleInput:
        for i in range(4):
            yield SimpleInput(text=f"hello world {doc.text} {i}")


@pytest.fixture(scope="module")
def streaming_deployment():
    protocol = "http"
    with Deployment(uses=MyExecutor, protocol=protocol) as dep:
        yield dep


@pytest.mark.asyncio
async def test_issue_6090(streaming_deployment):
    """Tests if streaming works with pydantic models with complex fields which are not
    str, int, or float.
    """

    docs = []
    protocol = "http"
    client = Client(port=streaming_deployment.port, protocol=protocol, asyncio=True)
    example_doc = InputWithComplexFields(text="my input text")
    async for doc in client.stream_doc(
        on="/stream",
        inputs=example_doc,
        input_type=InputWithComplexFields,
        return_type=InputWithComplexFields,
    ):
        docs.append(doc)

    assert [d.text for d in docs] == [
        'hello world my input text 0',
        'hello world my input text 1',
        'hello world my input text 2',
        'hello world my input text 3',
    ]
    assert docs[0].nested_field.name == "test_name"


@pytest.mark.asyncio
async def test_issue_6090_get_params(streaming_deployment):
    """Tests if streaming works with pydantic models with complex fields which are not
    str, int, or float.
    """

    docs = []
    url = (
        f"http://localhost:{streaming_deployment.port}/stream-simple?text=my_input_text"
    )
    async with aiohttp.ClientSession() as session:

        async with session.get(url) as resp:
            async for chunk in resp.content.iter_any():
                events = chunk.split(b'event: ')[1:]
                for event in events:
                    if event.startswith(b'update'):
                        parsed = event[HTTPClientlet.UPDATE_EVENT_PREFIX :].decode()
                        parsed = SimpleInput.parse_raw(parsed)
                        docs.append(parsed)
                    elif event.startswith(b'end'):
                        pass

    assert [d.text for d in docs] == [
        'hello world my_input_text 0',
        'hello world my_input_text 1',
        'hello world my_input_text 2',
        'hello world my_input_text 3',
    ]
