from __future__ import annotations

import asyncio
import contextlib
import copy
import functools
import inspect
import multiprocessing
import os
import threading
import warnings
from collections.abc import AsyncGenerator, AsyncIterator, Generator, Iterator
from types import SimpleNamespace
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    NamedTuple,
    Optional,
    Type,
    TypeVar,
    Union,
    _GenericAlias,
    overload,
)

from jina._docarray import DocumentArray, docarray_v2
from jina.constants import __args_executor_init__, __cache_path__, __default_endpoint__
from jina.enums import BetterEnum, ProviderType
from jina.helper import (
    ArgNamespace,
    T,
    get_or_reuse_loop,
    iscoroutinefunction,
    typename,
)
from jina.importer import ImportExtensions
from jina.jaml import JAML, JAMLCompatible, env_var_regex, internal_var_regex
from jina.logging.logger import JinaLogger
from jina.serve.executors.decorators import (
    _init_requests_by_class,
    avoid_concurrent_lock_cls,
)
from jina.serve.executors.metas import get_executor_taboo
from jina.serve.helper import (
    _get_workspace_from_name_and_shards,
    store_init_kwargs,
    wrap_func,
)
from jina.serve.instrumentation import MetricsTimer

if docarray_v2:
    from docarray.documents.legacy import LegacyDocument

if TYPE_CHECKING:  # pragma: no cover
    from opentelemetry.context.context import Context

__dry_run_endpoint__ = '_jina_dry_run_'

__all__ = ['BaseExecutor', __dry_run_endpoint__]


def is_pydantic_model(annotation: Type) -> bool:
    """Method to detect if parameter annotation corresponds to a Pydantic model

    :param annotation: The annotation from which to extract PydantiModel.
    :return: boolean indicating if a Pydantic model is inside the annotation
    """
    try:
        from typing import get_args, get_origin
    except ImportError:
        from typing_extensions import get_args, get_origin

    from pydantic import BaseModel

    origin = get_origin(annotation) or annotation
    args = get_args(annotation)

    # If the origin itself is a Pydantic model, return True
    if isinstance(origin, type) and issubclass(origin, BaseModel):
        return True

    # Check the arguments (for the actual types inside Union, Optional, etc.)
    if args:
        return any(is_pydantic_model(arg) for arg in args)

    return False


def get_inner_pydantic_model(annotation: Type) -> bool:
    """Method to get the Pydantic model corresponding, in case there is optional or something

    :param annotation: The annotation from which to extract PydantiModel.
    :return: The inner Pydantic model expected
    """
    try:
        from typing import Optional, Type, Union, get_args, get_origin

        from pydantic import BaseModel

        origin = get_origin(annotation) or annotation
        args = get_args(annotation)

        # If the origin itself is a Pydantic model, return True
        if isinstance(origin, type) and issubclass(origin, BaseModel):
            return origin

        # Check the arguments (for the actual types inside Union, Optional, etc.)
        if args:
            for arg in args:
                if is_pydantic_model(arg):
                    return arg
    except:
        pass
    return None


class ExecutorType(type(JAMLCompatible), type):
    """The class of Executor type, which is the metaclass of :class:`BaseExecutor`."""

    def __new__(cls, *args, **kwargs):
        """
        # noqa: DAR101
        # noqa: DAR102

        :return: Executor class
        """
        _cls = super().__new__(cls, *args, **kwargs)
        # this needs to be here, in the case where Executors inherited do not define new `requests`
        _init_requests_by_class(_cls)
        return cls.register_class(_cls)

    @staticmethod
    def register_class(cls):
        """
        Register a class and wrap update, train, aggregate functions.

        :param cls: The class.
        :return: The class, after being registered.
        """
        reg_cls_set = getattr(cls, '_registered_class', set())

        cls_id = f'{cls.__module__}.{cls.__name__}'
        if cls_id not in reg_cls_set:
            arg_spec = inspect.getfullargspec(cls.__init__)

            if not arg_spec.varkw and not __args_executor_init__.issubset(
                arg_spec.args
            ):
                raise TypeError(
                    f'{cls.__init__} does not follow the full signature of `Executor.__init__`, '
                    f'please add `**kwargs` to your __init__ function'
                )
            taboo = get_executor_taboo()

            wrap_func(cls, ['__init__'], store_init_kwargs, taboo=taboo)
            wrap_func(cls, ['__init__'], avoid_concurrent_lock_cls(cls))

            reg_cls_set.add(cls_id)
            setattr(cls, '_registered_class', reg_cls_set)
        return cls


T = TypeVar('T', bound='_FunctionWithSchema')


class _FunctionWithSchema(NamedTuple):
    fn: Callable
    is_generator: bool
    is_batch_docs: bool
    is_singleton_doc: False
    parameters_is_pydantic_model: bool
    parameters_model: Type
    request_schema: Type[DocumentArray] = DocumentArray
    response_schema: Type[DocumentArray] = DocumentArray

    def validate(self):
        assert not (
            self.is_singleton_doc and self.is_batch_docs
        ), f'Cannot specify both the `doc` and the `docs` paramater for {self.fn.__name__}'
        assert not (
            self.is_generator and self.is_batch_docs
        ), f'Cannot specify the `docs` parameter if the endpoint {self.fn.__name__} is a generator'
        if docarray_v2:
            from docarray import BaseDoc, DocList

            if not self.is_generator:
                if self.is_batch_docs and (
                    not issubclass(self.request_schema, DocList)
                    or not issubclass(self.response_schema, DocList)
                ):
                    faulty_schema = (
                        'request_schema'
                        if not issubclass(self.request_schema, DocList)
                        else 'response_schema'
                    )
                    raise Exception(
                        f'The {faulty_schema} schema for {self.fn.__name__}: {self.request_schema} is not a DocList. Please make sure that your endpoint used DocList for request and response schema'
                    )
                if self.is_singleton_doc and (
                    not issubclass(self.request_schema, BaseDoc)
                    or not issubclass(self.response_schema, BaseDoc)
                ):
                    faulty_schema = (
                        'request_schema'
                        if not issubclass(self.request_schema, BaseDoc)
                        else 'response_schema'
                    )
                    raise Exception(
                        f'The {faulty_schema} schema for {self.fn.__name__}: {self.request_schema} is not a BaseDoc. Please make sure that your endpoint used BaseDoc for request and response schema'
                    )
            else:
                if not issubclass(self.request_schema, BaseDoc) or not (
                    issubclass(self.response_schema, BaseDoc)
                    or issubclass(self.response_schema, BaseDoc)
                ):  # response_schema may be a DocList because by default we use LegacyDocument, and for generators we ignore response
                    faulty_schema = (
                        'request_schema'
                        if not issubclass(self.request_schema, BaseDoc)
                        else 'response_schema'
                    )
                    raise Exception(
                        f'The {faulty_schema} schema for {self.fn.__name__}: {self.request_schema} is not a BaseDoc. Please make sure that your streaming endpoints used BaseDoc for request and response schema'
                    )

    @staticmethod
    def get_function_with_schema(fn: Callable) -> T:
        # if it's not a generator function, infer the type annotation from the docs parameter
        # otherwise, infer from the doc parameter (since generator endpoints expect only 1 document as input)
        is_generator = getattr(fn, '__is_generator__', False)
        is_singleton_doc = 'doc' in fn.__annotations__
        is_batch_docs = (
            not is_singleton_doc
        )  # some tests just use **kwargs and should work as before
        assert not (
            is_singleton_doc and is_batch_docs
        ), f'Cannot specify both the `doc` and the `docs` paramater for {fn.__name__}'
        assert not (
            is_generator and is_batch_docs
        ), f'Cannot specify the `docs` parameter if the endpoint {fn.__name__} is a generator'
        docs_annotation = fn.__annotations__.get(
            'docs', fn.__annotations__.get('doc', None)
        )
        parameters_model = (
            fn.__annotations__.get('parameters', None) if docarray_v2 else None
        )
        parameters_is_pydantic_model = False
        if parameters_model is not None and docarray_v2:
            from pydantic import BaseModel

            parameters_is_pydantic_model = is_pydantic_model(parameters_model)
            parameters_model = get_inner_pydantic_model(parameters_model)

        if docarray_v2:
            from docarray import BaseDoc, DocList

            default_annotations = (
                DocList[LegacyDocument] if is_batch_docs else LegacyDocument
            )
        else:
            from jina import Document, DocumentArray

            default_annotations = DocumentArray if is_batch_docs else Document

        if docs_annotation is None:
            pass
        elif type(docs_annotation) is str:
            warnings.warn(
                f'`docs` annotation must be a type hint, got {docs_annotation}'
                ' instead, you should maybe remove the string annotation. Default value'
                'DocumentArray will be used instead.'
            )
            docs_annotation = None
        elif not isinstance(docs_annotation, type):
            warnings.warn(
                f'`docs` annotation must be a class if you want to use it'
                f' as schema input, got {docs_annotation}. try to remove the Optional'
                f'.fallback to default behavior'
                ''
            )
            docs_annotation = None

        return_annotation = fn.__annotations__.get('return', None)

        if return_annotation is None:
            pass
        elif type(return_annotation) is str:
            warnings.warn(
                f'`return` annotation must be a class if you want to use it'
                f' as schema input, got {docs_annotation}. try to remove the Optional'
                f'.fallback to default behavior'
                ''
            )
            return_annotation = None
        elif isinstance(return_annotation, _GenericAlias):
            from typing import get_args, get_origin

            if get_origin(return_annotation) == Generator:
                return_annotation = get_args(return_annotation)[0]
            elif get_origin(return_annotation) == AsyncGenerator:
                return_annotation = get_args(return_annotation)[0]
            elif get_origin(return_annotation) == Iterator:
                return_annotation = get_args(return_annotation)[0]
            elif get_origin(return_annotation) == AsyncIterator:
                return_annotation = get_args(return_annotation)[0]

        elif not isinstance(return_annotation, type):
            warnings.warn(
                f'`return` annotation must be a class if you want to use it'
                f'as schema input, got {docs_annotation}, fallback to default behavior'
                ''
            )
            return_annotation = None

        request_schema = docs_annotation or default_annotations
        response_schema = return_annotation or default_annotations
        fn_with_schema = _FunctionWithSchema(
            fn=fn,
            is_generator=is_generator,
            is_singleton_doc=is_singleton_doc,
            is_batch_docs=is_batch_docs,
            parameters_model=parameters_model,
            parameters_is_pydantic_model=parameters_is_pydantic_model,
            request_schema=request_schema,
            response_schema=response_schema,
        )
        fn_with_schema.validate()
        return fn_with_schema


class BaseExecutor(JAMLCompatible, metaclass=ExecutorType):
    """
    The base class of all Executors, can be used to build encoder, indexer, etc.

    :class:`jina.Executor` as an alias for this class.

    EXAMPLE USAGE

    .. code-block:: python

        from jina import Executor, requests, Flow


        class MyExecutor(Executor):
            @requests
            def foo(self, docs, **kwargs):
                print(docs)  # process docs here


        f = Flow().add(uses=Executor)  # you can add your Executor to a Flow

    Any executor inherited from :class:`BaseExecutor` always has the **meta** defined in :mod:`jina.executors.metas.defaults`.

    All arguments in the :func:`__init__` can be specified with a ``with`` map in the YAML config. Example:

    .. highlight:: python
    .. code-block:: python

        class MyAwesomeExecutor(Executor):
            def __init__(awesomeness=5):
                pass

    is equal to

    .. highlight:: yaml
    .. code-block:: yaml

        jtype: MyAwesomeExecutor
        with:
            awesomeness: 5

    """

    def __init__(
        self,
        metas: Optional[Dict] = None,
        requests: Optional[Dict] = None,
        runtime_args: Optional[Dict] = None,
        workspace: Optional[str] = None,
        dynamic_batching: Optional[Dict] = None,
        **kwargs,
    ):
        """`metas` and `requests` are always auto-filled with values from YAML config.

        :param metas: a dict of metas fields
        :param requests: a dict of endpoint-function mapping
        :param runtime_args: a dict of arguments injected from :class:`Runtime` during runtime
        :param kwargs: additional extra keyword arguments to avoid failing when extra params ara passed that are not expected
        :param workspace: the workspace of the executor. Only used if a workspace is not already provided in `metas` or `runtime_args`
        :param dynamic_batching: a dict of endpoint-dynamic_batching config mapping
        """
        self._add_metas(metas)
        self._add_requests(requests)
        self._add_dynamic_batching(dynamic_batching)
        self._add_runtime_args(runtime_args)
        self.logger = JinaLogger(self.__class__.__name__, **vars(self.runtime_args))
        self._validate_sagemaker()
        self._init_instrumentation(runtime_args)
        self._init_monitoring()
        self._init_workspace = workspace
        if __dry_run_endpoint__ not in self.requests:
            self.requests[__dry_run_endpoint__] = (
                _FunctionWithSchema.get_function_with_schema(
                    self.__class__._dry_run_func
                )
            )
        else:
            self.logger.warning(
                f' Endpoint {__dry_run_endpoint__} is defined by the Executor. Be aware that this endpoint is usually reserved to enable health checks from the Client through the gateway.'
                f' So it is recommended not to expose this endpoint. '
            )
        if type(self) == BaseExecutor:
            self.requests[__default_endpoint__] = (
                _FunctionWithSchema.get_function_with_schema(
                    self.__class__._dry_run_func
                )
            )

        self._lock = contextlib.AsyncExitStack()
        try:
            if not getattr(self.runtime_args, 'allow_concurrent', False):
                self._lock = (
                    asyncio.Lock()
                )  # Lock to run in Executor non async methods in a way that does not block the event loop to do health checks without the fear of having race conditions or multithreading issues.
        except RuntimeError:
            pass

        self._write_lock = (
            threading.Lock()
        )  # watch because this makes it no serializable

    def _get_endpoint_models_dict(self):
        from jina._docarray import docarray_v2

        if not docarray_v2:
            from docarray.document.pydantic_model import PydanticDocument

        endpoint_models = {}
        for endpoint, function_with_schema in self.requests.items():
            _is_generator = function_with_schema.is_generator
            _is_singleton_doc = function_with_schema.is_singleton_doc
            _is_batch_docs = function_with_schema.is_batch_docs
            _parameters_model = function_with_schema.parameters_model
            if docarray_v2:
                # if the endpoint is not a generator endpoint, then the request schema is a DocumentArray and we need
                # to get the doc_type from the schema
                # otherwise, since generator endpoints only accept a Document as input, the request_schema is the schema
                # of the Document
                if not _is_generator:
                    request_schema = (
                        function_with_schema.request_schema.doc_type
                        if _is_batch_docs
                        else function_with_schema.request_schema
                    )
                    response_schema = (
                        function_with_schema.response_schema.doc_type
                        if _is_batch_docs
                        else function_with_schema.response_schema
                    )
                else:
                    request_schema = function_with_schema.request_schema
                    response_schema = function_with_schema.response_schema
            else:
                request_schema = PydanticDocument
                response_schema = PydanticDocument
            endpoint_models[endpoint] = {
                'input': {
                    'name': request_schema.__name__,
                    'model': request_schema,
                },
                'output': {
                    'name': response_schema.__name__,
                    'model': response_schema,
                },
                'is_generator': _is_generator,
                'is_singleton_doc': _is_singleton_doc,
                'parameters': {
                    'name': (
                        _parameters_model.__name__
                        if _parameters_model is not None
                        else None
                    ),
                    'model': _parameters_model,
                },
            }
        return endpoint_models

    def _dry_run_func(self, *args, **kwargs):
        pass

    def _init_monitoring(self):
        if (
            hasattr(self.runtime_args, 'metrics_registry')
            and self.runtime_args.metrics_registry
        ):
            with ImportExtensions(
                required=True,
                help_text='You need to install the `prometheus_client` to use the montitoring functionality of jina',
            ):
                from prometheus_client import Summary

            self._summary_method = Summary(
                'process_request_seconds',
                'Time spent when calling the executor request method',
                registry=self.runtime_args.metrics_registry,
                namespace='jina',
                labelnames=('executor', 'executor_endpoint', 'runtime_name'),
            )
            self._metrics_buffer = {'process_request_seconds': self._summary_method}

        else:
            self._summary_method = None
            self._metrics_buffer = None

        if self.meter:
            self._process_request_histogram = self.meter.create_histogram(
                name='jina_process_request_seconds',
                description='Time spent when calling the executor request method',
            )
            self._histogram_buffer = {
                'jina_process_request_seconds': self._process_request_histogram
            }
        else:
            self._process_request_histogram = None
            self._histogram_buffer = None

    def _init_instrumentation(self, _runtime_args: Optional[Dict] = None):
        if not _runtime_args:
            _runtime_args = {}

        instrumenting_module_name = _runtime_args.get('name', self.__class__.__name__)

        args_tracer_provider = _runtime_args.get('tracer_provider', None)
        if args_tracer_provider:
            self.tracer_provider = args_tracer_provider
            self.tracer = self.tracer_provider.get_tracer(instrumenting_module_name)
        else:
            self.tracer_provider = None
            self.tracer = None

        args_meter_provider = _runtime_args.get('meter_provider', None)
        if args_meter_provider:
            self.meter_provider = args_meter_provider
            self.meter = self.meter_provider.get_meter(instrumenting_module_name)
        else:
            self.meter_provider = None
            self.meter = None

    @property
    def requests(self):
        """
        Get the request dictionary corresponding to this specific class

        :return: Returns the requests corresponding to the specific Executor instance class
        """
        if hasattr(self, '_requests'):
            return self._requests
        else:
            if not hasattr(self, 'requests_by_class'):
                self.requests_by_class = {}
            if self.__class__.__name__ not in self.requests_by_class:
                self.requests_by_class[self.__class__.__name__] = {}
            # we need to copy so that different instances with different (requests) in input do not disturb one another
            self._requests = copy.copy(self.requests_by_class[self.__class__.__name__])
            return self._requests

    @property
    def write_endpoints(self):
        """
        Get the list of endpoints bound to write methods

        :return: Returns the list of endpoints bound to write methods
        """
        if hasattr(self, '_write_methods'):
            endpoints = []
            for endpoint, fn in self.requests.items():
                if fn.fn.__name__ in self._write_methods:
                    endpoints.append(endpoint)
            return endpoints
        else:
            return []

    def _add_requests(self, _requests: Optional[Dict]):
        if _requests:
            func_names = {f.fn.__name__: e for e, f in self.requests.items()}
            for endpoint, func in _requests.items():
                # the following line must be `getattr(self.__class__, func)` NOT `getattr(self, func)`
                # this to ensure we always have `_func` as unbound method
                if func in func_names:
                    if func_names[func] in self.requests:
                        del self.requests[func_names[func]]

                _func = getattr(self.__class__, func)
                if callable(_func):
                    # the target function is not decorated with `@requests` yet
                    self.requests[endpoint] = (
                        _FunctionWithSchema.get_function_with_schema(_func)
                    )
                elif typename(_func) == 'jina.executors.decorators.FunctionMapper':
                    # the target function is already decorated with `@requests`, need unwrap with `.fn`
                    self.requests[endpoint] = (
                        _FunctionWithSchema.get_function_with_schema(_func.fn)
                    )
                else:
                    raise TypeError(
                        f'expect {typename(self)}.{func} to be a function, but receiving {typename(_func)}'
                    )

    def _validate_sagemaker(self):
        # sagemaker expects the POST /invocations endpoint to be defined.
        # if it is not defined, we check if there is only one endpoint defined,
        # and if so, we use it as the POST /invocations endpoint, or raise an error
        if (
            not hasattr(self, 'runtime_args')
            or not hasattr(self.runtime_args, 'provider')
            or self.runtime_args.provider != ProviderType.SAGEMAKER.value
        ):
            return

        remove_keys = set()
        for k in self.requests.keys():
            if k != '/invocations':
                remove_keys.add(k)

        if '/invocations' in self.requests:
            for k in remove_keys:
                self.requests.pop(k)
            return

        if (
            hasattr(self.runtime_args, 'provider_endpoint')
            and self.runtime_args.provider_endpoint
        ):
            endpoint_to_use = ('/' + self.runtime_args.provider_endpoint).lower()
        elif len(self.requests) == 1:
            endpoint_to_use = list(self.requests.keys())[0]
        else:
            raise ValueError('Cannot identify the endpoint to use for "/invocations"')

        if endpoint_to_use in list(self.requests.keys()):
            self.logger.warning(f'Using "{endpoint_to_use}" as "/invocations" route')
            self.requests['/invocations'] = self.requests[endpoint_to_use]
            if (
                getattr(self, 'dynamic_batching', {}).get(endpoint_to_use, None)
                is not None
            ):
                self.dynamic_batching['/invocations'] = self.dynamic_batching[
                    endpoint_to_use
                ]
                self.dynamic_batching.pop(endpoint_to_use)
            for k in remove_keys:
                self.requests.pop(k)
            return

    def _add_dynamic_batching(self, _dynamic_batching: Optional[Dict]):
        from collections.abc import Mapping

        def deep_update(source, overrides):
            for key, value in overrides.items():
                if isinstance(value, Mapping) and value:
                    returned = deep_update(source.get(key, {}), value)
                    source[key] = returned
                else:
                    source[key] = overrides[key]
            return source

        if _dynamic_batching:
            self.dynamic_batching = getattr(self, 'dynamic_batching', {})
            self.dynamic_batching = deep_update(
                self.dynamic_batching, _dynamic_batching
            )

    def _add_metas(self, _metas: Optional[Dict]):
        from jina.serve.executors.metas import get_default_metas

        tmp = get_default_metas()

        if _metas:
            tmp.update(_metas)

        unresolved_attr = False
        target = SimpleNamespace()
        # set self values filtered by those non-exist, and non-expandable
        for k, v in tmp.items():
            if k == 'workspace' and not (v is None or v == ''):
                warnings.warn(
                    'Setting `workspace` via `metas.workspace` is deprecated. '
                    'Instead, use `f.add(..., workspace=...)` when defining a a Flow in Python; '
                    'the `workspace` parameter when defining a Flow using YAML; '
                    'or `--workspace` when starting an Executor using the CLI.',
                    category=DeprecationWarning,
                )
            if not hasattr(target, k):
                if isinstance(v, str):
                    if not env_var_regex.findall(v):
                        setattr(target, k, v)
                    else:
                        unresolved_attr = True
                else:
                    setattr(target, k, v)
            elif type(getattr(target, k)) == type(v):
                setattr(target, k, v)

        if unresolved_attr:
            _tmp = vars(self)
            _tmp['metas'] = tmp
            new_metas = JAML.expand_dict(_tmp)['metas']

            for k, v in new_metas.items():
                if not hasattr(target, k):
                    if isinstance(v, str):
                        if not (
                            env_var_regex.findall(v) or internal_var_regex.findall(v)
                        ):
                            setattr(target, k, v)
                        else:
                            raise ValueError(
                                f'{k}={v} is not substitutable or badly referred'
                            )
                    else:
                        setattr(target, k, v)
        # `name` is important as it serves as an identifier of the executor
        # if not given, then set a name by the rule
        if not getattr(target, 'name', None):
            setattr(target, 'name', self.__class__.__name__)

        self.metas = target

    def close(self) -> None:
        """
        Always invoked as executor is destroyed.

        You can write destructor & saving logic here.
        """
        pass

    def __call__(self, req_endpoint: str, **kwargs):
        """
        # noqa: DAR101
        # noqa: DAR102
        # noqa: DAR201
        """
        if req_endpoint in self.requests:
            return self.requests[req_endpoint](
                self, **kwargs
            )  # unbound method, self is required
        elif __default_endpoint__ in self.requests:
            return self.requests[__default_endpoint__](
                self, **kwargs
            )  # unbound method, self is required

    async def __acall__(self, req_endpoint: str, **kwargs):
        """
        # noqa: DAR101
        # noqa: DAR102
        # noqa: DAR201
        """

        if req_endpoint in self.requests:
            return await self.__acall_endpoint__(req_endpoint, **kwargs)
        elif __default_endpoint__ in self.requests:
            return await self.__acall_endpoint__(__default_endpoint__, **kwargs)

    async def __acall_endpoint__(
        self, req_endpoint, tracing_context: Optional['Context'], **kwargs
    ):
        # Decorator to make sure that `parameters` are passed as PydanticModels if needed
        def parameters_as_pydantic_models_decorator(func, parameters_pydantic_model):
            @functools.wraps(func)  # Step 2: Use functools.wraps to preserve metadata
            def wrapper(*args, **kwargs):
                parameters = kwargs.get('parameters', None)
                if parameters is not None:
                    parameters = parameters_pydantic_model(**parameters)
                    kwargs['parameters'] = parameters
                result = func(*args, **kwargs)
                return result

            return wrapper

        # Decorator to make sure that `docs` are fed one by one to method using singleton document serving
        def loop_docs_decorator(func):
            @functools.wraps(func)  # Step 2: Use functools.wraps to preserve metadata
            def wrapper(*args, **kwargs):
                docs = kwargs.pop('docs')
                if docarray_v2:
                    from docarray import DocList

                    ret = DocList[response_schema]()
                else:
                    ret = DocumentArray()
                for doc in docs:
                    f_ret = func(*args, doc=doc, **kwargs)
                    if f_ret is None:
                        ret.append(doc)  # this means change in place
                    else:
                        ret.append(f_ret)
                return ret

            return wrapper

        def async_loop_docs_decorator(func):
            @functools.wraps(func)  # Step 2: Use functools.wraps to preserve metadata
            async def wrapper(*args, **kwargs):
                docs = kwargs.pop('docs')
                if docarray_v2:
                    from docarray import DocList

                    ret = DocList[response_schema]()
                else:
                    ret = DocumentArray()
                for doc in docs:
                    f_ret = await original_func(*args, doc=doc, **kwargs)
                    if f_ret is None:
                        ret.append(doc)  # this means change in place
                    else:
                        ret.append(f_ret)
                return ret

            return wrapper

        fn_info = self.requests[req_endpoint]
        original_func = fn_info.fn
        is_generator = fn_info.is_generator
        is_batch_docs = fn_info.is_batch_docs
        response_schema = fn_info.response_schema
        parameters_model = fn_info.parameters_model
        is_parameters_pydantic_model = fn_info.parameters_is_pydantic_model

        func = original_func
        if is_generator or is_batch_docs:
            pass
        elif kwargs.get('docs', None) is not None:
            # This means I need to pass every doc (most likely 1, but potentially more)
            if iscoroutinefunction(original_func):
                func = async_loop_docs_decorator(original_func)
            else:
                func = loop_docs_decorator(original_func)

        if is_parameters_pydantic_model:
            func = parameters_as_pydantic_models_decorator(func, parameters_model)

        async def exec_func(
            summary, histogram, histogram_metric_labels, tracing_context
        ):
            with MetricsTimer(summary, histogram, histogram_metric_labels):
                if iscoroutinefunction(func):
                    return await func(self, tracing_context=tracing_context, **kwargs)
                else:
                    async with self._lock:
                        return await get_or_reuse_loop().run_in_executor(
                            None,
                            functools.partial(
                                func, self, tracing_context=tracing_context, **kwargs
                            ),
                        )

        runtime_name = (
            self.runtime_args.name if hasattr(self.runtime_args, 'name') else None
        )

        _summary = (
            self._summary_method.labels(
                self.__class__.__name__, req_endpoint, runtime_name
            )
            if self._summary_method
            else None
        )
        _histogram_metric_labels = {
            'executor': self.__class__.__name__,
            'executor_endpoint': req_endpoint,
            'runtime_name': runtime_name,
        }

        if self.tracer:
            with self.tracer.start_as_current_span(
                req_endpoint, context=tracing_context
            ):
                from opentelemetry.propagate import extract
                from opentelemetry.trace.propagation.tracecontext import (
                    TraceContextTextMapPropagator,
                )

                tracing_carrier_context = {}
                TraceContextTextMapPropagator().inject(tracing_carrier_context)
                return await exec_func(
                    _summary,
                    self._process_request_histogram,
                    _histogram_metric_labels,
                    extract(tracing_carrier_context),
                )
        else:
            return await exec_func(
                _summary,
                self._process_request_histogram,
                _histogram_metric_labels,
                None,
            )

    @property
    def workspace(self) -> Optional[str]:
        """
        Get the workspace directory of the Executor.

        :return: returns the workspace of the current shard of this Executor.
        """
        workspace = (
            getattr(self.runtime_args, 'workspace', None)
            or getattr(self.metas, 'workspace')
            or self._init_workspace
            or __cache_path__
        )
        if workspace:
            shard_id = getattr(
                self.runtime_args,
                'shard_id',
                None,
            )
            return _get_workspace_from_name_and_shards(
                workspace=workspace, shard_id=shard_id, name=self.metas.name
            )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @classmethod
    def from_hub(
        cls: Type[T],
        uri: str,
        context: Optional[Dict[str, Any]] = None,
        uses_with: Optional[Dict] = None,
        uses_metas: Optional[Dict] = None,
        uses_requests: Optional[Dict] = None,
        uses_dynamic_batching: Optional[Dict] = None,
        **kwargs,
    ) -> T:
        """Construct an Executor from Hub.

        :param uri: a hub Executor scheme starts with `jinahub://`
        :param context: context replacement variables in a dict, the value of the dict is the replacement.
        :param uses_with: dictionary of parameters to overwrite from the default config's with field
        :param uses_metas: dictionary of parameters to overwrite from the default config's metas field
        :param uses_requests: dictionary of parameters to overwrite from the default config's requests field
        :param uses_dynamic_batching: dictionary of parameters to overwrite from the default config's dynamic_batching field
        :param kwargs: other kwargs accepted by the CLI ``jina hub pull``
        :return: the Hub Executor object.

        .. highlight:: python
        .. code-block:: python

            from jina import Executor
            from docarray import Document, DocumentArray

            executor = Executor.from_hub(
                uri='jinahub://CLIPImageEncoder', install_requirements=True
            )

        """
        from hubble.executor.helper import is_valid_huburi

        _source = None
        if is_valid_huburi(uri):
            from hubble.executor.hubio import HubIO
            from hubble.executor.parsers import set_hub_pull_parser

            _args = ArgNamespace.kwargs2namespace(
                {'no_usage': True, **kwargs},
                set_hub_pull_parser(),
                positional_args=(uri,),
            )
            _source = HubIO(args=_args).pull()

        if not _source or _source.startswith('docker://'):
            raise ValueError(
                f'Can not construct a native Executor from {uri}. Looks like you want to use it as a '
                f'Docker container, you may want to use it in the Flow via `.add(uses={uri})` instead.'
            )
        return cls.load_config(
            _source,
            context=context,
            uses_with=uses_with,
            uses_metas=uses_metas,
            uses_requests=uses_requests,
            uses_dynamic_batching=uses_dynamic_batching,
        )

    # overload_inject_start_executor_serve
    @overload
    def serve(
        self,
        *,
        allow_concurrent: Optional[bool] = False,
        compression: Optional[str] = None,
        connection_list: Optional[str] = None,
        cors: Optional[bool] = False,
        description: Optional[str] = None,
        disable_auto_volume: Optional[bool] = False,
        docker_kwargs: Optional[dict] = None,
        entrypoint: Optional[str] = None,
        env: Optional[dict] = None,
        exit_on_exceptions: Optional[List] = [],
        external: Optional[bool] = False,
        floating: Optional[bool] = False,
        force_update: Optional[bool] = False,
        gpus: Optional[str] = None,
        grpc_channel_options: Optional[dict] = None,
        grpc_metadata: Optional[dict] = None,
        grpc_server_options: Optional[dict] = None,
        host: Optional[List] = ['0.0.0.0'],
        install_requirements: Optional[bool] = False,
        log_config: Optional[str] = None,
        metrics: Optional[bool] = False,
        metrics_exporter_host: Optional[str] = None,
        metrics_exporter_port: Optional[int] = None,
        monitoring: Optional[bool] = False,
        name: Optional[str] = 'executor',
        native: Optional[bool] = False,
        no_reduce: Optional[bool] = False,
        output_array_type: Optional[str] = None,
        polling: Optional[str] = 'ANY',
        port: Optional[int] = None,
        port_monitoring: Optional[int] = None,
        prefer_platform: Optional[str] = None,
        protocol: Optional[Union[str, List[str]]] = ['GRPC'],
        provider: Optional[str] = ['NONE'],
        provider_endpoint: Optional[str] = None,
        py_modules: Optional[List] = None,
        quiet: Optional[bool] = False,
        quiet_error: Optional[bool] = False,
        raft_configuration: Optional[dict] = None,
        reload: Optional[bool] = False,
        replicas: Optional[int] = 1,
        retries: Optional[int] = -1,
        runtime_cls: Optional[str] = 'WorkerRuntime',
        shards: Optional[int] = 1,
        ssl_certfile: Optional[str] = None,
        ssl_keyfile: Optional[str] = None,
        stateful: Optional[bool] = False,
        timeout_ctrl: Optional[int] = 60,
        timeout_ready: Optional[int] = 600000,
        timeout_send: Optional[int] = None,
        title: Optional[str] = None,
        tls: Optional[bool] = False,
        traces_exporter_host: Optional[str] = None,
        traces_exporter_port: Optional[int] = None,
        tracing: Optional[bool] = False,
        uses: Optional[Union[str, Type['BaseExecutor'], dict]] = 'BaseExecutor',
        uses_after: Optional[Union[str, Type['BaseExecutor'], dict]] = None,
        uses_after_address: Optional[str] = None,
        uses_before: Optional[Union[str, Type['BaseExecutor'], dict]] = None,
        uses_before_address: Optional[str] = None,
        uses_dynamic_batching: Optional[dict] = None,
        uses_metas: Optional[dict] = None,
        uses_requests: Optional[dict] = None,
        uses_with: Optional[dict] = None,
        uvicorn_kwargs: Optional[dict] = None,
        volumes: Optional[List] = None,
        when: Optional[dict] = None,
        workspace: Optional[str] = None,
        **kwargs,
    ):
        """Serve this Executor in a temporary Flow. Useful in testing an Executor in remote settings.

        :param allow_concurrent: Allow concurrent requests to be processed by the Executor. This is only recommended if the Executor is thread-safe.
        :param compression: The compression mechanism used when sending requests from the Head to the WorkerRuntimes. For more details, check https://grpc.github.io/grpc/python/grpc.html#compression.
        :param connection_list: dictionary JSON with a list of connections to configure
        :param cors: If set, a CORS middleware is added to FastAPI frontend to allow cross-origin access.
        :param description: The description of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param disable_auto_volume: Do not automatically mount a volume for dockerized Executors.
        :param docker_kwargs: Dictionary of kwargs arguments that will be passed to Docker SDK when starting the docker '
          container.

          More details can be found in the Docker SDK docs:  https://docker-py.readthedocs.io/en/stable/
        :param entrypoint: The entrypoint command overrides the ENTRYPOINT in Docker image. when not set then the Docker image ENTRYPOINT takes effective.
        :param env: The map of environment variables that are available inside runtime
        :param exit_on_exceptions: List of exceptions that will cause the Executor to shut down.
        :param external: The Deployment will be considered an external Deployment that has been started independently from the Flow.This Deployment will not be context managed by the Flow.
        :param floating: If set, the current Pod/Deployment can not be further chained, and the next `.add()` will chain after the last Pod/Deployment not this current one.
        :param force_update: If set, always pull the latest Hub Executor bundle even it exists on local
        :param gpus: This argument allows dockerized Jina Executors to discover local gpu devices.

              Note,
              - To access all gpus, use `--gpus all`.
              - To access multiple gpus, e.g. make use of 2 gpus, use `--gpus 2`.
              - To access specified gpus based on device id, use `--gpus device=[YOUR-GPU-DEVICE-ID]`
              - To access specified gpus based on multiple device id, use `--gpus device=[YOUR-GPU-DEVICE-ID1],device=[YOUR-GPU-DEVICE-ID2]`
              - To specify more parameters, use `--gpus device=[YOUR-GPU-DEVICE-ID],runtime=nvidia,capabilities=display
        :param grpc_channel_options: Dictionary of kwargs arguments that will be passed to the grpc channel as options when creating a channel, example : {'grpc.max_send_message_length': -1}. When max_attempts > 1, the 'grpc.service_config' option will not be applicable.
        :param grpc_metadata: The metadata to be passed to the gRPC request.
        :param grpc_server_options: Dictionary of kwargs arguments that will be passed to the grpc server as options when starting the server, example : {'grpc.max_send_message_length': -1}
        :param host: The host of the Gateway, which the client should connect to, by default it is 0.0.0.0. In the case of an external Executor (`--external` or `external=True`) this can be a list of hosts.  Then, every resulting address will be considered as one replica of the Executor.
        :param install_requirements: If set, try to install `requirements.txt` from the local Executor if exists in the Executor folder. If using Hub, install `requirements.txt` in the Hub Executor bundle to local.
        :param log_config: The config name or the absolute path to the YAML config file of the logger used in this object.
        :param metrics: If set, the sdk implementation of the OpenTelemetry metrics will be available for default monitoring and custom measurements. Otherwise a no-op implementation will be provided.
        :param metrics_exporter_host: If tracing is enabled, this hostname will be used to configure the metrics exporter agent.
        :param metrics_exporter_port: If tracing is enabled, this port will be used to configure the metrics exporter agent.
        :param monitoring: If set, spawn an http server with a prometheus endpoint to expose metrics
        :param name: The name of this object.

              This will be used in the following places:
              - how you refer to this object in Python/YAML/CLI
              - visualization
              - log message header
              - ...

              When not given, then the default naming strategy will apply.
        :param native: If set, only native Executors is allowed, and the Executor is always run inside WorkerRuntime.
        :param no_reduce: Disable the built-in reduction mechanism. Set this if the reduction is to be handled by the Executor itself by operating on a `docs_matrix` or `docs_map`
        :param output_array_type: The type of array `tensor` and `embedding` will be serialized to.

          Supports the same types as `docarray.to_protobuf(.., ndarray_type=...)`, which can be found
          `here <https://docarray.jina.ai/fundamentals/document/serialization/#from-to-protobuf>`.
          Defaults to retaining whatever type is returned by the Executor.
        :param polling: The polling strategy of the Deployment and its endpoints (when `shards>1`).
              Can be defined for all endpoints of a Deployment or by endpoint.
              Define per Deployment:
              - ANY: only one (whoever is idle) Pod polls the message
              - ALL: all Pods poll the message (like a broadcast)
              Define per Endpoint:
              JSON dict, {endpoint: PollingType}
              {'/custom': 'ALL', '/search': 'ANY', '*': 'ANY'}
        :param port: The port for input data to bind to, default is a random port between [49152, 65535]. In the case of an external Executor (`--external` or `external=True`) this can be a list of ports. Then, every resulting address will be considered as one replica of the Executor.
        :param port_monitoring: The port on which the prometheus server is exposed, default is a random port between [49152, 65535]
        :param prefer_platform: The preferred target Docker platform. (e.g. "linux/amd64", "linux/arm64")
        :param protocol: Communication protocol of the server exposed by the Executor. This can be a single value or a list of protocols, depending on your chosen Gateway. Choose the convenient protocols from: ['GRPC', 'HTTP', 'WEBSOCKET'].
        :param provider: If set, Executor is translated to a custom container compatible with the chosen provider. Choose the convenient providers from: ['NONE', 'SAGEMAKER', 'AZURE'].
        :param provider_endpoint: If set, Executor endpoint will be explicitly chosen and used in the custom container operated by the provider.
        :param py_modules: The customized python modules need to be imported before loading the executor

          Note that the recommended way is to only import a single module - a simple python file, if your
          executor can be defined in a single file, or an ``__init__.py`` file if you have multiple files,
          which should be structured as a python package. For more details, please see the
          `Executor cookbook <https://jina.ai/serve/concepts/executor/executor-files/>`__
        :param quiet: If set, then no log will be emitted from this object.
        :param quiet_error: If set, then exception stack information will not be added to the log
        :param raft_configuration: Dictionary of kwargs arguments that will be passed to the RAFT node as configuration options when starting the RAFT node.
        :param reload: If set, the Executor will restart while serving if YAML configuration source or Executor modules are changed. If YAML configuration is changed, the whole deployment is reloaded and new processes will be restarted. If only Python modules of the Executor have changed, they will be reloaded to the interpreter without restarting process.
        :param replicas: The number of replicas in the deployment
        :param retries: Number of retries per gRPC call. If <0 it defaults to max(3, num_replicas)
        :param runtime_cls: The runtime class to run inside the Pod
        :param shards: The number of shards in the deployment running at the same time. For more details check https://jina.ai/serve/concepts/flow/create-flow/#complex-flow-topologies
        :param ssl_certfile: the path to the certificate file
        :param ssl_keyfile: the path to the key file
        :param stateful: If set, start consensus module to make sure write operations are properly replicated between all the replicas
        :param timeout_ctrl: The timeout in milliseconds of the control request, -1 for waiting forever
        :param timeout_ready: The timeout in milliseconds of a Pod waits for the runtime to be ready, -1 for waiting forever
        :param timeout_send: The timeout in milliseconds used when sending data requests to Executors, -1 means no timeout, disabled by default
        :param title: The title of this HTTP server. It will be used in automatics docs such as Swagger UI.
        :param tls: If set, connect to deployment using tls encryption
        :param traces_exporter_host: If tracing is enabled, this hostname will be used to configure the trace exporter agent.
        :param traces_exporter_port: If tracing is enabled, this port will be used to configure the trace exporter agent.
        :param tracing: If set, the sdk implementation of the OpenTelemetry tracer will be available and will be enabled for automatic tracing of requests and customer span creation. Otherwise a no-op implementation will be provided.
        :param uses: The config of the executor, it could be one of the followings:
                  * the string literal of an Executor class name
                  * an Executor YAML file (.yml, .yaml, .jaml)
                  * a Jina Hub Executor (must start with `jinahub://` or `jinahub+docker://`)
                  * a docker image (must start with `docker://`)
                  * the string literal of a YAML config (must start with `!` or `jtype: `)
                  * the string literal of a JSON config

                  When use it under Python, one can use the following values additionally:
                  - a Python dict that represents the config
                  - a text file stream has `.read()` interface
        :param uses_after: The executor attached after the Pods described by --uses, typically used for receiving from all shards, accepted type follows `--uses`. This argument only applies for sharded Deployments (shards > 1).
        :param uses_after_address: The address of the uses-before runtime
        :param uses_before: The executor attached before the Pods described by --uses, typically before sending to all shards, accepted type follows `--uses`. This argument only applies for sharded Deployments (shards > 1).
        :param uses_before_address: The address of the uses-before runtime
        :param uses_dynamic_batching: Dictionary of keyword arguments that will override the `dynamic_batching` configuration in `uses`
        :param uses_metas: Dictionary of keyword arguments that will override the `metas` configuration in `uses`
        :param uses_requests: Dictionary of keyword arguments that will override the `requests` configuration in `uses`
        :param uses_with: Dictionary of keyword arguments that will override the `with` configuration in `uses`
        :param uvicorn_kwargs: Dictionary of kwargs arguments that will be passed to Uvicorn server when starting the server

          More details can be found in Uvicorn docs: https://www.uvicorn.org/settings/
        :param volumes: The path on the host to be mounted inside the container.

          Note,
          - If separated by `:`, then the first part will be considered as the local host path and the second part is the path in the container system.
          - If no split provided, then the basename of that directory will be mounted into container's root path, e.g. `--volumes="/user/test/my-workspace"` will be mounted into `/my-workspace` inside the container.
          - All volumes are mounted with read-write mode.
        :param when: The condition that the documents need to fulfill before reaching the Executor.The condition can be defined in the form of a `DocArray query condition <https://docarray.jina.ai/fundamentals/documentarray/find/#query-by-conditions>`
        :param workspace: The working directory for any IO operations in this object. If not set, then derive from its parent `workspace`.

        .. # noqa: DAR202
        .. # noqa: DAR101
        .. # noqa: DAR003
        """

    # overload_inject_end_executor_serve

    @classmethod
    def serve(
        cls,
        uses_with: Optional[Dict] = None,
        uses_metas: Optional[Dict] = None,
        uses_requests: Optional[Dict] = None,
        stop_event: Optional[Union['threading.Event', 'multiprocessing.Event']] = None,
        uses_dynamic_batching: Optional[Dict] = None,
        reload: bool = False,
        **kwargs,
    ):
        """Serve this Executor in a temporary Flow. Useful in testing an Executor in remote settings.

        :param uses_with: dictionary of parameters to overwrite from the default config's with field
        :param uses_metas: dictionary of parameters to overwrite from the default config's metas field
        :param uses_requests: dictionary of parameters to overwrite from the default config's requests field
        :param reload: If set, the Executor reloads the modules as they change
        :param stop_event: a threading event or a multiprocessing event that once set will resume the control Flow
            to main thread.
        :param uses_dynamic_batching: dictionary of parameters to overwrite from the default config's dynamic_batching field
        :param reload: a flag indicating if the Executor should watch the Python files of its implementation to reload the code live while serving.
        :param kwargs: other kwargs accepted by the Flow, full list can be found `here <https://jina.ai/serve/api/jina.orchestrate.flow.base/>`

        """
        warnings.warn(
            f'Executor.serve() is no more supported and will be deprecated soon. Use Deployment to serve an Executor instead: '
            f'https://jina.ai/serve/concepts/executor/serve/',
            DeprecationWarning,
        )
        from jina.orchestrate.deployments import Deployment

        dep = Deployment(
            uses=cls,
            uses_with=uses_with,
            uses_metas=uses_metas,
            uses_requests=uses_requests,
            uses_dynamic_batching=uses_dynamic_batching,
            reload=reload,
            **kwargs,
        )
        with dep:
            dep.block(stop_event)

    class StandaloneExecutorType(BetterEnum):
        """
        Type of standalone Executors
        """

        EXTERNAL = 0  # served by a gateway
        SHARED = 1  # not served by a gateway, served by head/worker

    @staticmethod
    def to_kubernetes_yaml(
        uses: str,
        output_base_path: str,
        k8s_namespace: Optional[str] = None,
        executor_type: Optional[
            StandaloneExecutorType
        ] = StandaloneExecutorType.EXTERNAL,
        uses_with: Optional[Dict] = None,
        uses_metas: Optional[Dict] = None,
        uses_requests: Optional[Dict] = None,
        uses_dynamic_batching: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Converts the Executor into a set of yaml deployments to deploy in Kubernetes.

        If you don't want to rebuild image on Jina Hub,
        you can set `JINA_HUB_NO_IMAGE_REBUILD` environment variable.

        :param uses: the Executor to use. Has to be containerized and accessible from K8s
        :param output_base_path: The base path where to dump all the yaml files
        :param k8s_namespace: The name of the k8s namespace to set for the configurations. If None, the name of the Flow will be used.
        :param executor_type: The type of Executor. Can be external or shared. External Executors include the Gateway. Shared Executors don't. Defaults to External
        :param uses_with: dictionary of parameters to overwrite from the default config's with field
        :param uses_metas: dictionary of parameters to overwrite from the default config's metas field
        :param uses_requests: dictionary of parameters to overwrite from the default config's requests field
        :param uses_dynamic_batching: dictionary of parameters to overwrite from the default config's dynamic_batching field
        :param kwargs: other kwargs accepted by the Flow, full list can be found `here <https://jina.ai/serve/api/jina.orchestrate.flow.base/>`
        """
        warnings.warn(
            f'Executor.to_kubernetes_yaml() is no more supported and will be deprecated soon. Use Deployment to export kubernetes YAML files: '
            f'https://jina.ai/serve/concepts/executor/serve/#serve-via-kubernetes',
            DeprecationWarning,
        )
        from jina.orchestrate.flow.base import Flow

        Flow(**kwargs).add(
            uses=uses,
            uses_with=uses_with,
            uses_metas=uses_metas,
            uses_requests=uses_requests,
            uses_dynamic_batching=uses_dynamic_batching,
        ).to_kubernetes_yaml(
            output_base_path=output_base_path,
            k8s_namespace=k8s_namespace,
            include_gateway=executor_type
            == BaseExecutor.StandaloneExecutorType.EXTERNAL,
        )

    to_k8s_yaml = to_kubernetes_yaml

    @staticmethod
    def to_docker_compose_yaml(
        uses: str,
        output_path: Optional[str] = None,
        network_name: Optional[str] = None,
        executor_type: Optional[
            StandaloneExecutorType
        ] = StandaloneExecutorType.EXTERNAL,
        uses_with: Optional[Dict] = None,
        uses_metas: Optional[Dict] = None,
        uses_requests: Optional[Dict] = None,
        uses_dynamic_batching: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Converts the Executor into a yaml file to run with `docker-compose up`
        :param uses: the Executor to use. Has to be containerized
        :param output_path: The output path for the yaml file
        :param network_name: The name of the network that will be used by the deployment name
        :param executor_type: The type of Executor. Can be external or shared. External Executors include the Gateway. Shared Executors don't. Defaults to External
        :param uses_with: dictionary of parameters to overwrite from the default config's with field
        :param uses_metas: dictionary of parameters to overwrite from the default config's metas field
        :param uses_requests: dictionary of parameters to overwrite from the default config's requests field
        :param uses_dynamic_batching: dictionary of parameters to overwrite from the default config's requests field
        :param kwargs: other kwargs accepted by the Flow, full list can be found `here <https://jina.ai/serve/api/jina.orchestrate.flow.base/>`
        """

        warnings.warn(
            f'Executor.to_docker_compose_yaml() is no more supported and will be deprecated soon. Use Deployment to export docker compose YAML files: '
            f'https://jina.ai/serve/concepts/executor/serve/#serve-via-docker-compose',
            DeprecationWarning,
        )

        from jina.orchestrate.flow.base import Flow

        f = Flow(**kwargs).add(
            uses=uses,
            uses_with=uses_with,
            uses_metas=uses_metas,
            uses_requests=uses_requests,
            uses_dynamic_batching=uses_dynamic_batching,
        )
        f.to_docker_compose_yaml(
            output_path=output_path,
            network_name=network_name,
            include_gateway=executor_type
            == BaseExecutor.StandaloneExecutorType.EXTERNAL,
        )

    def monitor(
        self, name: Optional[str] = None, documentation: Optional[str] = None
    ) -> Optional[MetricsTimer]:
        """
        Get a given prometheus metric, if it does not exist yet, it will create it and store it in a buffer.
        :param name: the name of the metrics
        :param documentation:  the description of the metrics

        :return: the given prometheus metrics or None if monitoring is not enable.
        """
        _summary = (
            self._metrics_buffer.get(name, None) if self._metrics_buffer else None
        )
        _histogram = (
            self._histogram_buffer.get(name, None) if self._histogram_buffer else None
        )

        if self._metrics_buffer and not _summary:
            from prometheus_client import Summary

            _summary = Summary(
                name,
                documentation,
                registry=self.runtime_args.metrics_registry,
                namespace='jina',
                labelnames=('runtime_name',),
            ).labels(self.runtime_args.name)
            self._metrics_buffer[name] = _summary

        if self._histogram_buffer and not _histogram:
            _histogram = self.meter.create_histogram(
                name=f'jina_{name}', description=documentation
            )
            self._histogram_buffer[name] = _histogram

        if _summary or _histogram:
            return MetricsTimer(
                _summary,
                _histogram,
                histogram_metric_labels={'runtime_name': self.runtime_args.name},
            )

        return contextlib.nullcontext()

    def snapshot(self, snapshot_file: str):
        """
        Interface to take a snapshot from the Executor. Implement it to enable periodic snapshots
        :param snapshot_file: The file path where to store the binary representation of the Executor snapshot
        """
        raise Exception('Raising an Exception. Snapshot is not enabled by default')

    def restore(self, snapshot_file: str):
        """
        Interface to restore the state of the Executor from a snapshot that has been taken by the snapshot method.
        :param snapshot_file: The file path from where to reconstruct the Executor
        """
        pass

    def _run_snapshot(self, snapshot_file: str, did_raise_exception):
        try:
            from pathlib import Path

            p = Path(snapshot_file)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.touch()
            with self._write_lock:
                self.snapshot(snapshot_file)
        except:
            did_raise_exception.set()
            raise

    def _run_restore(self, snapshot_file: str, did_raise_exception):
        try:
            with self._write_lock:
                self.restore(snapshot_file)
        except:
            did_raise_exception.set()
            raise
        finally:
            os.remove(snapshot_file)
