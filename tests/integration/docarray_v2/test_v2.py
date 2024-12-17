import os
import time
from typing import (
    Any,
    AsyncGenerator,
    AsyncIterator,
    Dict,
    Generator,
    Iterator,
    List,
    Optional,
    Union,
)

import numpy as np
import pytest
from docarray import BaseDoc, DocList
from docarray.documents import ImageDoc, TextDoc
from docarray.documents.legacy import LegacyDocument
from docarray.typing import AnyTensor, ImageUrl, NdArray

from jina import Client, Deployment, Executor, Flow, dynamic_batching, requests
from jina.excepts import RuntimeFailToStart
from jina.helper import random_port


@pytest.mark.parametrize(
    'protocols', [['grpc', 'http', 'websocket']]
)
@pytest.mark.parametrize('reduce', [False, True])
@pytest.mark.parametrize('sleep_time', [5])
@pytest.mark.skipif(
    'GITHUB_WORKFLOW' in os.environ,
    reason='tests support for docarray>=0.30 and not working on GITHUB since issue with restarting server in grpc',
)
def test_flow_with_shards_all_shards_return(protocols, reduce, sleep_time):
    from typing import List

    from docarray import BaseDoc, DocList
    from docarray.documents import TextDoc

    class TextDocWithId(TextDoc):
        id: str
        l: List[int] = []

    class ResultTestDoc(BaseDoc):
        price: int = '2'
        l: List[int] = [3]
        matches: DocList[TextDocWithId]

    class SimilarityTestIndexer(Executor):
        """Simulates an indexer where no shard would fail, they all pass results"""

        def __init__(self, sleep_time=0.1, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._docs = DocList[TextDocWithId]()
            time.sleep(sleep_time)

        @requests(on=['/index'])
        def index(
                self, docs: DocList[TextDocWithId], **kwargs
        ) -> DocList[TextDocWithId]:
            for doc in docs:
                self._docs.append(doc)

        @requests(on=['/search'])
        def search(
                self, docs: DocList[TextDocWithId], **kwargs
        ) -> DocList[ResultTestDoc]:
            resp = DocList[ResultTestDoc]()
            for q in docs:
                res = ResultTestDoc(id=q.id, matches=self._docs[0:3])
                resp.append(res)
            return resp

    ports = [random_port() for _ in protocols]
    with Flow(protocol=protocols, port=ports).add(
            uses=SimilarityTestIndexer,
            uses_with={'sleep_time': sleep_time},
            shards=2,
            reduce=reduce,
    ):
        time.sleep(5)
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            index_da = DocList[TextDocWithId](
                [TextDocWithId(id=f'{i}', text=f'ID {i}') for i in range(10)]
            )
            c.index(inputs=index_da, request_size=1, return_type=DocList[TextDocWithId])

            responses = c.search(
                inputs=index_da[0:1], request_size=1, return_type=DocList[ResultTestDoc]
            )
            assert len(responses) == 1 if reduce else 2
            for r in responses:
                assert r.l[0] == 3
                assert len(r.matches) == 6
                for match in r.matches:
                    assert 'ID' in match.text


@pytest.mark.parametrize('reduce', [True, False])
@pytest.mark.parametrize('sleep_time', [5])
@pytest.mark.skipif(
    'GITHUB_WORKFLOW' in os.environ,
    reason='tests support for docarray>=0.30 and not working on GITHUB since issue with restarting server in grpc',
)
def test_deployments_with_shards_all_shards_return(reduce, sleep_time):
    from typing import List

    from docarray import BaseDoc, DocList
    from docarray.documents import TextDoc

    class TextDocWithId(TextDoc):
        id: str
        l: List[int] = []

    class ResultTestDoc(BaseDoc):
        price: int = '2'
        l: List[int] = [3]
        matches: DocList[TextDocWithId]

    class SimilarityTestIndexer(Executor):
        """Simulates an indexer where no shard would fail, they all pass results"""

        def __init__(self, sleep_time=0.1, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._docs = DocList[TextDocWithId]()
            time.sleep(sleep_time)

        @requests(on=['/index'])
        def index(
                self, docs: DocList[TextDocWithId], **kwargs
        ) -> DocList[TextDocWithId]:
            for doc in docs:
                self._docs.append(doc)

        @requests(on=['/search'])
        def search(
                self, docs: DocList[TextDocWithId], **kwargs
        ) -> DocList[ResultTestDoc]:
            resp = DocList[ResultTestDoc]()
            for q in docs:
                res = ResultTestDoc(id=q.id, matches=self._docs[0:3])
                resp.append(res)
            return resp

    with Deployment(
            uses=SimilarityTestIndexer,
            uses_with={'sleep_time': sleep_time},
            shards=2,
            reduce=reduce,
    ) as dep:
        time.sleep(5)
        index_da = DocList[TextDocWithId](
            [TextDocWithId(id=f'{i}', text=f'ID {i}') for i in range(10)]
        )
        dep.index(inputs=index_da, request_size=1, return_type=DocList[TextDocWithId])
        responses = dep.search(
            inputs=index_da[0:1], request_size=1, return_type=DocList[ResultTestDoc]
        )
        assert len(responses) == 1 if reduce else 2
        for r in responses:
            assert r.l[0] == 3
            assert len(r.matches) == 6
            for match in r.matches:
                assert 'ID' in match.text


@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket'], ['grpc', 'http', 'websocket']]
)
@pytest.mark.parametrize('replicas', [1, 3])
def test_different_document_schema(protocols, replicas):
    class Image(BaseDoc):
        #tensor: Optional[AnyTensor]
        url: ImageUrl
        lll: List[List[str]] = [[]]
        texts: DocList[TextDoc]

    class MyExecDifSchema(Executor):
        @requests(on='/foo')
        def foo(self, docs: DocList[Image], **kwargs) -> DocList[Image]:
            for doc in docs:
                #doc.tensor = np.zeros((10, 10, 10))
                doc.lll = [['aa'], ['bb']]
                doc.texts.append(TextDoc('ha'))
            return docs

    ports = [random_port() for _ in protocols]
    with Flow(port=ports, protocol=protocols, replicas=replicas).add(uses=MyExecDifSchema) as f:
        time.sleep(5)
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/foo',
                inputs=DocList[Image](
                    [
                        Image(
                            url='https://via.placeholder.com/150.png',
                            texts=DocList[TextDoc]([TextDoc('hey')]),
                        )
                    ]
                ),
                return_type=DocList[Image],
            )
            docs = docs.to_doc_vec()
            #assert docs.tensor.ndim == 4
            assert docs[0].lll == [['aa'], ['bb']]
            assert len(docs[0].texts) == 2
            assert docs[0].texts[0].text == 'hey'
            assert docs[0].texts[1].text == 'ha'


@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket'], ['grpc', 'http', 'websocket']]
)
@pytest.mark.parametrize('replicas', [1, 3])
def test_send_custom_doc(protocols, replicas):
    class MyDoc(BaseDoc):
        my_text: str

    class MyExecCustomDoc(Executor):
        @requests(on='/foo')
        def foo(self, docs: DocList[MyDoc], **kwargs) -> DocList[MyDoc]:
            docs[0].my_text = 'hello world'
            return docs

    ports = [random_port() for _ in protocols]
    with Flow(port=ports, protocol=protocols, replicas=replicas).add(uses=MyExecCustomDoc):
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/foo', inputs=MyDoc(my_text='hello'), return_type=DocList[MyDoc]
            )
            assert docs[0].my_text == 'hello world'


@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket']]
)
@pytest.mark.parametrize('replicas', [1, 3])
def test_input_response_schema(protocols, replicas):
    class MyDoc(BaseDoc):
        text: str

    class MyExecRespSchema(Executor):
        @requests(
            on='/foo',
            request_schema=DocList[MyDoc],
            response_schema=DocList[MyDoc],
        )
        def foo(self, docs, **kwargs):
            assert docs.__class__.doc_type == MyDoc
            docs[0].text = 'hello world'
            return docs

    ports = [random_port() for _ in protocols]
    with Flow(port=ports, protocol=protocols, replicas=replicas).add(uses=MyExecRespSchema):
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/foo', inputs=MyDoc(text='hello'), return_type=DocList[MyDoc]
            )
            assert docs[0].text == 'hello world'
            assert docs.__class__.doc_type == MyDoc


@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket'], ['grpc', 'http', 'websocket']]
)
@pytest.mark.parametrize('replicas', [1, 3])
def test_input_response_schema_annotation(protocols, replicas):
    class MyDoc(BaseDoc):
        text: str

    class MyExecAnnotation(Executor):
        @requests(on='/bar')
        def bar(self, docs: DocList[MyDoc], **kwargs) -> DocList[MyDoc]:
            assert docs.__class__.doc_type == MyDoc
            docs[0].text = 'hello world'
            return docs

    ports = [random_port() for _ in protocols]
    with Flow(port=ports, protocol=protocols, replicas=replicas).add(uses=MyExecAnnotation):
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/bar', inputs=MyDoc(text='hello'), return_type=DocList[MyDoc]
            )
            assert docs[0].text == 'hello world'
            assert docs.__class__.doc_type == MyDoc


@pytest.mark.parametrize('endpoint', [f'task{i + 1}' for i in range(6)])
def test_generator_endpoints_type_annotations(endpoint):
    class InputDocument(BaseDoc):
        input: str
        n: int

    class OutputDocument(BaseDoc):
        output: str

    class GeneratorExecutor(Executor):
        @requests(on='/task1', response_schema=OutputDocument)
        async def task1(self, doc: InputDocument, **kwargs):
            yield OutputDocument(text='hello world')

        @requests(on='/task2')
        async def task2(self, doc: InputDocument, **kwargs) -> OutputDocument:
            yield OutputDocument(text='hello world')

        @requests(on='/task3')
        async def task3(
                self, doc: InputDocument, **kwargs
        ) -> Generator[OutputDocument, None, None]:
            yield OutputDocument(text='hello world')

        @requests(on='/task4')
        async def task4(
                self, doc: InputDocument, **kwargs
        ) -> AsyncGenerator[OutputDocument, None]:
            yield OutputDocument(text='hello world')

        @requests(on='/task5')
        async def task5(self, doc: InputDocument, **kwargs) -> Iterator[OutputDocument]:
            yield OutputDocument(text='hello world')

        @requests(on='/task6')
        async def task6(
                self, doc: InputDocument, **kwargs
        ) -> AsyncIterator[OutputDocument]:
            yield OutputDocument(text='hello world')

    assert (
            GeneratorExecutor.requests_by_class['GeneratorExecutor'][
                f'/{endpoint}'
            ].request_schema
            == InputDocument
    )
    assert (
            GeneratorExecutor.requests_by_class['GeneratorExecutor'][
                f'/{endpoint}'
            ].response_schema
            == OutputDocument
    )


@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket']]
)
@pytest.mark.parametrize('replicas', [1, 3])
def test_different_output_input(protocols, replicas):
    class InputDoc(BaseDoc):
        img: ImageDoc

    class OutputDoc(BaseDoc):
        embedding: AnyTensor
        t: str

    class MyExecForFlow(Executor):
        @requests(on='/bar')
        def bar(self, docs: DocList[InputDoc], **kwargs) -> DocList[OutputDoc]:
            docs_return = DocList[OutputDoc](
                [OutputDoc(embedding=np.zeros((100, 1)), t='hey') for _ in range(len(docs))]
            )
            return docs_return

        @requests(on='/bar_with_dbatch')
        @dynamic_batching(preferred_batch_size=4)
        def bar_with_dbatch(
                self, docs: DocList[InputDoc], **kwargs
        ) -> DocList[OutputDoc]:
            docs_return = DocList[OutputDoc](
                [OutputDoc(embedding=np.zeros((100, 1)), t='hey') for _ in range(len(docs))]
            )
            return docs_return

    ports = [random_port() for _ in protocols]
    with Flow(port=ports, protocol=protocols, replicas=replicas).add(uses=MyExecForFlow):
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/bar',
                inputs=InputDoc(img=ImageDoc(tensor=np.zeros((3, 224, 224)))),
                return_type=DocList[OutputDoc],
            )
            assert docs[0].embedding.shape == (100, 1)
            assert docs.__class__.doc_type == OutputDoc
            docs = c.post(
                on='/bar_with_dbatch',
                inputs=InputDoc(img=ImageDoc(tensor=np.zeros((3, 224, 224)))),
                return_type=DocList[OutputDoc],
            )
            assert docs[0].embedding.shape == (100, 1)
            assert docs.__class__.doc_type == OutputDoc


@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['grpc', 'http']]
)
def test_different_output_input_deployment(protocols):
    class InputDoc(BaseDoc):
        img: ImageDoc

    class OutputDoc(BaseDoc):
        embedding: AnyTensor
        t: str

    class MyExecForDepl(Executor):
        @requests(on='/bar')
        def bar(self, docs: DocList[InputDoc], **kwargs) -> DocList[OutputDoc]:
            docs_return = DocList[OutputDoc](
                [OutputDoc(embedding=np.zeros((100, 1)), t='hey') for _ in range(len(docs))]
            )
            return docs_return

        @requests(on='/bar_with_dbatch')
        @dynamic_batching(preferred_batch_size=4)
        def bar_with_dbatch(
                self, docs: DocList[InputDoc], **kwargs
        ) -> DocList[OutputDoc]:
            docs_return = DocList[OutputDoc](
                [OutputDoc(embedding=np.zeros((100, 1)), t='hey') for _ in range(len(docs))]
            )
            return docs_return

    ports = [random_port() for _ in protocols]
    with Deployment(port=ports, protocol=protocols, uses=MyExecForDepl, include_gateway=False):
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/bar',
                inputs=InputDoc(img=ImageDoc(tensor=np.zeros((3, 224, 224)))),
                return_type=DocList[OutputDoc],
            )
            assert docs[0].embedding.shape == (100, 1)
            assert docs.__class__.doc_type == OutputDoc
            docs = c.post(
                on='/bar_with_dbatch',
                inputs=InputDoc(img=ImageDoc(tensor=np.zeros((3, 224, 224)))),
                return_type=DocList[OutputDoc],
            )
            assert docs[0].embedding.shape == (100, 1)
            assert docs.__class__.doc_type == OutputDoc


@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket'], ['grpc', 'http', 'websocket']]
)
def test_chain(protocols):
    class Input1(BaseDoc):
        img: ImageDoc

    class Output1(BaseDoc):
        embedding: AnyTensor

    class Output2(BaseDoc):
        a: str

    class Exec1Chain(Executor):
        @requests(on='/bar')
        def bar(self, docs: DocList[Input1], **kwargs) -> DocList[Output1]:
            docs_return = DocList[Output1](
                [Output1(embedding=np.zeros((100, 1))) for _ in range(len(docs))]
            )
            return docs_return

    class Exec2Chain(Executor):
        @requests(on='/bar')
        def bar(self, docs: DocList[Output1], **kwargs) -> DocList[Output2]:
            docs_return = DocList[Output2](
                [
                    Output2(a=f'shape input {docs[0].embedding.shape[0]}')
                    for _ in range(len(docs))
                ]
            )
            return docs_return

    ports = [random_port() for _ in protocols]
    with Flow(port=ports, protocol=protocols).add(uses=Exec1Chain).add(uses=Exec2Chain):
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/bar',
                inputs=Input1(img=ImageDoc(tensor=np.zeros((3, 224, 224)))),
                return_type=DocList[Output2],
            )
            assert len(docs) == 1
            assert docs[0].a == 'shape input 100'
            if len(protocols) == 1 and protocols[0] == 'grpc':
                import grpc
                from docarray.documents.legacy import LegacyDocument
                from google.protobuf.json_format import MessageToDict

                from jina.proto import jina_pb2
                from jina.proto.jina_pb2_grpc import JinaDiscoverEndpointsRPCStub
                from jina.serve.executors import __dry_run_endpoint__
                from jina.serve.runtimes.helper import (
                    _create_aux_model_doc_list_to_list,
                    _create_pydantic_model_from_schema,
                )

                channel = grpc.insecure_channel(f'0.0.0.0:{ports[0]}')
                stub = JinaDiscoverEndpointsRPCStub(channel)
                res = stub.endpoint_discovery(
                    jina_pb2.google_dot_protobuf_dot_empty__pb2.Empty(),
                )
                schema_map = MessageToDict(res.schemas)
                assert set(schema_map.keys()) == {__dry_run_endpoint__, '/bar'}
                v = schema_map[__dry_run_endpoint__]
                assert v['input'] == LegacyDocument.schema()
                assert v['output'] == LegacyDocument.schema()
                v = schema_map['/bar']
                assert (
                        v['input']
                        == _create_pydantic_model_from_schema(
                    _create_aux_model_doc_list_to_list(Input1).schema(),
                    'Input1',
                    {},
                ).schema()
                )
                assert (
                        v['output']
                        == _create_pydantic_model_from_schema(
                    _create_aux_model_doc_list_to_list(Output2).schema(),
                    'Output2',
                    {},
                ).schema()
                )


@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket'], ['grpc', 'http', 'websocket']]
)
def test_default_endpoint(protocols):
    class Input1(BaseDoc):
        img: ImageDoc

    class Output1(BaseDoc):
        embedding: AnyTensor

    class Output2(BaseDoc):
        a: str

    class Exec1Default(Executor):
        @requests()
        def bar(self, docs: DocList[Input1], **kwargs) -> DocList[Output1]:
            docs_return = DocList[Output1](
                [Output1(embedding=np.zeros((100, 1))) for _ in range(len(docs))]
            )
            return docs_return

    class Exec2Default(Executor):
        @requests()
        def bar(self, docs: DocList[Output1], **kwargs) -> DocList[Output2]:
            docs_return = DocList[Output2](
                [
                    Output2(a=f'shape input {docs[0].embedding.shape[0]}')
                    for _ in range(len(docs))
                ]
            )
            return docs_return

    ports = [random_port() for _ in protocols]
    with Flow(port=ports, protocol=protocols).add(uses=Exec1Default).add(
            uses=Exec2Default
    ):
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/default',
                inputs=Input1(img=ImageDoc(tensor=np.zeros((3, 224, 224)))),
                return_type=DocList[Output2],
            )
            assert len(docs) == 1
            assert docs[0].a == 'shape input 100'

        if len(protocols) == 1 and protocols[0] == 'grpc':
            import grpc
            from docarray.documents.legacy import LegacyDocument
            from google.protobuf.json_format import MessageToDict

            from jina.proto import jina_pb2
            from jina.proto.jina_pb2_grpc import JinaDiscoverEndpointsRPCStub
            from jina.serve.executors import __default_endpoint__, __dry_run_endpoint__
            from jina.serve.runtimes.helper import (
                _create_aux_model_doc_list_to_list,
                _create_pydantic_model_from_schema,
            )

            channel = grpc.insecure_channel(f'0.0.0.0:{ports[0]}')
            stub = JinaDiscoverEndpointsRPCStub(channel)
            res = stub.endpoint_discovery(
                jina_pb2.google_dot_protobuf_dot_empty__pb2.Empty(),
            )
            schema_map = MessageToDict(res.schemas)
            assert set(schema_map.keys()) == {
                __dry_run_endpoint__,
                __default_endpoint__,
            }
            v = schema_map[__dry_run_endpoint__]
            assert v['input'] == LegacyDocument.schema()
            assert v['output'] == LegacyDocument.schema()
            v = schema_map[__default_endpoint__]
            assert (
                    v['input']
                    == _create_pydantic_model_from_schema(
                _create_aux_model_doc_list_to_list(Input1).schema(), 'Input1', {}
            ).schema()
            )
            assert (
                    v['output']
                    == _create_pydantic_model_from_schema(
                _create_aux_model_doc_list_to_list(Output2).schema(), 'Output2', {}
            ).schema()
            )


@pytest.mark.parametrize(
    'protocols', [['grpc'], ['http'], ['websocket']]
)
@pytest.mark.parametrize('reduce', [True, False])
def test_complex_topology_bifurcation(protocols, reduce):
    class DocTest(BaseDoc):
        text: str

    class ExecutorTest(Executor):
        def __init__(self, text, **kwargs):
            super().__init__(**kwargs)
            self.text = text

        @requests
        def endpoint(self, docs: DocList[DocTest], **kwargs) -> DocList[DocTest]:
            for doc in docs:
                doc.text = self.text

    class ReduceExecutorTest(Executor):
        @requests
        def endpoint(self, docs: DocList[DocTest], **kwargs) -> DocList[DocTest]:
            return docs

    ports = [random_port() for _ in protocols]
    flow = (
        Flow(protocol=protocols, port=ports)
            .add(uses=ExecutorTest, uses_with={'text': 'exec1'}, name='pod0')
            .add(
            uses=ExecutorTest, uses_with={'text': 'exec2'}, needs='gateway', name='pod1'
        )
            .add(
            uses=ExecutorTest, uses_with={'text': 'exec3'}, needs='gateway', name='pod2'
        )
            .add(
            needs=['pod0', 'pod1', 'pod2'],
            uses=ReduceExecutorTest,
            no_reduce=not reduce,
            name='pod3',
        )
    )

    with flow:
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                '/',
                inputs=DocList[DocTest]([DocTest(text='') for _ in range(5)]),
                return_type=DocList[DocTest],
            )
            assert len(docs) == 5 if reduce else 15
            for doc in docs:
                assert 'exec' in doc.text


@pytest.fixture()
def temp_workspace(tmpdir):
    import os

    os.environ['TEMP_WORKSPACE'] = str(tmpdir)
    yield
    os.unsetenv('TEMP_WORKSPACE')


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
def test_condition_feature(protocol, temp_workspace, tmpdir):
    class ProcessingTestDocConditions(BaseDoc):
        text: str
        tags: Dict[str, int]

    class ConditionDumpExecutor(Executor):
        @requests
        def foo(
                self, docs: DocList[ProcessingTestDocConditions], **kwargs
        ) -> DocList[ProcessingTestDocConditions]:
            with open(
                    os.path.join(str(self.workspace), f'{self.metas.name}.txt'),
                    'w',
                    encoding='utf-8',
            ) as fp:
                for doc in docs:
                    fp.write(doc.text)
                    doc.text += f' processed by {self.metas.name}'

    class FirstExec(Executor):
        @requests
        def foo(
                self, docs: DocList[LegacyDocument], **kwargs
        ) -> DocList[ProcessingTestDocConditions]:
            output_da = DocList[ProcessingTestDocConditions](
                [
                    ProcessingTestDocConditions(text='type1', tags={'type': 1}),
                    ProcessingTestDocConditions(text='type2', tags={'type': 2}),
                ]
            )
            return output_da

    class JoinerExec(Executor):
        @requests
        def foo(
                self, docs: DocList[ProcessingTestDocConditions], **kwargs
        ) -> DocList[ProcessingTestDocConditions]:
            pass

    f = (
        Flow(protocol=protocol)
            .add(uses=FirstExec, name='first')
            .add(
            uses=ConditionDumpExecutor,
            uses_metas={'name': 'exec1'},
            workspace=os.environ['TEMP_WORKSPACE'],
            name='exec1',
            needs=['first'],
            when={'tags__type': {'$eq': 1}},
        )
            .add(
            uses=ConditionDumpExecutor,
            workspace=os.environ['TEMP_WORKSPACE'],
            uses_metas={'name': 'exec2'},
            name='exec2',
            needs='first',
            when={'tags__type': {'$gt': 1}},
        )
            .needs_all('joiner', uses=JoinerExec)
    )

    with f:
        input_da = DocList[LegacyDocument]([])

        ret = f.post(
            on='/bar',
            inputs=input_da,
            return_type=DocList[ProcessingTestDocConditions],
        )
        assert len(ret) == 2
        types_set = set()
        for doc in ret:
            if doc.tags['type'] == 1:
                assert doc.text == 'type1 processed by exec1'
            else:
                assert doc.tags['type'] == 2
                assert doc.text == 'type2 processed by exec2'
            types_set.add(doc.tags['type'])

        assert types_set == {1, 2}

        with open(
                os.path.join(str(tmpdir), 'exec1', '0', f'exec1.txt'), 'r', encoding='utf-8'
        ) as fp:
            assert fp.read() == 'type1'

        with open(
                os.path.join(str(tmpdir), 'exec2', '0', f'exec2.txt'), 'r', encoding='utf-8'
        ) as fp:
            assert fp.read() == 'type2'


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
def test_endpoints_target_executors_combinations(protocol):
    class Foo(Executor):
        @requests(on='/hello')
        def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
            for doc in docs:
                doc.text += 'Processed by foo'

    class Bar(Executor):
        @requests(on='/hello')
        def bar(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
            for doc in docs:
                doc.text += 'Processed by bar'

    f = Flow(protocol=protocol).add(name='p0', uses=Foo).add(name='p1', uses=Bar)

    with f:
        docs = f.post(
            '/hello',
            inputs=DocList[TextDoc]([TextDoc(text='')]),
            return_type=DocList[TextDoc],
        )
        assert len(docs) == 1
        for doc in docs:
            assert doc.text == 'Processed by fooProcessed by bar'
        docs = f.post(
            '/hello',
            target_executor='p1',
            inputs=DocList[TextDoc]([TextDoc(text='')]),
            return_type=DocList[TextDoc],
        )
        assert len(docs) == 1
        for doc in docs:
            assert doc.text == 'Processed by bar'


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
def test_floating_executors(protocol, tmpdir):
    TIME_SLEEP_FLOATING = 1.0

    class FloatingTestExecutor(Executor):
        def __init__(self, file_name, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.file_name = file_name

        @requests
        def foo(
                self, docs: DocList[LegacyDocument], **kwargs
        ) -> DocList[LegacyDocument]:
            time.sleep(TIME_SLEEP_FLOATING)
            with open(self.file_name, 'a+', encoding='utf-8') as f:
                f.write('here ')

            for d in docs:
                d.text = 'change it'

    NUM_REQ = 20
    file_name = os.path.join(str(tmpdir), 'file.txt')
    expected_str = 'here ' * NUM_REQ

    f = (
        Flow(protocol=protocol)
            .add(name='first')
            .add(
            name='second',
            floating=True,
            uses=FloatingTestExecutor,
            uses_with={'file_name': file_name},
        )
    )

    with f:
        for j in range(NUM_REQ):
            start_time = time.time()
            ret = f.post(
                on='/default', inputs=DocList[LegacyDocument]([LegacyDocument(text='')])
            )
            end_time = time.time()
            assert (
                           end_time - start_time
                   ) < TIME_SLEEP_FLOATING  # check that the response arrives before the
            # Floating Executor finishes
            assert len(ret) == 1
            assert ret[0].text == ''

    with open(file_name, 'r', encoding='utf-8') as f:
        resulted_str = f.read()

    assert resulted_str == expected_str


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
def test_empty_input_output(protocol, ctxt_manager):
    if ctxt_manager == 'deployment' and protocol == 'websocket':
        return

    class Foo(Executor):
        @requests(on='/hello')
        def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
            for doc in docs:
                doc.text += 'Processed by foo'

    if ctxt_manager == 'flow':
        ctxt_mgr = Flow(protocol=protocol).add(uses=Foo)
    else:
        ctxt_mgr = Deployment(protocol=protocol, uses=Foo)

    with ctxt_mgr:
        ret = ctxt_mgr.post(on='/hello', inputs=DocList[TextDoc]())
        assert len(ret) == 0


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
def test_input_output_with_shaped_tensor(protocol, ctxt_manager):
    if ctxt_manager == 'deployment' and protocol == 'websocket':
        return

    class MyDoc(BaseDoc):
        text: str
        embedding: NdArray[128]

    class Foo(Executor):
        @requests(on='/hello')
        def foo(self, docs: DocList[MyDoc], **kwargs) -> DocList[MyDoc]:
            for doc in docs:
                doc.text += 'Processed by foo'

    if ctxt_manager == 'flow':
        ctxt_mgr = Flow(protocol=protocol).add(uses=Foo)
    else:
        ctxt_mgr = Deployment(protocol=protocol, uses=Foo)

    with ctxt_mgr:
        ret = ctxt_mgr.post(
            on='/hello',
            inputs=DocList[MyDoc]([MyDoc(text='', embedding=np.random.rand(128))]),
        )
        assert len(ret) == 1


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
def test_send_parameters(protocol, ctxt_manager):
    if ctxt_manager == 'deployment' and protocol == 'websocket':
        return

    class FooSendExecutor(Executor):
        @requests(on='/hello')
        def foo(self, docs: DocList[TextDoc], parameters, **kwargs) -> DocList[TextDoc]:
            for doc in docs:
                doc.text += f'Processed by foo with {parameters["param"]}'

    if ctxt_manager == 'flow':
        ctxt_mgr = Flow(protocol=protocol).add(uses=FooSendExecutor)
    else:
        ctxt_mgr = Deployment(protocol=protocol, uses=FooSendExecutor)

    with ctxt_mgr:
        ret = ctxt_mgr.post(
            on='/hello',
            parameters={'param': '5'},
            inputs=DocList[TextDoc]([TextDoc(text='')]),
        )
        assert len(ret) == 1
        assert ret[0].text == 'Processed by foo with 5'


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
def test_get_parameters_back(protocol, ctxt_manager):
    if ctxt_manager == 'deployment' and protocol == 'websocket':
        return

    class FooParams(Executor):
        @requests(on='/hello')
        def foo(self, parameters, **kwargs):
            return {'back': parameters}

    if ctxt_manager == 'flow':
        ctxt_mgr = Flow(protocol=protocol).add(uses=FooParams, name='foo')
    else:
        ctxt_mgr = Deployment(protocol=protocol, uses=FooParams, name='foo')

    with ctxt_mgr:
        ret = ctxt_mgr.post(
            on='/hello', parameters={'param': '5'}, return_responses=True
        )
        assert len(ret) == 1
        assert ret[0].parameters == {
            'param': '5',
            '__results__': {'foo/rep-0': {'back': {'param': '5'}}},
        }


@pytest.mark.parametrize('protocol', ['grpc', 'http'])
@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
def test_raise_exception(protocol, ctxt_manager):
    from jina.excepts import BadServer

    if ctxt_manager == 'deployment' and protocol == 'websocket':
        return

    class FooExcep(Executor):
        @requests(on='/hello')
        def foo(self, **kwargs):
            raise Exception('Raising some exception from Executor')

    if ctxt_manager == 'flow':
        ctxt_mgr = Flow(protocol=protocol).add(uses=FooExcep, name='foo')
    else:
        ctxt_mgr = Deployment(protocol=protocol, uses=FooExcep, name='foo')

    with ctxt_mgr:
        if protocol == 'http':
            with pytest.raises(ValueError) as excinfo:
                ctxt_mgr.post(
                    on='/hello', parameters={'param': '5'}, return_responses=True
                )
            assert excinfo.value.args[0] == {
                'detail': "Exception('Raising some exception from Executor')"
            }
        elif protocol == 'grpc':
            with pytest.raises(BadServer):
                ctxt_mgr.post(
                    on='/hello', parameters={'param': '5'}, return_responses=True
                )


def test_custom_gateway():
    from docarray import DocList

    from jina import Executor, Flow, requests
    from jina.serve.runtimes.gateway.http import FastAPIBaseGateway

    PARAMETERS = {'dog': 'woof'}

    class MyGateway(FastAPIBaseGateway):
        @property
        def app(self):
            from fastapi import FastAPI

            app = FastAPI(title='Custom FastAPI Gateway')

            @app.get('/endpoint_executor')
            async def get_executor(text: str):
                docs = DocList[TextDoc](
                    [
                        TextDoc(text=f'executor {text}'),
                        TextDoc(text=f'executor {text}'.upper()),
                    ]
                )
                resp = await self.executor['executor1'].post(
                    on='/',
                    inputs=docs,
                    parameters=PARAMETERS,
                    return_type=DocList[TextDoc],
                )
                assert resp.doc_type is TextDoc
                return {'result': [doc.text for doc in resp]}

            @app.get('/endpoint_stream_docs')
            async def get_endpoint_stream_docs(text: str):
                docs = DocList[TextDoc](
                    [
                        TextDoc(text=f'stream {text}'),
                        TextDoc(text=f'stream {text}'.upper()),
                    ]
                )
                async for resp in self.streamer.stream_docs(
                        docs,
                        parameters=PARAMETERS,
                        target_executor='executor1',
                        return_type=DocList[TextDoc],
                ):
                    assert resp.doc_type is TextDoc
                    return {'result': [doc.text for doc in resp]}

            @app.get('/endpoint_stream')
            async def get_endpoint_stream(text: str):
                docs = DocList[TextDoc](
                    [
                        TextDoc(text=f'stream {text}'),
                        TextDoc(text=f'stream {text}'.upper()),
                    ]
                )
                async for resp, _ in self.streamer.stream(
                        docs,
                        parameters=PARAMETERS,
                        target_executor='executor1',
                        return_type=DocList[TextDoc],
                ):
                    assert resp.doc_type is TextDoc
                    return {'result': [doc.text for doc in resp]}

            return app

    class FirstExec(Executor):
        @requests
        def func(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
            for doc in docs:
                doc.text += ' THIS SHOULD NOT HAVE HAPPENED!'

    class SecondExec(Executor):
        @requests
        def func(
                self, docs: DocList[TextDoc], parameters, **kwargs
        ) -> DocList[TextDoc]:
            for doc in docs:
                doc.text += f' Second(parameters={str(parameters)})'

    with Flow().config_gateway(uses=MyGateway, protocol='http').add(
            uses=FirstExec, name='executor0'
    ).add(uses=SecondExec, name='executor1') as flow:
        import requests

        r = requests.get(f'http://localhost:{flow.port}/endpoint_executor?text=meow')
        assert r.json()['result'] == [
            f'executor meow Second(parameters={str(PARAMETERS)})',
            f'EXECUTOR MEOW Second(parameters={str(PARAMETERS)})',
        ]

        r = requests.get(f'http://localhost:{flow.port}/endpoint_stream_docs?text=meow')
        assert r.json()['result'] == [
            f'stream meow Second(parameters={str(PARAMETERS)})',
            f'STREAM MEOW Second(parameters={str(PARAMETERS)})',
        ]

        r = requests.get(f'http://localhost:{flow.port}/endpoint_stream?text=meow')
        assert r.json()['result'] == [
            f'stream meow Second(parameters={str(PARAMETERS)})',
            f'STREAM MEOW Second(parameters={str(PARAMETERS)})',
        ]


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
def test_any_endpoint(protocol, ctxt_manager):
    if ctxt_manager == 'deployment' and protocol == 'websocket':
        return

    class FooAny(Executor):
        @requests
        def foo(self, docs: DocList[TextDoc], parameters, **kwargs) -> DocList[TextDoc]:
            for doc in docs:
                doc.text = 'Foo'

    if ctxt_manager == 'flow':
        ctxt_mgr = Flow(protocol=protocol).add(uses=FooAny, name='foo')
    else:
        ctxt_mgr = Deployment(protocol=protocol, uses=FooAny, name='foo')

    with ctxt_mgr:
        ret = ctxt_mgr.post(on='/index', inputs=DocList[TextDoc]([TextDoc(text='')]))
        assert len(ret) == 1
        assert ret[0].text == 'Foo'


def test_flow_compatible_with_default():
    class FirstCompatible(Executor):
        @requests
        def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[ImageDoc]:
            pass

    class SecondCompatible(Executor):
        @requests(on=['/index'])
        def foo(self, docs: DocList[ImageDoc], **kwargs) -> DocList[ImageDoc]:
            pass

    f = Flow().add(uses=FirstCompatible).add(uses=SecondCompatible)

    with f:
        pass


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
def test_flow_incompatible_linear(protocol):
    class First(Executor):
        @requests
        def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
            pass

    class Second(Executor):
        @requests
        def foo(self, docs: DocList[ImageDoc], **kwargs) -> DocList[ImageDoc]:
            pass

    f = Flow(protocol=protocol).add(uses=First).add(uses=Second)

    with pytest.raises(RuntimeFailToStart):
        with f:
            pass


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
def test_flow_compatible_different_exact_schema(protocol):
    from pydantic import Field

    class MyFirstDoc(BaseDoc):
        a: str = Field(default='My first default')

    class MySecondDoc(BaseDoc):
        a: str = Field(default='My second default')

    class FirstTestComp(Executor):
        @requests
        def foo(self, docs: DocList[MyFirstDoc], **kwargs) -> DocList[MyFirstDoc]:
            pass

    class SecondTestComp(Executor):
        @requests
        def foo(self, docs: DocList[MySecondDoc], **kwargs) -> DocList[MySecondDoc]:
            pass

    f = Flow(protocol=protocol).add(uses=FirstTestComp).add(uses=SecondTestComp)

    with f:
        pass


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
def test_wrong_schemas(ctxt_manager, protocol):
    if ctxt_manager == 'deployment' and protocol == 'websocket':
        return
    with pytest.raises(RuntimeError):

        class MyExec(Executor):
            @requests
            def foo(self, docs: TextDoc, **kwargs) -> DocList[TextDoc]:
                pass

    if ctxt_manager == 'flow':
        ctxt_mgr = Flow(protocol=protocol).add(
            uses='tests.integration.docarray_v2.wrong_schema_executor.WrongSchemaExec'
        )
    else:
        ctxt_mgr = Deployment(
            protocol=protocol,
            uses='tests.integration.docarray_v2.wrong_schema_executor.WrongSchemaExec',
        )

    with pytest.raises(RuntimeFailToStart):
        with ctxt_mgr:
            pass


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
def test_flow_incompatible_bifurcation(protocol):
    class First(Executor):
        @requests
        def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
            pass

    class Second(Executor):
        @requests
        def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[ImageDoc]:
            pass

    class Previous(Executor):
        @requests
        def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
            pass

    f = (
        Flow(protocol=protocol)
            .add(uses=Previous, name='previous')
            .add(uses=First, name='first', needs='previous')
            .add(uses=Second, name='second', needs='previous')
            .needs_all()
    )

    with pytest.raises(RuntimeFailToStart):
        with f:
            pass


class ExternalDeploymentDoc(BaseDoc):
    tags: Dict[str, str] = {}


@pytest.fixture(scope='function')
def input_docs():
    return DocList[ExternalDeploymentDoc]([ExternalDeploymentDoc() for _ in range(50)])


@pytest.fixture
def num_shards(request):
    return request.param


def _external_deployment_args(num_shards, port=None):
    from jina.parsers import set_deployment_parser

    args = [
        '--uses',
        'MyExternalExecutor',
        '--name',
        'external_real',
        '--port',
        str(port) if port else str(random_port()),
        '--host-in',
        '0.0.0.0',
        '--shards',
        str(num_shards),
        '--polling',
        'all',
    ]
    return set_deployment_parser().parse_args(args)


@pytest.fixture(scope='function')
def external_deployment_args(num_shards, port=None):
    return _external_deployment_args(num_shards, port)


@pytest.fixture
def external_deployment(external_deployment_args):
    return Deployment(external_deployment_args)


import uuid


class MyExternalExecutor(Executor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._id = str(uuid.uuid4())

    @requests(on='/index')
    def foo(self, docs, *args, **kwargs):
        for doc in docs:
            doc.tags['name'] = self.runtime_args.name
            doc.tags['uuid'] = self._id


@pytest.mark.parametrize('num_shards', [1, 2], indirect=True)
@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
def test_flow_with_external_deployment(
        external_deployment, external_deployment_args, input_docs, num_shards, protocol
):
    with external_deployment:
        external_args = vars(external_deployment_args)
        del external_args['name']
        del external_args['external']
        del external_args['deployment_role']
        flow = Flow(protocol=protocol).add(
            **external_args,
            name='external_fake',
            external=True,
        )
        with flow:
            resp = flow.index(inputs=input_docs)

        assert len(resp) == len(input_docs)
        assert len(resp) > 0
        for doc in resp:
            assert 'external_real' in doc.tags['name']


@pytest.mark.parametrize('protocols', [['grpc'], ['http'], ['grpc', 'http']])
@pytest.mark.parametrize('replicas', [1, 3])
def test_deployments(protocols, replicas):
    class InputDoc(BaseDoc):
        img: ImageDoc

    class OutputDoc(BaseDoc):
        embedding: AnyTensor

    class MyExecD(Executor):
        @requests(on='/bar')
        def bar(self, docs: DocList[InputDoc], **kwargs) -> DocList[OutputDoc]:
            docs_return = DocList[OutputDoc](
                [OutputDoc(embedding=np.zeros((100, 1))) for _ in range(len(docs))]
            )
            return docs_return

    ports = [random_port() for _ in protocols]
    with Deployment(port=ports, protocol=protocols, replicas=replicas, uses=MyExecD):
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/bar',
                inputs=InputDoc(img=ImageDoc(tensor=np.zeros((3, 224, 224)))),
                return_type=DocList[OutputDoc],
            )
            assert docs[0].embedding.shape == (100, 1)
            assert docs.__class__.doc_type == OutputDoc


@pytest.mark.parametrize('protocols', [['grpc'], ['http'], ['grpc', 'http']])
@pytest.mark.parametrize('replicas', [1, 3])
@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
def test_serve_complex_model(protocols, replicas, ctxt_manager):
    class InputComplexDoc(BaseDoc):
        img: ImageDoc

    class OutputComplexDoc(BaseDoc):
        tensor: Optional[AnyTensor]
        url: ImageUrl
        lll: List[List[List[int]]] = [[[5]]]
        fff: List[List[List[float]]] = [[[5.2]]]
        single_text: TextDoc
        texts: DocList[TextDoc]
        d: Dict[str, str] = {'a': 'b'}
        u: Union[str, int]
        lu: List[Union[str, int]] = [0, 1, 2]

    class MyComplexServeExec(Executor):
        @requests(on='/bar')
        def bar(
                self, docs: DocList[InputComplexDoc], **kwargs
        ) -> DocList[OutputComplexDoc]:
            docs_return = DocList[OutputComplexDoc](
                [
                    OutputComplexDoc(
                        url='photo.jpg',
                        lll=[[[40]]],
                        fff=[[[40.2]]],
                        d={'b': 'a'},
                        texts=DocList[TextDoc](
                            [TextDoc(text='hey ha', embedding=np.zeros(3))]
                        ),
                        single_text=TextDoc(
                            text='single hey ha', embedding=np.zeros(2)
                        ),
                        u='a',
                        lu=[3, 4],
                    )
                    for _ in range(len(docs))
                ]
            )
            return docs_return

    ports = [random_port() for _ in protocols]
    if ctxt_manager == 'flow':
        ctxt = Flow(port=ports, protocol=protocols).add(
            replicas=replicas, uses=MyComplexServeExec
        )
    else:
        ctxt = Deployment(
            port=ports, protocol=protocols, replicas=replicas, uses=MyComplexServeExec
        )
    with ctxt:
        for port, protocol in zip(ports, protocols):
            c = Client(port=port, protocol=protocol)
            docs = c.post(
                on='/bar',
                inputs=InputComplexDoc(img=ImageDoc(tensor=np.zeros((3, 224, 224)))),
                return_type=DocList[OutputComplexDoc],
            )
            assert docs[0].url == 'photo.jpg'
            assert docs[0].lll == [[[40]]]
            assert docs[0].fff == [[[40.2]]]
            assert docs[0].d == {'b': 'a'}
            assert docs[0].u == 'a'
            assert docs[0].lu == ['3', '4']
            assert len(docs[0].texts) == 1
            assert docs[0].single_text.text == 'single hey ha'
            assert docs[0].single_text.embedding.shape == (2,)
            assert len(docs[0].texts) == 1
            assert docs[0].texts[0].text == 'hey ha'
            assert docs[0].texts[0].embedding.shape == (3,)


def test_deployments_with_shards_one_shard_fails():
    from docarray import DocList
    from docarray.documents import TextDoc

    class TextDocWithId(TextDoc):
        id: str

    class KVTestIndexer(Executor):
        """Simulates an indexer where one shard would fail"""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._docs_dict = {}

        @requests(on=['/index'])
        def index(
                self, docs: DocList[TextDocWithId], **kwargs
        ) -> DocList[TextDocWithId]:
            for doc in docs:
                self._docs_dict[doc.id] = doc

        @requests(on=['/search'])
        def search(
                self, docs: DocList[TextDocWithId], **kwargs
        ) -> DocList[TextDocWithId]:
            for doc in docs:
                doc.text = self._docs_dict[doc.id].text

    with Deployment(uses=KVTestIndexer, shards=2) as dep:
        index_da = DocList[TextDocWithId](
            [TextDocWithId(id=f'{i}', text=f'ID {i}') for i in range(100)]
        )
        dep.index(inputs=index_da, request_size=1, return_type=DocList[TextDocWithId])
        responses = dep.search(
            inputs=index_da, request_size=1, return_type=DocList[TextDocWithId]
        )
        for q, r in zip(index_da, responses):
            assert q.text == r.text


def test_issue_shards_missmatch_endpoint_and_shard_with_lists():
    class MyDoc(BaseDoc):
        text: str
        embedding: NdArray[128]

    class MyDocWithMatchesAndScores(MyDoc):
        matches: DocList[MyDoc]
        scores: List[float]

    class MyExecIssueShards(Executor):
        @requests(on='/search')
        def foo(
                self, docs: DocList[MyDoc], **kwargs
        ) -> DocList[MyDocWithMatchesAndScores]:
            res = DocList[MyDocWithMatchesAndScores]()
            for doc in docs:
                new_doc = MyDocWithMatchesAndScores(
                    id=doc.id,
                    text=doc.text,
                    embedding=doc.embedding,
                    matches=[MyDoc(text='m', embedding=np.random.rand(128))],
                    scores=[1.0 for _ in docs],
                )
                res.append(new_doc)
            return res

    d = Deployment(uses=MyExecIssueShards, shards=2)
    with d:
        res = d.post(
            on='/search',
            inputs=DocList[MyDoc](
                [MyDoc(text='hey ha', embedding=np.random.rand(128))]
            ),
            return_type=DocList[MyDocWithMatchesAndScores],
        )
        assert len(res) == 1
        for doc in res:
            assert len(doc.scores) == 2
            assert len(doc.matches) == 2


@pytest.mark.parametrize('protocol', ['grpc', 'http'])
def test_closing_executor(tmpdir, protocol):
    class ClosingExec(Executor):
        def __init__(self, file_path, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._file_path = file_path

        def close(self) -> None:
            with open(self._file_path, 'w') as f:
                f.write('I closed')

    file_path = f'{str(tmpdir)}/file.txt'
    d = Deployment(
        uses=ClosingExec, uses_with={'file_path': file_path}, protocol=protocol
    )
    with d:
        pass

    with open(file_path, 'r') as f:
        r = f.read()
    assert r == 'I closed'


def test_issue_dict_docs_http():
    class AuxDoc(BaseDoc):
        a: str

    class TagsDoc(BaseDoc):
        tags: Dict[str, Any] = dict()
        aux: AuxDoc

    class TagsDocExecutor(Executor):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

        @requests(on=['/index'])
        async def filter(self, docs: DocList[TagsDoc], **kwargs) -> DocList[TagsDoc]:
            for doc in docs:
                doc.aux.a = 'b'
                doc.tags = {'a': {'b': 1}}
            return docs

    f = Flow(protocol='http').add(uses=TagsDocExecutor)
    doc1 = TagsDoc(aux=AuxDoc(a='a'))

    with f:
        res = f.post(on='/index', inputs=doc1, return_type=DocList[TagsDoc])
        assert len(res) == 1
        for doc in res:
            assert doc.aux.a == 'b'
            assert doc.tags == {'a': {'b': 1}}


def test_issue_with_monitoring():
    class InputDocMonitor(BaseDoc):
        text: str

    class OutputDocMonitor(BaseDoc):
        price: int

    class MonitorExecTest(Executor):
        @requests
        def foo(
                self, docs: DocList[InputDocMonitor], **kwargs
        ) -> DocList[OutputDocMonitor]:
            ret = DocList[OutputDocMonitor]()
            for doc in docs:
                ret.append(OutputDocMonitor(price=2))
            return ret

    f = Flow(monitoring=True).add(uses=MonitorExecTest, monitoring=True)
    with f:
        ret = f.post(
            on='/',
            inputs=DocList[InputDocMonitor]([InputDocMonitor(text='2')]),
            return_type=DocList[OutputDocMonitor],
        )
        assert len(ret) == 1
        assert ret[0].price == 2


@pytest.mark.parametrize('ctxt_manager', ['flow', 'deployment'])
@pytest.mark.parametrize('include_gateway', [False, True])
def test_doc_with_examples(ctxt_manager, include_gateway):
    if ctxt_manager == 'flow' and include_gateway:
        return
    import random
    import string

    random_example = ''.join(random.choices(string.ascii_letters, k=10))
    random_description = ''.join(random.choices(string.ascii_letters, k=10))
    from pydantic.fields import Field

    class MyDocWithExample(BaseDoc):
        """This test should be in description"""

        t: str = Field(examples=[random_example], description=random_description)

        class Config:
            title: str = 'MyDocWithExampleTitle'
            schema_extra: Dict = {'extra_key': 'extra_value'}

    class MyExecDocWithExample(Executor):
        @requests
        def foo(
                self, docs: DocList[MyDocWithExample], **kwargs
        ) -> DocList[MyDocWithExample]:
            pass

    port = random_port()

    if ctxt_manager == 'flow':
        ctxt = Flow(protocol='http', port=port).add(uses=MyExecDocWithExample)
    else:
        ctxt = Deployment(
            uses=MyExecDocWithExample,
            protocol='http',
            port=port,
            include_gateway=include_gateway,
        )

    with ctxt:
        import requests as general_requests

        resp = general_requests.get(f'http://localhost:{port}/openapi.json')
        resp_str = str(resp.json())
        assert random_example in resp_str
        assert random_description in resp_str
        assert 'This test should be in description' in resp_str
        assert 'MyDocWithExampleTitle' in resp_str
        assert 'extra_key' in resp_str


def test_issue_fastapi_multiple_models_same_name():
    class MyRandomModel(BaseDoc):
        a: str

    class MyInputModel(BaseDoc):
        b: Optional[MyRandomModel] = None

    class MyFailingExecutor(Executor):
        @requests(on='/generate')
        def generate(
                self, docs: DocList[MyInputModel], **kwargs
        ) -> DocList[MyRandomModel]:
            return DocList[MyRandomModel]([doc.b for doc in docs])

    with Flow(protocol='http').add(uses=MyFailingExecutor) as f:
        res = f.post(
            on='/generate',
            inputs=[MyInputModel(b=MyRandomModel(a='hey'))],
            return_type=DocList[MyRandomModel],
        )
        assert res[0].a == 'hey'


@pytest.mark.repeat(10)
def test_exception_handling_in_dynamic_batch():
    from jina.proto import jina_pb2

    class DummyEmbeddingDoc(BaseDoc):
        lf: List[float] = []

    class SlowExecutorWithException(Executor):

        @dynamic_batching(preferred_batch_size=3, timeout=1000)
        @requests(on='/foo')
        def foo(self, docs: DocList[TextDoc], **kwargs) -> DocList[DummyEmbeddingDoc]:
            ret = DocList[DummyEmbeddingDoc]()
            for doc in docs:
                if doc.text == 'fail':
                    raise Exception('Fail is in the Batch')
                ret.append(DummyEmbeddingDoc(lf=[0.1, 0.2, 0.3]))
            return ret

    depl = Deployment(uses=SlowExecutorWithException)

    with depl:
        da = DocList[TextDoc]([TextDoc(text=f'good-{i}') for i in range(50)])
        da[4].text = 'fail'
        responses = depl.post(
            on='/foo',
            inputs=da,
            request_size=1,
            return_responses=True,
            continue_on_error=True,
            results_in_order=True,
        )
        assert len(responses) == 50  # 1 request per input
        num_failed_requests = 0
        for r in responses:
            if r.header.status.code == jina_pb2.StatusProto.StatusCode.ERROR:
                num_failed_requests += 1

        assert 1 <= num_failed_requests <= 3  # 3 requests in the dynamic batch failing
