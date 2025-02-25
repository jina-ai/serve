import copy
from typing import Any, Dict, List, Optional, Tuple, Union

from jina._docarray import docarray_v2, is_pydantic_v2

_SPECIFIC_EXECUTOR_SEPARATOR = '__'


def _spit_key_and_executor_name(key_name: str) -> Tuple[str]:
    """Split a specific key into a key, name pair

    ex: 'key__my_executor' will be split into 'key', 'my_executor'

    :param key_name: key name of the param
    :return: return the split 'key', 'executor_name' for the key_name
    """
    key_split = key_name.split(_SPECIFIC_EXECUTOR_SEPARATOR)

    new_key_name = key_split.pop(-1)
    executor_name = ''.join(key_split)

    return new_key_name, executor_name


def _get_name_from_replicas_name(name: str) -> Tuple[str]:
    """return the original name without the replicas

    ex: 'exec1/rep-0' will be transform into 'exec1'

    :param name: name of the DataRequest
    :return: return the original name without the replicas
    """
    return name.split('/')[0]


def _is_param_for_specific_executor(key_name: str) -> bool:
    """Tell if a key is for a specific Executor

    ex: 'key' is for every Executor whereas 'my_executor__key' is only for 'my_executor'

    :param key_name: key name of the param
    :return: return True if key_name is for specific Executor, False otherwise
    """
    if _SPECIFIC_EXECUTOR_SEPARATOR in key_name:
        if key_name.startswith(_SPECIFIC_EXECUTOR_SEPARATOR) or key_name.endswith(
            _SPECIFIC_EXECUTOR_SEPARATOR
        ):
            return False
        return True
    else:
        return False


def _parse_specific_params(parameters: Dict, executor_name: str):
    """Parse the parameters dictionary to filter executor specific parameters

    :param parameters: dictionary container the parameters
    :param executor_name: name of the Executor
    :returns: the parsed parameters after applying filtering for the specific Executor
    """
    parsed_params = copy.deepcopy(parameters)

    for key in parameters:
        if _is_param_for_specific_executor(key):
            (
                key_name,
                key_executor_name,
            ) = _spit_key_and_executor_name(key)

            if key_executor_name == executor_name:
                parsed_params[key_name] = parameters[key]

            del parsed_params[key]

    specific_parameters = parameters.get(executor_name, None)
    if specific_parameters:
        parsed_params.update(**specific_parameters)

    return parsed_params


if docarray_v2 and not is_pydantic_v2:
    from docarray import BaseDoc, DocList
    from docarray.typing import AnyTensor
    from pydantic import create_model
    from pydantic.fields import FieldInfo

    from jina._docarray import docarray_v2

    RESERVED_KEYS = [
        'type',
        'anyOf',
        '$ref',
        'additionalProperties',
        'allOf',
        'items',
        'definitions',
        'properties',
        'default',
    ]

    def _create_aux_model_doc_list_to_list(model):
        fields: Dict[str, Any] = {}
        for field_name, field in model.__annotations__.items():
            if field_name not in model.__fields__:
                continue
            field_info = model.__fields__[field_name].field_info
            try:
                if issubclass(field, DocList):
                    t: Any = field.doc_type
                    t_aux = _create_aux_model_doc_list_to_list(t)
                    fields[field_name] = (List[t_aux], field_info)
                else:
                    fields[field_name] = (field, field_info)
            except TypeError:
                fields[field_name] = (field, field_info)
        return create_model(
            model.__name__,
            __base__=model,
            __validators__=model.__validators__,
            **fields,
        )

    def _get_field_from_type(
        field_schema,
        field_name,
        root_schema,
        cached_models,
        is_tensor=False,
        num_recursions=0,
        base_class=BaseDoc,
        definitions: Optional[Dict] = None,
    ):
        if not definitions:
            definitions = {}
        field_type = field_schema.get('type', None)
        tensor_shape = field_schema.get('tensor/array shape', None)
        if 'anyOf' in field_schema:
            any_of_types = []
            for any_of_schema in field_schema['anyOf']:
                if '$ref' in any_of_schema:
                    obj_ref = any_of_schema.get('$ref')
                    ref_name = obj_ref.split('/')[-1]
                    any_of_types.append(
                        _create_pydantic_model_from_schema(
                            definitions[ref_name],
                            ref_name,
                            cached_models=cached_models,
                            base_class=base_class,
                            definitions=definitions,
                        )
                    )
                else:
                    any_of_types.append(
                        _get_field_from_type(
                            any_of_schema,
                            field_name,
                            root_schema=root_schema,
                            cached_models=cached_models,
                            is_tensor=tensor_shape is not None,
                            num_recursions=0,
                            base_class=base_class,
                            definitions=definitions,
                        )
                    )  # No Union of Lists
            ret = Union[tuple(any_of_types)]
            for rec in range(num_recursions):
                ret = List[ret]
        elif field_type == 'string':
            ret = str
            for rec in range(num_recursions):
                ret = List[ret]
        elif field_type == 'integer':
            ret = int
            for rec in range(num_recursions):
                ret = List[ret]
        elif field_type == 'number':
            if num_recursions == 0:
                ret = float
            elif num_recursions == 1:
                # This is a hack because AnyTensor is more generic than a simple List and it comes as simple List
                if is_tensor:
                    ret = AnyTensor
                else:
                    ret = List[float]
            else:
                ret = float
                for rec in range(num_recursions):
                    ret = List[ret]
        elif field_type == 'boolean':
            ret = bool
            for rec in range(num_recursions):
                ret = List[ret]
        elif field_type == 'object' or field_type is None:
            if 'additionalProperties' in field_schema:  # handle Dictionaries
                additional_props = field_schema['additionalProperties']
                if additional_props.get('type') == 'object':
                    ret = Dict[
                        str,
                        _create_pydantic_model_from_schema(
                            additional_props,
                            field_name,
                            cached_models=cached_models,
                            base_class=base_class,
                        ),
                    ]
                else:
                    ret = Dict[str, Any]
            else:
                obj_ref = field_schema.get('$ref') or field_schema.get('allOf', [{}])[
                    0
                ].get('$ref', None)
                if num_recursions == 0:  # single object reference
                    if obj_ref:
                        ref_name = obj_ref.split('/')[-1]
                        ret = _create_pydantic_model_from_schema(
                            definitions[ref_name],
                            ref_name,
                            cached_models=cached_models,
                            base_class=base_class,
                            definitions=definitions,
                        )
                    else:
                        ret = Any
                else:  # object reference in definitions
                    if obj_ref:
                        ref_name = obj_ref.split('/')[-1]
                        ret = DocList[
                            _create_pydantic_model_from_schema(
                                definitions[ref_name],
                                ref_name,
                                cached_models=cached_models,
                                base_class=base_class,
                                definitions=definitions,
                            )
                        ]
                    else:
                        ret = DocList[
                            _create_pydantic_model_from_schema(
                                field_schema,
                                field_name,
                                cached_models=cached_models,
                                base_class=base_class,
                                definitions=definitions,
                            )
                        ]
        elif field_type == 'array':
            ret = _get_field_from_type(
                field_schema=field_schema.get('items', {}),
                field_name=field_name,
                root_schema=root_schema,
                cached_models=cached_models,
                is_tensor=tensor_shape is not None,
                num_recursions=num_recursions + 1,
                base_class=base_class,
                definitions=definitions,
            )
        else:
            if num_recursions > 0:
                raise ValueError(
                    f"Unknown array item type: {field_type} for field_name {field_name}"
                )
            else:
                raise ValueError(
                    f"Unknown field type: {field_type} for field_name {field_name}"
                )
        return ret

    def _create_pydantic_model_from_schema(
        schema: Dict[str, any],
        model_name: str,
        cached_models: Dict,
        base_class=BaseDoc,
        definitions: Optional[Dict] = None,
    ) -> type:
        if not definitions:
            definitions = schema.get('definitions', {})
        cached_models = cached_models if cached_models is not None else {}
        fields: Dict[str, Any] = {}
        if model_name in cached_models:
            return cached_models[model_name]
        for field_name, field_schema in schema.get('properties', {}).items():
            field_type = _get_field_from_type(
                field_schema=field_schema,
                field_name=field_name,
                root_schema=schema,
                cached_models=cached_models,
                is_tensor=False,
                num_recursions=0,
                base_class=base_class,
                definitions=definitions,
            )
            fields[field_name] = (
                field_type,
                FieldInfo(default=field_schema.pop('default', None), **field_schema),
            )

        model = create_model(model_name, __base__=base_class, **fields)
        model.__config__.title = schema.get('title', model.__config__.title)

        for k in RESERVED_KEYS:
            if k in schema:
                schema.pop(k)
        model.__config__.schema_extra = schema
        cached_models[model_name] = model
        return model
