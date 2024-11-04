from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Union

from jina._docarray import docarray_v2
from jina.importer import ImportExtensions
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
        import pydantic
        from fastapi import FastAPI, HTTPException, Request
        from fastapi.middleware.cors import CORSMiddleware
        from pydantic import BaseModel, Field
        from pydantic.config import BaseConfig, inherit_config

    import os

    from jina.proto import jina_pb2
    from jina.serve.runtimes.gateway.models import _to_camel_case

    if not docarray_v2:
        logger.warning('Only docarray v2 is supported with CSP. ')
        return

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
        import json
        from typing import List, Type, Union

        try:
            from typing import get_args, get_origin
        except ImportError:
            from typing_extensions import get_args, get_origin

        from docarray.base_doc.docarray_response import DocArrayResponse
        from pydantic import BaseModel, ValidationError, parse_obj_as

        app_kwargs = dict(
            path=f'/{endpoint_path.strip("/")}',
            methods=['POST'],
            summary=f'Endpoint {endpoint_path}',
            response_model=Union[output_model, List[output_model]],
            response_class=DocArrayResponse,
        )

        def is_valid_csv(content: str) -> bool:
            import csv
            from io import StringIO

            try:
                f = StringIO(content)
                reader = csv.DictReader(f)
                for _ in reader:
                    pass

                return True
            except Exception:
                return False

        async def process(body) -> output_model:
            req = DataRequest()
            if body.header is not None:
                req.header.request_id = body.header.request_id

            if body.parameters is not None:
                req.parameters = body.parameters
            req.header.exec_endpoint = endpoint_path
            req.document_array_cls = DocList[input_doc_list_model]

            data = body.data
            if isinstance(data, list):
                req.data.docs = DocList[input_doc_list_model](data)
            else:
                req.data.docs = DocList[input_doc_list_model]([data])
                if body.header is None:
                    req.header.request_id = req.docs[0].id

            resp = await caller(req)
            status = resp.header.status

            if status.code == jina_pb2.StatusProto.ERROR:
                raise HTTPException(status_code=499, detail=status.description)
            else:
                return output_model(data=resp.docs, parameters=resp.parameters)

        @app.api_route(**app_kwargs)
        async def post(request: Request):
            content_type = request.headers.get('content-type')
            if content_type == 'application/json':
                json_body = await request.json()
                return await process(input_model(**json_body))

            elif content_type in ('text/csv', 'application/csv'):
                import csv
                from io import StringIO

                bytes_body = await request.body()
                csv_body = bytes_body.decode('utf-8')
                if not is_valid_csv(csv_body):
                    raise HTTPException(
                        status_code=400,
                        detail='Invalid CSV input. Please check your input.',
                    )

                def construct_model_from_line(
                        model: Type[BaseModel], line: List[str]
                ) -> BaseModel:
                    parsed_fields = {}
                    model_fields = model.__fields__

                    for field_str, (field_name, field_info) in zip(
                            line, model_fields.items()
                    ):
                        field_type = field_info.outer_type_

                        # Handle Union types by attempting to arse each potential type
                        if get_origin(field_type) is Union:
                            for possible_type in get_args(field_type):
                                if possible_type is str:
                                    parsed_fields[field_name] = field_str
                                    break
                                else:
                                    try:
                                        parsed_fields[field_name] = parse_obj_as(
                                            possible_type, json.loads(field_str)
                                        )
                                        break
                                    except (json.JSONDecodeError, ValidationError):
                                        continue
                        # Handle list of nested models
                        elif get_origin(field_type) is list:
                            list_item_type = get_args(field_type)[0]
                            if field_str:
                                parsed_list = json.loads(field_str)
                                if issubclass(list_item_type, BaseModel):
                                    parsed_fields[field_name] = parse_obj_as(
                                        List[list_item_type], parsed_list
                                    )
                                else:
                                    parsed_fields[field_name] = parsed_list
                        # General parsing attempt for other types
                        else:
                            if field_str:
                                try:
                                    parsed_fields[field_name] = field_info.type_(field_str)
                                except (ValueError, TypeError):
                                    # Fallback to parse_obj_as when type is more complex, e., AnyUrl or ImageBytes
                                    parsed_fields[field_name] = parse_obj_as(field_info.type_, field_str)

                    return model(**parsed_fields)

                # NOTE: Sagemaker only supports csv files without header, so we enforce
                # the header by getting the field names from the input model.
                # This will also enforce the order of the fields in the csv file.
                # This also means, all fields in the input model must be present in the
                # csv file including the optional ones.
                # We also expect the csv file to have no quotes and use the escape char '\'
                field_names = [f for f in input_doc_list_model.__fields__]
                data = []
                for line in csv.reader(
                        StringIO(csv_body),
                        delimiter=',',
                        quoting=csv.QUOTE_NONE,
                        escapechar='\\',
                ):
                    if len(line) != len(field_names):
                        raise HTTPException(
                            status_code=400,
                            detail=f'Invalid CSV format. Line {line} doesn\'t match '
                                   f'the expected field order {field_names}.',
                        )
                    data.append(construct_model_from_line(input_doc_list_model, line))

                return await process(input_model(data=data))

            else:
                raise HTTPException(
                    status_code=400,
                    detail=f'Invalid content-type: {content_type}. '
                           f'Please use either application/json or text/csv.',
                )

    for endpoint, input_output_map in request_models_map.items():
        if endpoint != '_jina_dry_run_':
            input_doc_model = input_output_map['input']['model']
            output_doc_model = input_output_map['output']['model']
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
                __config__=_config,
            )

            add_post_route(
                endpoint,
                input_model=endpoint_input_model,
                output_model=endpoint_output_model,
                input_doc_list_model=input_doc_model,
                output_doc_list_model=output_doc_model,
            )

    from jina.serve.runtimes.gateway.health_model import JinaHealthModel

    # `/ping` route is required by AWS Sagemaker
    @app.get(
        path='/ping',
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
