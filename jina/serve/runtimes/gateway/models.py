from collections import defaultdict
from datetime import datetime
from enum import Enum
from types import SimpleNamespace
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Union

from google.protobuf.descriptor import Descriptor, FieldDescriptor
from pydantic import BaseConfig, BaseModel, Field, create_model, root_validator

from jina._docarray import docarray_v2
from jina.proto.jina_pb2 import DataRequestProto, JinaInfoProto, RouteProto, StatusProto

if TYPE_CHECKING:  # pragma: no cover
    from google.protobuf.pyext.cpp_message import GeneratedProtocolMessageType

PROTO_TO_PYDANTIC_MODELS = SimpleNamespace()
PROTOBUF_TO_PYTHON_TYPE = {
    FieldDescriptor.TYPE_INT32: int,
    FieldDescriptor.TYPE_INT64: int,
    FieldDescriptor.TYPE_UINT32: int,
    FieldDescriptor.TYPE_UINT64: int,
    FieldDescriptor.TYPE_SINT32: int,
    FieldDescriptor.TYPE_SINT64: int,
    FieldDescriptor.TYPE_BOOL: bool,
    FieldDescriptor.TYPE_FLOAT: float,
    FieldDescriptor.TYPE_DOUBLE: float,
    FieldDescriptor.TYPE_FIXED32: float,
    FieldDescriptor.TYPE_FIXED64: float,
    FieldDescriptor.TYPE_SFIXED32: float,
    FieldDescriptor.TYPE_SFIXED64: float,
    FieldDescriptor.TYPE_BYTES: bytes,
    FieldDescriptor.TYPE_STRING: str,
    FieldDescriptor.TYPE_ENUM: Enum,
    FieldDescriptor.TYPE_MESSAGE: None,
}

DESCRIPTION_DATA = 'Data to send, a list of dict/string/bytes that can be converted into a list of `Document` objects'
DESCRIPTION_TARGET_EXEC = (
    'A regex string representing the specific pods/deployments targeted by the request.'
)
DESCRIPTION_PARAMETERS = 'A dictionary of parameters to be sent to the executor.'
DESCRIPTION_EXEC_ENDPOINT = (
    'The endpoint string, by convention starts with `/`. '
    'All executors bind with `@requests(on=exec_endpoint)` will receive this request.'
)


class CustomConfig(BaseConfig):
    """Pydantic config for Camel case and enum handling"""

    use_enum_values = True
    allow_population_by_field_name = True


def _get_oneof_validator(oneof_fields: List, oneof_key: str) -> Callable:
    """
    Pydantic root validator (pre) classmethod generator to confirm only one oneof field is passed

    :param oneof_fields: list of field names for oneof
    :type oneof_fields: List
    :param oneof_key: oneof key
    :type oneof_key: str
    :return: classmethod for validating oneof fields
    """

    def oneof_validator(cls, values):
        if len(set(oneof_fields).intersection(set(values))) > 1:
            raise ValueError(
                f'only one field among {oneof_fields} can be set for key {oneof_key}!'
            )
        return values

    oneof_validator.__qualname__ = 'validate_' + oneof_key
    return root_validator(pre=True, allow_reuse=True)(oneof_validator)


def _get_oneof_setter(oneof_fields: List, oneof_key: str) -> Callable:
    """
    Pydantic root validator (post) classmethod generator to set the oneof key

    :param oneof_fields: list of field names for oneof
    :type oneof_fields: List
    :param oneof_key: oneof key
    :type oneof_key: str
    :return: classmethod for setting oneof fields in Pydantic models
    """

    def oneof_setter(cls, values):
        for oneof_field in oneof_fields:
            if (
                oneof_field in values
                and values[oneof_field] == cls.__fields__[oneof_field].default
            ):
                values.pop(oneof_field)
        return values

    oneof_setter.__qualname__ = 'set_' + oneof_key
    return root_validator(pre=False, allow_reuse=True)(oneof_setter)


def protobuf_to_pydantic_model(
    protobuf_model: Union[Descriptor, 'GeneratedProtocolMessageType']
) -> BaseModel:
    """
    Converts Protobuf messages to Pydantic model for jsonschema creation/validattion

    ..note:: Model gets assigned in the global Namespace :data:PROTO_TO_PYDANTIC_MODELS

    :param protobuf_model: message from jina.proto file
    :type protobuf_model: Union[Descriptor, GeneratedProtocolMessageType]
    :return: Pydantic model
    """

    all_fields = {}
    camel_case_fields = {}  # {"random_string": {"alias": "randomString"}}
    oneof_fields = defaultdict(list)
    oneof_field_validators = {}

    desc = (
        protobuf_model
        if isinstance(protobuf_model, Descriptor)
        else getattr(protobuf_model, 'DESCRIPTOR', None)
    )
    if desc:
        model_name = desc.name
        protobuf_fields = desc.fields
    else:
        raise ValueError(
            f'protobuf_model is of type {type(protobuf_model)} and has no attribute "DESCRIPTOR"'
        )

    if model_name in vars(PROTO_TO_PYDANTIC_MODELS):
        return PROTO_TO_PYDANTIC_MODELS.__getattribute__(model_name)

    for f in protobuf_fields:
        field_name = f.name
        camel_case_fields[field_name] = {'alias': f.camelcase_name}

        field_type = PROTOBUF_TO_PYTHON_TYPE[f.type]
        default_value = f.default_value
        default_factory = None

        if f.containing_oneof:
            # Proto Field type: oneof
            # NOTE: oneof fields are handled as a post-processing step
            oneof_fields[f.containing_oneof.name].append(field_name)

        if field_type is Enum:
            # Proto Field Type: enum
            enum_dict = {}

            for enum_field in f.enum_type.values:
                enum_dict[enum_field.name] = enum_field.number

            field_type = Enum(f.enum_type.name, enum_dict)

        if f.message_type:
            if f.message_type.name == 'Struct':
                # Proto Field Type: google.protobuf.Struct
                field_type = Dict
                default_factory = dict
            elif f.message_type.name == 'Timestamp':
                # Proto Field Type: google.protobuf.Timestamp
                field_type = datetime
                default_factory = datetime.now
            else:
                # Proto field type: Proto message defined in jina.proto
                if f.message_type.name == model_name:
                    # Self-referencing models
                    field_type = model_name
                else:
                    # This field_type itself a Pydantic model
                    field_type = protobuf_to_pydantic_model(f.message_type)
                    PROTO_TO_PYDANTIC_MODELS.model_name = field_type

        if f.label == FieldDescriptor.LABEL_REPEATED:
            field_type = List[field_type]

        all_fields[field_name] = (
            field_type,
            (
                Field(default_factory=default_factory)
                if default_factory
                else Field(default=default_value)
            ),
        )

    # Post-processing (Handle oneof fields)
    for oneof_k, oneof_v_list in oneof_fields.items():
        oneof_field_validators[f'oneof_validator_{oneof_k}'] = _get_oneof_validator(
            oneof_fields=oneof_v_list, oneof_key=oneof_k
        )
        oneof_field_validators[f'oneof_setter_{oneof_k}'] = _get_oneof_setter(
            oneof_fields=oneof_v_list, oneof_key=oneof_k
        )

    CustomConfig.fields = camel_case_fields
    if model_name == 'DocumentProto':
        from docarray.document.pydantic_model import PydanticDocument

        model = PydanticDocument
    elif model_name == 'DocumentArrayProto':
        from docarray.document.pydantic_model import PydanticDocumentArray

        model = PydanticDocumentArray
    else:
        model = create_model(
            model_name,
            **all_fields,
            __config__=CustomConfig,
            __validators__=oneof_field_validators,
        )
        model.update_forward_refs()
    PROTO_TO_PYDANTIC_MODELS.__setattr__(model_name, model)

    return model


if not docarray_v2:
    for proto in (RouteProto, StatusProto, DataRequestProto, JinaInfoProto):
        protobuf_to_pydantic_model(proto)
else:
    for proto in (RouteProto, StatusProto, JinaInfoProto):
        protobuf_to_pydantic_model(proto)


def _to_camel_case(snake_str: str) -> str:
    components = snake_str.split('_')
    # We capitalize the first letter of each component except the first one
    # with the 'title' method and join them together.
    return components[0] + ''.join(x.title() for x in components[1:])


if not docarray_v2:
    from docarray.document.pydantic_model import PydanticDocument, PydanticDocumentArray

    class JinaRequestModel(BaseModel):
        """
        Jina HTTP request model.
        """

        # the dict one is only for compatibility.
        # So we will accept data: {[Doc1.to_dict, Doc2...]} and data: {docs: [[Doc1.to_dict, Doc2...]}
        data: Optional[
            Union[
                PydanticDocumentArray,
                Dict[str, PydanticDocumentArray],
            ]
        ] = Field(
            None,
            example=[
                {'text': 'hello, world!'},
                {'uri': 'https://jina.ai/serve/_static/logo-light.svg'},
            ],
            description=DESCRIPTION_DATA,
        )
        target_executor: Optional[str] = Field(
            None,
            example='',
            description=DESCRIPTION_TARGET_EXEC,
        )
        parameters: Optional[Dict] = Field(
            None,
            example={},
            description=DESCRIPTION_PARAMETERS,
        )

        class Config:
            alias_generator = _to_camel_case
            allow_population_by_field_name = True

    class JinaResponseModel(BaseModel):
        """
        Jina HTTP Response model. Only `request_id` and `data` are preserved.
        """

        header: PROTO_TO_PYDANTIC_MODELS.HeaderProto = None
        parameters: Dict = None
        routes: List[PROTO_TO_PYDANTIC_MODELS.RouteProto] = None
        data: Optional[PydanticDocumentArray] = None

        class Config:
            alias_generator = _to_camel_case
            allow_population_by_field_name = True

    class JinaEndpointRequestModel(JinaRequestModel):
        """
        Jina HTTP request model that allows customized endpoint.
        """

        exec_endpoint: str = Field(
            default='/',
            example='/',
            description='The endpoint string, by convention starts with `/`. '
            'If you specify it as `/foo`, then all executors bind with `@requests(on="/foo")` will receive the request.',
        )
