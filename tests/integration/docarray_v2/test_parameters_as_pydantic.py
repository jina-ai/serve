from typing import Dict

import pytest
from docarray import BaseDoc, DocList
from docarray.documents import TextDoc
from pydantic import BaseModel

from jina import Deployment, Executor, Flow, requests
from jina.helper import random_port


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
@pytest.mark.parametrize('parameters_in_client', ['dict', 'model'])
def test_parameters_as_pydantic(protocol, ctxt_manager, parameters_in_client):
    if ctxt_manager == 'deployment' and protocol == 'websocket':
        return

    class Parameters(BaseModel):
        param: str
        num: int = 5

    class FooParameterExecutor(Executor):
        @requests(on='/hello')
        def foo(
                self, docs: DocList[TextDoc], parameters: Parameters, **kwargs
        ) -> DocList[TextDoc]:
            for doc in docs:
                doc.text += f'Processed by foo with param: {parameters.param} and num: {parameters.num}'

        @requests(on='/hello_single')
        def bar(self, doc: TextDoc, parameters: Parameters, **kwargs) -> TextDoc:
            doc.text = f'Processed by bar with param: {parameters.param} and num: {parameters.num}'

    if ctxt_manager == 'flow':
        ctxt_mgr = Flow(protocol=protocol).add(uses=FooParameterExecutor)
    else:
        ctxt_mgr = Deployment(protocol=protocol, uses=FooParameterExecutor)

    params_to_send = (
        {'param': 'value'}
        if parameters_in_client == 'dict'
        else Parameters(param='value')
    )
    with ctxt_mgr:
        ret = ctxt_mgr.post(
            on='/hello',
            parameters=params_to_send,
            inputs=DocList[TextDoc]([TextDoc(text='')]),
        )
        assert len(ret) == 1
        assert ret[0].text == 'Processed by foo with param: value and num: 5'

        ret = ctxt_mgr.post(
            on='/hello_single',
            parameters=params_to_send,
            inputs=DocList[TextDoc]([TextDoc(text='')]),
        )
        assert len(ret) == 1
        assert ret[0].text == 'Processed by bar with param: value and num: 5'
        if protocol == 'http':
            import requests as global_requests

            for endpoint in {'hello', 'hello_single'}:
                processed_by = 'foo' if endpoint == 'hello' else 'bar'
                url = f'http://localhost:{ctxt_mgr.port}/{endpoint}'
                myobj = {'data': {'text': ''}, 'parameters': {'param': 'value'}}
                resp = global_requests.post(url, json=myobj)
                resp_json = resp.json()
                assert (
                        resp_json['data'][0]['text']
                        == f'Processed by {processed_by} with param: value and num: 5'
                )
                myobj = {'data': [{'text': ''}], 'parameters': {'param': 'value'}}
                resp = global_requests.post(url, json=myobj)
                resp_json = resp.json()
                assert (
                        resp_json['data'][0]['text']
                        == f'Processed by {processed_by} with param: value and num: 5'
                )


@pytest.mark.parametrize('protocol', ['http', 'websocket', 'grpc'])
@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
def test_parameters_invalid(protocol, ctxt_manager):
    # TODO: websocket test is failing with flow as well
    if protocol == 'websocket':
        return

    class Parameters(BaseModel):
        param: str
        num: int

    class FooInvalidParameterExecutor(Executor):
        @requests(on='/hello')
        def foo(
                self, docs: DocList[TextDoc], parameters: Parameters, **kwargs
        ) -> DocList[TextDoc]:
            for doc in docs:
                doc.text += f'Processed by foo with param: {parameters.param} and num: {parameters.num}'

    if ctxt_manager == 'flow':
        ctxt_mgr = Flow(protocol=protocol).add(uses=FooInvalidParameterExecutor)
    else:
        ctxt_mgr = Deployment(protocol=protocol, uses=FooInvalidParameterExecutor)

    params_to_send = {'param': 'value'}
    with ctxt_mgr:
        with pytest.raises(Exception):
            _ = ctxt_mgr.post(
                on='/hello',
                parameters=params_to_send,
                inputs=DocList[TextDoc]([TextDoc(text='')]),
            )


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
def test_parameters_as_pydantic_in_flow_only_first(protocol):
    class Input1(BaseDoc):
        text: str

    class Output1(BaseDoc):
        price: int

    class Output2(BaseDoc):
        a: str

    class ParametersFirst(BaseModel):
        mult: int

    class Exec1Chain(Executor):
        @requests(on='/bar')
        def bar(
                self, docs: DocList[Input1], parameters: ParametersFirst, **kwargs
        ) -> DocList[Output1]:
            docs_return = DocList[Output1](
                [Output1(price=5 * parameters.mult) for _ in range(len(docs))]
            )
            return docs_return

    class Exec2Chain(Executor):
        @requests(on='/bar')
        def bar(self, docs: DocList[Output1], **kwargs) -> DocList[Output2]:
            docs_return = DocList[Output2](
                [Output2(a=f'final price {docs[0].price}') for _ in range(len(docs))]
            )
            return docs_return

    f = Flow(protocol=protocol).add(uses=Exec1Chain).add(uses=Exec2Chain)
    with f:
        docs = f.post(
            on='/bar',
            inputs=Input1(text='ignored'),
            parameters={'mult': 10},
            return_type=DocList[Output2],
        )
        assert docs[0].a == 'final price 50'


@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
def test_parameters_as_pydantic_in_flow_second(protocol):
    class Input1(BaseDoc):
        text: str

    class Output1(BaseDoc):
        price: int

    class Output2(BaseDoc):
        a: str

    class ParametersSecond(BaseModel):
        mult: int

    class Exec1Chain(Executor):
        @requests(on='/bar')
        def bar(self, docs: DocList[Input1], **kwargs) -> DocList[Output1]:
            docs_return = DocList[Output1]([Output1(price=5) for _ in range(len(docs))])
            return docs_return

    class Exec2Chain(Executor):
        @requests(on='/bar')
        def bar(
                self, docs: DocList[Output1], parameters: ParametersSecond, **kwargs
        ) -> DocList[Output2]:
            docs_return = DocList[Output2](
                [
                    Output2(a=f'final price {docs[0].price * parameters.mult}')
                    for _ in range(len(docs))
                ]
            )
            return docs_return

    f = Flow(protocol=protocol).add(uses=Exec1Chain).add(uses=Exec2Chain)
    with f:
        docs = f.post(
            on='/bar',
            inputs=Input1(text='ignored'),
            parameters={'mult': 10},
            return_type=DocList[Output2],
        )
        assert docs[0].a == 'final price 50'


@pytest.mark.parametrize('ctxt_manager', ['flow', 'deployment'])
@pytest.mark.parametrize('include_gateway', [False, True])
def test_openai(ctxt_manager, include_gateway):
    if ctxt_manager == 'flow' and include_gateway:
        return
    import random
    import string

    random_example = ''.join(random.choices(string.ascii_letters, k=10))
    random_description = ''.join(random.choices(string.ascii_letters, k=10))
    from pydantic import BaseModel
    from pydantic.fields import Field

    class MyDocWithExample(BaseDoc):
        """This test should be in description"""

        t: str = Field(examples=[random_example], description=random_description)

        class Config:
            title: str = 'MyDocWithExampleTitle'
            schema_extra: Dict = {'extra_key': 'extra_value'}

    class MyConfigParam(BaseModel):
        """Configuration for Executor endpoint"""

        param1: int = Field(description='batch size', example=256)

    class MyExecDocWithExample(Executor):
        @requests
        def foo(
                self, docs: DocList[MyDocWithExample], parameters: MyConfigParam, **kwargs
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
        assert 'MyConfigParam' in resp_str
        assert 'Configuration for Executor endpoint' in resp_str
        assert 'batch size' in resp_str
        assert '256' in resp_str


@pytest.mark.parametrize('ctxt_manager', ['deployment', 'flow'])
def test_parameters_all_default_not_required(ctxt_manager):
    class DefaultParameters(BaseModel):
        param: str = 'default'
        num: int = 5

    class DefaultParamExecutor(Executor):
        @requests(on='/hello')
        def foo(
            self, docs: DocList[TextDoc], parameters: DefaultParameters, **kwargs
        ) -> DocList[TextDoc]:
            for doc in docs:
                doc.text += f'Processed by foo with param: {parameters.param} and num: {parameters.num}'

        @requests(on='/hello_single')
        def bar(self, doc: TextDoc, parameters: DefaultParameters, **kwargs) -> TextDoc:
            doc.text = f'Processed by bar with param: {parameters.param} and num: {parameters.num}'

    if ctxt_manager == 'flow':
        ctxt_mgr = Flow(protocol='http').add(uses=DefaultParamExecutor)
    else:
        ctxt_mgr = Deployment(protocol='http', uses=DefaultParamExecutor)

    with ctxt_mgr:
        ret = ctxt_mgr.post(
            on='/hello',
            inputs=DocList[TextDoc]([TextDoc(text='')]),
        )
        assert len(ret) == 1
        assert ret[0].text == 'Processed by foo with param: default and num: 5'

        ret = ctxt_mgr.post(
            on='/hello_single',
            inputs=DocList[TextDoc]([TextDoc(text='')]),
        )
        assert len(ret) == 1
        assert ret[0].text == 'Processed by bar with param: default and num: 5'
        import requests as global_requests

        for endpoint in {'hello', 'hello_single'}:
            processed_by = 'foo' if endpoint == 'hello' else 'bar'
            url = f'http://localhost:{ctxt_mgr.port}/{endpoint}'
            myobj = {'data': {'text': ''}}
            resp = global_requests.post(url, json=myobj)
            resp_json = resp.json()
            assert (
                    resp_json['data'][0]['text']
                    == f'Processed by {processed_by} with param: default and num: 5'
            )
            myobj = {'data': [{'text': ''}]}
            resp = global_requests.post(url, json=myobj)
            resp_json = resp.json()
            assert (
                    resp_json['data'][0]['text']
                    == f'Processed by {processed_by} with param: default and num: 5'
            )
