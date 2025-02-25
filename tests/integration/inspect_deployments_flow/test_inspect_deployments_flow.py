import os

import pytest

from jina import Client, DocumentArray, Executor, Flow, requests
from tests import random_docs


class DummyEvaluator1(Executor):
    tag = 1

    @requests(on=['/index'])
    def craft(self, docs, *args, **kwargs):
        tmp_dir = os.environ.get('TEST_EVAL_FLOW_TMPDIR')
        with open(f'{tmp_dir}/{self.tag}.txt', 'a', encoding='utf-8') as fp:
            fp.write(f'{docs[0].id}')
        return None


class DummyEvaluator2(DummyEvaluator1):
    tag = 2


class DummyEvaluator3(DummyEvaluator1):
    tag = 3


docs = DocumentArray([x for x in random_docs(1)])
params = ['HANG', 'COLLECT', 'REMOVE']


def validate(ids, expect):
    assert len(ids) > 0
    for j in ids:
        tmp_dir = os.environ.get('TEST_EVAL_FLOW_TMPDIR')
        fname = f'{tmp_dir}/{j}.txt'
        assert os.path.exists(fname) == expect
        if expect:
            with open(fname, encoding='utf-8') as fp:
                assert fp.read() != ''


@pytest.fixture
def temp_folder(tmpdir):
    os.environ['TEST_EVAL_FLOW_TMPDIR'] = str(tmpdir)
    yield
    del os.environ['TEST_EVAL_FLOW_TMPDIR']


@pytest.mark.parametrize('inspect', params)
@pytest.mark.parametrize('protocol', ['websocket', 'grpc'])
def test_flow1(inspect, protocol, temp_folder):
    f = Flow(protocol=protocol, inspect=inspect).add(
        uses=DummyEvaluator1,
        env={'TEST_EVAL_FLOW_TMPDIR': os.environ.get('TEST_EVAL_FLOW_TMPDIR')},
    )

    with f:
        res = f.post(on='/index', inputs=docs)

    assert len(res) > 0


@pytest.mark.parametrize('inspect', params)
@pytest.mark.parametrize('protocol', ['http', 'websocket', 'grpc'])
def test_flow2(inspect, protocol, temp_folder):
    f = (
        Flow(protocol=protocol, inspect=inspect)
        .add()
        .inspect(
            uses=DummyEvaluator1,
            env={'TEST_EVAL_FLOW_TMPDIR': os.environ.get('TEST_EVAL_FLOW_TMPDIR')},
        )
    )

    with f:
        res = f.index(docs)

    assert len(res) > 0
    validate([1], expect=f.args.inspect.is_keep)


@pytest.mark.parametrize('inspect', params)
@pytest.mark.parametrize('protocol', ['http', 'websocket', 'grpc'])
def test_flow3(inspect, protocol, temp_folder):
    env = {'TEST_EVAL_FLOW_TMPDIR': os.environ.get('TEST_EVAL_FLOW_TMPDIR')}

    f = (
        Flow(protocol=protocol, inspect=inspect)
        .add(name='p1')
        .inspect(uses='DummyEvaluator1', env=env)
        .add(name='p2', needs='gateway')
        .needs(['p1', 'p2'])
        .inspect(uses='DummyEvaluator2', env=env)
    )

    with f:
        res = f.index(docs)

    assert len(res) > 0
    validate([1, 2], expect=f.args.inspect.is_keep)


@pytest.mark.parametrize('inspect', params)
@pytest.mark.parametrize('protocol', ['http', 'websocket', 'grpc'])
def test_flow4(inspect, protocol, temp_folder):
    env = {'TEST_EVAL_FLOW_TMPDIR': os.environ.get('TEST_EVAL_FLOW_TMPDIR')}

    f = (
        Flow(protocol=protocol, inspect=inspect)
        .add()
        .inspect(uses='DummyEvaluator1', env=env)
        .add()
        .inspect(uses='DummyEvaluator2', env=env)
        .add()
        .inspect(uses='DummyEvaluator3', env=env)
        .plot(build=True)
    )

    with f:
        res = f.index(docs)

    assert len(res) > 0
    validate([1, 2, 3], expect=f.args.inspect.is_keep)


class AddEvaluationExecutor(Executor):
    @requests
    def transform(self, docs, *args, **kwargs):
        import time

        time.sleep(0.5)
        for doc in docs:
            doc.evaluations['evaluate'].value = 10.0


@pytest.mark.repeat(5)
@pytest.mark.parametrize('protocol', ['http', 'websocket', 'grpc'])
def test_flow_returned_collect(protocol, port_generator):
    # TODO(Joan): This test passes because we pass the `SlowExecutor` but I do not know how to make the `COLLECT` deployment
    # use an specific executor.

    exposed_port = port_generator()

    def validate_func(resp):
        num_evaluations = 0
        scores = set()
        for doc in resp.docs:
            num_evaluations += len(doc.evaluations)
            scores.add(doc.evaluations['evaluate'].value)
        assert num_evaluations == 1
        assert 10.0 in scores

    f = (
        Flow(protocol=protocol, inspect='COLLECT', port=exposed_port)
        .add()
        .inspect(
            uses=AddEvaluationExecutor,
        )
    )

    with f:
        response = Client(port=exposed_port, protocol=protocol).index(
            inputs=docs, return_responses=True
        )
    validate_func(response[0])


@pytest.mark.repeat(5)
@pytest.mark.parametrize('inspect', ['HANG', 'REMOVE'])
@pytest.mark.parametrize('protocol', ['websocket', 'grpc'])
def test_flow_not_returned(inspect, protocol, port_generator):
    exposed_port = port_generator()

    def validate_func(resp):
        for doc in resp.data.docs:
            assert len(doc.evaluations) == 0

    f = (
        Flow(protocol=protocol, inspect=inspect, port=exposed_port)
        .add()
        .inspect(
            uses=AddEvaluationExecutor,
        )
    )

    with f:
        res = Client(protocol=protocol, port=exposed_port).index(
            inputs=docs, return_responses=True
        )

    validate_func(res[0])
