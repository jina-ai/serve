import pytest
from typing import List
from docarray.documents import ImageDoc, TextDoc
from docarray import BaseDoc, DocList

from jina import Deployment, Executor, Flow, requests, dynamic_batching
from jina.excepts import RuntimeFailToStart


@pytest.mark.parametrize('protocol', ['http'])
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


@pytest.mark.parametrize('protocol', ['http'])
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


@pytest.mark.parametrize('protocol', ['http'])
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


@pytest.mark.parametrize('protocol', ['http'])
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

    depl = Deployment(uses=SlowExecutorWithException, include_gateway=False)

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
