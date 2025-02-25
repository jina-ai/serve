import asyncio

import pytest
import time

from jina import Document, DocumentArray
from jina.serve.runtimes.worker.batch_queue import BatchQueue
from jina.types.request.data import DataRequest


@pytest.mark.asyncio
@pytest.mark.parametrize('flush_all', [False, True])
async def test_batch_queue_timeout(flush_all):
    async def foo(docs, **kwargs):
        await asyncio.sleep(0.1)
        return DocumentArray([Document(text='Done') for _ in docs])

    bq: BatchQueue = BatchQueue(
        foo,
        request_docarray_cls=DocumentArray,
        response_docarray_cls=DocumentArray,
        preferred_batch_size=4,
        timeout=2000,
        flush_all=flush_all,
    )

    three_data_requests = [DataRequest() for _ in range(3)]
    for req in three_data_requests:
        req.data.docs = DocumentArray.empty(1)
        assert req.docs[0].text == ''

    async def process_request(req):
        q = await bq.push(req)
        _ = await q.get()
        q.task_done()
        return req

    init_time = time.time()
    tasks = [asyncio.create_task(process_request(req)) for req in three_data_requests]
    responses = await asyncio.gather(*tasks)
    time_spent = (time.time() - init_time) * 1000
    assert time_spent >= 2000
    # Test that since no more docs arrived, the function was triggerred after timeout
    for resp in responses:
        assert resp.docs[0].text == 'Done'

    four_data_requests = [DataRequest() for _ in range(4)]
    for req in four_data_requests:
        req.data.docs = DocumentArray.empty(1)
        assert req.docs[0].text == ''
    init_time = time.time()
    tasks = [asyncio.create_task(process_request(req)) for req in four_data_requests]
    responses = await asyncio.gather(*tasks)
    time_spent = (time.time() - init_time) * 1000
    assert time_spent < 2000
    # Test that since no more docs arrived, the function was triggerred after timeout
    for resp in responses:
        assert resp.docs[0].text == 'Done'

    await bq.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('flush_all', [False, True])
async def test_batch_queue_timeout_does_not_wait_previous_batch(flush_all):
    batches_lengths_computed = []

    async def foo(docs, **kwargs):
        await asyncio.sleep(4)
        batches_lengths_computed.append(len(docs))
        return DocumentArray([Document(text='Done') for _ in docs])

    bq: BatchQueue = BatchQueue(
        foo,
        request_docarray_cls=DocumentArray,
        response_docarray_cls=DocumentArray,
        preferred_batch_size=5,
        timeout=3000,
        flush_all=flush_all,
    )

    data_requests = [DataRequest() for _ in range(3)]
    for req in data_requests:
        req.data.docs = DocumentArray([Document(text=''), Document(text='')])

    extra_data_request = DataRequest()
    extra_data_request.data.docs = DocumentArray([Document(text=''), Document(text='')])

    async def process_request(req, sleep=0):
        if sleep > 0:
            await asyncio.sleep(sleep)
        q = await bq.push(req)
        _ = await q.get()
        q.task_done()
        return req

    init_time = time.time()
    tasks = [asyncio.create_task(process_request(req)) for req in data_requests]
    tasks.append(asyncio.create_task(process_request(extra_data_request, sleep=2)))
    _ = await asyncio.gather(*tasks)
    time_spent = (time.time() - init_time) * 1000

    if flush_all is False:
        # TIME TAKEN: 8000 for first batch of requests, plus 4000 for second batch that is fired inmediately
        # BEFORE FIX in https://github.com/jina-ai/jina/pull/6071, this would take: 8000 + 3000 + 4000 (Timeout would start counting too late)
        assert time_spent >= 8000
        assert time_spent <= 8500
        assert batches_lengths_computed == [5, 2, 1]
    else:
        assert time_spent >= 7000
        assert time_spent <= 7500
        assert batches_lengths_computed == [6, 2]

    await bq.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('flush_all', [False, True])
async def test_batch_queue_req_length_larger_than_preferred(flush_all):
    async def foo(docs, **kwargs):
        await asyncio.sleep(0.1)
        return DocumentArray([Document(text='Done') for _ in docs])

    bq: BatchQueue = BatchQueue(
        foo,
        request_docarray_cls=DocumentArray,
        response_docarray_cls=DocumentArray,
        preferred_batch_size=4,
        timeout=2000,
        flush_all=flush_all,
    )

    data_requests = [DataRequest() for _ in range(3)]
    for req in data_requests:
        req.data.docs = DocumentArray.empty(10)  # 30 docs in total
        assert req.docs[0].text == ''

    async def process_request(req):
        q = await bq.push(req)
        _ = await q.get()
        q.task_done()
        return req

    init_time = time.time()
    tasks = [asyncio.create_task(process_request(req)) for req in data_requests]
    responses = await asyncio.gather(*tasks)
    time_spent = (time.time() - init_time) * 1000
    assert time_spent < 2000
    # Test that since no more docs arrived, the function was triggerred after timeout
    for resp in responses:
        assert resp.docs[0].text == 'Done'

    await bq.close()


@pytest.mark.asyncio
async def test_exception():
    BAD_REQUEST_IDX = [2, 6]

    async def foo(docs, **kwargs):
        await asyncio.sleep(0.1)
        assert len(docs) == 1
        if docs[0].text == 'Bad':
            raise Exception
        for doc in docs:
            doc.text += ' Processed'

    bq: BatchQueue = BatchQueue(
        foo,
        request_docarray_cls=DocumentArray,
        response_docarray_cls=DocumentArray,
        preferred_batch_size=1,
        timeout=500,
        flush_all=False,
    )

    data_requests = [DataRequest() for _ in range(35)]
    for i, req in enumerate(data_requests):
        req.data.docs = DocumentArray(
            Document(text=f'{i}' if i not in BAD_REQUEST_IDX else 'Bad')
        )

    async def process_request(req):
        q = await bq.push(req)
        item = await q.get()
        q.task_done()
        return item

    tasks = [asyncio.create_task(process_request(req)) for req in data_requests]
    items = await asyncio.gather(*tasks)
    for i, item in enumerate(items):
        if i not in BAD_REQUEST_IDX:
            assert item is None
        else:
            assert isinstance(item, Exception)
    for i, req in enumerate(data_requests):
        if i not in BAD_REQUEST_IDX:
            assert req.docs[0].text == f'{i} Processed'
        else:
            assert req.docs[0].text == 'Bad'


@pytest.mark.asyncio
async def test_exception_more_complex():
    TRIGGER_BAD_REQUEST_IDX = [2, 6]
    EXPECTED_BAD_REQUESTS = [2, 3, 6, 7]

    # REQUESTS 0, 1 should be good
    # REQUESTS 2, 3 should be bad
    # REQUESTS 4, 5 should be good
    # REQUESTS 6, 7 should be bad
    async def foo(docs, **kwargs):
        await asyncio.sleep(0.1)
        if docs[0].text == 'Bad':
            raise Exception
        for doc in docs:
            doc.text = 'Processed'

    bq: BatchQueue = BatchQueue(
        foo,
        request_docarray_cls=DocumentArray,
        response_docarray_cls=DocumentArray,
        preferred_batch_size=2,
        timeout=500,
        flush_all=False,
    )

    data_requests = [DataRequest() for _ in range(35)]
    for i, req in enumerate(data_requests):
        req.data.docs = DocumentArray(
            Document(text='' if i not in TRIGGER_BAD_REQUEST_IDX else 'Bad')
        )

    async def process_request(req):
        q = await bq.push(req)
        item = await q.get()
        q.task_done()
        return item

    tasks = [asyncio.create_task(process_request(req)) for req in data_requests]
    items = await asyncio.gather(*tasks)
    for i, item in enumerate(items):
        if i not in EXPECTED_BAD_REQUESTS:
            assert item is None
        else:
            assert isinstance(item, Exception)
    for i, req in enumerate(data_requests):
        if i not in EXPECTED_BAD_REQUESTS:
            assert req.docs[0].text == 'Processed'
        elif i in TRIGGER_BAD_REQUEST_IDX:
            assert req.docs[0].text == 'Bad'
        else:
            assert req.docs[0].text == ''


@pytest.mark.asyncio
@pytest.mark.parametrize('flush_all', [False, True])
async def test_exception_all(flush_all):
    async def foo(docs, **kwargs):
        raise AssertionError

    bq: BatchQueue = BatchQueue(
        foo,
        request_docarray_cls=DocumentArray,
        response_docarray_cls=DocumentArray,
        preferred_batch_size=2,
        flush_all=flush_all,
        timeout=500,
    )

    data_requests = [DataRequest() for _ in range(10)]
    for i, req in enumerate(data_requests):
        req.data.docs = DocumentArray(Document(text=''))

    async def process_request(req):
        q = await bq.push(req)
        item = await q.get()
        q.task_done()
        return item

    tasks = [asyncio.create_task(process_request(req)) for req in data_requests]
    items = await asyncio.gather(*tasks)
    for i, item in enumerate(items):
        assert isinstance(item, Exception)


@pytest.mark.asyncio
async def test_repr_and_str():
    async def foo(docs, **kwargs):
        return DocumentArray([Document(text='Done') for _ in docs])

    bq: BatchQueue = BatchQueue(
        foo,
        request_docarray_cls=DocumentArray,
        response_docarray_cls=DocumentArray,
        preferred_batch_size=4,
        timeout=500,
    )

    assert repr(bq) == str(bq)


@pytest.mark.parametrize('num_requests', [33, 127, 100])
@pytest.mark.parametrize('preferred_batch_size', [7, 61, 100])
@pytest.mark.parametrize('timeout', [0.3, 500])
@pytest.mark.parametrize('flush_all', [False, True])
@pytest.mark.asyncio
async def test_return_proper_assignment(num_requests, preferred_batch_size, timeout, flush_all):
    import random

    async def foo(docs, **kwargs):
        if not flush_all:
            assert len(docs) <= preferred_batch_size
        else:
            assert len(docs) >= preferred_batch_size
        await asyncio.sleep(0.1)
        for doc in docs:
            doc.text += ' Processed'

    bq: BatchQueue = BatchQueue(
        foo,
        request_docarray_cls=DocumentArray,
        response_docarray_cls=DocumentArray,
        preferred_batch_size=preferred_batch_size,
        flush_all=flush_all,
        timeout=timeout,
    )

    data_requests = [DataRequest() for _ in range(num_requests)]
    len_requests = []
    for i, req in enumerate(data_requests):
        len_request = random.randint(2, 27)
        len_requests.append(len_request)
        req.data.docs = DocumentArray(
            [
                Document(text=f'Text {j} from request {i} with len {len_request}')
                for j in range(len_request)
            ]
        )

    async def process_request(req):
        q = await bq.push(req)
        item = await q.get()
        q.task_done()
        return item

    tasks = [asyncio.create_task(process_request(req)) for req in data_requests]
    items = await asyncio.gather(*tasks)
    for i, item in enumerate(items):
        assert item is None

    for i, (resp, length) in enumerate(zip(data_requests, len_requests)):
        assert len(resp.docs) == length
        for j, d in enumerate(resp.docs):
            assert d.text == f'Text {j} from request {i} with len {length} Processed'
