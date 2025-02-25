import multiprocessing
import time
import uuid

import pytest
from docarray import DocumentArray

from jina import Client, Executor, requests
from jina.parsers import set_gateway_parser
from jina.serve.runtimes.asyncio import AsyncNewLoopRuntime
from jina.serve.runtimes.servers import BaseServer
from jina.serve.runtimes.worker.request_handling import WorkerRequestHandler
from jina.serve.runtimes.gateway.request_handling import GatewayRequestHandler
from tests.helper import _generate_pod_args

from tests.integration.runtimes.test_runtimes import (
    _create_gateway_runtime,
    _create_head_runtime,
)


class DummyExec(Executor):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._id = str(uuid.uuid4())

    @requests(on='/foo')
    def foo(self, docs, *args, **kwargs):
        docs[0].text = self._id


def _create_worker_runtime(port, name='', executor=None):
    args = _generate_pod_args()
    args.port = [port]
    args.uses = 'DummyExec'
    args.name = name
    if executor:
        args.uses = executor
    with AsyncNewLoopRuntime(args, req_handler_cls=WorkerRequestHandler) as runtime:
        runtime.run_forever()


def _create_worker(port):
    # create a single worker runtime
    p = multiprocessing.Process(target=_create_worker_runtime, args=(port,))
    p.start()
    time.sleep(0.1)
    return p


def _create_gateway(port, graph, pod_addr, protocol, retries=-1, log_config='default'):
    # create a single worker runtime
    # create a single gateway runtime
    p = multiprocessing.Process(
        target=_create_gateway_runtime,
        args=(graph, pod_addr, port, protocol, retries, log_config),
    )
    p.start()
    time.sleep(0.1)
    return p


def _create_head(port, connection_list_dict, polling, retries=-1):
    p = multiprocessing.Process(
        target=_create_head_runtime,
        args=(port, connection_list_dict, 'head', polling, None, None, retries),
    )
    p.start()
    time.sleep(0.1)
    return p


def _check_all_replicas_connected(num_replicas, gateway_port, protocol):
    """check if all replicas are connected"""
    exec_ids = set()
    exec_id_list = []
    for i in range(num_replicas + 1):
        id_ = _send_request(gateway_port, protocol, request_size=2)[0].text
        exec_ids.add(id_)
        exec_id_list.append(id_)
    print(exec_id_list)
    assert len(exec_ids) == num_replicas


def _send_request(gateway_port, protocol, request_size=1):
    """send request to gateway and see what happens"""
    c = Client(host='localhost', port=gateway_port, protocol=protocol)
    res = c.post('/foo', inputs=DocumentArray.empty(2), request_size=request_size)
    assert len(res) == 2
    return res


def _test_error(gateway_port, error_ports, protocol):
    if not isinstance(error_ports, list):
        error_ports = [error_ports]
    with pytest.raises(ConnectionError) as err_info:  # assert correct error is thrown
        _send_request(gateway_port, protocol)
    # assert error message contains the port(s) of the broken executor(s)
    for port in error_ports:
        assert str(port) in err_info.value.args[0]


@pytest.mark.parametrize('protocol', ['http'])
@pytest.mark.parametrize('fail_endpoint_discovery', [True, False])
@pytest.mark.asyncio
async def test_runtimes_reconnect(port_generator, protocol, fail_endpoint_discovery):
    # create gateway and workers manually, then terminate worker process to provoke an error
    worker_port = port_generator()
    gateway_port = port_generator()
    graph_description = '{"start-gateway": ["pod0"], "pod0": ["end-gateway"]}'
    pod_addresses = f'{{"pod0": ["0.0.0.0:{worker_port}"]}}'

    gateway_process = _create_gateway(
        gateway_port, graph_description, pod_addresses, protocol
    )

    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{gateway_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    try:
        if fail_endpoint_discovery:
            # send request while Executor is not UP, WILL FAIL
            p = multiprocessing.Process(
                target=_send_request, args=(gateway_port, protocol)
            )
            p.start()
            p.join()
            assert p.exitcode != 0, f"The _send_request #0 Process exited with exitcode {p.exitcode}"  # The request will fail and raise

        worker_process = _create_worker(worker_port)
        assert BaseServer.wait_for_ready_or_shutdown(
            timeout=5.0,
            ctrl_address=f'0.0.0.0:{worker_port}',
            ready_or_shutdown_event=multiprocessing.Event(),
        ), "The BaseServer wait_for_ready_or_shutdown for worker_port failed"
        time.sleep(3)

        p = multiprocessing.Process(target=_send_request, args=(gateway_port, protocol))
        p.start()
        p.join()
        assert p.exitcode == 0, f"The _send_request #1 Process exited with exitcode {p.exitcode}"  # The request will not fail and raise
        worker_process.terminate()  # kill worker
        worker_process.join()
        assert not worker_process.is_alive()

        # send request while Executor is not UP, WILL FAIL
        p = multiprocessing.Process(target=_send_request, args=(gateway_port, protocol))
        p.start()
        p.join()
        assert p.exitcode != 0, f"The _send_request #2 Process exited with exitcode {p.exitcode}"  # The request will not fail and rais

        worker_process = _create_worker(worker_port)

        time.sleep(3)

        assert BaseServer.wait_for_ready_or_shutdown(
            timeout=5.0,
            ctrl_address=f'0.0.0.0:{worker_port}',
            ready_or_shutdown_event=multiprocessing.Event(),
        ), "The BaseServer wait_for_ready_or_shutdown for worker_port failed"
        p = multiprocessing.Process(target=_send_request, args=(gateway_port, protocol))
        p.start()
        p.join()
        assert (
                p.exitcode == 0
        ), f"The _send_request #3 Process exited with exitcode {p.exitcode}"  # The request will not fail and rais  # if exitcode != 0 then test in other process did not pass and this should fail
        # ----------- 2. test that gateways remain alive -----------
        # just do the same again, expecting the same failure
        worker_process.terminate()  # kill worker
        worker_process.join()
        assert not worker_process.is_alive(), "Worker process is still alive"
        assert (
                worker_process.exitcode == 0
        ), f"The worker_process Process exited with exitcode {worker_process.exitcode}" # if exitcode != 0 then test in other process did not pass and this should fail

    except Exception as exc:
        print(f'===> Exception: {exc}')
        assert False
    finally:  # clean up runtimes
        gateway_process.terminate()
        gateway_process.join()
        worker_process.terminate()
        worker_process.join()


@pytest.mark.parametrize(
    'fail_before_endpoint_discovery', [True, False]
)  # if not before, then after
@pytest.mark.parametrize('protocol', ['http', 'websocket'])
@pytest.mark.asyncio
async def test_runtimes_headless_topology(
        port_generator, protocol, fail_before_endpoint_discovery
):
    # create gateway and workers manually, then terminate worker process to provoke an error
    worker_port = port_generator()
    gateway_port = port_generator()
    graph_description = '{"start-gateway": ["pod0"], "pod0": ["end-gateway"]}'
    pod_addresses = f'{{"pod0": ["0.0.0.0:{worker_port}"]}}'

    worker_process = _create_worker(worker_port)
    gateway_process = _create_gateway(
        gateway_port, graph_description, pod_addresses, protocol
    )

    time.sleep(1.0)

    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{worker_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{gateway_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    if (
            fail_before_endpoint_discovery
    ):  # kill worker before having sent the first request, so before endpoint discov.
        worker_process.terminate()
        worker_process.join()

    try:
        if fail_before_endpoint_discovery:
            # here worker is already dead before the first request, so endpoint discovery will fail
            # ----------- 1. test that useful errors are given when endpoint discovery fails -----------
            # we have to do this in a new process because otherwise grpc will be sad and everything will crash :(
            p = multiprocessing.Process(
                target=_test_error, args=(gateway_port, worker_port, protocol)
            )
            p.start()
            p.join()
            assert (
                    p.exitcode == 0
            )  # if exitcode != 0 then test in other process did not pass and this should fail
        else:
            # just ping the Flow without having killed a worker before. This (also) performs endpoint discovery
            p = multiprocessing.Process(
                target=_send_request, args=(gateway_port, protocol)
            )
            p.start()
            p.join()
            # only now do we kill the worker, after having performed successful endpoint discovery
            # so in this case, the actual request will fail, not the discovery, which is handled differently by Gateway
            worker_process.terminate()  # kill worker
            worker_process.join()
            assert not worker_process.is_alive()
        # ----------- 2. test that gateways remain alive -----------
        # just do the same again, expecting the same failure
        p = multiprocessing.Process(
            target=_test_error, args=(gateway_port, worker_port, protocol)
        )
        p.start()
        p.join()
        assert (
                p.exitcode == 0
        )  # if exitcode != 0 then test in other process did not pass and this should fail
    except Exception:
        assert False
    finally:  # clean up runtimes
        gateway_process.terminate()
        worker_process.terminate()
        gateway_process.join()
        worker_process.join()


@pytest.mark.parametrize('protocol', ['http', 'websocket'])
@pytest.mark.asyncio
async def test_runtimes_resource_not_found(port_generator, protocol, monkeypatch):
    async def patch_endpoint_discovery(self, empty, context):
        import grpc

        context.set_code(grpc.StatusCode.NOT_FOUND)

    async def patch_process_data(self, requests_, context, **kwargs):
        import grpc

        context.set_code(grpc.StatusCode.NOT_FOUND)

    monkeypatch.setattr(
        WorkerRequestHandler,
        'endpoint_discovery',
        patch_endpoint_discovery,
    )

    monkeypatch.setattr(
        WorkerRequestHandler,
        'process_data',
        patch_process_data,
    )

    gateway_port = port_generator()
    worker_port = port_generator()
    graph_description = '{"start-gateway": ["pod0"], "pod0": ["end-gateway"]}'
    pod_addresses = f'{{"pod0": ["0.0.0.0:{worker_port}"]}}'

    worker_process = _create_worker(worker_port)
    gateway_process = _create_gateway(
        gateway_port, graph_description, pod_addresses, protocol
    )

    time.sleep(1.0)

    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{gateway_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    try:
        # ----------- 1. test that useful errors are given when endpoint discovery fails -----------
        # we have to do this in a new process because otherwise grpc will be sad and everything will crash :(
        p = multiprocessing.Process(
            target=_test_error,
            args=(gateway_port, worker_port, protocol),
        )
        p.start()
        p.join()
        assert (
                p.exitcode == 0
        )  # if exitcode != 0 then test in other process did not pass and this should fail
    except Exception:
        assert False
    finally:  # clean up runtimes
        gateway_process.terminate()
        gateway_process.join()
        worker_process.terminate()
        worker_process.join()


@pytest.mark.parametrize('protocol', ['http'])
@pytest.mark.parametrize('fail_endpoint_discovery', [False])
@pytest.mark.asyncio
async def test_runtimes_reconnect_replicas(
        port_generator, protocol, fail_endpoint_discovery
):
    # create gateway and workers manually, then terminate worker process to provoke an error
    worker_ports = [port_generator() for _ in range(3)]
    worker0_port, worker1_port, worker2_port = worker_ports
    gateway_port = port_generator()
    graph_description = '{"start-gateway": ["pod0"], "pod0": ["end-gateway"]}'
    pod_addresses = f'{{"pod0": ["0.0.0.0:{worker0_port}", "0.0.0.0:{worker1_port}", "0.0.0.0:{worker2_port}"]}}'

    worker_processes = []
    for p in worker_ports:
        worker_processes.append(_create_worker(p))
        time.sleep(1.0)
        BaseServer.wait_for_ready_or_shutdown(
            timeout=5.0,
            ctrl_address=f'0.0.0.0:{p}',
            ready_or_shutdown_event=multiprocessing.Event(),
        )

    gateway_process = _create_gateway(
        gateway_port, graph_description, pod_addresses, protocol
    )
    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{gateway_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    p_first_check = multiprocessing.Process(
        target=_check_all_replicas_connected, args=(3, gateway_port, protocol)
    )
    p_first_check.start()
    p_first_check.join()
    assert (
            p_first_check.exitcode == 0
    )  # all replicas are connected. At the end, the Flow should return to this state.

    worker_processes[1].terminate()  # kill 'middle' worker
    worker_processes[1].join()
    p_second_check = None

    try:
        if fail_endpoint_discovery:
            # send request while Executor is not UP, WILL FAIL
            p = multiprocessing.Process(
                target=_send_request, args=(gateway_port, protocol)
            )
            p.start()
            p.join()

        p = multiprocessing.Process(target=_send_request, args=(gateway_port, protocol))
        p.start()
        p.join()

        p = multiprocessing.Process(target=_send_request, args=(gateway_port, protocol))
        p.start()
        p.join()

        worker_processes[1] = _create_worker(worker_ports[1])

        assert BaseServer.wait_for_ready_or_shutdown(
            timeout=5.0,
            ctrl_address=f'0.0.0.0:{worker_ports[1]}',
            ready_or_shutdown_event=multiprocessing.Event(),
        )

        time.sleep(1)

        p_second_check = multiprocessing.Process(
            target=_check_all_replicas_connected, args=(3, gateway_port, protocol)
        )
        p_second_check.start()
        p_second_check.join()
        assert p_second_check.exitcode == 0  # all replicas are connected again.
    except Exception:
        assert False
    finally:  # clean up runtimes
        gateway_process.terminate()
        gateway_process.join()
        p_first_check.terminate()
        p_first_check.join()
        for p in worker_processes:
            p.terminate()
            p.join()
        if p_second_check:
            p_second_check.terminate()
            p_second_check.join()


@pytest.mark.parametrize('protocol', ['http', 'websocket'])
@pytest.mark.parametrize('fail_before_endpoint_discovery', [True, False])
@pytest.mark.asyncio
async def test_runtimes_replicas(
        port_generator, protocol, fail_before_endpoint_discovery
):
    # create gateway and workers manually, then terminate worker process to provoke an error
    worker_ports = [port_generator() for _ in range(3)]
    worker0_port, worker1_port, worker2_port = worker_ports
    gateway_port = port_generator()
    graph_description = '{"start-gateway": ["pod0"], "pod0": ["end-gateway"]}'
    pod_addresses = f'{{"pod0": ["0.0.0.0:{worker0_port}", "0.0.0.0:{worker1_port}", "0.0.0.0:{worker2_port}"]}}'

    worker_processes = []
    for p in worker_ports:
        worker_processes.append(_create_worker(p))
        time.sleep(0.1)
        BaseServer.wait_for_ready_or_shutdown(
            timeout=5.0,
            ctrl_address=f'0.0.0.0:{p}',
            ready_or_shutdown_event=multiprocessing.Event(),
        )

    gateway_process = _create_gateway(
        gateway_port, graph_description, pod_addresses, protocol
    )
    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{gateway_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    if (
            not fail_before_endpoint_discovery
    ):  # make successful request and trigger endpoint discovery
        # we have to do this in a new process because otherwise grpc will be sad and everything will crash :(
        p = multiprocessing.Process(target=_send_request, args=(gateway_port, protocol))
        p.start()
        p.join()
        # different replica should be picked, no error should be raised
        assert (
                p.exitcode == 0
        )  # if exitcode != 0 then test in other process did not pass and this should fail

    worker_processes[0].terminate()  # kill first worker
    worker_processes[0].join()

    try:
        for _ in range(
                len(worker_ports)
        ):  # make sure all workers are targeted by round robin
            # ----------- 1. test that useful errors are given -----------
            # we have to do this in a new process because otherwise grpc will be sad and everything will crash :(
            p = multiprocessing.Process(
                target=_send_request, args=(gateway_port, protocol)
            )
            p.start()
            p.join()
            # different replica should be picked, no error should be raised
            assert (
                    p.exitcode == 0
            )  # if exitcode != 0 then test in other process did not pass and this should fail
    except Exception:
        assert False
    finally:  # clean up runtimes
        gateway_process.terminate()
        gateway_process.join()
        for p in worker_processes:
            p.terminate()
            p.join()


@pytest.mark.parametrize(
    'terminate_head', [True]
)  # option with False times out because backoffs accumulate
@pytest.mark.parametrize('protocol', ['http', 'websocket'])
@pytest.mark.asyncio
async def test_runtimes_headful_topology(port_generator, protocol, terminate_head):
    # create gateway and workers manually, then terminate worker process to provoke an error
    worker_port = port_generator()
    gateway_port = port_generator()
    head_port = port_generator()
    graph_description = '{"start-gateway": ["pod0"], "pod0": ["end-gateway"]}'
    pod_addresses = f'{{"pod0": ["0.0.0.0:{head_port}"]}}'

    connection_list_dict = {'0': [f'127.0.0.1:{worker_port}']}

    head_process = _create_head(head_port, connection_list_dict, 'ANY')
    worker_process = _create_worker(worker_port)
    gateway_process = _create_gateway(
        gateway_port, graph_description, pod_addresses, protocol
    )

    time.sleep(5.0)

    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{head_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{worker_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{gateway_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    # terminate pod, either head or worker behind the head
    if terminate_head:
        head_process.terminate()
        head_process.join()
        error_port = head_port
    else:
        worker_process.terminate()  # kill worker
        worker_process.join()
        error_port = worker_port
    error_port = (
        head_port if protocol == 'websocket' else error_port
    )  # due to error msg length constraints ws will always report the head address

    try:
        # ----------- 1. test that useful errors are given -----------
        # we have to do this in a new process because otherwise grpc will be sad and everything will crash :(
        p = multiprocessing.Process(
            target=_test_error, args=(gateway_port, error_port, protocol)
        )
        p.start()
        p.join()
        assert (
                p.exitcode == 0
        )  # if exitcode != 0 then test in other process did not pass and this should fail
        # ----------- 2. test that gateways remain alive -----------
        # just do the same again, expecting the same outcome
        p = multiprocessing.Process(
            target=_test_error, args=(gateway_port, error_port, protocol)
        )
        p.start()
        p.join()
        assert (
                p.exitcode == 0
        )  # if exitcode != 0 then test in other process did not pass and this should fail
    except Exception:
        raise
    finally:  # clean up runtimes
        gateway_process.terminate()
        worker_process.terminate()
        head_process.terminate()
        gateway_process.join()
        worker_process.join()
        head_process.join()


def _send_gql_request(gateway_port):
    """send request to gateway and see what happens"""
    mutation = (
            f'mutation {{'
            + '''docs(data: {text: "abcd"}) { 
                    id 
                } 
            }
    '''
    )
    c = Client(host='localhost', port=gateway_port, protocol='http')
    return c.mutate(mutation=mutation)


def _test_gql_error(gateway_port, error_port):
    with pytest.raises(ConnectionError) as err_info:  # assert correct error is thrown
        _send_gql_request(gateway_port)
    # assert error message contains useful info
    assert str(error_port) in err_info.value.args[0]


def _create_gqlgateway_runtime(graph_description, pod_addresses, port):
    with AsyncNewLoopRuntime(
            set_gateway_parser().parse_args(
                [
                    '--graph-description',
                    graph_description,
                    '--deployments-addresses',
                    pod_addresses,
                    '--port',
                    str(port),
                    '--expose-graphql-endpoint',
                    '--protocol',
                    'http',
                ]
            ),
            req_handler_cls=GatewayRequestHandler,
    ) as runtime:
        runtime.run_forever()


def _create_gqlgateway(port, graph, pod_addr):
    p = multiprocessing.Process(
        target=_create_gqlgateway_runtime,
        args=(graph, pod_addr, port),
    )
    p.start()
    return p


@pytest.mark.asyncio
async def test_runtimes_graphql(port_generator):
    # create gateway and workers manually, then terminate worker process to provoke an error
    worker_port = port_generator()
    gateway_port = port_generator()
    graph_description = '{"start-gateway": ["pod0"], "pod0": ["end-gateway"]}'
    pod_addresses = f'{{"pod0": ["0.0.0.0:{worker_port}"]}}'

    worker_process = _create_worker(worker_port)
    gateway_process = _create_gqlgateway(gateway_port, graph_description, pod_addresses)

    time.sleep(5.0)

    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{worker_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{gateway_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    worker_process.terminate()  # kill worker
    worker_process.join()

    try:
        # ----------- 1. test that useful errors are given -----------
        # we have to do this in a new process because otherwise grpc will be sad and everything will crash :(
        p = multiprocessing.Process(
            target=_test_gql_error, args=(gateway_port, worker_port)
        )
        p.start()
        p.join()
        assert (
                p.exitcode == 0
        )  # if exitcode != 0 then test in other process did not pass and this should fail
        # ----------- 2. test that gateways remain alive -----------
        # just do the same again, expecting the same outcome
        p = multiprocessing.Process(
            target=_test_gql_error, args=(gateway_port, worker_port)
        )
        p.start()
        p.join()
        assert (
                p.exitcode == 0
        )  # if exitcode != 0 then test in other process did not pass and this should fail
    except Exception:
        raise
    finally:  # clean up runtimes
        gateway_process.terminate()
        worker_process.terminate()
        gateway_process.join()
        worker_process.join()


@pytest.mark.asyncio
async def test_replica_retry(port_generator):
    # test that if one replica is down, the other replica(s) will be used
    # create gateway and workers manually, then terminate worker process to provoke an error
    worker_ports = [port_generator() for _ in range(3)]
    worker0_port, worker1_port, worker2_port = worker_ports
    gateway_port = port_generator()
    graph_description = '{"start-gateway": ["pod0"], "pod0": ["end-gateway"]}'
    pod_addresses = f'{{"pod0": ["0.0.0.0:{worker0_port}", "0.0.0.0:{worker1_port}", "0.0.0.0:{worker2_port}"]}}'

    worker_processes = []
    for p in worker_ports:
        worker_processes.append(_create_worker(p))
        time.sleep(3.0)
        BaseServer.wait_for_ready_or_shutdown(
            timeout=5.0,
            ctrl_address=f'0.0.0.0:{p}',
            ready_or_shutdown_event=multiprocessing.Event(),
        )

    gateway_process = _create_gateway(
        gateway_port, graph_description, pod_addresses, 'grpc'
    )
    time.sleep(3.0)
    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{gateway_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    try:
        # ----------- 1. ping Flow once to trigger endpoint discovery -----------
        # we have to do this in a new process because otherwise grpc will be sad and everything will crash :(
        p = multiprocessing.Process(target=_send_request, args=(gateway_port, 'grpc'))
        p.start()
        p.join()
        assert p.exitcode == 0
        # kill second worker, which would be responsible for the second call (round robin)
        worker_processes[1].terminate()
        worker_processes[1].join()
        # ----------- 2. test that redundant replicas take over -----------
        # we have to do this in a new process because otherwise grpc will be sad and everything will crash :(
        p = multiprocessing.Process(target=_send_request, args=(gateway_port, 'grpc'))
        p.start()
        p.join()
        assert p.exitcode == 0
    except Exception:
        assert False
    finally:  # clean up runtimes
        gateway_process.terminate()
        gateway_process.join()
        for p in worker_processes:
            p.terminate()
            p.join()


@pytest.mark.asyncio
async def test_replica_retry_all_fail(port_generator):
    # test that if one replica is down, the other replica(s) will be used
    # create gateway and workers manually, then terminate worker process to provoke an error
    worker_ports = [port_generator() for _ in range(3)]
    worker0_port, worker1_port, worker2_port = worker_ports
    gateway_port = port_generator()
    graph_description = '{"start-gateway": ["pod0"], "pod0": ["end-gateway"]}'
    pod_addresses = f'{{"pod0": ["0.0.0.0:{worker0_port}", "0.0.0.0:{worker1_port}", "0.0.0.0:{worker2_port}"]}}'

    worker_processes = []
    for p in worker_ports:
        worker_processes.append(_create_worker(p))
        time.sleep(3.0)
        BaseServer.wait_for_ready_or_shutdown(
            timeout=5.0,
            ctrl_address=f'0.0.0.0:{p}',
            ready_or_shutdown_event=multiprocessing.Event(),
        )

    gateway_process = _create_gateway(
        gateway_port, graph_description, pod_addresses, 'grpc'
    )
    time.sleep(3.0)
    BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'0.0.0.0:{gateway_port}',
        ready_or_shutdown_event=multiprocessing.Event(),
    )

    try:
        # ----------- 1. ping Flow once to trigger endpoint discovery -----------
        # we have to do this in a new process because otherwise grpc will be sad and everything will crash :(
        p = multiprocessing.Process(target=_send_request, args=(gateway_port, 'grpc'))
        p.start()
        p.join()
        assert p.exitcode == 0
        # kill all workers
        for p in worker_processes:
            p.terminate()
            p.join()
        # ----------- 2. test that call fails with informative error message -----------
        # we have to do this in a new process because otherwise grpc will be sad and everything will crash :(
        p = multiprocessing.Process(
            target=_test_error, args=(gateway_port, worker_ports, 'grpc')
        )
        p.start()
        p.join()
        assert p.exitcode == 0
    except Exception:
        assert False
    finally:  # clean up runtimes
        gateway_process.terminate()
        gateway_process.join()
        for p in worker_processes:
            p.terminate()
            p.join()
