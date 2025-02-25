import os
import time

import pytest
import requests

from jina import Deployment, Executor, Flow, helper
from jina import requests as req
from jina.clients import Client
from jina.orchestrate.pods.factory import PodFactory
from jina.parsers import set_gateway_parser
from tests import random_docs

cur_dir = os.path.dirname(os.path.abspath(__file__))


@pytest.fixture(scope='function')
def flow():
    return Flow(protocol='grpc').add()


@pytest.fixture(scope='function')
def flow_with_websocket():
    return Flow(protocol='websocket').add()


@pytest.fixture(scope='function')
def flow_with_http():
    return Flow(protocol='http').add()


@pytest.fixture(scope='function')
def test_img_1():
    return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAA2ElEQVR4nADIADf/AxWcWRUeCEeBO68T3u1qLWarHqMaxDnxhAEaLh0Ssu6ZGfnKcjP4CeDLoJok3o4aOPYAJocsjktZfo4Z7Q/WR1UTgppAAdguAhR+AUm9AnqRH2jgdBZ0R+kKxAFoAME32BL7fwQbcLzhw+dXMmY9BS9K8EarXyWLH8VYK1MACkxlLTY4Eh69XfjpROqjE7P0AeBx6DGmA8/lRRlTCmPkL196pC0aWBkVs2wyjqb/LABVYL8Xgeomjl3VtEMxAeaUrGvnIawVh/oBAAD///GwU6v3yCoVAAAAAElFTkSuQmCC'


@pytest.fixture(scope='function')
def test_img_2():
    return 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAgAAAAICAIAAABLbSncAAAA2ElEQVR4nADIADf/AvdGjTZeOlQq07xSYPgJjlWRwfWEBx2+CgAVrPrP+O5ghhOa+a0cocoWnaMJFAsBuCQCgiJOKDBcIQTiLieOrPD/cp/6iZ/Iu4HqAh5dGzggIQVJI3WqTxwVTDjs5XJOy38AlgHoaKgY+xJEXeFTyR7FOfF7JNWjs3b8evQE6B2dTDvQZx3n3Rz6rgOtVlaZRLvR9geCAxuY3G+0mepEAhrTISES3bwPWYYi48OUrQOc//IaJeij9xZGGmDIG9kc73fNI7eA8VMBAAD//0SxXMMT90UdAAAAAElFTkSuQmCC'


@pytest.mark.parametrize(
    'port, route, status_code',
    [(helper.random_port(), '/status', 200), (helper.random_port(), '/api/ass', 404)],
)
def test_gateway_ready(port, route, status_code):
    p = set_gateway_parser().parse_args(
        [
            '--port',
            str(port),
            '--protocol',
            'http',
            '--graph-description',
            '{}',
            '--deployments-addresses',
            '{}',
        ]
    )
    with PodFactory.build_pod(p):
        time.sleep(0.5)
        a = requests.get(f'http://localhost:{port}{route}')
    assert a.status_code == status_code


def test_gateway_index(flow_with_http, test_img_1, test_img_2):
    with flow_with_http:
        time.sleep(0.5)
        r = requests.post(
            f'http://localhost:{flow_with_http.port}/index',
            json={'data': {'docs': [{'uri': test_img_1}, {'uri': test_img_2}]}},
        )

    assert r.status_code == 200
    resp = r.json()
    assert 'data' in resp
    assert len(resp['data']) == 2
    assert resp['data'][0]['uri'] == test_img_1


# Timeout is necessary to fail in case of hanging client requests
@pytest.mark.timeout(60)
def test_client_websocket(mocker, flow_with_websocket):
    with flow_with_websocket:
        time.sleep(0.5)
        client = Client(
            host='localhost',
            port=str(flow_with_websocket.port),
            protocol='websocket',
        )
        # Test that a regular index request triggers the correct callbacks
        on_always_mock = mocker.Mock()
        on_error_mock = mocker.Mock()
        on_done_mock = mocker.Mock()
        client.post(
            '',
            random_docs(1),
            request_size=1,
            on_always=on_always_mock,
            on_error=on_error_mock,
            on_done=on_done_mock,
            return_responses=True,
        )
        on_always_mock.assert_called_once()
        on_done_mock.assert_called_once()
        on_error_mock.assert_not_called()


@pytest.mark.parametrize('protocol', ['websocket', 'grpc', 'http'])
def test_client_from_kwargs(protocol):
    Client(port=12345, host='0.0.0.1', protocol=protocol)


@pytest.mark.parametrize('protocol', ['websocket', 'grpc', 'http'])
def test_independent_client(protocol):
    with Flow(protocol=protocol) as f:
        c = Client(
            host='localhost',
            port=f.port,
            protocol=protocol,
        )
        assert type(c) == type(f.client)
        c.post('/')


class MyExec(Executor):
    @req
    def foo(self, docs, **kwargs):
        pass


@pytest.mark.slow
@pytest.mark.parametrize('protocol', ['http', 'websocket', 'grpc'])
@pytest.mark.parametrize('use_stream', [True, False])
def test_all_sync_clients(protocol, mocker, use_stream):
    f = Flow(protocol=protocol).add(uses=MyExec)
    docs = list(random_docs(1000))
    m1 = mocker.Mock()
    m2 = mocker.Mock()
    m3 = mocker.Mock()
    m4 = mocker.Mock()
    with f:
        c = Client(
            host='localhost',
            port=f.port,
            protocol=protocol,
        )
        c.post('/', on_done=m1, stream=use_stream)
        c.post('/foo', docs, on_done=m2, stream=use_stream)
        c.post('/foo', on_done=m3, stream=use_stream)
        c.post(
            '/foo', docs, parameters={'hello': 'world'}, on_done=m4, stream=use_stream
        )

    m1.assert_called_once()
    m2.assert_called()
    m3.assert_called_once()
    m4.assert_called()

@pytest.mark.slow
@pytest.mark.parametrize('use_stream', [True, False])
def test_deployment_sync_client(mocker, use_stream):
    dep = Deployment(uses=MyExec)
    docs = list(random_docs(1000))
    m1 = mocker.Mock()
    m2 = mocker.Mock()
    m3 = mocker.Mock()
    m4 = mocker.Mock()
    with dep:
        c = Client(
            host='localhost',
            port=dep.port,
        )
        c.post('/', on_done=m1, stream=use_stream)
        c.post('/foo', docs, on_done=m2, stream=use_stream)
        c.post('/foo', on_done=m3, stream=use_stream)
        c.post(
            '/foo', docs, parameters={'hello': 'world'}, on_done=m4, stream=use_stream
        )

    m1.assert_called_once()
    m2.assert_called()
    m3.assert_called_once()
    m4.assert_called()
