import multiprocessing
import os

import pytest

from jina import Deployment, DocumentArray, Flow
from jina.clients import Client
from jina.clients.base.retry import wait_or_raise_err, sync_wait_or_raise_err
from tests import random_docs

cur_dir = os.path.dirname(os.path.abspath(__file__))


def _random_post_request(client, on_error_mock, use_stream):
    return client.post(
        '/',
        random_docs(1),
        request_size=1,
        max_attempts=10,
        initial_backoff=0.5,
        max_backoff=6,
        on_error=on_error_mock,
        stream=use_stream,
    )


def _start_runtime(protocol, port, flow_or_deployment, stop_event, start_event=None):
    cntx = (
        Flow(protocol=protocol, port=port)
        if flow_or_deployment == 'flow'
        else Deployment(include_gateway=True, protocol=protocol, port=port)
    )
    with cntx:
        if start_event:
            start_event.set()
        cntx.block(stop_event)


@pytest.mark.skipif("GITHUH_WORKFLOWS" in os.environ, reason="Flaky in GH Actions")
@pytest.mark.timeout(90)
def test_grpc_stream_transient_error_iterable_input(port_generator, mocker):
    random_port = port_generator()
    stop_event = multiprocessing.Event()
    start_event = multiprocessing.Event()
    t = multiprocessing.Process(
        target=_start_runtime,
        args=('grpc', random_port, 'flow', stop_event, start_event),
    )
    t.start()
    start_event.wait(5)
    max_attempts = 5
    initial_backoff = 0.8
    backoff_multiplier = 1.5
    max_backoff = 5
    try:
        client = Client(host=f'grpc://localhost:{random_port}')

        for attempt in range(1, max_attempts + 1):
            try:
                on_error_mock = mocker.Mock()
                response = client.post(
                    '/',
                    random_docs(1),
                    request_size=1,
                    on_error=on_error_mock,
                    return_responses=True,
                    timeout=0.5,
                )
                assert len(response) == 1

                on_error_mock.assert_not_called()
            except ConnectionError as err:
                sync_wait_or_raise_err(
                    attempt=attempt,
                    err=err,
                    max_attempts=max_attempts,
                    backoff_multiplier=backoff_multiplier,
                    initial_backoff=initial_backoff,
                    max_backoff=max_backoff,
                )
    finally:
        stop_event.set()
        t.join(5)
        t.terminate()


@pytest.mark.skipif("GITHUH_WORKFLOWS" in os.environ, reason="Flaky in GH Actions")
@pytest.mark.timeout(90)
@pytest.mark.parametrize('flow_or_deployment', ['deployment', 'flow'])
def test_grpc_stream_transient_error_docarray_input(
    flow_or_deployment, port_generator, mocker
):
    random_port = port_generator()
    stop_event = multiprocessing.Event()
    start_event = multiprocessing.Event()
    t = multiprocessing.Process(
        target=_start_runtime,
        args=('grpc', random_port, flow_or_deployment, stop_event, start_event),
    )
    t.start()
    start_event.wait(5)
    num_docs = 10
    try:
        client = Client(host=f'grpc://localhost:{random_port}')

        on_error_mock = mocker.Mock()
        response = client.post(
            '/',
            DocumentArray.empty(num_docs),
            request_size=1,
            on_error=on_error_mock,
            return_responses=True,
            timeout=0.5,
            max_attempts=5,
            initial_backoff=0.8,
            backoff_multiplier=1.5,
            max_backoff=5,
        )
        assert len(response) == num_docs

        on_error_mock.assert_not_called()
    finally:
        stop_event.set()
        t.join(5)
        t.terminate()


@pytest.mark.skipif("GITHUH_WORKFLOWS" in os.environ, reason="Flaky in GH Actions")
@pytest.mark.timeout(90)
@pytest.mark.asyncio
@pytest.mark.parametrize('flow_or_deployment', ['deployment', 'flow'])
@pytest.mark.ignore
async def test_async_grpc_stream_transient_error(
    flow_or_deployment, port_generator, mocker
):
    random_port = port_generator()
    stop_event = multiprocessing.Event()
    start_event = multiprocessing.Event()
    t = multiprocessing.Process(
        target=_start_runtime,
        args=('grpc', random_port, flow_or_deployment, stop_event, start_event),
    )
    t.start()
    start_event.wait(5)
    max_attempts = 5
    initial_backoff = 0.8
    backoff_multiplier = 1.5
    max_backoff = 5
    try:
        client = Client(host=f'grpc://localhost:{random_port}', asyncio=True)

        for attempt in range(1, max_attempts + 1):
            try:
                on_error_mock = mocker.Mock()
                response = [
                    response
                    async for response in client.post(
                        '/',
                        random_docs(1),
                        request_size=1,
                        on_error=on_error_mock,
                        return_responses=True,
                        timeout=0.5,
                    )
                ]
                assert len(response) == 1

                on_error_mock.assert_not_called()
            except ConnectionError as err:
                await wait_or_raise_err(
                    attempt=attempt,
                    err=err,
                    max_attempts=max_attempts,
                    backoff_multiplier=backoff_multiplier,
                    initial_backoff=initial_backoff,
                    max_backoff=max_backoff,
                )
    finally:
        stop_event.set()
        t.join(5)
        t.terminate()


@pytest.mark.skipif("GITHUH_WORKFLOWS" in os.environ, reason="Flaky in GH Actions")
@pytest.mark.timeout(300)
@pytest.mark.parametrize('flow_or_deployment', ['flow', 'deployment'])
@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
def test_sync_clients_max_attempts_transient_error(
    mocker, flow_or_deployment, protocol, port_generator
):
    if flow_or_deployment == 'deployment' and protocol in ['websocket', 'http']:
        return
    random_port = port_generator()
    client = Client(host=f'{protocol}://localhost:{random_port}')
    stop_event = multiprocessing.Event()
    start_event = multiprocessing.Event()
    t = multiprocessing.Process(
        target=_start_runtime,
        args=(protocol, random_port, flow_or_deployment, stop_event, start_event),
    )
    t.start()
    start_event.wait(5)
    try:
        # Test that a regular index request triggers the correct callbacks
        on_error_mock = mocker.Mock()
        response = _random_post_request(client, on_error_mock, use_stream=False)
        assert len(response) == 1

        on_error_mock.assert_not_called()
    finally:
        stop_event.set()
        t.join(5)
        t.terminate()


@pytest.mark.skipif("GITHUH_WORKFLOWS" in os.environ, reason="Flaky in GH Actions")
@pytest.mark.timeout(60)
@pytest.mark.parametrize('protocol', ['grpc', 'http', 'websocket'])
def test_sync_clients_max_attempts_raises_error(mocker, protocol, port_generator):
    random_port = port_generator()
    on_always_mock = mocker.Mock()
    on_error_mock = mocker.Mock()
    on_done_mock = mocker.Mock()
    client = Client(host=f'{protocol}://localhost:{random_port}')

    def _request(stream_param=True):
        client.post(
            '/',
            random_docs(1),
            request_size=1,
            max_attempts=5,
            on_always=on_always_mock,
            on_error=on_error_mock,
            on_done=on_done_mock,
            return_responses=True,
            timeout=0.5,
            stream=stream_param,
        )

    if protocol == 'grpc':
        stream_opts = [True, False]
        for stream_param in stream_opts:
            with pytest.raises(ConnectionError):
                _request(stream_param)
    else:
        with pytest.raises(ConnectionError):
            _request()
