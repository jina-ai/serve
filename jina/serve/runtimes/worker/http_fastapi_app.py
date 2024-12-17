import inspect
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Union

from jina import Document, DocumentArray
from jina._docarray import docarray_v2
from jina.importer import ImportExtensions
from jina.serve.networking.sse import EventSourceResponse
from jina.types.request.data import DataRequest


if TYPE_CHECKING:
    from jina.logging.logger import JinaLogger

if docarray_v2:
    from docarray import BaseDoc, DocList


def get_fastapi_app(
    request_models_map: Dict,
    caller: Callable,
    logger: 'JinaLogger',
    cors: bool = False,
    **kwargs,
):
    """
    Get the app from FastAPI as the REST interface.

    :param request_models_map: Map describing the endpoints and its Pydantic models
    :param caller: Callable to be handled by the endpoints of the returned FastAPI app
    :param logger: Logger object
    :param cors: If set, a CORS middleware is added to FastAPI frontend to allow cross-origin access.
    :param kwargs: Extra kwargs to make it compatible with other methods
    :return: fastapi app
    """
    with ImportExtensions(required=True):
        from fastapi import FastAPI, Response, HTTPException, status as http_status
        import pydantic
        from fastapi.middleware.cors import CORSMiddleware
    import os

    from pydantic import BaseModel, Field
    from pydantic.config import BaseConfig, inherit_config

    from jina.proto import jina_pb2
    from jina.serve.runtimes.gateway.models import _to_camel_case

    class Header(BaseModel):
        request_id: Optional[str] = Field(
            description='Request ID', example=os.urandom(16).hex()
        )

        class Config(BaseConfig):
            alias_generator = _to_camel_case
            allow_population_by_field_name = True

    class InnerConfig(BaseConfig):
        alias_generator = _to_camel_case
        allow_population_by_field_name = True

    app = FastAPI()

    if cors:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=['*'],
            allow_credentials=True,
            allow_methods=['*'],
            allow_headers=['*'],
        )
        logger.warning('CORS is enabled. This service is accessible from any website!')

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
        if docarray_v2:
            from docarray.base_doc.docarray_response import DocArrayResponse

            app_kwargs['response_class'] = DocArrayResponse

        @app.api_route(**app_kwargs)
        async def post(body: input_model, response: Response):
            req = DataRequest()
            if body.header is not None:
                req.header.request_id = body.header.request_id

            if body.parameters is not None:
                req.parameters = body.parameters
            req.header.exec_endpoint = endpoint_path
            data = body.data
            if isinstance(data, list):
                if not docarray_v2:
                    req.direct_docs = DocumentArray.from_pydantic_model(data)
                else:
                    req.document_array_cls = DocList[input_doc_model]
                    req.direct_docs = DocList[input_doc_list_model](data)
            else:
                if not docarray_v2:
                    req.direct_docs = DocumentArray([Document.from_pydantic_model(data)])
                else:
                    req.document_array_cls = DocList[input_doc_model]
                    req.direct_docs = DocList[input_doc_list_model]([data])
                if body.header is None:
                    req.header.request_id = req.docs[0].id

            resp = await caller(req)
            status = resp.header.status

            if status.code == jina_pb2.StatusProto.ERROR:
                raise HTTPException(status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR, detail=status.description)
            else:
                if not docarray_v2:
                    docs_response = resp.docs.to_dict()
                else:
                    docs_response = resp.docs
                ret = output_model(data=docs_response, parameters=resp.parameters)

                return ret

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
        async def streaming_get(request: Request = None, body: input_doc_model = None):
            if not body:
                query_params = dict(request.query_params)
                body = (
                    input_doc_model.parse_obj(query_params)
                    if docarray_v2
                    else Document.from_dict(query_params)
                )
            else:
                if not docarray_v2:
                    body = Document.from_pydantic_model(body)
            req = DataRequest()
            req.header.exec_endpoint = endpoint_path
            if not docarray_v2:
                req.direct_docs = DocumentArray([body])
            else:
                req.document_array_cls = DocList[input_doc_model]
                req.direct_docs = DocList[input_doc_model]([body])
            event_generator = _gen_dict_documents(await caller(req))
            return EventSourceResponse(event_generator)

    for endpoint, input_output_map in request_models_map.items():
        if endpoint != '_jina_dry_run_':
            input_doc_model = input_output_map['input']['model']
            output_doc_model = input_output_map['output']['model']
            is_generator = input_output_map['is_generator']
            parameters_model = input_output_map['parameters']['model']
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

            if docarray_v2:
                _config = inherit_config(InnerConfig, BaseDoc.__config__)
            else:
                _config = input_doc_model.__config__

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

    from jina.serve.runtimes.gateway.health_model import JinaHealthModel

    @app.get(
        path='/',
        summary='Get the health of Jina Executor service',
        response_model=JinaHealthModel,
    )
    async def _executor_health():
        """
        Get the health of this Gateway service.
        .. # noqa: DAR201

        """
        return {}

    return app


async def _gen_dict_documents(gen):
    if inspect.isasyncgen(gen):
        async for document in gen:
            yield _doc_to_event(document)
    else:
        for document in gen:
            yield _doc_to_event(document)
    yield {'event': 'end'}


def _doc_to_event(doc):
    if not docarray_v2:
        return {'event': 'update', 'data': doc.to_dict()}
    else:
        return {'event': 'update', 'data': doc.dict()}
