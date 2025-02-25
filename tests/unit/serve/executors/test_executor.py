import asyncio
import multiprocessing
import os
import time
from multiprocessing import Process
from threading import Event

import pytest
import yaml
from docarray import Document, DocumentArray
from pytest import FixtureRequest

from jina import Client, Executor, Flow, dynamic_batching, requests
from jina.clients.request import request_generator
from jina.constants import __cache_path__
from jina.excepts import RuntimeFailToStart
from jina.helper import random_port
from jina.serve.executors.decorators import write
from jina.serve.executors.metas import get_default_metas
from jina.serve.networking.utils import send_request_async
from jina.serve.runtimes.asyncio import AsyncNewLoopRuntime
from jina.serve.runtimes.servers import BaseServer
from jina.serve.runtimes.worker.request_handling import WorkerRequestHandler
from tests.helper import _generate_pod_args


class WorkspaceExec(Executor):
    @requests
    def foo(self, docs, **kwargs):
        docs.texts = [self.workspace for _ in docs]


class MyServeExec(Executor):
    @requests
    def foo(self, docs, **kwargs):
        docs.texts = ['foo' for _ in docs]

    @requests(on='/bar')
    def bar(self, docs, **kwargs):
        docs.texts = ['bar' for _ in docs]


@pytest.fixture()
def exposed_port():
    port = random_port()
    yield port


@pytest.fixture(autouse=False)
def served_exec(request: FixtureRequest, exposed_port):
    import threading
    import time

    def serve_exec(**kwargs):
        MyServeExec.serve(**kwargs)

    e = threading.Event()

    kwargs = {'port': exposed_port, 'stop_event': e}
    enable_dynamic_batching = request.param
    if enable_dynamic_batching:
        kwargs['uses_dynamic_batching'] = {
            '/bar': {'preferred_batch_size': 4, 'timeout': 5000}
        }

    t = threading.Thread(
        name='serve-exec',
        target=serve_exec,
        kwargs=kwargs,
    )
    t.start()
    time.sleep(3)  # allow Flow to start

    yield

    e.set()  # set event and stop (unblock) the Flow
    t.join()


@pytest.mark.parametrize('uses', ['jinaai://jina-ai/DummyHubExecutor'])
def test_executor_load_from_hub(uses):
    exec = Executor.from_hub(uses, uses_metas={'name': 'hello123'})
    da = DocumentArray([Document()])
    exec.foo(da)
    assert da.texts == ['hello']
    assert exec.metas.name == 'hello123'


def test_executor_import_with_external_dependencies(capsys):
    ex = Executor.load_config('../../hubble-executor/config.yml')
    assert ex.bar == 123
    ex.foo()
    out, err = capsys.readouterr()
    assert 'hello' in out


def test_executor_with_pymodule_path():
    with pytest.raises(FileNotFoundError):
        _ = Executor.load_config(
            '''
        jtype: BaseExecutor
        py_modules:
            - jina.no_valide.executor
        '''
        )

    ex = Executor.load_config(
        '''
    jtype: MyExecutor
    with:
        bar: 123
    py_modules:
        - unit.serve.executors.dummy_executor
    '''
    )
    assert ex.bar == 123
    assert ex.process(DocumentArray([Document()]))[0].text == 'hello world'


def test_flow_uses_with_pymodule_path():
    with Flow.load_config(
        '''
    jtype: Flow
    executors:
        - uses: unit.serve.executors.dummy_executor.MyExecutor
          uses_with:
            bar: 123
    '''
    ):
        pass

    with Flow().add(
        uses='unit.serve.executors.dummy_executor.MyExecutor', uses_with={'bar': 123}
    ):
        pass

    with pytest.raises(RuntimeFailToStart):
        with Flow.load_config(
            '''
            jtype: Flow
            executors:
                - uses: jina.no_valide.executor
                  uses_with:
                    bar: 123
            '''
        ):
            pass


@property
def workspace(self) -> str:
    """
    Get the path of the current shard.

    :return: returns the workspace of the shard of this Executor.
    """
    return os.path.abspath(
        self.metas.workspace
        or (
            os.path.join(self.runtime_args.workspace, self.metas.name)
            if self.metas.shard_id == -1
            else os.path.join(
                self.runtime_args.workspace, self.metas.name, self.metas.shard_id
            )
        )
    )


@pytest.fixture
def shard_id(request):
    return request.param


@pytest.fixture
def test_metas_workspace_simple(tmpdir):
    metas = get_default_metas()
    metas['workspace'] = str(tmpdir)
    metas['name'] = 'test'
    return metas


@pytest.fixture
def test_bad_metas_workspace(tmpdir):
    metas = get_default_metas()
    return metas


@pytest.fixture
def test_metas_workspace_replica_pods(tmpdir, shard_id):
    metas = get_default_metas()
    metas['workspace'] = str(tmpdir)
    metas['name'] = 'test'
    metas['shard_id'] = shard_id
    return metas


def test_executor_workspace_simple(test_metas_workspace_simple):
    executor = Executor(metas=test_metas_workspace_simple)
    assert executor.workspace == os.path.abspath(
        os.path.join(
            test_metas_workspace_simple['workspace'],
            test_metas_workspace_simple['name'],
        )
    )


def test_executor_workspace_simple_workspace(tmpdir):
    runtime_workspace = os.path.join(tmpdir, 'test2')
    workspace = os.path.join(tmpdir, 'some_folder')
    name = 'test_meta'

    executor = Executor(metas={'name': name, 'workspace': workspace})
    assert executor.workspace == os.path.abspath(os.path.join(workspace, name))

    executor = Executor(metas={'name': name}, runtime_args={'workspace': workspace})
    assert executor.workspace == os.path.abspath(os.path.join(workspace, name))

    # metas after runtime_args
    executor = Executor(
        metas={'name': name, 'workspace': workspace},
        runtime_args={'workspace': runtime_workspace},
    )
    assert executor.workspace == os.path.abspath(os.path.join(runtime_workspace, name))

    executor = Executor(
        metas={'name': name, 'workspace': workspace},
        runtime_args={'shard_id': 1},
    )
    assert executor.workspace == os.path.abspath(os.path.join(workspace, name, '1'))

    executor = Executor(
        metas={'name': name},
        runtime_args={'workspace': workspace, 'shard_id': 1},
    )
    assert executor.workspace == os.path.abspath(os.path.join(workspace, name, '1'))


@pytest.mark.parametrize('shard_id', [0, 1, 2], indirect=True)
def test_executor_workspace(test_metas_workspace_replica_pods, shard_id):
    executor = Executor(
        metas={'name': test_metas_workspace_replica_pods['name']},
        runtime_args=test_metas_workspace_replica_pods,
    )

    assert executor.workspace == os.path.abspath(
        os.path.join(
            test_metas_workspace_replica_pods['workspace'],
            test_metas_workspace_replica_pods['name'],
            str(shard_id),
        )
    )


@pytest.mark.parametrize('shard_id', [None, -1], indirect=True)
def test_executor_workspace_parent_replica_nopea(
    test_metas_workspace_replica_pods, shard_id
):
    executor = Executor(
        metas={'name': test_metas_workspace_replica_pods['name']},
        runtime_args=test_metas_workspace_replica_pods,
    )
    assert executor.workspace == os.path.abspath(
        os.path.join(
            test_metas_workspace_replica_pods['workspace'],
            test_metas_workspace_replica_pods['name'],
        )
    )


@pytest.mark.parametrize('shard_id', [0, 1, 2], indirect=True)
def test_executor_workspace_parent_noreplica_pod(
    test_metas_workspace_replica_pods, shard_id
):
    executor = Executor(
        metas={'name': test_metas_workspace_replica_pods['name']},
        runtime_args=test_metas_workspace_replica_pods,
    )
    assert executor.workspace == os.path.abspath(
        os.path.join(
            test_metas_workspace_replica_pods['workspace'],
            test_metas_workspace_replica_pods['name'],
            str(shard_id),
        )
    )


@pytest.mark.parametrize('shard_id', [None, -1], indirect=True)
def test_executor_workspace_parent_noreplica_nopea(
    test_metas_workspace_replica_pods, shard_id
):
    executor = Executor(
        metas={'name': test_metas_workspace_replica_pods['name']},
        runtime_args=test_metas_workspace_replica_pods,
    )
    assert executor.workspace == os.path.abspath(
        os.path.join(
            test_metas_workspace_replica_pods['workspace'],
            test_metas_workspace_replica_pods['name'],
        )
    )


def test_workspace_not_exists(tmpdir):
    class MyExec(Executor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        def do(self, *args, **kwargs):
            with open(
                os.path.join(self.workspace, 'text.txt'), 'w', encoding='utf-8'
            ) as f:
                f.write('here!')

    e = MyExec(metas={'workspace': tmpdir})
    e.do()


@pytest.mark.parametrize(
    'uses_requests, expected',
    [
        (None, {'/foo', '/default', '*'}),
        ({'/nofoo': 'foo'}, {'/nofoo', '/default', '*'}),
        ({'/nofoo': 'foo', '/new': 'default'}, {'/nofoo', '/new', '*'}),
        ({'/new': 'default'}, {'/foo', '/new', '*'}),
        ({'/nofoo': 'foo', '/new': 'all'}, {'/nofoo', '/default', '/new'}),
        ({'/new': 'all'}, {'/foo', '/default', '/new'}),
    ],
)
def test_override_requests(uses_requests, expected):
    from jina.serve.executors import __dry_run_endpoint__

    expected.add(__dry_run_endpoint__)

    class OverrideExec(Executor):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        @requests()
        def default(self, *args, **kwargs):
            pass

        @requests(on='*')
        def all(self, *args, **kwargs):
            pass

        @requests(on='/foo')
        def foo(self, *args, **kwargs):
            pass

    exec = OverrideExec(requests=uses_requests)
    assert expected == set(exec.requests.keys())


def test_map_nested():
    class NestedExecutor(Executor):
        @requests
        def foo(self, docs: DocumentArray, **kwargs):
            def bar(d: Document):
                d.text = 'hello'
                return d

            docs.apply(bar)
            return docs

    N = 2
    da = DocumentArray.empty(N)
    exec = NestedExecutor()
    da1 = exec.foo(da)
    assert da1.texts == ['hello'] * N


@pytest.mark.asyncio
async def test_async():
    class AsyncExecutor(Executor):
        @requests
        async def foo(self, docs: DocumentArray, **kwargs):
            for d in docs:
                d.text = 'hello'
            return docs

    N = 2
    da = DocumentArray.empty(N)
    exec = AsyncExecutor()
    da1 = await exec.foo(da)
    assert da1.texts == ['hello'] * N


def set_hello(d: Document):
    d.text = 'hello'
    return d


@pytest.mark.asyncio
async def test_async_apply():
    class AsyncExecutor(Executor):
        @requests
        async def foo(self, docs: DocumentArray, **kwargs):
            docs.apply(set_hello)
            return docs

    N = 2
    da = DocumentArray.empty(N)
    exec = AsyncExecutor()
    da1 = await exec.foo(da)
    assert da1.texts == ['hello'] * N


@pytest.mark.parametrize('served_exec', [False, True], indirect=True)
def test_serve(served_exec, exposed_port):
    docs = Client(port=exposed_port).post(on='/bar', inputs=DocumentArray.empty(5))

    assert docs.texts == ['bar' for _ in docs]


def test_set_workspace(tmpdir):
    complete_workspace = os.path.abspath(os.path.join(tmpdir, 'WorkspaceExec', '0'))
    with Flow().add(uses=WorkspaceExec, workspace=str(tmpdir)) as f:
        resp = f.post(on='/foo', inputs=Document())
    assert resp[0].text == complete_workspace
    with Flow().add(uses=WorkspaceExec, uses_metas={'workspace': str(tmpdir)}) as f:
        resp = f.post(on='/foo', inputs=Document())
    assert resp[0].text == complete_workspace
    complete_workspace_no_replicas = os.path.abspath(
        os.path.join(tmpdir, 'WorkspaceExec')
    )
    assert (
        WorkspaceExec(workspace=str(tmpdir)).workspace == complete_workspace_no_replicas
    )


def test_default_workspace(tmpdir):
    with Flow().add(uses=WorkspaceExec) as f:
        resp = f.post(on='/foo', inputs=Document())
    assert resp[0].text

    result_workspace = resp[0].text

    assert result_workspace == os.path.join(__cache_path__, 'WorkspaceExec', '0')


@pytest.mark.parametrize(
    'exec_type',
    [Executor.StandaloneExecutorType.EXTERNAL, Executor.StandaloneExecutorType.SHARED],
)
@pytest.mark.parametrize(
    'uses',
    ['jinahub+docker://DummyHubExecutor', 'jinaai+docker://jina-ai/DummyHubExecutor'],
)
def test_to_k8s_yaml(tmpdir, exec_type, uses):
    Executor.to_kubernetes_yaml(
        output_base_path=tmpdir,
        uses=uses,
        executor_type=exec_type,
    )

    with open(
        os.path.join(tmpdir, 'executor0', 'executor0.yml'), encoding='utf-8'
    ) as f:
        exec_yaml = list(yaml.safe_load_all(f))[-1]
        assert exec_yaml['spec']['template']['spec']['containers'][0][
            'image'
        ].startswith('registry')

    if exec_type == Executor.StandaloneExecutorType.SHARED:
        assert set(os.listdir(tmpdir)) == {
            'executor0',
        }
    else:
        assert set(os.listdir(tmpdir)) == {
            'executor0',
            'gateway',
        }

        with open(
            os.path.join(tmpdir, 'gateway', 'gateway.yml'), encoding='utf-8'
        ) as f:
            gatewayyaml = list(yaml.safe_load_all(f))[-1]
            assert (
                gatewayyaml['spec']['template']['spec']['containers'][0]['ports'][0][
                    'containerPort'
                ]
                == 8080
            )
            gateway_args = gatewayyaml['spec']['template']['spec']['containers'][0][
                'args'
            ]
            assert gateway_args[gateway_args.index('--port') + 1] == '8080'


@pytest.mark.parametrize(
    'exec_type',
    [Executor.StandaloneExecutorType.EXTERNAL, Executor.StandaloneExecutorType.SHARED],
)
@pytest.mark.parametrize(
    'uses',
    ['jinaai+docker://jina-ai/DummyHubExecutor'],
)
def test_to_docker_compose_yaml(tmpdir, exec_type, uses):
    compose_file = os.path.join(tmpdir, 'compose.yml')
    Executor.to_docker_compose_yaml(
        output_path=compose_file,
        port_expose=2020,
        uses=uses,
        executor_type=exec_type,
    )

    with open(compose_file, encoding='utf-8') as f:
        services = list(yaml.safe_load_all(f))[0]['services']
        assert services['executor0']['image'].startswith('registry')

        if exec_type == Executor.StandaloneExecutorType.SHARED:
            assert len(services) == 1
        else:
            assert len(services) == 2
            assert services['gateway']['ports'][0] == '2020:2020'
            gateway_args = services['gateway']['command']
            assert gateway_args[gateway_args.index('--port') + 1] == '2020'


def _create_test_data_message(counter=0):
    return list(request_generator('/', DocumentArray([Document(text=str(counter))])))[0]


@pytest.mark.asyncio
async def test_blocking_sync_exec():
    SLEEP_TIME = 0.01
    REQUEST_COUNT = 100

    class BlockingExecutor(Executor):
        @requests
        def foo(self, docs: DocumentArray, **kwargs):
            time.sleep(SLEEP_TIME)
            for doc in docs:
                doc.text = 'BlockingExecutor'
            return docs

    args = _generate_pod_args(['--uses', 'BlockingExecutor'])

    cancel_event = multiprocessing.Event()

    def start_runtime(args, cancel_event):
        with AsyncNewLoopRuntime(
            args, cancel_event=cancel_event, req_handler_cls=WorkerRequestHandler
        ) as runtime:
            runtime.run_forever()

    runtime_thread = Process(
        target=start_runtime,
        args=(args, cancel_event),
        daemon=True,
    )
    runtime_thread.start()

    assert BaseServer.wait_for_ready_or_shutdown(
        timeout=5.0,
        ctrl_address=f'{args.host}:{args.port[0]}',
        ready_or_shutdown_event=Event(),
    )

    send_tasks = []
    start_time = time.time()
    for i in range(REQUEST_COUNT):
        send_tasks.append(
            asyncio.create_task(
                send_request_async(
                    _create_test_data_message(),
                    target=f'{args.host}:{args.port[0]}',
                    timeout=3.0,
                )
            )
        )

    results = await asyncio.gather(*send_tasks)
    end_time = time.time()

    assert all(result.docs.texts == ['BlockingExecutor'] for result in results)
    assert end_time - start_time < (REQUEST_COUNT * SLEEP_TIME) * 2.0

    cancel_event.set()
    runtime_thread.join()


def test_executors_inheritance_binding():
    class A(Executor):
        @requests(on='/index')
        def a(self, **kwargs):
            pass

        @requests
        def default_a(self, **kwargs):
            pass

    class B(A):
        @requests(on='/index')
        def b(self, **kwargs):
            pass

    class C(B):
        pass

    assert set(A().requests.keys()) == {'/index', '/default', '_jina_dry_run_'}
    assert A().requests['/index'].fn == A.a
    assert A().requests['/default'].fn == A.default_a
    assert set(B().requests.keys()) == {'/index', '/default', '_jina_dry_run_'}
    assert B().requests['/index'].fn == B.b
    assert B().requests['/default'].fn == A.default_a
    assert set(C().requests.keys()) == {'/index', '/default', '_jina_dry_run_'}
    assert C().requests['/index'].fn == B.b
    assert C().requests['/default'].fn == A.default_a


@pytest.mark.parametrize(
    'inputs,expected_values',
    [
        (
            dict(preferred_batch_size=4, timeout=5_000),
            dict(preferred_batch_size=4, timeout=5_000, flush_all=False, use_custom_metric=False, custom_metric=None, use_dynamic_batching=True),
        ),
        (
            dict(preferred_batch_size=4, timeout=5_000, flush_all=True),
            dict(preferred_batch_size=4, timeout=5_000, flush_all=True, use_custom_metric=False, custom_metric=None, use_dynamic_batching=True),
        ),
        (
            dict(preferred_batch_size=4),
            dict(preferred_batch_size=4, timeout=10_000, flush_all=False, use_custom_metric=False, custom_metric=None, use_dynamic_batching=True),
        ),
    ],
)
def test_dynamic_batching(inputs, expected_values):
    class MyExec(Executor):
        @dynamic_batching(**inputs)
        def foo(self, docs, **kwargs):
            pass

    exec = MyExec()
    assert exec.dynamic_batching['foo'] == expected_values


@pytest.mark.parametrize(
    'inputs,expected_values',
    [
        (
            dict(preferred_batch_size=4, timeout=5_000),
            dict(preferred_batch_size=4, timeout=5_000, flush_all=False, use_custom_metric=False, custom_metric=None, use_dynamic_batching=True),
        ),
        (
            dict(preferred_batch_size=4, timeout=5_000, flush_all=True),
            dict(preferred_batch_size=4, timeout=5_000, flush_all=True, use_custom_metric=False, custom_metric=None, use_dynamic_batching=True),
        ),
        (
            dict(preferred_batch_size=4),
            dict(preferred_batch_size=4, timeout=10_000, flush_all=False, use_custom_metric=False, custom_metric=None, use_dynamic_batching=True),
        ),
    ],
)
def test_combined_decorators(inputs, expected_values):
    class MyExecutor(Executor):
        @dynamic_batching(**inputs)
        @requests(on='/foo')
        def foo(self, docs, **kwargs):
            pass

    exec = MyExecutor()
    assert exec.dynamic_batching['foo'] == expected_values

    class MyExecutor2(Executor):
        @requests(on='/foo')
        @dynamic_batching(**inputs)
        def foo(self, docs, **kwargs):
            pass

    exec = MyExecutor2()
    assert exec.dynamic_batching['foo'] == expected_values


def test_write_decorator():
    class WriteExecutor(Executor):
        @write
        @requests(on='/delete')
        def delete(self, **kwargs):
            pass

        @requests(on='/bar')
        @write
        def bar(self, **kwargs):
            pass

        @requests(on='/index')
        @write()
        def index(self, **kwargs):
            pass

        @write()
        @requests(on='/update')
        def update(self, **kwargs):
            pass

        @requests(on='/search')
        def search(self, **kwargs):
            pass

        @requests
        def foo(self, **kwargs):
            pass

    exec = WriteExecutor()
    assert set(exec.write_endpoints) == {'/index', '/update', '/delete', '/bar'}
