"""Decorators and wrappers designed for wrapping :class:`BaseExecutor` functions. """

import functools
import inspect
import os
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Type, Union

from jina._docarray import Document, DocumentArray
from jina.constants import __cache_path__
from jina.helper import is_generator, iscoroutinefunction
from jina.importer import ImportExtensions


@functools.lru_cache()
def _get_locks_root() -> Path:
    locks_root = Path(os.path.join(__cache_path__, 'locks'))

    if not locks_root.exists():
        locks_root.mkdir(parents=True, exist_ok=True)

    return locks_root


def avoid_concurrent_lock_cls(cls):
    """Wraps a function to lock a filelock for concurrent access with the name of the class to which it applies, to avoid deadlocks
    :param cls: the class to which is applied, only when the class corresponds to the instance type, this filelock will apply
    :return: the wrapped function
    """

    def avoid_concurrent_lock_wrapper(func: Callable) -> Callable:
        """Wrap the function around a File Lock to make sure that the function is run by a single replica in the same machine
        :param func: the function to decorate
        :return: the wrapped function
        """

        @functools.wraps(func)
        def arg_wrapper(self, *args, **kwargs):
            if func.__name__ != '__init__':
                raise TypeError(
                    'this decorator should only be used on __init__ method of an executor'
                )

            if self.__class__ == cls:
                with ImportExtensions(
                    required=False,
                    help_text=f'FileLock is needed to guarantee non-concurrent initialization of replicas in the '
                    f'same machine.',
                ):
                    import filelock

                    locks_root = _get_locks_root()

                    lock_file = locks_root.joinpath(f'{self.__class__.__name__}.lock')

                    file_lock = filelock.FileLock(lock_file, timeout=-1)

                with file_lock:
                    f = func(self, *args, **kwargs)
                return f
            else:
                return func(self, *args, **kwargs)

        return arg_wrapper

    return avoid_concurrent_lock_wrapper


def _init_requests_by_class(cls):
    """
    To allow inheritance and still have coherent usage of `requests`. Makes sure that a child class inherits requests from parents

    :param cls: The class.
    """
    if not hasattr(cls, 'requests_by_class'):
        cls.requests_by_class = {}

    if cls.__name__ not in cls.requests_by_class:
        cls.requests_by_class[cls.__name__] = {}

        def _inherit_from_parent_class_inner(cls_):
            for parent_class in cls_.__bases__:
                parent_dict = cls.requests_by_class.get(parent_class.__name__, {})
                for k, v in parent_dict.items():
                    if k not in cls.requests_by_class[cls.__name__]:
                        cls.requests_by_class[cls.__name__][k] = v
                _inherit_from_parent_class_inner(parent_class)

        # assume that `requests` is called when importing class, so parent classes will be processed before
        # inherit all the requests from parents
        _inherit_from_parent_class_inner(cls)


def write(
    func: Optional[
        Callable[
            [
                'DocumentArray',
                Dict,
                'DocumentArray',
                List['DocumentArray'],
                List['DocumentArray'],
            ],
            Optional[Union['DocumentArray', Dict]],
        ]
    ] = None
):
    """
    `@write` is a decorator indicating that the function decorated will change the Executor finite state machine

    Calls to methods decorated with `write` will be handled by `RAFT` consensus algorithm to guarantee the consensus of the Executor between replicas when used as a `StatefulDeployment`

    EXAMPLE USAGE

    .. code-block:: python

        from jina import Deployment, Executor, requests
        from jina.serve.executors.decorators import write
        from docarray import DocList
        from docarray.documents import TextDoc


        class MyStateStatefulExecutor(Executor):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._docs_dict = {}

            @requests(on=['/index'])
            @write
            def index(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
                for doc in docs:
                    self._docs_dict[doc.id] = doc

            @requests(on=['/search'])
            def search(self, docs: DocList[TextDoc], **kwargs) -> DocList[TextDoc]:
                for doc in docs:
                    self.logger.debug(f'Searching against {len(self._docs_dict)} documents')
                    doc.text = self._docs_dict[doc.id].text


        d = Deployment(
            name='stateful_executor',
            uses=MyStateStatefulExecutor,
            replicas=3,
            stateful=True,
            workspace='./raft',
            peer_ports=[12345, 12346, 12347],
        )
        with d:
            d.post(
                on='/index', inputs=TextDoc(text='I am here!')
            )  # send doc to `index` method which will be replicated using RAFT
            d.post(
                on='/search', inputs=TextDoc(text='Who is there?')
            )  # send doc to `search` method, that will bypass the RAFT apply


    :param func: the method to decorate
    :return: decorated function
    """

    class WriteMethodDecorator:
        def __init__(self, fn):
            self._requests_decorator = None
            fn = self._unwrap_requests_decorator(fn)
            if iscoroutinefunction(fn):

                @functools.wraps(fn)
                async def arg_wrapper(
                    executor_instance, *args, **kwargs
                ):  # we need to get the summary from the executor, so we need to access the self
                    with executor_instance._write_lock:
                        return await fn(executor_instance, *args, **kwargs)

                self.fn = arg_wrapper
            else:

                @functools.wraps(fn)
                def arg_wrapper(
                    executor_instance, *args, **kwargs
                ):  # we need to get the summary from the executor, so we need to access the self
                    with executor_instance._write_lock:
                        return fn(executor_instance, *args, **kwargs)

                self.fn = arg_wrapper

        def _unwrap_requests_decorator(self, fn):
            if type(fn).__name__ == 'FunctionMapper':
                self._requests_decorator = fn
                return fn.fn
            else:
                return fn

        def _inject_owner_attrs(self, owner, name):
            if not hasattr(owner, '_write_methods'):
                owner._write_methods = []

            owner._write_methods.append(self.fn.__name__)

        def __set_name__(self, owner, name):
            _init_requests_by_class(owner)
            if self._requests_decorator:
                self._requests_decorator._inject_owner_attrs(owner, name, None, None)

            self._inject_owner_attrs(owner, name)

            setattr(owner, name, self.fn)

        def __call__(self, *args, **kwargs):
            # this is needed to make this decorator work in combination with `@requests`
            return self.fn(*args, **kwargs)

    if func:
        return WriteMethodDecorator(func)
    else:
        return WriteMethodDecorator


def requests(
    func: Optional[
        Callable[
            [
                'DocumentArray',
                Dict,
                'DocumentArray',
                List['DocumentArray'],
                List['DocumentArray'],
            ],
            Optional[Union['DocumentArray', Dict]],
        ]
    ] = None,
    *,
    on: Optional[Union[str, Sequence[str]]] = None,
    request_schema: Optional[Type[DocumentArray]] = None,
    response_schema: Optional[Union[Type[DocumentArray], Type[Document]]] = None,
):
    """
    `@requests` defines the endpoints of an Executor. It has a keyword `on=` to
    define the endpoint.

    A class method decorated with plain `@requests` (without `on=`) is the default
    handler for all endpoints.
    That means, it is the fallback handler for endpoints that are not found.

    EXAMPLE USAGE

    .. code-block:: python

        from jina import Executor, requests, Flow
        from docarray import Document

        # define Executor with custom `@requests` endpoints
        class MyExecutor(Executor):
            @requests(on='/index')
            def index(self, docs, **kwargs):
                print(docs)  # index docs here

            @requests(on=['/search', '/query'])
            def search(self, docs, **kwargs):
                print(docs)  # perform search here

            @requests  # default/fallback endpoint
            def foo(self, docs, **kwargs):
                print(docs)  # process docs here


        f = Flow().add(uses=MyExecutor)  # add your Executor to a Flow
        with f:
            f.post(
                on='/index', inputs=Document(text='I am here!')
            )  # send doc to `index` method
            f.post(
                on='/search', inputs=Document(text='Who is there?')
            )  # send doc to `search` method
            f.post(
                on='/query', inputs=Document(text='Who is there?')
            )  # send doc to `search` method
            f.post(on='/bar', inputs=Document(text='Who is there?'))  # send doc to
            # `foo` method

    :param func: the method to decorate
    :param on: the endpoint string, by convention starts with `/`
    :param request_schema: the type of the input document
    :param response_schema: the type of the output document
    :return: decorated function
    """
    from jina.constants import __args_executor_func__, __default_endpoint__

    if func:
        setattr(func, '__is_generator__', is_generator(func))

    class FunctionMapper:
        def __init__(self, fn):

            if fn:
                setattr(fn, '__is_generator__', is_generator(fn))
            self._batching_decorator = None
            self._write_decorator = None
            fn = self._unwrap_batching_decorator(fn)
            fn = self._unwrap_write_decorator(fn)
            arg_spec = inspect.getfullargspec(fn)
            if not arg_spec.varkw and not __args_executor_func__.issubset(
                arg_spec.args
            ):
                raise TypeError(
                    f'{fn} accepts only {arg_spec.args} which is fewer than expected, '
                    f'please add `**kwargs` to the function signature.'
                )

            if iscoroutinefunction(fn):

                @functools.wraps(fn)
                async def arg_wrapper(
                    executor_instance, *args, **kwargs
                ):  # we need to get the summary from the executor, so we need to access the self
                    return await fn(executor_instance, *args, **kwargs)

                self.fn = arg_wrapper
            else:

                @functools.wraps(fn)
                def arg_wrapper(
                    executor_instance, *args, **kwargs
                ):  # we need to get the summary from the executor, so we need to access the self
                    return fn(executor_instance, *args, **kwargs)

                self.fn = arg_wrapper

        def _unwrap_batching_decorator(self, fn):
            if type(fn).__name__ == 'DynamicBatchingDecorator':
                self._batching_decorator = fn
                return fn.fn
            else:
                return fn

        def _unwrap_write_decorator(self, fn):
            if type(fn).__name__ == 'WriteMethodDecorator':
                self._write_decorator = fn
                return fn.fn
            else:
                return fn

        def _inject_owner_attrs(
            self, owner, name, request_schema_arg, response_schema_arg
        ):
            if not hasattr(owner, 'requests'):
                owner.requests = {}

            from jina.serve.executors import _FunctionWithSchema

            fn_with_schema = _FunctionWithSchema.get_function_with_schema(self.fn)

            request_schema_arg = (
                request_schema_arg
                if request_schema_arg
                else fn_with_schema.request_schema
            )
            response_schema_arg = (
                response_schema_arg
                if response_schema_arg
                else fn_with_schema.response_schema
            )

            fn_with_schema = _FunctionWithSchema(
                fn=fn_with_schema.fn,
                is_generator=fn_with_schema.is_generator,
                is_singleton_doc=fn_with_schema.is_singleton_doc,
                is_batch_docs=fn_with_schema.is_batch_docs,
                parameters_is_pydantic_model=fn_with_schema.parameters_is_pydantic_model,
                parameters_model=fn_with_schema.parameters_model,
                request_schema=request_schema_arg,
                response_schema=response_schema_arg,
            )
            fn_with_schema.validate()

            if isinstance(on, (list, tuple)):
                for o in on:
                    owner.requests_by_class[owner.__name__][o] = fn_with_schema
            else:
                owner.requests_by_class[owner.__name__][
                    on or __default_endpoint__
                ] = fn_with_schema

            setattr(owner, name, self.fn)

        def __set_name__(self, owner, name):
            _init_requests_by_class(owner)
            if self._batching_decorator:
                self._batching_decorator._inject_owner_attrs(owner, name)
            if self._write_decorator:
                self._write_decorator._inject_owner_attrs(owner, name)
            self.fn.class_name = owner.__name__
            self._inject_owner_attrs(owner, name, request_schema, response_schema)

        def __call__(self, *args, **kwargs):
            # this is needed to make this decorator work in combination with `@requests`
            return self.fn(*args, **kwargs)

    if func:
        return FunctionMapper(func)
    else:
        return FunctionMapper


def dynamic_batching(
    func: Callable[
        [
            'DocumentArray',
            Dict,
            'DocumentArray',
            List['DocumentArray'],
            List['DocumentArray'],
        ],
        Optional[Union['DocumentArray', Dict]],
    ] = None,
    *,
    preferred_batch_size: Optional[int] = None,
    timeout: Optional[float] = 10_000,
    flush_all: bool = False,
    custom_metric: Optional[Callable[['DocumentArray'], Union[float, int]]] = None,
    use_custom_metric: bool = False,
    use_dynamic_batching: bool = True,
):
    """
    `@dynamic_batching` defines the dynamic batching behavior of an Executor.
    Dynamic batching works by collecting Documents from multiple requests in a queue, and passing them to the Executor
    in batches of specified size.
    This can improve throughput and resource utilization at the cost of increased latency.
    TODO(johannes) add docstring example

    :param func: the method to decorate
    :param preferred_batch_size: target number of Documents in a batch. The batcher will collect requests until `preferred_batch_size` is reached,
        or until `timeout` is reached. Therefore, the actual batch size can be smaller or equal to `preferred_batch_size`, except if `flush_all` is set to True
    :param timeout: maximum time in milliseconds to wait for a request to be assigned to a batch.
        If the oldest request in the queue reaches a waiting time of `timeout`, the batch will be passed to the Executor,
        even if it contains fewer than `preferred_batch_size` Documents.
        Default is 10_000ms (10 seconds).
    :param flush_all: Determines if once the batches is triggered by timeout or preferred_batch_size, the function will receive everything that the batcher has accumulated or not.
        If this is true, `preferred_batch_size` is used as a trigger mechanism.
    :param custom_metric: Potential lambda function to measure the "weight" of each request.
    :param use_custom_metric: Determines if we need to use the `custom_metric` to determine preferred_batch_size.
    :param use_dynamic_batching: Determines if we should apply dynamic batching for this method.
    :return: decorated function
    """

    class DynamicBatchingDecorator:
        def __init__(self, fn):
            self._requests_decorator = None
            fn = self._unwrap_requests_decorator(fn)
            if iscoroutinefunction(fn):

                @functools.wraps(fn)
                async def arg_wrapper(
                    executor_instance, *args, **kwargs
                ):  # we need to get the summary from the executor, so we need to access the self
                    return await fn(executor_instance, *args, **kwargs)

                self.fn = arg_wrapper
            else:

                @functools.wraps(fn)
                def arg_wrapper(
                    executor_instance, *args, **kwargs
                ):  # we need to get the summary from the executor, so we need to access the self
                    return fn(executor_instance, *args, **kwargs)

                self.fn = arg_wrapper

        def _unwrap_requests_decorator(self, fn):
            if type(fn).__name__ == 'FunctionMapper':
                self._requests_decorator = fn
                return fn.fn
            else:
                return fn

        def _inject_owner_attrs(self, owner, name):
            if not hasattr(owner, 'dynamic_batching'):
                owner.dynamic_batching = {}

            fn_name = self.fn.__name__
            if not owner.dynamic_batching.get(fn_name):
                owner.dynamic_batching[fn_name] = {}

            owner.dynamic_batching[fn_name][
                'preferred_batch_size'
            ] = preferred_batch_size
            owner.dynamic_batching[fn_name]['timeout'] = timeout
            owner.dynamic_batching[fn_name]['flush_all'] = flush_all
            owner.dynamic_batching[fn_name]['use_custom_metric'] = use_custom_metric
            owner.dynamic_batching[fn_name]['custom_metric'] = custom_metric
            owner.dynamic_batching[fn_name]['use_dynamic_batching'] = use_dynamic_batching
            setattr(owner, name, self.fn)

        def __set_name__(self, owner, name):
            _init_requests_by_class(owner)
            if self._requests_decorator:
                self._requests_decorator._inject_owner_attrs(owner, name, None, None)
            self.fn.class_name = owner.__name__
            self._inject_owner_attrs(owner, name)

        def __call__(self, *args, **kwargs):
            # this is needed to make this decorator work in combination with `@requests`
            return self.fn(*args, **kwargs)

    if func:
        return DynamicBatchingDecorator(func)
    else:
        return DynamicBatchingDecorator


def monitor(
    *,
    name: Optional[str] = None,
    documentation: Optional[str] = None,
):
    """
    Decorator and context manager that allows monitoring of an Executor.

    You can access these metrics by enabling
    monitoring on your Executor. It will track the time spent calling the function and the number of times it has been
    called. Under the hood it will create a prometheus Summary : https://prometheus.io/docs/practices/histograms/.

    EXAMPLE USAGE

        As decorator

        .. code-block:: python

            from jina import Executor, monitor


            class MyExecutor(Executor):
                @requests  # `@requests` are monitored automatically
                def foo(self, docs, *args, **kwargs):
                    ...
                    self.my_method()
                    ...

                # custom metric for `my_method`
                @monitor(name='metric_name', documentation='useful information goes here')
                def my_method(self):
                    ...

        As context manager

        .. code-block:: python

            from jina import Executor, requests


            class MyExecutor(Executor):
                @requests  # `@requests` are monitored automatically
                def foo(self, docs, *args, **kwargs):
                    ...
                    # custom metric for code block
                    with self.monitor('metric_name', 'useful information goes here'):
                        docs = process(docs)

        To enable the defined :meth:`monitor` blocks, enable monitoring on the Flow level

        .. code-block:: python

            from jina import Flow

            f = Flow(monitoring=True, port_monitoring=9090).add(
                uses=MyExecutor, port_monitoring=9091
            )
            with f:
                ...

    :warning: Don't use this decorator in combination with the @request decorator. @request's are already monitored.

    :param name: the name of the metrics, by default it is based on the name of the method it decorates
    :param documentation:  the description of the metrics, by default it is based on the name of the method it decorates

    :return: decorator which takes as an input a single callable
    """

    def _decorator(func: Callable):
        name_ = name if name else f'{func.__name__}_seconds'
        documentation_ = (
            documentation
            if documentation
            else f'Time spent calling method {func.__name__}'
        )

        @functools.wraps(func)
        def _f(self, *args, **kwargs):
            with self.monitor(name_, documentation_):
                return func(self, *args, **kwargs)

        return _f

    return _decorator
