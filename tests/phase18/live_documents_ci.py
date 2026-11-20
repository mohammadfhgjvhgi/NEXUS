#!/usr/bin/env python3
"""Phase 18 live proof — real documents, real files, real index (CI-safe).

What this proves, on a real machine, with real files on disk:

1. §18.3 docx — a real DOCX is created, saved, re-read and verified;
2. §18.3 docx — edit + format verbs on a real file, verified;
3. §18.4 pptx — three slides + a real PNG, sources extracted, verified;
4. §18.5 pdf — a real two-page PDF read, searched, extracted,
   summarized and analyzed;
5. §18.2 pipeline — DOCX + PDF ingested into a real file-backed SQLite
   index; the index answers *where* a word lives; the handle closes
   (the Windows law);
6. §18.1 docling — the availability probe tells the truth: absent →
   the adapter refuses honestly; present → a real parse through the
   NEXUS contract;
7. §18.2 memory — documents remembered into §12 with provenance,
   recalled with sources; the engine closes.

Exit code 0 only if every rung held.  No secrets, no network.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fixtures import PDF_PAGE_1, PDF_PAGE_2, PNG_1X1, write_pdf  # noqa: E402

from nexus.documents import (  # noqa: E402
    BackendUnavailableError,
    DoclingParseBackend,
    DocumentEngine,
    DocumentSource,
)
from nexus.memory import MemoryEngine, MemoryType, SQLiteMemoryStore  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def record(label: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((label, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))


def rung_1_docx_roundtrip(tmp: Path) -> None:
    from nexus.documents import docx_verify

    doc = DocumentEngine.docx_create()
    doc.add_heading("NEXUS Document Intelligence", level=1)
    doc.add_paragraph("Documents become real runtime objects.")
    doc.add_table([["surface", "status"], ["docx", "green"]])
    path = doc.save(tmp / "live.docx")
    back = DocumentEngine.docx_read(path)
    verdict = docx_verify(path, expect_text="runtime objects")
    ok = (
        [p.text for p in back.paragraphs] == [
            "NEXUS Document Intelligence",
            "Documents become real runtime objects.",
        ]
        and back.tables[0].rows == [["surface", "status"], ["docx", "green"]]
        and verdict.ok
    )
    record("18.3 docx: create → save → read → verify roundtrip", ok,
           f"paragraphs={len(back.paragraphs)} verify={verdict.ok}")


def rung_2_docx_edit_format(tmp: Path) -> None:
    from nexus.documents import docx_verify

    doc = DocumentEngine.docx_create()
    doc.add_paragraph("original text")
    doc.set_text(0, "edited text")
    doc.format_paragraph(0, bold=True, alignment="center", size_pt=14)
    doc.add_heading("Section", level=2)
    doc.delete_paragraph(-1)  # the heading goes away again
    path = doc.save(tmp / "edit.docx")
    back = DocumentEngine.docx_read(path)
    run = back.paragraphs[0].runs[0]
    ok = (
        back.paragraphs[0].text == "edited text"
        and run.bold and run.size_pt == 14.0
        and back.paragraphs[0].alignment == "center"
        and len(back.paragraphs) == 1
        and docx_verify(path).ok
    )
    record("18.3 docx: edit + format verbs hold on disk", ok,
           f"text={back.paragraphs[0].text!r} bold={run.bold} size={run.size_pt}")


def rung_3_pptx_full(tmp: Path) -> None:
    pres = DocumentEngine.pptx_create()
    pres.add_slide("NEXUS Documents", ["docx pptx pdf", "stdlib floor"])
    pres.add_slide("Pipeline", ["parse structure extract", "index memory"])
    pres.add_image(1, PNG_1X1)
    pres.add_slide("Proof", ["real files in, verified files out"])
    path = DocumentEngine.pptx_save(pres, tmp / "live.pptx")
    back = DocumentEngine.pptx_read(path)
    sources = DocumentEngine.pptx_sources(back)
    verdict = DocumentEngine.pptx_verify(
        path, expect_titles=[s["title"] for s in sources]
    )
    ok = (
        [s.title for s in back.slides] == ["NEXUS Documents", "Pipeline", "Proof"]
        and back.slides[1].image is not None
        and sources[2]["bullets"] == ["real files in, verified files out"]
        and verdict.ok
    )
    record("18.4 pptx: slides + image + sources + verify", ok,
           f"slides={len(back.slides)} image={back.slides[1].image is not None} "
           f"verify={verdict.ok}")


def rung_4_pdf_verbs(tmp: Path) -> None:
    pdf_path = tmp / "live.pdf"
    pdf_path.write_bytes(
        write_pdf([PDF_PAGE_1, PDF_PAGE_2], title="NEXUS PDF Fixture")
    )
    engine = DocumentEngine(use_docling=False)
    doc = engine.pdf_read(pdf_path)
    hits = engine.pdf_search(doc, "document")
    text = engine.pdf_extract(doc, page=2)
    summary = engine.pdf_summarize(doc, max_sentences=3)
    analysis = engine.pdf_analyze(doc)
    ok = (
        len(doc.pages) == 2
        and doc.metadata.get("Title") == "NEXUS PDF Fixture"
        and hits and hits[0]["page"] == 2
        and "provenance" in text
        and len(summary) == 3
        and analysis["pages"] == 2 and analysis["words"] > 30
    )
    record("18.5 pdf: read + search + extract + summarize + analyze", ok,
           f"pages={len(doc.pages)} hits={len(hits)} summary={len(summary)}")
    engine.close()


def rung_5_pipeline_index(tmp: Path) -> None:
    from nexus.documents import DocumentIndex
    from nexus.documents.docx import DocxDocument

    index_path = tmp / "index.db"
    engine = DocumentEngine(use_docling=False, index=None)
    # rebind the engine onto a file-backed index — a real database on disk
    engine.index = DocumentIndex(index_path)
    engine._pipeline._index = engine.index  # the engine owns its plumbing

    doc = DocxDocument()
    doc.add_heading("Index rung", level=1)
    doc.add_paragraph("the inverted index answers where a word lives")
    docx_path = doc.save(tmp / "idx.docx")
    report = engine.ingest(docx_path)
    hits = engine.index.search("inverted index")
    stats = engine.index.stats()
    ok = (
        report.index_id is not None
        and bool(hits) and hits[0]["locator"] == "paragraph 2"
        and stats["documents"] == 1 and stats["postings"] > 5
    )
    record("18.2 index: real SQLite on disk answers *where*", ok,
           f"doc_id={report.index_id} hit={hits[0]['locator'] if hits else 'none'} "
           f"postings={stats['postings']}")
    engine.index.close()
    engine._owns_index = False  # already closed — the engine must not re-close
    engine.close()


def rung_6_docling_probe() -> None:
    availability_ok = True
    detail = ""
    backend = DoclingParseBackend()
    from nexus.documents import docling_available

    availability = docling_available(refresh=True)
    if not availability.installed:
        try:
            backend.parse(DocumentSource(data=b"%PDF-1.4 probe", name="p.pdf"))
            availability_ok = False
            detail = "absent engine did not refuse"
        except BackendUnavailableError:
            availability_ok = True
            detail = f"honest absence — {availability.detail[:80]}"
    else:
        try:
            parsed = backend.parse(
                DocumentSource(data=b"%PDF-1.4 probe", name="p.pdf")
            )
            availability_ok = parsed.parser == "docling"
            detail = f"present v{availability.version} — parsed through the contract"
        except Exception as exc:  # noqa: BLE001 — the engine failed, recorded
            availability_ok = False
            detail = f"present v{availability.version} but failed: {exc}"[:110]
    record("18.1 docling: the availability probe tells the truth", availability_ok, detail)


def rung_7_memory_roundtrip(tmp: Path) -> None:
    memory = MemoryEngine(SQLiteMemoryStore(str(tmp / "mem.sqlite")))
    engine = DocumentEngine(use_docling=False, memory=memory)
    from fixtures import build_docx

    path = build_docx(tmp / "mem.docx")
    report = engine.ingest(path)
    rows = engine.recall("document runtime")
    fact = next((r for r in rows if r["type"] == MemoryType.FACT), None)
    ok = (
        report.memory_records == 2
        and fact is not None
        and bool(fact["sources"])
        and fact["sources"][0]["method"] == "document"
    )
    record("18.2 memory: documents remembered with provenance", ok,
           f"records={report.memory_records} sources={len(fact['sources']) if fact else 0}")
    memory.close()
    engine.close()


def main() -> int:
    print("=" * 66)
    print("PHASE 18 — Document Intelligence · live proof (real files)")
    print("=" * 66)
    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)
        rung_1_docx_roundtrip(tmp)
        rung_2_docx_edit_format(tmp)
        rung_3_pptx_full(tmp)
        rung_4_pdf_verbs(tmp)
        rung_5_pipeline_index(tmp)
        rung_6_docling_probe()
        rung_7_memory_roundtrip(tmp)
    print("-" * 66)
    failed = [r for r in RESULTS if not r[1]]
    print(f"LIVE PROOF: {len(RESULTS) - len(failed)}/{len(RESULTS)} rungs passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
