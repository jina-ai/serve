import asyncio
import copy
from asyncio import Event, Task
from typing import Callable, Dict, List, Optional, TYPE_CHECKING, Union
from jina._docarray import docarray_v2

if not docarray_v2:
    from docarray import DocumentArray
else:
    from docarray import DocList
from jina.types.request.data import DataRequest

if TYPE_CHECKING:
    from jina._docarray import DocumentArray


class BatchQueue:
    """A batch queue that holds the data request and the callable to batch requests to."""

    def __init__(
            self,
            func: Callable,
            request_docarray_cls,
            response_docarray_cls,
            output_array_type: Optional[str] = None,
            params: Optional[Dict] = None,
            flush_all: bool = False,
            preferred_batch_size: int = 4,
            timeout: int = 10_000,
            custom_metric: Optional[Callable[['DocumentArray'], Union[int, float]]] = None,
            use_custom_metric: bool = False,
            **kwargs,
    ) -> None:
        # To keep old user behavior, we use data lock when flush_all is true and no allow_concurrent
        self.func = func
        if params is None:
            params = dict()
        self._is_closed = False
        self._output_array_type = output_array_type
        self.params = params
        self._request_docarray_cls = request_docarray_cls
        self._response_docarray_cls = response_docarray_cls
        self._flush_all = flush_all
        self._preferred_batch_size: int = preferred_batch_size
        self._custom_metric = None if not use_custom_metric else custom_metric
        self._metric_value = 0
        self._timeout: int = timeout
        self._reset()
        self._flush_trigger: Event = Event()
        self._timer_started, self._timer_finished = False, False
        self._timer_task: Optional[Task] = None

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(preferred_batch_size={self._preferred_batch_size}, timeout={self._timeout})'

    def __str__(self) -> str:
        return self.__repr__()

    def _reset(self) -> None:
        """Set all events and reset the batch queue."""
        self._requests: List[DataRequest] = []
        # a list of every request idx inside self._requests
        self._request_idxs: List[int] = []
        self._request_lens: List[int] = []
        self._docs_metrics: List[int] = []
        self._requests_completed: List[asyncio.Queue] = []
        if not docarray_v2:
            self._big_doc: DocumentArray = DocumentArray.empty()
        else:
            self._big_doc = self._request_docarray_cls()
        self._metric_value = 0

        self._flush_task: Optional[Task] = None
        self._flush_trigger: Event = Event()

    def _cancel_timer_if_pending(self):
        if (
                self._timer_task
                and not self._timer_task.done()
                and not self._timer_task.cancelled()
        ):
            self._timer_finished = False
            self._timer_task.cancel()

    def _start_timer(self):
        self._cancel_timer_if_pending()
        self._timer_task = asyncio.create_task(self._sleep_then_set())

    async def _sleep_then_set(self):
        """Sleep and then set the event"""
        self._timer_finished = False
        await asyncio.sleep(self._timeout / 1000)
        self._flush_trigger.set()
        self._timer_finished = True

    async def push(self, request: DataRequest, http=False) -> asyncio.Queue:
        """Append request to the the list of requests to be processed.

        This method creates an asyncio Queue for that request and keeps track of it. It returns
        this queue to the caller so that the caller can now when this request has been processed

        :param request: The request to append to the queue.
        :param http: Flag to determine if the request is served via HTTP for some optims

        :return: The queue that will receive when the request is processed.
        """
        docs = request.docs

        if not self._timer_task or self._timer_finished:
            # If there is no timer (first arrival), or the timer is already consumed, any new push should trigger a new Timer, before
            # this push requests the data lock. The order of accessing the data lock guarantees that this request will be put in the `big_doc`
            # before the `flush` task processes it.
            self._start_timer()
        if not self._flush_task:
            self._flush_task = asyncio.create_task(self._await_then_flush(http))
        self._big_doc.extend(docs)
        next_req_idx = len(self._requests)
        num_docs = len(docs)
        metric_value = num_docs
        if self._custom_metric is not None:
            metrics = [self._custom_metric(doc) for doc in docs]
            metric_value += sum(metrics)
            self._docs_metrics.extend(metrics)
        self._metric_value += metric_value
        self._request_idxs.extend([next_req_idx] * num_docs)
        self._request_lens.append(num_docs)
        self._requests.append(request)
        queue = asyncio.Queue()
        self._requests_completed.append(queue)
        if self._metric_value >= self._preferred_batch_size:
            self._flush_trigger.set()

        return queue

    async def _await_then_flush(self, http=False) -> None:
        """Process all requests in the queue once flush_trigger event is set.
        :param http: Flag to determine if the request is served via HTTP for some optims
        """

        def _get_docs_groups_completed_request_indexes(
                non_assigned_docs,
                non_assigned_docs_reqs_idx,
                sum_from_previous_mini_batch_in_first_req_idx,
                requests_lens_in_batch,
        ):
            """
            This method groups all the `non_assigned_docs` into groups of docs according to the `req_idx` they belong to.
            They are only distributed when we are sure that the request is full.

            :param non_assigned_docs: The documents that have already been processed but have not been assigned to a request result
            :param non_assigned_docs_reqs_idx: The request IDX that are not yet completed (not all of its docs have been processed)
            :param sum_from_previous_mini_batch_in_first_req_idx: The number of docs from previous iteration that belong to the first non_assigned_req_idx. This is useful to make sure we know when a request is completed.
            :param requests_lens_in_batch: List of lens of documents for each request in the batch.

            :return: list of document groups and a list of request Idx to which each of these groups belong
            """
            distributed_requests = []
            completed_req_idx = []
            num_distributed_docs = 0
            num_docs_in_req_idx = 0
            min_involved_req_idx = non_assigned_docs_reqs_idx[0]
            req_idx = min_involved_req_idx
            for req_idx in non_assigned_docs_reqs_idx:
                sum_from_previous_mini_batch_in_first_req_idx -= (
                    1  # the previous leftovers are being allocated here
                )
                if req_idx > min_involved_req_idx:
                    request_bucket = non_assigned_docs[
                                     num_distributed_docs: num_distributed_docs
                                                           + num_docs_in_req_idx
                                     ]
                    num_distributed_docs += num_docs_in_req_idx
                    completed_req_idx.append(min_involved_req_idx)
                    min_involved_req_idx = req_idx
                    num_docs_in_req_idx = 0
                    distributed_requests.append(request_bucket)
                num_docs_in_req_idx += 1

            if (
                    req_idx not in completed_req_idx
                    and num_docs_in_req_idx + sum_from_previous_mini_batch_in_first_req_idx
                    == requests_lens_in_batch[req_idx]
            ):
                completed_req_idx.append(req_idx)
                request_bucket = non_assigned_docs[
                                 num_distributed_docs: num_distributed_docs + num_docs_in_req_idx
                                 ]
                distributed_requests.append(request_bucket)

            return distributed_requests, completed_req_idx

        async def _assign_results(
                non_assigned_docs,
                non_assigned_docs_reqs_idx,
                sum_from_previous_mini_batch_in_first_req_idx,
                requests_lens_in_batch,
                requests_in_batch,
                requests_completed_in_batch,
        ):
            """
            This method aims to assign to the corresponding request objects the resulting documents from the mini batches.
            They are assigned when we are sure that the Request is fully processed.
            It also communicates to the corresponding queue that the request is full so that it can be returned

            :param non_assigned_docs: The documents that have already been processed but have not been assigned to a request result
            :param non_assigned_docs_reqs_idx: The request IDX that are not yet completed (not all of its docs have been processed)
            :param sum_from_previous_mini_batch_in_first_req_idx: The number of docs from previous iteration that belong to the first non_assigned_req_idx. This is useful to make sure we know when a request is completed.
            :param requests_lens_in_batch: List of lens of documents for each request in the batch.
            :param requests_in_batch: List requests in batch
            :param requests_completed_in_batch: List of queues for requests to be completed

            :return: amount of assigned documents so that some documents can come back in the next iteration
            """
            (
                docs_grouped,
                completed_req_idxs,
            ) = _get_docs_groups_completed_request_indexes(
                non_assigned_docs,
                non_assigned_docs_reqs_idx,
                sum_from_previous_mini_batch_in_first_req_idx,
                requests_lens_in_batch
            )
            num_assigned_docs = sum(len(group) for group in docs_grouped)

            for docs_group, request_idx in zip(docs_grouped, completed_req_idxs):
                request = requests_in_batch[request_idx]
                request_completed = requests_completed_in_batch[request_idx]
                if http is False or self._output_array_type is not None:
                    request.direct_docs = None  # batch queue will work in place, therefore result will need to read from data.
                    request.data.set_docs_convert_arrays(
                        docs_group, ndarray_type=self._output_array_type
                    )
                else:
                    request.direct_docs = docs_group
                await request_completed.put(None)

            return num_assigned_docs

        def batch(iterable_1, iterable_2, n: Optional[int] = 1, iterable_metrics: Optional = None):
            if n is None:
                yield iterable_1, iterable_2
                return
            elif iterable_metrics is None:
                items = len(iterable_1)
                for ndx in range(0, items, n):
                    yield iterable_1[ndx: min(ndx + n, items)], iterable_2[
                                                                ndx: min(ndx + n, items)
                                                                ]
            else:
                batch_idx = 0
                batch_weight = 0

                for i, (item, weight) in enumerate(zip(iterable_1, iterable_metrics)):
                    batch_weight += weight

                    if batch_weight >= n:
                        yield iterable_1[batch_idx: i + 1], iterable_2[batch_idx: i + 1]
                        batch_idx = i + 1
                        batch_weight = 0

                # Yield any remaining items
                if batch_weight > 0:
                    yield iterable_1[batch_idx: len(iterable_1)], iterable_2[batch_idx: len(iterable_1)]

        await self._flush_trigger.wait()
        # writes to shared data between tasks need to be mutually exclusive
        big_doc_in_batch = copy.copy(self._big_doc)
        requests_idxs_in_batch = copy.copy(self._request_idxs)
        requests_lens_in_batch = copy.copy(self._request_lens)
        docs_metrics_in_batch = copy.copy(self._docs_metrics)
        requests_in_batch = copy.copy(self._requests)
        requests_completed_in_batch = copy.copy(self._requests_completed)

        self._reset()

        # At this moment, we have documents concatenated in big_doc_in_batch corresponding to requests in
        # requests_idxs_in_batch with its lengths stored in requests_lens_in_batch. For each requests, there is a queue to
        # communicate that the request has been processed properly.

        if not docarray_v2:
            non_assigned_to_response_docs: DocumentArray = DocumentArray.empty()
        else:
            non_assigned_to_response_docs = self._response_docarray_cls()

        non_assigned_to_response_request_idxs = []
        sum_from_previous_first_req_idx = 0
        for docs_inner_batch, req_idxs in batch(
                big_doc_in_batch, requests_idxs_in_batch,
                self._preferred_batch_size if not self._flush_all else None,
                docs_metrics_in_batch if self._custom_metric is not None else None
        ):
            involved_requests_min_indx = req_idxs[0]
            involved_requests_max_indx = req_idxs[-1]
            input_len_before_call: int = len(docs_inner_batch)
            batch_res_docs = None
            try:
                batch_res_docs = await self.func(
                    docs=docs_inner_batch,
                    parameters=self.params,
                    docs_matrix=None,  # joining manually with batch queue is not supported right now
                    tracing_context=None,
                )
                # Output validation
                if (docarray_v2 and isinstance(batch_res_docs, DocList)) or (
                        not docarray_v2
                        and isinstance(batch_res_docs, DocumentArray)
                ):
                    if not len(batch_res_docs) == input_len_before_call:
                        raise ValueError(
                            f'Dynamic Batching requires input size to equal output size. Expected output size {input_len_before_call}, but got {len(batch_res_docs)}'
                        )
                elif batch_res_docs is None:
                    if not len(docs_inner_batch) == input_len_before_call:
                        raise ValueError(
                            f'Dynamic Batching requires input size to equal output size. Expected output size {input_len_before_call}, but got {len(docs_inner_batch)}'
                        )
                else:
                    array_name = (
                        'DocumentArray' if not docarray_v2 else 'DocList'
                    )
                    raise TypeError(
                        f'The return type must be {array_name} / `None` when using dynamic batching, '
                        f'but getting {batch_res_docs!r}'
                    )
            except Exception as exc:
                # All the requests containing docs in this Exception should be raising it
                for request_full in requests_completed_in_batch[
                                    involved_requests_min_indx: involved_requests_max_indx + 1
                                    ]:
                    await request_full.put(exc)
            else:
                # We need to attribute the docs to their requests
                non_assigned_to_response_docs.extend(
                    batch_res_docs or docs_inner_batch
                )
                non_assigned_to_response_request_idxs.extend(req_idxs)
                num_assigned_docs = await _assign_results(
                    non_assigned_to_response_docs,
                    non_assigned_to_response_request_idxs,
                    sum_from_previous_first_req_idx,
                    requests_lens_in_batch,
                    requests_in_batch,
                    requests_completed_in_batch,
                )

                sum_from_previous_first_req_idx = (
                        len(non_assigned_to_response_docs) - num_assigned_docs
                )
                non_assigned_to_response_docs = non_assigned_to_response_docs[
                                                num_assigned_docs:
                                                ]
                non_assigned_to_response_request_idxs = (
                    non_assigned_to_response_request_idxs[num_assigned_docs:]
                )
        if len(non_assigned_to_response_request_idxs) > 0:
            _ = await _assign_results(
                non_assigned_to_response_docs,
                non_assigned_to_response_request_idxs,
                sum_from_previous_first_req_idx,
                requests_lens_in_batch,
                requests_in_batch,
                requests_completed_in_batch,
            )

    async def close(self):
        """Closes the batch queue by flushing pending requests."""
        if not self._is_closed:
            # debug print amount of requests to be processed.
            self._flush_trigger.set()
            if self._flush_task:
                await self._flush_task
            self._cancel_timer_if_pending()
            self._is_closed = True
