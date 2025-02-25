"""Module containing the Base Client for Jina."""

import abc
import argparse
import inspect
import os
from abc import ABC
from typing import TYPE_CHECKING, AsyncIterator, Callable, Iterator, Optional, Union, Tuple

from jina.excepts import BadClientInput
from jina.helper import T, parse_client, send_telemetry_event, typename
from jina.logging.logger import JinaLogger
from jina.logging.predefined import default_logger

if TYPE_CHECKING:  # pragma: no cover
    from jina.clients.request import GeneratorSourceType
    from jina.types.request import Request, Response

    InputType = Union[GeneratorSourceType, Callable[..., GeneratorSourceType]]
    CallbackFnType = Optional[Callable[[Response], None]]
from jina.serve.instrumentation import InstrumentationMixin


class BaseClient(InstrumentationMixin, ABC):
    """A base client for connecting to the Flow Gateway.

    :param args: the Namespace from argparse
    :param kwargs: additional parameters that can be accepted by client parser
    """

    def __init__(
            self,
            args: Optional['argparse.Namespace'] = None,
            **kwargs,
    ):
        if args and isinstance(args, argparse.Namespace):
            self.args = args
        else:
            self.args = parse_client(kwargs)

        self.logger = JinaLogger(self.__class__.__name__, **vars(self.args))

        if not self.args.proxy and os.name != 'nt':
            # (Han 2020 12.12): gRPC channel is over HTTP2 and it does not work when we have proxy
            # as many enterprise users are behind proxy, a quick way to
            # surpass it is by temporally unset proxy. Please do NOT panic as it will NOT
            # affect users os-level envs.
            os.unsetenv('http_proxy')
            os.unsetenv('https_proxy')
        self._setup_instrumentation(
            name=(
                self.args.name
                if hasattr(self.args, 'name')
                else self.__class__.__name__
            ),
            tracing=self.args.tracing,
            traces_exporter_host=self.args.traces_exporter_host,
            traces_exporter_port=self.args.traces_exporter_port,
            metrics=self.args.metrics,
            metrics_exporter_host=self.args.metrics_exporter_host,
            metrics_exporter_port=self.args.metrics_exporter_port,
        )
        send_telemetry_event(event='start', obj_cls_name=self.__class__.__name__)

    async def close(self):
        """Closes the potential resources of the Client.
        :return: Return whatever a close method may return
        """
        return self.teardown_instrumentation()

    def teardown_instrumentation(self):
        """Shut down the OpenTelemetry tracer and meter if available. This ensures that the daemon threads for
        exporting metrics data is properly cleaned up.
        """
        try:
            if self.tracing and self.tracer_provider:
                if hasattr(self.tracer_provider, 'force_flush'):
                    self.tracer_provider.force_flush()
                if hasattr(self.tracer_provider, 'shutdown'):
                    self.tracer_provider.shutdown()
            if self.metrics and self.meter_provider:
                if hasattr(self.meter_provider, 'force_flush'):
                    self.meter_provider.force_flush()
                if hasattr(self.meter_provider, 'shutdown'):
                    self.meter_provider.shutdown()
        except Exception as ex:
            self.logger.warning(f'Exception during instrumentation teardown, {str(ex)}')

    @staticmethod
    def check_input(inputs: Optional['InputType'] = None, **kwargs) -> None:
        """Validate the inputs and print the first request if success.

        :param inputs: the inputs
        :param kwargs: keyword arguments
        """

        if inputs is None:
            # empty inputs is considered as valid
            return

        if hasattr(inputs, '__call__'):
            # it is a function
            inputs = inputs()

        kwargs['data'] = inputs
        kwargs['exec_endpoint'] = '/'

        if inspect.isasyncgenfunction(inputs) or inspect.isasyncgen(inputs):
            raise BadClientInput(
                'checking the validity of an async generator is not implemented yet'
            )

        try:
            from jina.clients.request import request_generator

            r = next(request_generator(**kwargs))
            from jina.types.request import Request

            if not isinstance(r, Request):
                raise TypeError(f'{typename(r)} is not a valid Request')
        except Exception as ex:
            default_logger.error(f'inputs is not valid!')
            raise BadClientInput from ex

    def _get_requests(
            self, inputs, **kwargs
    ) -> Tuple[Union[Iterator['Request'], AsyncIterator['Request']], Optional[int]]:
        """
        Get request in generator.

        :param inputs: The inputs argument to get the requests from.
        :param kwargs: Keyword arguments.
        :return: Iterator of request and the length of the inputs.
        """
        _kwargs = vars(self.args)
        if hasattr(inputs, '__call__'):
            inputs = inputs()

        _kwargs['data'] = inputs
        # override by the caller-specific kwargs
        _kwargs.update(kwargs)

        if hasattr(inputs, '__len__'):
            total_docs = len(inputs)
        elif 'total_docs' in _kwargs:
            total_docs = _kwargs['total_docs']
        else:
            total_docs = None

        if total_docs:
            inputs_length = max(1, total_docs / _kwargs['request_size'])
        else:
            inputs_length = None

        if inspect.isasyncgen(inputs):
            from jina.clients.request.asyncio import request_generator

            return request_generator(**_kwargs), inputs_length
        else:
            from jina.clients.request import request_generator

            return request_generator(**_kwargs), inputs_length

    @abc.abstractmethod
    async def _get_results(
            self,
            inputs: 'InputType',
            on_done: 'CallbackFnType',
            on_error: Optional['CallbackFnType'] = None,
            on_always: Optional['CallbackFnType'] = None,
            **kwargs,
    ):
        ...

    @abc.abstractmethod
    def _is_flow_ready(self, **kwargs) -> bool:
        """Sends a dry run to the Flow to validate if the Flow is ready to receive requests

        :param kwargs: potential kwargs received passed from the public interface
        """
        ...

    @property
    def client(self: T) -> T:
        """Return the client object itself

        :return: the Client object
        """
        return self

    async def _get_streaming_results(self, **kwargs):
        """Get the results from the Flow

        :param kwargs: potential kwargs received passed from the public interface
        """
        raise NotImplementedError(
            f'Streaming endpoints are not supported yet for {self.__class__.__name__}'
        )
