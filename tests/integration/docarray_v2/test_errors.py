import pytest
from docarray import DocList
from docarray.documents import ImageDoc, TextDoc

from jina import Deployment, Executor, Flow, requests
from jina.excepts import RuntimeFailToStart


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
