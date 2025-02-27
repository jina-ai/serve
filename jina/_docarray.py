try:
    from docarray import BaseDoc as Document
    from docarray import DocList as DocumentArray

    docarray_v2 = True

    from jina._docarray_legacy import LegacyDocumentJina

except ImportError:
    from docarray import Document, DocumentArray

    docarray_v2 = False


import pydantic

is_pydantic_v2 = pydantic.__version__.startswith('2.')

