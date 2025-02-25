import multiprocessing
import random
import time
from functools import partial

import pytest

from jina import Client, Document, DocumentArray, Executor, Flow, requests
from jina.types.request.data import Response

NUM_REQUESTS = 5


class MyExecutor(Executor):
    @requests(on='/ping')
    def ping(self, **kwargs):
        time.sleep(0.1 * random.random())


@pytest.mark.parametrize('protocol', ['http', 'grpc'])
@pytest.mark.parametrize('shards', [10])
@pytest.mark.parametrize('polling', ['ANY', 'ALL'])
@pytest.mark.parametrize('prefetch', [1, 10])
@pytest.mark.parametrize('concurrent', [15])
@pytest.mark.parametrize('use_stream', [False, True])
@pytest.mark.parametrize('reuse_session', [True, False])
def test_concurrent_clients(
    concurrent, protocol, shards, polling, prefetch, reraise, use_stream, reuse_session
):

    if not use_stream and protocol != 'grpc':
        return

    if reuse_session and protocol != 'http':
        return

    def pong(peer_hash, queue, resp: Response):
        for d in resp.docs:
            queue.put((peer_hash, d.text))

    def peer_client(port, protocol, peer_hash, queue):
        c = Client(protocol=protocol, port=port, reuse_session=reuse_session)
        for _ in range(NUM_REQUESTS):
            c.post(
                '/ping',
                Document(text=peer_hash),
                on_done=lambda r: pong(peer_hash, queue, r),
                return_responses=True,
                stream=use_stream,
            )

    f = Flow(protocol=protocol, prefetch=prefetch).add(
        uses=MyExecutor, shards=shards, polling=polling
    )

    with f:
        pqueue = multiprocessing.Queue()
        port = f.port
        process_pool = []
        for peer_id in range(concurrent):
            p = multiprocessing.Process(
                target=partial(peer_client, port, protocol, str(peer_id), pqueue),
                daemon=True,
            )
            p.start()
            process_pool.append(p)

        for p in process_pool:
            p.join()

        queue_len = 0
        while not pqueue.empty():
            peer_hash, text = pqueue.get()
            assert peer_hash == text
            queue_len += 1
        assert queue_len == concurrent * NUM_REQUESTS
