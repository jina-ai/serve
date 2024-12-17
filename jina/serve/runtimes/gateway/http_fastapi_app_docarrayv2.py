from typing import TYPE_CHECKING, Dict, List, Optional, Union

from jina.excepts import InternalNetworkError
from jina.helper import get_full_version
from jina.importer import ImportExtensions
from jina.logging.logger import JinaLogger
from jina.serve.networking.sse import EventSourceResponse
from jina.types.request.data import DataRequest

if TYPE_CHECKING:  # pragma: no cover
    from opentelemetry import trace

    from jina.serve.runtimes.gateway.streamer import GatewayStreamer


def get_fastapi_app(
    streamer: 'GatewayStreamer',
    title: str,
    description: str,
    expose_graphql_endpoint: bool,
    cors: bool,
    logger: 'JinaLogger',
    tracing: Optional[bool] = None,
    tracer_provider: Optional['trace.TracerProvider'] = None,
    **kwargs,
):
    """
    Get the app from FastAPI as the REST interface.

    :param streamer: gateway streamer object
    :param title: The title of this HTTP server. It will be used in automatics docs such as Swagger UI.
    :param description: The description of this HTTP server. It will be used in automatics docs such as Swagger UI.
    :param expose_graphql_endpoint: If set, /graphql endpoint is added to HTTP interface.
    :param cors: If set, a CORS middleware is added to FastAPI frontend to allow cross-origin access.
    :param logger: Jina logger.
    :param tracing: Enables tracing if set to True.
    :param tracer_provider: If tracing is enabled the tracer_provider will be used to instrument the code.
    :param kwargs: Extra kwargs to make it compatible with other methods
    :return: fastapi app
    """
    if expose_graphql_endpoint:
        logger.error(f' GraphQL endpoint is not enabled when using docarray >0.30')
    with ImportExtensions(required=True):
        from fastapi import FastAPI, Response, HTTPException, status as http_status
        from fastapi.middleware.cors import CORSMiddleware
        import pydantic
        from pydantic import Field
    from docarray import BaseDoc, DocList
    from docarray.base_doc.docarray_response import DocArrayResponse

    from jina import __version__

    app = FastAPI(
        title=title or 'My Jina Service',
        description=description
        or 'This is my awesome service. You can set `title` and `description` in your `Flow` or `Gateway` '
        'to customize the title and description.',
        version=__version__,
    )

    if tracing:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, tracer_provider=tracer_provider)

    if cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=['*'],
            allow_credentials=True,
            allow_methods=['*'],
            allow_headers=['*'],
        )
        logger.warning('CORS is enabled. This service is accessible from any website!')

    @app.on_event('shutdown')
    async def _shutdown():
        await streamer.close()

    import os

    from pydantic import BaseModel
    from pydantic.config import BaseConfig, inherit_config

    from jina.proto import jina_pb2
    from jina.serve.runtimes.gateway.models import (
        PROTO_TO_PYDANTIC_MODELS,
        _to_camel_case,
    )
    from jina.types.request.status import StatusMessage

    class Header(BaseModel):
        request_id: Optional[str] = Field(
            description='Request ID', example=os.urandom(16).hex()
        )
        target_executor: Optional[str] = Field(default=None, example="")

        class Config(BaseConfig):
            alias_generator = _to_camel_case
            allow_population_by_field_name = True

    class InnerConfig(BaseConfig):
        alias_generator = _to_camel_case
        allow_population_by_field_name = True

    @app.get(
        path='/dry_run',
        summary='Get the readiness of Jina Flow service, sends an empty DocumentArray to the complete Flow to '
        'validate connectivity',
        response_model=PROTO_TO_PYDANTIC_MODELS.StatusProto,
    )
    async def _flow_health():
        """
        Get the health of the complete Flow service.
        .. # noqa: DAR201

        """

        docs = DocList[BaseDoc]([])

        try:
            async for _ in streamer.stream_docs(docs, request_size=1):
                status_message = StatusMessage()
                status_message.set_code(jina_pb2.StatusProto.SUCCESS)
                return status_message.to_dict()
        except Exception as ex:
            status_message = StatusMessage()
            status_message.set_exception(ex)
            return status_message.to_dict(use_integers_for_enums=True)

    request_models_map = streamer._endpoints_models_map

    if '/status' not in request_models_map:
        from jina.serve.runtimes.gateway.health_model import JinaInfoModel

        @app.get(
            path='/status',
            summary='Get the status of Jina service',
            response_model=JinaInfoModel,
            tags=['Debug'],
        )
        async def _status():
            """
            Get the status of this Jina service.

            This is equivalent to running `jina -vf` from command line.

            .. # noqa: DAR201
            """
            version, env_info = get_full_version()
            for k, v in version.items():
                version[k] = str(v)
            for k, v in env_info.items():
                env_info[k] = str(v)
            return {'jina': version, 'envs': env_info}

    def _generate_exception_header(error: InternalNetworkError):
        import traceback

        exception_dict = {
            'name': str(error.__class__),
            'stacks': [
                str(x) for x in traceback.extract_tb(error.og_exception.__traceback__)
            ],
            'executor': '',
        }
        status_dict = {
            'code': DataRequest().status.ERROR,
            'description': error.details() if error.details() else '',
            'exception': exception_dict,
        }
        header_dict = {'request_id': error.request_id, 'status': status_dict}
        return header_dict

    def add_post_route(
        endpoint_path,
        input_model,
        output_model,
        input_doc_list_model=None,
        output_doc_list_model=None,
    ):
        app_kwargs = dict(
            path=f'/{endpoint_path.strip("/")}',
            methods=['POST'],
            summary=f'Endpoint {endpoint_path}',
            response_model=output_model,
        )
        app_kwargs['response_class'] = DocArrayResponse

        @app.api_route(**app_kwargs)
        async def post(body: input_model, response: Response):
            target_executor = None
            req_id = None
            if body.header is not None:
                target_executor = body.header.target_executor
                req_id = body.header.request_id
            data = body.data
            if isinstance(data, list):
                docs = DocList[input_doc_list_model](data)
            else:
                docs = DocList[input_doc_list_model]([data])
                if body.header is None:
                    if hasattr(docs[0], 'id'):
                        req_id = docs[0].id

            try:
                async for resp in streamer.stream_docs(
                    docs,
                    exec_endpoint=endpoint_path,
                    parameters=body.parameters,
                    target_executor=target_executor,
                    request_id=req_id,
                    return_results=True,
                    return_type=DocList[output_doc_list_model],
                ):
                    status = resp.header.status

                    if status.code == jina_pb2.StatusProto.ERROR:
                        raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=status.description)
                    else:
                        result_dict = resp.to_dict()
                        return result_dict
            except InternalNetworkError as err:
                import grpc

                if (
                    err.code() == grpc.StatusCode.UNAVAILABLE
                    or err.code() == grpc.StatusCode.NOT_FOUND
                ):
                    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
                elif err.code() == grpc.StatusCode.DEADLINE_EXCEEDED:
                    response.status_code = status.HTTP_504_GATEWAY_TIMEOUT
                else:
                    response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
                result = body.dict()  # send back the request
                result['header'] = _generate_exception_header(
                    err
                )  # attach exception details to response header
                logger.error(
                    f'Error while getting responses from deployments: {err.details()}'
                )
                return result

    def add_streaming_routes(
        endpoint_path,
        input_doc_model=None,
    ):
        from fastapi import Request

        @app.api_route(
            path=f'/{endpoint_path.strip("/")}',
            methods=['GET'],
            summary=f'Streaming Endpoint {endpoint_path}',
        )
        async def streaming_get(request: Request, body: input_doc_model = None):
            body = body or dict(request.query_params)
            body = input_doc_model.parse_obj(body)

            async def event_generator():
                async for doc, error in streamer.stream_doc(
                    doc=body, exec_endpoint=endpoint_path
                ):
                    if error:
                        raise HTTPException(status_code=499, detail=str(error))
                    yield {'event': 'update', 'data': doc.dict()}
                yield {'event': 'end'}

            return EventSourceResponse(event_generator())

    for endpoint, input_output_map in request_models_map.items():
        if endpoint != '_jina_dry_run_':
            input_doc_model = input_output_map['input']
            output_doc_model = input_output_map['output']
            is_generator = input_output_map['is_generator']
            parameters_model = input_output_map['parameters']
            parameters_model_needed = parameters_model is not None
            if parameters_model_needed:
                try:
                    _ = parameters_model()
                    parameters_model_needed = False
                except:
                    parameters_model_needed = True
                parameters_model = parameters_model if parameters_model_needed else Optional[parameters_model]
                default_parameters = (
                    ... if parameters_model_needed else None
                )
            else:
                parameters_model = Optional[Dict]
                default_parameters = None

            _config = inherit_config(InnerConfig, BaseDoc.__config__)

            endpoint_input_model = pydantic.create_model(
                f'{endpoint.strip("/")}_input_model',
                data=(Union[List[input_doc_model], input_doc_model], ...),
                parameters=(parameters_model, default_parameters),
                header=(Optional[Header], None),
                __config__=_config,
            )

            endpoint_output_model = pydantic.create_model(
                f'{endpoint.strip("/")}_output_model',
                data=(Union[List[output_doc_model], output_doc_model], ...),
                parameters=(Optional[Dict], None),
                header=(Optional[Header], None),
                __config__=_config,
            )

            if is_generator:
                add_streaming_routes(
                    endpoint,
                    input_doc_model=input_doc_model,
                )
            else:
                add_post_route(
                    endpoint,
                    input_model=endpoint_input_model,
                    output_model=endpoint_output_model,
                    input_doc_list_model=input_doc_model,
                    output_doc_list_model=output_doc_model,
                )

    return app
