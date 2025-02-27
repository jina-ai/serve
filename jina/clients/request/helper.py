"""Module for helper functions for clients."""

from typing import Optional, Tuple

from jina._docarray import Document, DocumentArray, docarray_v2
from jina.enums import DataInputType
from jina.types.request.data import DataRequest

if docarray_v2:
    from docarray import DocList, BaseDoc


def _new_data_request_from_batch(
    batch,
    data_type: DataInputType,
    endpoint: str,
    target: Optional[str],
    parameters: Optional[dict],
) -> DataRequest:
    req = _new_data_request(endpoint, target, parameters)

    # add docs fields
    _add_docs(req, batch, data_type)

    return req


def _new_data_request(
    endpoint: str, target: Optional[str], parameters: Optional[dict]
) -> DataRequest:
    req = DataRequest()

    # set up header
    req.header.exec_endpoint = endpoint
    if target:
        req.header.target_executor = target
    # add parameters field
    if parameters:
        req.parameters = parameters
    return req


def _new_doc_from_data(
    data, data_type: DataInputType
) -> Tuple['Document', 'DataInputType']:
    def _build_doc_from_content():
        return Document(content=data), DataInputType.CONTENT

    if data_type == DataInputType.DICT:
        return (
            (Document(**data), DataInputType.DICT)
            if docarray_v2
            else (Document.from_dict(data), DataInputType.DICT)
        )
    if data_type == DataInputType.AUTO or data_type == DataInputType.DOCUMENT:
        if isinstance(data, Document):
            # if incoming is already primitive type Document, then all good, best practice!
            return data, DataInputType.DOCUMENT
        elif isinstance(data, dict):
            return (
                (Document(**data), DataInputType.DICT)
                if docarray_v2
                else (Document.from_dict(data), DataInputType.DICT)
            )
        else:
            try:
                d = Document(data)
                return d, DataInputType.DOCUMENT  # NOT HIT
            except ValueError:
                # AUTO has a fallback, now reconsider it as content
                if data_type == DataInputType.AUTO:
                    return _build_doc_from_content()
                else:
                    raise

    elif data_type == DataInputType.CONTENT:
        return _build_doc_from_content()


def _add_docs(req: DataRequest, batch, data_type: DataInputType) -> None:
    if not docarray_v2:
        da = DocumentArray([])
    else:
        if len(batch) > 0:
            da = DocList[batch[0].__class__]()
        else:
            da = DocList[BaseDoc]()

    for content in batch:
        d, data_type = _new_doc_from_data(content, data_type)
        da.append(d)
    req.document_array_cls = da.__class__
    req.direct_docs = da
    #req.data.docs = da
