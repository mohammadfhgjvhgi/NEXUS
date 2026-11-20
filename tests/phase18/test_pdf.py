"""Phase 18 · §18.5 PDF — read · search · extract · summarize · analyze."""

from __future__ import annotations

import pytest
from fixtures import PDF_PAGE_1, PDF_PAGE_2, write_pdf

from nexus.documents import (
    DocumentSource,
    ParseError,
    UnsupportedDocumentError,
)
from nexus.documents.pdf import (
    PdfParseBackend,
    analyze,
    extract,
    parse_pdf,
    search,
    summarize,
)

TWO_PAGES = [PDF_PAGE_1, PDF_PAGE_2]


def _doc() -> object:
    return parse_pdf(write_pdf(TWO_PAGES, title="NEXUS PDF Fixture"))


def test_read_pages_and_metadata() -> None:
    doc = _doc()
    assert len(doc.pages) == 2
    assert doc.metadata["Title"] == "NEXUS PDF Fixture"
    assert doc.metadata["Producer"] == "nexus-phase18-fixture"
    assert doc.fonts == ("F1",)


def test_read_rejects_non_pdf() -> None:
    with pytest.raises(ParseError):
        parse_pdf(b"definitely not a pdf")


def test_extract_all_text_roundtrip() -> None:
    doc = _doc()
    text = extract(doc)
    assert "i7-3770" in text
    assert "document intelligence" in text


def test_extract_single_page() -> None:
    doc = _doc()
    page_one = extract(doc, page=1)
    assert "Windows" in page_one and "provenance" not in page_one
    with pytest.raises(IndexError):
        extract(doc, page=9)


def test_search_hits_with_pages_and_context() -> None:
    doc = _doc()
    hits = search(doc, "document")
    assert hits, "the word is on page 2"
    assert all(h["page"] == 2 for h in hits)
    assert all("context" in h and h["match"] == "document" for h in hits)


def test_search_honest_empty() -> None:
    doc = _doc()
    assert search(doc, "") == []
    assert search(doc, "zzz-not-there") == []


def test_search_counts_multiple_occurrences() -> None:
    doc = _doc()
    hits = search(doc, "local")
    assert len(hits) >= 2, "page 1 uses it twice"


def test_summarize_top_sentences_in_order() -> None:
    doc = _doc()
    summary = summarize(doc, max_sentences=3)
    assert len(summary) == 3
    positions = [doc.text.find(s) for s in summary]
    assert positions == sorted(positions), "summary keeps document order"


def test_summarize_respects_limit() -> None:
    doc = _doc()
    assert len(summarize(doc, max_sentences=1)) == 1
    full = summarize(doc, max_sentences=50)
    assert len(full) >= 4


def test_analyze_stats() -> None:
    report = analyze(_doc())
    assert report["pages"] == 2
    assert report["words"] > 30
    assert [p["page"] for p in report["per_page"]] == [1, 2]
    assert report["empty_pages"] == []
    assert report["fonts"] == ["F1"]


def test_corrupt_flate_stream_is_honest(tmp_path) -> None:
    raw = bytearray(write_pdf(["payload text here"]))
    # locate the stream payload and scramble it — the parser must refuse
    start = raw.find(b"stream\n") + len(b"stream\n")
    raw[start : start + 12] = b"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b"
    with pytest.raises(ParseError):
        parse_pdf(bytes(raw))


def test_backend_kind_law() -> None:
    with pytest.raises(UnsupportedDocumentError):
        PdfParseBackend().parse(DocumentSource(data=b"PK\x03\x04", name="x.docx"))


def test_backend_pages_are_locators() -> None:
    data = write_pdf(TWO_PAGES)
    parsed = PdfParseBackend().parse(DocumentSource(data=data, name="t.pdf"))
    assert parsed.parser == "native.pdf" and parsed.kind == "pdf"
    assert [b.locator for b in parsed.blocks] == ["page 1", "page 2"]
    assert [s.name for s in parsed.structure] == ["page 1", "page 2"]
