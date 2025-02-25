import pytest
from jina import Flow, Executor, Deployment, requests, Client
from docarray import BaseDoc, DocList
from docarray.documents import TextDoc, ImageDoc
from jina.helper import random_port
from jina.excepts import RuntimeFailToStart
import asyncio


@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket'], ['grpc', 'http']]
)
@pytest.mark.parametrize('return_type', ['batch', 'singleton'])
@pytest.mark.parametrize('include_gateway', [True, False])
@pytest.mark.parametrize('reuse_session', [True, False])
def test_singleton_return(ctxt_manager, protocols, return_type, include_gateway, reuse_session):
    if reuse_session and 'http' not in protocols:
        return
    if 'websocket' in protocols and ctxt_manager != 'flow':
        return
    if not include_gateway and ctxt_manager == 'flow':
        return

    class MySingletonReturnInputDoc(BaseDoc):
        text: str
        price: int

    class MySingletonReturnOutputDoc(BaseDoc):
        text: str
        category: str

    class MySingletonExecutorReturn(Executor):

        @requests(on='/foo')
        def foo(
            self, docs: DocList[MySingletonReturnInputDoc], **kwargs
        ) -> DocList[MySingletonReturnOutputDoc]:
            return DocList[MySingletonReturnOutputDoc](
                [
                    MySingletonReturnOutputDoc(
                        text=docs[0].text + '_changed', category=str(docs[0].price + 1)
                    )
                ]
            )

        @requests(on='/foo_single')
        def foo_single(
            self, doc: MySingletonReturnInputDoc, **kwargs
        ) -> MySingletonReturnOutputDoc:
            return MySingletonReturnOutputDoc(
                text=doc.text + '_changed', category=str(doc.price + 1)
            )

    ports = [random_port() for _ in protocols]

    if ctxt_manager == 'flow':
        ctxt = Flow(ports=ports, protocol=protocols).add(uses=MySingletonExecutorReturn)
    else:
        ctxt = Deployment(
            ports=ports,
            protocol=protocols,
            uses=MySingletonExecutorReturn,
            include_gateway=include_gateway,
        )

    with ctxt:
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol, reuse_session=reuse_session)
            docs = c.post(
                on='/foo',
                inputs=MySingletonReturnInputDoc(text='hello', price=2),
                return_type=(
                    DocList[MySingletonReturnOutputDoc]
                    if return_type == 'batch'
                    else MySingletonReturnOutputDoc
                ),
            )
            if return_type == 'batch':
                assert docs[0].text == 'hello_changed'
                assert docs[0].category == str(3)
            else:
                assert docs.text == 'hello_changed'
                assert docs.category == str(3)

            docs = c.post(
                on='/foo_single',
                inputs=MySingletonReturnInputDoc(text='hello', price=2),
                return_type=(
                    DocList[MySingletonReturnOutputDoc]
                    if return_type == 'batch'
                    else MySingletonReturnOutputDoc
                ),
            )
            if return_type == 'batch':
                assert docs[0].text == 'hello_changed'
                assert docs[0].category == str(3)
            else:
                assert docs.text == 'hello_changed'
                assert docs.category == str(3)


@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket'], ['grpc', 'http']]
)
@pytest.mark.parametrize('return_type', ['batch', 'singleton'])
@pytest.mark.parametrize('reuse_session', [True, False])
def test_singleton_return_async(ctxt_manager, protocols, return_type, reuse_session):
    if reuse_session and 'http' not in protocols:
        return
    if 'websocket' in protocols and ctxt_manager != 'flow':
        return

    class MySingletonReturnInputDoc(BaseDoc):
        text: str
        price: int

    class MySingletonReturnOutputDoc(BaseDoc):
        text: str
        category: str

    class MySingletonExecutorReturn(Executor):

        @requests(on='/foo')
        async def foo(
            self, docs: DocList[MySingletonReturnInputDoc], **kwargs
        ) -> DocList[MySingletonReturnOutputDoc]:
            await asyncio.sleep(0.01)
            return DocList[MySingletonReturnOutputDoc](
                [
                    MySingletonReturnOutputDoc(
                        text=docs[0].text + '_changed', category=str(docs[0].price + 1)
                    )
                ]
            )

        @requests(on='/foo_single')
        async def foo_single(
            self, doc: MySingletonReturnInputDoc, **kwargs
        ) -> MySingletonReturnOutputDoc:
            await asyncio.sleep(0.01)
            return MySingletonReturnOutputDoc(
                text=doc.text + '_changed', category=str(doc.price + 1)
            )

    ports = [random_port() for _ in protocols]

    if ctxt_manager == 'flow':
        ctxt = Flow(ports=ports, protocol=protocols).add(uses=MySingletonExecutorReturn)
    else:
        ctxt = Deployment(
            ports=ports, protocol=protocols, uses=MySingletonExecutorReturn
        )

    with ctxt:
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol, reuse_session=reuse_session)
            docs = c.post(
                on='/foo',
                inputs=MySingletonReturnInputDoc(text='hello', price=2),
                return_type=(
                    DocList[MySingletonReturnOutputDoc]
                    if return_type == 'batch'
                    else MySingletonReturnOutputDoc
                ),
            )
            if return_type == 'batch':
                assert docs[0].text == 'hello_changed'
                assert docs[0].category == str(3)
            else:
                assert docs.text == 'hello_changed'
                assert docs.category == str(3)

            docs = c.post(
                on='/foo_single',
                inputs=MySingletonReturnInputDoc(text='hello', price=2),
                return_type=(
                    DocList[MySingletonReturnOutputDoc]
                    if return_type == 'batch'
                    else MySingletonReturnOutputDoc
                ),
            )
            if return_type == 'batch':
                assert docs[0].text == 'hello_changed'
                assert docs[0].category == str(3)
            else:
                assert docs.text == 'hello_changed'
                assert docs.category == str(3)


@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket'], ['grpc', 'http']]
)
@pytest.mark.parametrize('return_type', ['batch', 'singleton'])
def test_singleton_in_place(ctxt_manager, protocols, return_type):
    if 'websocket' in protocols and ctxt_manager != 'flow':
        return

    class MySingletonInPlaceDoc(BaseDoc):
        text: str
        price: int

    class MySingletonExecutorInPlace(Executor):

        @requests(on='/foo')
        def foo(
            self, docs: DocList[MySingletonInPlaceDoc], **kwargs
        ) -> DocList[MySingletonInPlaceDoc]:
            for doc in docs:
                doc.text = doc.text + '_changed'
                doc.price += 1

        @requests(on='/foo_single')
        def foo_single(
            self, doc: MySingletonInPlaceDoc, **kwargs
        ) -> MySingletonInPlaceDoc:
            doc.text = doc.text + '_changed'
            doc.price += 1

    ports = [random_port() for _ in protocols]

    if ctxt_manager == 'flow':
        ctxt = Flow(ports=ports, protocol=protocols).add(
            uses=MySingletonExecutorInPlace
        )
    else:
        ctxt = Deployment(
            ports=ports, protocol=protocols, uses=MySingletonExecutorInPlace
        )

    with ctxt:
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/foo',
                inputs=MySingletonInPlaceDoc(text='hello', price=2),
                return_type=(
                    DocList[MySingletonInPlaceDoc]
                    if return_type == 'batch'
                    else MySingletonInPlaceDoc
                ),
            )
            if return_type == 'batch':
                assert docs[0].text == 'hello_changed'
                assert docs[0].price == 3
            else:
                assert docs.text == 'hello_changed'
                assert docs.price == 3

            docs = c.post(
                on='/foo_single',
                inputs=MySingletonInPlaceDoc(text='hello', price=2),
                return_type=(
                    DocList[MySingletonInPlaceDoc]
                    if return_type == 'batch'
                    else MySingletonInPlaceDoc
                ),
            )
            if return_type == 'batch':
                assert docs[0].text == 'hello_changed'
                assert docs[0].price == 3
            else:
                assert docs.text == 'hello_changed'
                assert docs.price == 3


@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['http', 'grpc', 'websocket']]
)
@pytest.mark.parametrize('return_type', ['batch', 'singleton'])
def test_singleton_in_flow_in_the_middle(protocols, return_type):
    class MySingletonFlowDoc(BaseDoc):
        text: str
        num: int

    class InputDoc(BaseDoc):
        input: str

    class OutputDoc(BaseDoc):
        output: int

    class MyFirstSingletonIntheMiddleExecutor(Executor):

        @requests
        def foo(self, docs: DocList[InputDoc], **kwargs) -> DocList[MySingletonFlowDoc]:
            ret = DocList[MySingletonFlowDoc]()
            for doc in docs:
                ret.append(MySingletonFlowDoc(text=doc.input, num=len(doc.input)))
            return ret

    class MySingletonIntheMiddleExecutor(Executor):

        @requests
        def foo(self, doc: MySingletonFlowDoc, **kwargs) -> MySingletonFlowDoc:
            return MySingletonFlowDoc(text=doc.text, num=doc.num * 2)

    class MyLastSingletonIntheMiddleExecutor(Executor):

        @requests
        def foo(
            self, docs: DocList[MySingletonFlowDoc], **kwargs
        ) -> DocList[OutputDoc]:
            ret = DocList[OutputDoc]()
            for doc in docs:
                ret.append(OutputDoc(output=doc.num))
            return ret

    ports = [random_port() for _ in protocols]

    flow = (
        Flow(ports=ports, protocol=protocols)
        .add(uses=MyFirstSingletonIntheMiddleExecutor)
        .add(uses=MySingletonIntheMiddleExecutor)
        .add(uses=MyLastSingletonIntheMiddleExecutor)
    )

    with flow:
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/foo',
                inputs=InputDoc(input='hello'),
                return_type=DocList[OutputDoc] if return_type == 'batch' else OutputDoc,
            )
            if return_type == 'batch':
                assert docs[0].output == 2 * len('hello')
            else:
                assert docs.output == 2 * len('hello')

            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/foo',
                inputs=DocList[InputDoc](
                    [InputDoc(input='hello'), InputDoc(input='hello')]
                ),
                return_type=DocList[OutputDoc] if return_type == 'batch' else OutputDoc,
            )
            assert isinstance(docs, DocList[OutputDoc])  # I have sent 2
            assert len(docs) == 2
            for doc in docs:
                assert doc.output == 2 * len('hello')


@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['http', 'grpc', 'websocket']]
)
def test_flow_incompatibility_with_singleton(protocols):
    class First(Executor):
        @requests
        def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
            pass

    class Second(Executor):
        @requests
        def foo(self, doc: ImageDoc, **kwargs) -> ImageDoc:
            pass

    f = Flow(protocol=protocols).add(uses=First).add(uses=Second)

    with pytest.raises(RuntimeFailToStart):
        with f:
            pass


@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
@pytest.mark.parametrize('include_gateway', [True, False])
def test_call_from_requests_as_singleton(ctxt_manager, include_gateway):
    if not include_gateway and ctxt_manager == 'flow':
        return

    class MySingletonReturnInputDoc(BaseDoc):
        text: str
        price: int

    class MySingletonReturnOutputDoc(BaseDoc):
        text: str
        category: str

    class MySingletonExecutorReturn(Executor):

        @requests(on='/foo')
        def foo(
            self, docs: DocList[MySingletonReturnInputDoc], **kwargs
        ) -> DocList[MySingletonReturnOutputDoc]:
            ret = DocList[MySingletonReturnOutputDoc]()
            for doc in docs:
                ret.append(
                    MySingletonReturnOutputDoc(
                        text=doc.text + '_changed', category=str(doc.price + 1)
                    )
                )
            return ret

        @requests(on='/foo_single')
        def foo_single(
            self, doc: MySingletonReturnInputDoc, **kwargs
        ) -> MySingletonReturnOutputDoc:
            return MySingletonReturnOutputDoc(
                text=doc.text + '_changed', category=str(doc.price + 1)
            )

    port = random_port()

    if ctxt_manager == 'flow':
        ctxt = Flow(port=port, protocol='http').add(uses=MySingletonExecutorReturn)
    else:
        ctxt = Deployment(
            port=port,
            protocol='http',
            uses=MySingletonExecutorReturn,
            include_gateway=include_gateway,
        )

    with ctxt:
        import requests as global_requests

        for endpoint in {'foo', 'foo_single'}:
            url = f'http://localhost:{port}/{endpoint}'
            myobj = {'data': {'text': 'hello', 'price': 2}}
            resp = global_requests.post(url, json=myobj)
            resp_json = resp.json()
            assert resp_json['data'][0]['text'] == 'hello_changed'
            assert resp_json['data'][0]['category'] == str(3)
            myobj = {'data': [{'text': 'hello', 'price': 2}]}
            resp = global_requests.post(url, json=myobj)
            resp_json = resp.json()
            assert resp_json['data'][0]['text'] == 'hello_changed'
            assert resp_json['data'][0]['category'] == str(3)
            myobj = {
                'data': [{'text': 'hello', 'price': 2}, {'text': 'hello', 'price': 2}]
            }
            resp = global_requests.post(url, json=myobj)
            resp_json = resp.json()
            assert len(resp_json['data']) == 2
            for d in resp_json['data']:
                assert d['text'] == 'hello_changed'
                assert d['category'] == str(3)


def test_invalid_singleton_batch_combination():
    with pytest.raises(Exception):

        class Invalid1(Executor):
            @requests
            def foo(self, doc: ImageDoc, **kwargs) -> DocList[ImageDoc]:
                pass

    with pytest.raises(Exception):

        class Invalid2(Executor):
            @requests
            async def foo(self, doc: ImageDoc, **kwargs) -> DocList[ImageDoc]:
                pass

    with pytest.raises(Exception):

        class Invalid3(Executor):
            @requests
            async def foo(self, doc: ImageDoc, **kwargs) -> DocList[ImageDoc]:
                for _ in range(10):
                    yield doc

    with pytest.raises(Exception):

        class Invalid4(Executor):
            @requests
            def foo(self, docs: DocList[ImageDoc], **kwargs) -> ImageDoc:
                pass

    with pytest.raises(Exception):

        class Invalid6(Executor):
            @requests
            async def foo(self, docs: DocList[ImageDoc], **kwargs) -> ImageDoc:
                pass


@pytest.mark.asyncio
@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket'], ['grpc', 'http']]
)
@pytest.mark.parametrize('return_type', ['batch', 'singleton'])
@pytest.mark.parametrize('include_gateway', [True, False])
async def test_async_client(ctxt_manager, protocols, return_type, include_gateway):
    if 'websocket' in protocols and ctxt_manager != 'flow':
        return
    if not include_gateway and ctxt_manager == 'flow':
        return

    class MySingletonReturnInputDoc(BaseDoc):
        text: str
        price: int

    class MySingletonReturnOutputDoc(BaseDoc):
        text: str
        category: str

    class MySingletonExecutorReturn(Executor):

        @requests(on='/foo')
        def foo(
            self, docs: DocList[MySingletonReturnInputDoc], **kwargs
        ) -> DocList[MySingletonReturnOutputDoc]:
            return DocList[MySingletonReturnOutputDoc](
                [
                    MySingletonReturnOutputDoc(
                        text=docs[0].text + '_changed', category=str(docs[0].price + 1)
                    )
                ]
            )

        @requests(on='/foo_single')
        def foo_single(
            self, doc: MySingletonReturnInputDoc, **kwargs
        ) -> MySingletonReturnOutputDoc:
            return MySingletonReturnOutputDoc(
                text=doc.text + '_changed', category=str(doc.price + 1)
            )

    ports = [random_port() for _ in protocols]

    if ctxt_manager == 'flow':
        ctxt = Flow(ports=ports, protocol=protocols).add(uses=MySingletonExecutorReturn)
    else:
        ctxt = Deployment(
            ports=ports,
            protocol=protocols,
            uses=MySingletonExecutorReturn,
            include_gateway=include_gateway,
        )

    with ctxt:
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol, asyncio=True)

            async for doc in c.post(
                on='/foo',
                inputs=MySingletonReturnInputDoc(text='hello', price=2),
                return_type=(
                    DocList[MySingletonReturnOutputDoc]
                    if return_type == 'batch'
                    else MySingletonReturnOutputDoc
                ),
            ):
                if return_type == 'batch':
                    assert isinstance(doc, DocList)
                    assert len(doc) == 1
                    assert doc[0].text == 'hello_changed'
                    assert doc[0].category == str(3)
                else:
                    assert isinstance(doc, BaseDoc)
                    assert doc.text == 'hello_changed'
                    assert doc.category == str(3)

            async for doc in c.post(
                on='/foo_single',
                inputs=MySingletonReturnInputDoc(text='hello', price=2),
                return_type=(
                    DocList[MySingletonReturnOutputDoc]
                    if return_type == 'batch'
                    else MySingletonReturnOutputDoc
                ),
            ):
                if return_type == 'batch':
                    assert isinstance(doc, DocList)
                    assert len(doc) == 1
                    assert doc[0].text == 'hello_changed'
                    assert doc[0].category == str(3)
                else:
                    assert isinstance(doc, BaseDoc)
                    assert doc.text == 'hello_changed'
                    assert doc.category == str(3)
