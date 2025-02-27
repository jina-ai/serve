import asyncio
import copy
import re
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Type

import grpc.aio

from jina._docarray import DocumentArray, docarray_v2, is_pydantic_v2
from jina.constants import __default_endpoint__
from jina.excepts import InternalNetworkError
from jina.logging.logger import JinaLogger
from jina.serve.networking import GrpcConnectionPool
from jina.serve.runtimes.helper import _parse_specific_params
from jina.serve.runtimes.worker.request_handling import WorkerRequestHandler
from jina.types.request.data import DataRequest, SingleDocumentRequest

if docarray_v2:
    from docarray import DocList
    from jina._docarray import LegacyDocumentJina

    if not is_pydantic_v2:
        from jina.serve.runtimes.helper import _create_pydantic_model_from_schema as create_base_doc_from_schema
    else:
        from docarray.utils.create_dynamic_doc_class import create_base_doc_from_schema


    legacy_doc_schema = LegacyDocumentJina.schema()


class TopologyGraph:
    """
    :class TopologyGraph is a class that describes a computational graph of nodes, where each node represents
        a Deployment that needs to be sent requests in the order respecting the path traversal.

    :param graph_description: A dictionary describing the topology of the Deployments. 2 special nodes are expected, the name `start-gateway` and `end-gateway` to
        determine the nodes that receive the very first request and the ones whose response needs to be sent back to the client. All the nodes with no outgoing nodes
        will be considered to be floating, and they will be "flagged" so that the user can ignore their tasks and not await them.

    :param conditions: A dictionary describing which Executors have special conditions to be fullfilled by the `Documents` to be sent to them.
    :param reduce: Reduce requests arriving from multiple needed predecessors, True by default
    """

    class _ReqReplyNode:
        def __init__(
            self,
            name: str,
            number_of_parts: int = 1,
            floating: bool = False,
            filter_condition: dict = None,
            metadata: Optional[Dict] = None,
            reduce: bool = True,
            timeout_send: Optional[float] = None,
            retries: Optional[int] = -1,
            logger: Optional[JinaLogger] = None,
        ):
            self.name = name
            self.outgoing_nodes = []
            self.number_of_parts = number_of_parts
            self.floating = floating
            self.parts_to_send = []
            self.start_time = None
            self.end_time = None
            self.status = None
            self._filter_condition = filter_condition
            self._metadata = metadata
            self._reduce = reduce
            self._timeout_send = timeout_send
            self._retries = retries
            self.result_in_params_returned = None
            self.logger = logger or JinaLogger(self.__class__.__name__)
            self.endpoints = None
            self._pydantic_models_by_endpoint = None
            self._endpoints_proto = None

        @property
        def leaf(self):
            return len(self.outgoing_nodes) == 0

        def _validate_against_outgoing_nodes(self):
            def _check_schema_equality(schema_1, schema_2):
                from collections import OrderedDict

                # Naive check of compatibility
                schema_1_properties = OrderedDict(
                    sorted(schema_1.get('properties', {}).items())
                )
                schema_2_properties = OrderedDict(
                    sorted(schema_2.get('properties', {}).items())
                )
                if len(schema_1_properties) != len(schema_2_properties):
                    return False

                for property_1, property_2 in zip(
                    schema_1_properties.keys(), schema_2_properties.keys()
                ):
                    if property_1 != property_2:
                        return False

                    if schema_1_properties[property_1].get(
                        'type', None
                    ) != schema_2_properties[property_2].get('type', None):
                        return False

                    # TODO: Add more complex check for nested definitions

                return True

            for node in self.outgoing_nodes:
                # here validate for each endpoint that output of self matches input of node
                if node._pydantic_models_by_endpoint is not None:  # gateway end

                    for endp in self._pydantic_models_by_endpoint.keys():
                        outgoing_endp = endp
                        incoming_endp = (
                            endp
                            if endp in node._pydantic_models_by_endpoint
                            else __default_endpoint__
                        )

                        if incoming_endp in node._pydantic_models_by_endpoint:

                            if endp in node._pydantic_models_by_endpoint:
                                if not _check_schema_equality(
                                    self._pydantic_models_by_endpoint[outgoing_endp][
                                        'output'
                                    ].schema(),
                                    node._pydantic_models_by_endpoint[incoming_endp][
                                        'input'
                                    ].schema(),
                                ):
                                    raise Exception(
                                        f'The output schema of {self.name} at {outgoing_endp} endpoint is incompatible with the input schema of {node.name} at {incoming_endp} endpoint'
                                    )
                        else:
                            if (
                                outgoing_endp != __default_endpoint__
                            ):  # It could happen that there is an Encoder with default followed by an indexer with [index, search]
                                raise Exception(
                                    f'{node.name} does not expose {incoming_endp} which makes it impossible to be chained with {self.name} on {outgoing_endp}'
                                )
                            else:
                                self.logger.warning(
                                    f'{node.name} does not expose {incoming_endp} which could lead to incompatibility when calling non-explicitly bound endpoints'
                                )
                return node._validate_against_outgoing_nodes()
            return True

        def _update_requests_with_filter_condition(self, need_copy):
            for i in range(len(self.parts_to_send)):
                doc_array_cls = self.parts_to_send[i].document_array_cls
                req = (
                    self.parts_to_send[i]
                    if not need_copy
                    else copy.deepcopy(self.parts_to_send[i])
                )
                # somehow the document_array_cls is not copied
                req.document_array_cls = doc_array_cls
                if not docarray_v2:
                    filtered_docs = req.docs.find(self._filter_condition)
                else:
                    from docarray.utils.filter import filter_docs

                    filtered_docs = filter_docs(req.docs, self._filter_condition)
                req.data.docs = filtered_docs
                self.parts_to_send[i] = req

        def _update_request_by_params(
            self, deployment_name: str, request_input_parameters: Dict
        ):
            specific_parameters = _parse_specific_params(
                request_input_parameters, deployment_name
            )
            for i in range(len(self.parts_to_send)):
                self.parts_to_send[i].parameters = specific_parameters

        def _handle_internalnetworkerror(self, err):
            err_code = err.code()
            if err_code == grpc.StatusCode.UNAVAILABLE:
                err._details = (
                    err.details()
                    + f' |Gateway: Communication error with deployment {self.name} at address(es) {err.dest_addr}. '
                    f'Head or worker(s) may be down.'
                )
                raise err
            elif err_code == grpc.StatusCode.DEADLINE_EXCEEDED:
                err._details = (
                    err.details()
                    + f'|Gateway: Connection with deployment {self.name} at address(es) {err.dest_addr} could be established, but timed out.'
                    f' You can increase the allowed time by setting `timeout_send` in your Flow YAML `with` block or Flow `__init__()` method.'
                )
                raise err
            elif err_code == grpc.StatusCode.NOT_FOUND:
                err._details = (
                    err.details()
                    + f'\n|Gateway: Connection error with deployment `{self.name}` at address(es) {err.dest_addr}.'
                    f' Connection with {err.dest_addr} succeeded, but `{self.name}` was not found.'
                    f' Possibly `{self.name}` is behind an API gateway but not reachable.'
                )
                raise err
            else:
                raise

        def get_endpoints(
            self,
            connection_pool: GrpcConnectionPool,
            models_schema_list: List,
            models_list: List,
        ) -> asyncio.Task:
            # models_schema_list and models_list is given to each node. And each one fills its models
            from google.protobuf import json_format

            async def task():
                if self._endpoints_proto is None:
                    self.logger.debug(f'Getting Endpoints data from {self.name}')
                    endpoints_proto = await connection_pool.send_discover_endpoint(
                        self.name, retries=self._retries
                    )
                    # TODO: Try more often should not be able to start, synchronization issue
                    if endpoints_proto is not None:
                        endp, _ = endpoints_proto
                        self.endpoints = endp.endpoints
                        if docarray_v2:
                            schemas = json_format.MessageToDict(endp.schemas)
                            self._pydantic_models_by_endpoint = {}
                            models_created_by_name = {}
                            for endpoint, inner_dict in schemas.items():
                                input_model_name = inner_dict['input']['name']
                                input_model_schema = inner_dict['input']['model']
                                if input_model_schema in models_schema_list:
                                    input_model = models_list[
                                        models_schema_list.index(input_model_schema)
                                    ]
                                    models_created_by_name[input_model_name] = (
                                        input_model
                                    )
                                else:
                                    if input_model_name not in models_created_by_name:
                                        if input_model_schema == legacy_doc_schema:
                                            input_model = LegacyDocumentJina
                                        else:
                                            input_model = (
                                                create_base_doc_from_schema(
                                                    input_model_schema,
                                                    input_model_name,
                                                    models_created_by_name,
                                                )
                                            )
                                        models_created_by_name[input_model_name] = (
                                            input_model
                                        )
                                    input_model = models_created_by_name[
                                        input_model_name
                                    ]
                                    models_schema_list.append(input_model_schema)
                                    models_list.append(input_model)

                                output_model_name = inner_dict['output']['name']
                                output_model_schema = inner_dict['output']['model']
                                if output_model_schema in models_schema_list:
                                    output_model = models_list[
                                        models_schema_list.index(output_model_schema)
                                    ]
                                    models_created_by_name[output_model_name] = (
                                        output_model
                                    )
                                else:
                                    if output_model_name not in models_created_by_name:
                                        if output_model_name == legacy_doc_schema:
                                            output_model = LegacyDocumentJina
                                        else:
                                            output_model = (
                                                create_base_doc_from_schema(
                                                    output_model_schema,
                                                    output_model_name,
                                                    models_created_by_name,
                                                )
                                            )
                                        models_created_by_name[output_model_name] = (
                                            output_model
                                        )
                                    output_model = models_created_by_name[
                                        output_model_name
                                    ]
                                    models_schema_list.append(output_model)
                                    models_list.append(output_model)

                                parameters_model_name = inner_dict['parameters']['name']
                                parameters_model_schema = inner_dict['parameters'][
                                    'model'
                                ]
                                if parameters_model_schema is not None:
                                    if parameters_model_schema in models_schema_list:
                                        parameters_model = models_list[
                                            models_schema_list.index(
                                                parameters_model_schema
                                            )
                                        ]
                                        models_created_by_name[
                                            parameters_model_name
                                        ] = parameters_model
                                    else:
                                        if (
                                            parameters_model_name
                                            not in models_created_by_name
                                        ):
                                            from pydantic import BaseModel

                                            parameters_model = (
                                                create_base_doc_from_schema(
                                                    parameters_model_schema,
                                                    parameters_model_name,
                                                    models_created_by_name,
                                                    base_class=BaseModel,
                                                )
                                            )
                                            models_created_by_name[
                                                parameters_model_name
                                            ] = parameters_model
                                    parameters_model = models_created_by_name[
                                        parameters_model_name
                                    ]
                                    models_schema_list.append(parameters_model_schema)
                                    models_list.append(parameters_model)
                                else:
                                    parameters_model = None

                                self._pydantic_models_by_endpoint[endpoint] = {
                                    'input': input_model,
                                    'output': output_model,
                                    'is_generator': inner_dict['is_generator'],
                                    'is_singleton_doc': inner_dict['is_singleton_doc'],
                                    'parameters': parameters_model,
                                }
                        self._endpoints_proto = endpoints_proto
                    else:
                        raise Exception('Failed to get endpoints')
                return self._endpoints_proto

            return asyncio.create_task(task())

        async def stream_single_doc(
            self,
            request: SingleDocumentRequest,
            connection_pool: GrpcConnectionPool,
            endpoint: Optional[str],
            return_type: Type[DocumentArray] = DocumentArray,
        ):
            if docarray_v2:
                if self.endpoints and endpoint in self.endpoints:
                    request.document_cls = self._pydantic_models_by_endpoint[endpoint][
                        'input'
                    ]

            async for resp, _ in connection_pool.send_single_document_request(
                request=request,
                deployment=self.name,
                metadata=self._metadata,
                head=True,
                endpoint=endpoint,
                timeout=self._timeout_send,
                retries=self._retries,
            ):
                if issubclass(type(resp), BaseException):
                    raise resp
                else:
                    if docarray_v2:
                        if self.endpoints and endpoint in self.endpoints:
                            from docarray.base_doc import AnyDoc

                            # if return_type is not specified or if it is a default type, cast using retrieved
                            # schemas
                            if (
                                not return_type
                                or not return_type.doc_type
                                or return_type.doc_type is AnyDoc
                            ):
                                resp.document_cls = self._pydantic_models_by_endpoint[
                                    endpoint
                                ]['output']
                            else:
                                resp.document_array_cls = return_type
                    yield resp

        async def _wait_previous_and_send(
            self,
            request: Optional[DataRequest],
            previous_task: Optional[asyncio.Task],
            connection_pool: GrpcConnectionPool,
            endpoint: Optional[str],
            target_executor_pattern: Optional[str] = None,
            request_input_parameters: Dict = {},
            copy_request_at_send: bool = False,
            init_task: Optional[asyncio.Task] = None,
            return_type: Type[DocumentArray] = None,
        ):
            # Check my condition and send request with the condition
            metadata = {}
            if init_task is not None:
                await init_task
            if previous_task is not None:
                result = await previous_task
                request, metadata = result[0], result[1]
            if metadata and 'is-error' in metadata:
                return request, metadata
            elif request is not None:

                request.parameters = _parse_specific_params(
                    request.parameters, self.name
                )
                req_to_send = (
                    copy.deepcopy(request) if copy_request_at_send else request
                )
                if docarray_v2:
                    if self.endpoints and endpoint in self.endpoints:
                        req_to_send.document_array_cls = DocList[
                            self._pydantic_models_by_endpoint[endpoint]['input']
                        ]

                self.parts_to_send.append(req_to_send)
                # this is a specific needs
                if len(self.parts_to_send) == self.number_of_parts:
                    self.start_time = datetime.utcnow()
                    self._update_request_by_params(self.name, request_input_parameters)
                    if self._filter_condition is not None:
                        self._update_requests_with_filter_condition(
                            need_copy=not copy_request_at_send
                        )

                    # avoid sending to executor which does not bind to this endpoint
                    if endpoint is not None and self.endpoints is not None:
                        if (
                            endpoint not in self.endpoints
                            and __default_endpoint__ not in self.endpoints
                        ):
                            return request, metadata

                    if self._reduce and len(self.parts_to_send) > 1:
                        self.parts_to_send = [
                            WorkerRequestHandler.reduce_requests(self.parts_to_send)
                        ]

                    if target_executor_pattern is not None and not re.match(
                        target_executor_pattern, self.name
                    ):
                        return request, metadata
                    # otherwise, send to executor and get response
                    try:
                        result = await connection_pool.send_requests_once(
                            requests=self.parts_to_send,
                            deployment=self.name,
                            metadata=self._metadata,
                            head=True,
                            endpoint=endpoint,
                            timeout=self._timeout_send,
                            retries=self._retries,
                        )
                        if issubclass(type(result), BaseException):
                            raise result
                        else:
                            resp, metadata = result

                        if docarray_v2:
                            if self.endpoints and (
                                endpoint in self.endpoints
                                or __default_endpoint__ in self.endpoints
                            ):
                                from docarray.base_doc import AnyDoc

                                # if return_type is not specified or if it is a default type, cast using retrieved
                                # schemas
                                if (
                                    not return_type
                                    or not return_type.doc_type
                                    or return_type.doc_type is AnyDoc
                                ):
                                    pydantic_models = (
                                        self._pydantic_models_by_endpoint.get(endpoint)
                                        or self._pydantic_models_by_endpoint.get(
                                            __default_endpoint__
                                        )
                                    )
                                    resp.document_array_cls = DocList[
                                        pydantic_models['output']
                                    ]
                                else:
                                    resp.document_array_cls = return_type

                        if WorkerRequestHandler._KEY_RESULT in resp.parameters:
                            # Accumulate results from each Node and then add them to the original
                            self.result_in_params_returned = resp.parameters[
                                WorkerRequestHandler._KEY_RESULT
                            ]
                        request.parameters = request_input_parameters
                        resp.parameters = request_input_parameters
                        self.parts_to_send.clear()
                    except InternalNetworkError as err:
                        self._handle_internalnetworkerror(err)
                    except Exception as err:
                        self.logger.error(
                            f'Exception sending requests to {self.name}: {err}'
                        )
                        raise err

                    self.end_time = datetime.utcnow()
                    if metadata and 'is-error' in metadata:
                        self.status = resp.header.status
                    return resp, metadata

            return None, {}

        def _get_input_output_model_for_endpoint(
            self,
            previous_input,
            previous_output,
            previous_is_generator,
            previous_is_singleton_doc,
            previous_parameters,
            endpoint,
        ):
            if self._pydantic_models_by_endpoint is not None:

                if endpoint in self.endpoints:
                    # update output
                    # the only important for the gateway to know if is singleton is the first (so the last/ ignore previous is_singleton)
                    # the only important for the gateway to know if is generator is the last (so the first/previous precedence)
                    new_input = previous_input
                    if previous_input is None:
                        new_input = self._pydantic_models_by_endpoint[endpoint]['input']

                    is_generator = previous_is_generator
                    if previous_is_generator is None:
                        is_generator = self._pydantic_models_by_endpoint[endpoint][
                            'is_generator'
                        ]

                    if (
                        previous_output
                        and previous_output.schema()
                        == self._pydantic_models_by_endpoint[endpoint][
                            "output"
                        ].schema()
                    ):
                        # this is needed to not mix model IDs, otherwise FastAPI gets crazy
                        return {
                            'input': new_input,
                            'output': previous_output,
                            'is_generator': is_generator,
                            'is_singleton_doc': self._pydantic_models_by_endpoint[
                                endpoint
                            ]['is_singleton_doc'],
                            'parameters': self._pydantic_models_by_endpoint[endpoint][
                                'parameters'
                            ],
                        }
                    else:
                        return {
                            'input': new_input,
                            'output': self._pydantic_models_by_endpoint[endpoint][
                                'output'
                            ],
                            'is_generator': is_generator,
                            'is_singleton_doc': self._pydantic_models_by_endpoint[
                                endpoint
                            ]['is_singleton_doc'],
                            'parameters': self._pydantic_models_by_endpoint[endpoint][
                                'parameters'
                            ],
                        }
                else:
                    return {
                        'input': previous_input,
                        'output': previous_output,
                        'is_generator': previous_is_generator,
                        'is_singleton_doc': False,
                        'parameters': previous_parameters,
                    }
            return None

        def _get_leaf_input_output_model(
            self,
            previous_input,
            previous_output,
            previous_is_generator,
            previous_is_singleton_doc,
            previous_parameters,
            endpoint: Optional[str] = None,
        ):
            new_map = self._get_input_output_model_for_endpoint(
                previous_input,
                previous_output,
                previous_is_generator,
                previous_is_singleton_doc,
                previous_parameters,
                endpoint,
            )
            if self.leaf:  # I am like a leaf
                return list(
                    [new_map] if new_map is not None else []
                )  # I am the last in the chain
            list_of_outputs = []
            for outgoing_node in self.outgoing_nodes:
                list_of_maps = outgoing_node._get_leaf_input_output_model(
                    previous_input=new_map['input'] if new_map is not None else None,
                    previous_output=new_map['output'] if new_map is not None else None,
                    previous_is_generator=(
                        new_map['is_generator'] if new_map is not None else None
                    ),
                    previous_is_singleton_doc=(
                        new_map['is_singleton_doc'] if new_map is not None else None
                    ),
                    previous_parameters=(
                        new_map['parameters'] if new_map is not None else None
                    ),
                    endpoint=endpoint,
                )
                # We are interested in the last one, that will be the task that awaits all the previous
                list_of_outputs.extend(list_of_maps)

            return list_of_outputs

        def get_leaf_req_response_tasks(
            self,
            connection_pool: GrpcConnectionPool,
            request_to_send: Optional[DataRequest],
            previous_task: Optional[asyncio.Task],
            endpoint: Optional[str] = None,
            target_executor_pattern: Optional[str] = None,
            request_input_parameters: Dict = {},
            request_input_has_specific_params: bool = False,
            copy_request_at_send: bool = False,
            init_task: Optional[asyncio.Task] = None,
            return_type: Type[DocumentArray] = DocumentArray,
        ) -> List[Tuple[bool, asyncio.Task]]:
            """
            Gets all the tasks corresponding from all the subgraphs born from this node

            :param connection_pool: The connection_pool need to actually send the requests
            :param request_to_send: Optional request to be sent when the node is an origin of a graph
            :param previous_task: Optional task coming from the predecessor of the Node
            :param endpoint: Optional string defining the endpoint of this request
            :param target_executor_pattern: Optional regex pattern for the target executor to decide whether or not the Executor should receive the request
            :param request_input_parameters: The parameters coming from the Request as they arrive to the gateway
            :param request_input_has_specific_params: Parameter added for optimization. If this is False, there is no need to copy at all the request
            :param copy_request_at_send: Copy the request before actually calling the `ConnectionPool` sending
            :param init_task: Initial task to be called before sending any request

            .. note:
                deployment1 -> outgoing_nodes: deployment2
                deployment2 -> outgoing_nodes: deployment4
                deployment3 -> outgoing_nodes: deployment4
                deployment4 -> outgoing_nodes: deployment6
                deployment5 -> outgoing_nodes: deployment6
                deployment6 -> outgoing_nodes: []

                |-> deployment1 -> deployment2 -->
                |                   | -> deployment4 --->
                |-> deployment3 ---------->             | -> deployment6
                |-> deployment5 ------------------------>

                Let's imagine a graph from this. Node corresponding to Deployment6 will receive 2 calls from deployment4 and deployment5.
                The task returned by `deployment6` will backpropagated to the caller of deployment1.get_leaf_tasks, deployment3.get_leaf_tasks and deployment5.get_leaf_tasks.

                When the caller of these methods await them, they will fire the logic of sending requests and responses from and to every deployment

            :param return_type: the DocumentArray type to be returned. By default, it is `DocumentArray`.
            :return: Return a list of tuples, where tasks corresponding to the leafs of all the subgraphs born from this node are in each tuple.
                These tasks will be based on awaiting for the task from previous_node and sending a request to the corresponding node. The other member of the pair
                is a flag indicating if the task is to be awaited by the gateway or not.
            """
            wait_previous_and_send_task = asyncio.create_task(
                self._wait_previous_and_send(
                    request=request_to_send,
                    previous_task=previous_task,
                    connection_pool=connection_pool,
                    endpoint=endpoint,
                    target_executor_pattern=target_executor_pattern,
                    request_input_parameters=request_input_parameters,
                    copy_request_at_send=copy_request_at_send,
                    init_task=init_task,
                    return_type=return_type,
                )
            )
            if self.leaf:  # I am like a leaf
                return [
                    (not self.floating, wait_previous_and_send_task)
                ]  # I am the last in the chain
            hanging_tasks_tuples = []
            num_outgoing_nodes = len(self.outgoing_nodes)
            for outgoing_node in self.outgoing_nodes:
                t = outgoing_node.get_leaf_req_response_tasks(
                    connection_pool=connection_pool,
                    request_to_send=None,
                    previous_task=wait_previous_and_send_task,
                    endpoint=endpoint,
                    target_executor_pattern=target_executor_pattern,
                    request_input_parameters=request_input_parameters,
                    request_input_has_specific_params=request_input_has_specific_params,
                    copy_request_at_send=num_outgoing_nodes > 1
                    and request_input_has_specific_params,
                    return_type=return_type,
                )
                # We are interested in the last one, that will be the task that awaits all the previous
                hanging_tasks_tuples.extend(t)

            return hanging_tasks_tuples

        def add_route(self, request: 'DataRequest'):
            """
             Add routes to the DataRequest based on the state of request processing

             :param request: the request to add the routes to
            :return: modified request with added routes
            """

            def _find_route(request):
                for r in request.routes:
                    if r.executor == self.name:
                        return r
                return None

            r = _find_route(request)
            if r is None and self.start_time:
                r = request.routes.add()
                r.executor = self.name
                r.start_time.FromDatetime(self.start_time)
                if self.end_time:
                    r.end_time.FromDatetime(self.end_time)
                if self.status:
                    r.status.CopyFrom(self.status)
            for outgoing_node in self.outgoing_nodes:
                request = outgoing_node.add_route(request=request)
            return request

    class _EndGatewayNode(_ReqReplyNode):
        """
        Dummy node to be added before the gateway. This is to solve a problem we had when implementing `floating Executors`.
        If we do not add this at the end, this structure does not work:

            GATEWAY -> EXEC1 -> FLOATING
                    -> GATEWAY
        """

        def get_endpoints(self, *args, **kwargs) -> asyncio.Task:
            async def task_wrapper():
                from jina.serve.networking import default_endpoints_proto

                return default_endpoints_proto, None

            return asyncio.create_task(task_wrapper())

        def get_leaf_req_response_tasks(
            self, previous_task: Optional[asyncio.Task], *args, **kwargs
        ) -> List[Tuple[bool, asyncio.Task]]:
            return [(True, previous_task)]

        def _get_leaf_input_output_model(
            self,
            previous_input,
            previous_output,
            previous_is_generator,
            previous_is_singleton_doc,
            previous_parameters,
            endpoint: Optional[str] = None,
        ):
            return [
                {
                    'input': previous_input,
                    'output': previous_output,
                    'is_generator': previous_is_generator,
                    'is_singleton_doc': previous_is_singleton_doc,
                    'parameters': previous_parameters,
                }
            ]

    def __init__(
        self,
        graph_representation: Dict,
        graph_conditions: Dict = {},
        deployments_metadata: Dict = {},
        deployments_no_reduce: List[str] = [],
        timeout_send: Optional[float] = 1.0,
        retries: Optional[int] = -1,
        logger: Optional[JinaLogger] = None,
        *args,
        **kwargs,
    ):
        self.logger = logger or JinaLogger(self.__class__.__name__)
        num_parts_per_node = defaultdict(int)
        if 'start-gateway' in graph_representation:
            origin_node_names = graph_representation['start-gateway']
        else:
            origin_node_names = set()
        floating_deployment_set = set()
        node_set = set()
        for node_name, outgoing_node_names in graph_representation.items():
            if node_name not in {'start-gateway', 'end-gateway'}:
                node_set.add(node_name)
            if len(outgoing_node_names) == 0:
                floating_deployment_set.add(node_name)
            for out_node_name in outgoing_node_names:
                if out_node_name not in {'start-gateway', 'end-gateway'}:
                    node_set.add(out_node_name)
                    num_parts_per_node[out_node_name] += 1

        nodes = {}
        for node_name in node_set:
            condition = graph_conditions.get(node_name, None)
            metadata = deployments_metadata.get(node_name, None)
            nodes[node_name] = self._ReqReplyNode(
                name=node_name,
                number_of_parts=(
                    num_parts_per_node[node_name]
                    if num_parts_per_node[node_name] > 0
                    else 1
                ),
                floating=node_name in floating_deployment_set,
                filter_condition=condition,
                metadata=metadata,
                reduce=node_name not in deployments_no_reduce,
                timeout_send=timeout_send,
                retries=retries,
                logger=self.logger,
            )

        for node_name, outgoing_node_names in graph_representation.items():
            if node_name not in ['start-gateway', 'end-gateway']:
                for out_node_name in outgoing_node_names:
                    if out_node_name not in ['start-gateway', 'end-gateway']:
                        nodes[node_name].outgoing_nodes.append(nodes[out_node_name])
                    if out_node_name == 'end-gateway':
                        nodes[node_name].outgoing_nodes.append(
                            self._EndGatewayNode(name='__end_gateway__', floating=False)
                        )

        self._origin_nodes = [nodes[node_name] for node_name in origin_node_names]
        self.has_filter_conditions = bool(graph_conditions)
        self._all_endpoints = None

    async def _get_all_endpoints(
        self, connection_pool, retry_forever=False, is_cancel=None
    ):
        def _condition():
            if is_cancel is not None:
                is_cancelled = is_cancel.is_set()
                if is_cancelled:
                    self.logger.debug(f'cancel get all endpoints')
                return not is_cancelled
            else:
                return True

        if not self._all_endpoints:
            while _condition():
                try:
                    models_schemas_list = []
                    models_list = []
                    tasks_to_get_endpoints = [
                        node.get_endpoints(
                            connection_pool, models_schemas_list, models_list
                        )
                        for node in self.all_nodes
                    ]
                    await asyncio.gather(*tasks_to_get_endpoints)
                    endpoints = set()
                    for node in self.all_nodes:
                        if node.endpoints is not None:
                            endpoints.update(list(node.endpoints))
                    self._all_endpoints = endpoints
                    break
                except Exception as exc:
                    if not retry_forever:
                        raise exc
                    self.logger.warning(
                        f'Getting endpoints failed: {exc}. Waiting for another trial'
                    )
                    await asyncio.sleep(1)

        return self._all_endpoints

    def add_routes(self, request: 'DataRequest'):
        """
        Add routes to the DataRequest based on the state of request processing

        :param request: the request to add the routes to
        :return: modified request with added routes
        """
        for node in self._origin_nodes:
            request = node.add_route(request=request)
        return request

    @property
    def origin_nodes(self):
        """
        The list of origin nodes, the one that depend only on the gateway, so all the subgraphs will be born from them and they will
        send to their deployments the request as received by the client.

        :return: A list of nodes
        """
        return self._origin_nodes

    @property
    def all_nodes(self):
        """
        The set of all the nodes inside this Graph

        :return: A list of nodes
        """

        def _get_all_nodes(node, accum, accum_names):
            if node.name not in accum_names:
                accum.append(node)
                accum_names.append(node.name)
            for n in node.outgoing_nodes:
                _get_all_nodes(n, accum, accum_names)
            return accum, accum_names

        nodes = []
        node_names = []
        for origin_node in self.origin_nodes:
            subtree_nodes, subtree_node_names = _get_all_nodes(origin_node, [], [])
            for st_node, st_node_name in zip(subtree_nodes, subtree_node_names):
                if st_node_name not in node_names:
                    nodes.append(st_node)
                    node_names.append(st_node_name)
        return nodes

    def collect_all_results(self):
        """Collect all the results from every node into a single dictionary so that gateway can collect them

        :return: A dictionary of the results
        """
        res = {}
        for node in self.all_nodes:
            if node.result_in_params_returned:
                res.update(node.result_in_params_returned)
        return res

    def _validate_flow_docarray_compatibility(self):
        """
        Validates flow docarray validity in terms of input-output schemas of Executors
        """
        for node in self.origin_nodes:
            node._validate_against_outgoing_nodes()
