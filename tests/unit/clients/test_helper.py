import json
from typing import Any, Dict, List, Optional, Tuple

import pytest

from jina import Executor, Flow, requests
from jina.clients.base.grpc import client_grpc_options
from jina.clients.base.helper import HTTPClientlet, WebsocketClientlet
from jina.clients.request.helper import _new_data_request
from jina.excepts import BadServer
from jina.logging.logger import JinaLogger
from jina.serve.helper import get_default_grpc_options
from jina.types.request.data import DataRequest

logger = JinaLogger('clientlet')


class ClientTestExecutor(Executor):
    @requests
    def error(self, **kwargs):
        raise NotImplementedError


@pytest.fixture
def flow_with_exception_request():
    return Flow().add(uses=ClientTestExecutor).add()


@pytest.mark.asyncio
async def test_http_clientlet():
    from jina.helper import random_port

    port = random_port()
    with Flow(port=port, protocol='http').add():
        async with HTTPClientlet(
            logger=logger
        ) as iolet:
            request = _new_data_request('/', None, {'a': 'b'})
            assert request.header.target_executor == ''
            r_status, r_json = await iolet.send_message(url=f'http://localhost:{port}/post', request=request)
            response = DataRequest(r_json)
    assert response.header.exec_endpoint == '/'
    assert response.parameters == {'a': 'b'}


@pytest.mark.asyncio
async def test_http_clientlet_target():
    from jina.helper import random_port

    port = random_port()
    with Flow(port=port, protocol='http').add():
        async with HTTPClientlet(
            logger=logger
        ) as iolet:
            request = _new_data_request('/', 'nothing', {'a': 'b'})
            assert request.header.target_executor == 'nothing'
            r = await iolet.send_message(url=f'http://localhost:{port}/post', request=request)
            r_status, r_json = r
            response = DataRequest(r_json)
    assert response.header.exec_endpoint == '/'
    assert response.parameters == {'a': 'b'}


@pytest.mark.asyncio
async def test_websocket_clientlet():
    with pytest.raises(ConnectionError):
        async with WebsocketClientlet(url='ws://localhost:12345', logger=logger):
            pass


def test_client_behaviour(flow_with_exception_request, mocker):
    on_done_mock = mocker.Mock()
    on_always_mock = mocker.Mock()
    on_error_mock = None

    with pytest.raises(BadServer):
        with flow_with_exception_request as f:
            f.post(
                '',
                on_done=on_done_mock,
                on_error=on_error_mock,
                on_always=on_always_mock,
            )
        on_always_mock.assert_called_once()
        on_done_mock.assert_not_called()


def _get_grpc_service_config_json(
    options: List[Tuple[str, Any]]
) -> Optional[Dict[str, Any]]:
    for tup in options:
        if tup[0] == 'grpc.service_config':
            return json.loads(tup[1])

    return None


@pytest.mark.parametrize('max_attempts', [-1, 1, 2])
@pytest.mark.parametrize('grpc_options', [None, {"grpc.keepalive_time_ms": 9999}])
def test_client_grpc_options(max_attempts, grpc_options):
    default_options = get_default_grpc_options()
    backoff_multiplier = 1.5
    initial_backoff = 0.5
    max_backoff = 5
    options = client_grpc_options(
        backoff_multiplier=backoff_multiplier,
        initial_backoff=initial_backoff,
        max_attempts=max_attempts,
        max_backoff=max_backoff,
        args_channel_options=grpc_options,
    )
    assert len(options) >= len(default_options)
    if grpc_options and max_attempts <= 1:
        assert len(default_options) + 1 == len(options)
    elif grpc_options and max_attempts > 1:
        assert len(default_options) + 3 == len(options)
    elif not grpc_options and max_attempts <= 1:
        assert len(options) == len(default_options)
    elif not grpc_options and max_attempts > 1:
        assert len(default_options) + 2 == len(options)

    if max_attempts <= 1:
        assert not _get_grpc_service_config_json(options)
    else:
        service_config_json = _get_grpc_service_config_json(options)
        retry_config = service_config_json['methodConfig'][0]
        assert retry_config['name'] == [{}]
        assert retry_config['retryPolicy'] == {
            'maxAttempts': max_attempts,
            'initialBackoff': f'{initial_backoff}s',
            'backoffMultiplier': backoff_multiplier,
            'maxBackoff': f'{max_backoff}s',
            'retryableStatusCodes': ['UNAVAILABLE', 'DEADLINE_EXCEEDED', 'INTERNAL'],
        }
