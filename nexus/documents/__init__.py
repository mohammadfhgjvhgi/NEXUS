"""Document Intelligence (New Plan §18) — real documents, real support.

Public surface, composed by section:

* §18.1 — :class:`DoclingParseBackend` + :func:`docling_available`
  (MODE A/B) behind the :class:`ParseBackend` contract, with the
  native stdlib floors :class:`DocxParseBackend` ·
  :class:`PptxParseBackend` · :class:`PdfParseBackend`;
* §18.2 — :class:`DocumentPipeline` (Document → Parse → Structure →
  Extract → Index → Memory, verbatim) over :class:`DocumentIndex`,
  bridged into §12 by :class:`DocumentMemory`, orchestrated by
  :class:`DocumentEngine`;
* §18.3 — :mod:`.docx` (read · create · edit · format · save · verify);
* §18.4 — :mod:`.pptx` (create · slides · images · layout · sources ·
  save · verify);
* §18.5 — :mod:`.pdf` (read · search · extract · summarize · analyze).

Stdlib only; docling is the optional MODE A extra.
"""

from .contracts import (
    DOCUMENT_KINDS,
    PIPELINE_STAGES,
    BackendUnavailableError,
    DocumentError,
    DocumentKind,
    DocumentSource,
    DocumentVerification,
    ImageRef,
    ParseBackend,
    ParsedDocument,
    ParseError,
    StageState,
    StageTrace,
    StructureNode,
    TextBlock,
    UnsupportedDocumentError,
    VerifyError,
    sha256_hex,
    sniff_kind,
    utc_now_iso,
)
from .docling import (
    DOCLING_PINNED_SPEC,
    DoclingAvailability,
    DoclingParseBackend,
    docling_available,
)
from .docx import (
    DocxDocument,
    DocxParagraph,
    DocxParseBackend,
    DocxRun,
    DocxTable,
)
from .docx import (
    read as docx_read,
)
from .docx import (
    verify as docx_verify,
)
from .engine import DocumentEngine
from .index import DocumentIndex
from .memory import DocumentMemory
from .pdf import (
    PdfDocument,
    PdfPage,
    PdfParseBackend,
    parse_pdf,
)
from .pdf import (
    analyze as pdf_analyze,
)
from .pdf import (
    extract as pdf_extract,
)
from .pdf import (
    search as pdf_search,
)
from .pdf import (
    summarize as pdf_summarize,
)
from .pipeline import DocumentPipeline, DocumentReport
from .pptx import (
    PptxImage,
    PptxParseBackend,
    PptxPresentation,
    PptxSlide,
)
from .pptx import (
    read as pptx_read,
)
from .pptx import (
    verify as pptx_verify,
)

__all__ = [
    # contracts
    "DOCUMENT_KINDS",
    "PIPELINE_STAGES",
    "BackendUnavailableError",
    "DocumentError",
    "DocumentKind",
    "DocumentSource",
    "DocumentVerification",
    "ImageRef",
    "ParseBackend",
    "ParseError",
    "ParsedDocument",
    "StageState",
    "StageTrace",
    "StructureNode",
    "TextBlock",
    "UnsupportedDocumentError",
    "VerifyError",
    "sha256_hex",
    "sniff_kind",
    "utc_now_iso",
    # §18.1
    "DOCLING_PINNED_SPEC",
    "DoclingAvailability",
    "DoclingParseBackend",
    "docling_available",
    "DocxParseBackend",
    "PptxParseBackend",
    "PdfParseBackend",
    # §18.2
    "DocumentPipeline",
    "DocumentReport",
    "DocumentIndex",
    "DocumentMemory",
    "DocumentEngine",
    # §18.3
    "DocxDocument",
    "DocxParagraph",
    "DocxRun",
    "DocxTable",
    "docx_read",
    "docx_verify",
    # §18.4
    "PptxPresentation",
    "PptxSlide",
    "PptxImage",
    "pptx_read",
    "pptx_verify",
    # §18.5
    "PdfDocument",
    "PdfPage",
    "parse_pdf",
    "pdf_search",
    "pdf_extract",
    "pdf_summarize",
    "pdf_analyze",
]
