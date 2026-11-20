"""Phase 18 · §18.1–§18.2 contracts — verbatim vocab + honest shapes."""

from __future__ import annotations

import pytest

from nexus.documents import (
    DOCUMENT_KINDS,
    PIPELINE_STAGES,
    DocumentError,
    DocumentKind,
    DocumentSource,
    StageState,
    StageTrace,
    sha256_hex,
    sniff_kind,
)
from nexus.documents.docx import DocxDocument


def test_pipeline_stages_verbatim() -> None:
    """§18.2 — Document → Parse → Structure → Extract → Index → Memory."""
    assert PIPELINE_STAGES == ("parse", "structure", "extract", "index", "memory")


def test_document_kinds_verbatim() -> None:
    assert DOCUMENT_KINDS == ("docx", "pptx", "pdf", "unknown")


def test_sniff_pdf_magic() -> None:
    assert sniff_kind(b"%PDF-1.7\n...") == DocumentKind.PDF


def test_sniff_zip_packages_by_main_part() -> None:
    docx = DocxDocument()
    docx.add_paragraph("kind probe")
    assert sniff_kind(docx.to_bytes()) == DocumentKind.DOCX


def test_sniff_unknown_is_honest() -> None:
    assert sniff_kind(b"not a document at all") == DocumentKind.UNKNOWN
    assert sniff_kind(b"") == DocumentKind.UNKNOWN


def test_source_requires_data() -> None:
    with pytest.raises(DocumentError):
        DocumentSource(data=b"")


def test_source_memory_uri_default() -> None:
    src = DocumentSource(data=b"%PDF-1.4 x", name="note.pdf")
    assert src.uri == "memory://note.pdf"
    assert src.kind == DocumentKind.PDF


def test_source_from_path(tmp_path) -> None:
    target = tmp_path / "real.docx"
    DocxDocument().add_paragraph("from path")
    DocxDocument().save(target)
    src = DocumentSource.from_path(target)
    assert src.uri.startswith("file://")
    assert src.kind == DocumentKind.DOCX


def test_stage_states_and_trace() -> None:
    assert [s.value for s in StageState] == ["pending", "ok", "failed", "skipped"]
    trace = StageTrace(name="parse", state=StageState.OK, detail="blocks=3")
    assert trace.as_dict() == {"name": "parse", "state": "ok", "detail": "blocks=3"}


def test_sha256_hex_deterministic() -> None:
    assert sha256_hex(b"nexus") == sha256_hex(b"nexus")
    assert sha256_hex(b"nexus") != sha256_hex(b"document")
    assert len(sha256_hex(b"nexus")) == 64
