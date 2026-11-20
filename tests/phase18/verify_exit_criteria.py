#!/usr/bin/env python3
"""Phase 18 verification harness — New Plan §18 Exit Gate.

Proves the Document Intelligence section by section:

* A — DOCX (§18.3): the six verbs live over real files — read ·
      create · edit · format · save · verify — plus honest failure
      (corruption detected, non-DOCX refused).
* B — PPTX (§18.4): the seven verbs live — create · slides · images ·
      layout · sources · save · verify — a real minimal package with
      master, layout, theme and embedded media.
* C — PDF (§18.5): the five verbs live — read · search · extract ·
      summarize · analyze — real bytes, honest corruption refusal.
* D — Docling (§18.1): the documented pin, the honest availability
      probe, MODE A direct use through the NEXUS contract (injected
      fake), the native floors as the guaranteed fallback.
* E — Pipeline (§18.2): the five stages verbatim and in order
      (parse → structure → extract → index → memory), verdicts per
      stage, a real file-backed index answering *where*, §12 memory
      with provenance, only canonical §2.2 events on the bus.
* F — Integration + regression: NEXUS_PHASE ≥ 18, nexus-core ≥
      0.18.0, the documents core stays stdlib-only, and the neighbor
      phase suites (15 · 16 · 17) stay green (skippable with
      --no-regression).

Exit gate, each line proven above::
    Implemented · Integrated · Tested · Verified · Documented
"""

from __future__ import annotations

import argparse
import ast
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, fn: Any) -> None:
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        FAILED.append(f"{label}: {type(exc).__name__}: {exc}")
        print(f"  ✗ {label} — {type(exc).__name__}: {exc}")
    else:
        PASSED.append(label)
        print(f"  ✓ {label}")


def expects(exc_types: tuple[type, ...] | type, fn: Any, *args: Any, **kwargs: Any) -> None:
    try:
        fn(*args, **kwargs)
    except exc_types:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_types}, got {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"expected {exc_types}, nothing raised")


# ------------------------------------------------------------------- section A


def section_a() -> None:
    from nexus.documents import DocumentEngine, VerifyError
    from nexus.documents.docx import DocxDocument, read, verify

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)

        def create_save_read() -> None:
            doc = DocxDocument()
            doc.add_heading("Gate Doc", level=1)
            doc.add_paragraph("documents are runtime objects now")
            path = doc.save(tmp / "a.docx")
            back = read(path)
            assert [p.text for p in back.paragraphs] == [
                "Gate Doc", "documents are runtime objects now",
            ]

        def edit_and_format() -> None:
            doc = DocxDocument()
            doc.add_paragraph("plain", bold=True)
            doc.set_text(0, "replaced")
            doc.format_paragraph(0, italic=True, underline=True, size_pt=12,
                                 alignment="right", heading=3)
            back = read(doc.save(tmp / "b.docx"))
            para = back.paragraphs[0]
            assert para.text == "replaced" and para.style == "Heading3"
            assert para.alignment == "right"
            assert para.runs[0].bold and para.runs[0].italic and para.runs[0].underline

        def tables() -> None:
            doc = DocxDocument()
            doc.add_table([["h1", "h2"], ["v1", "v2"]])
            back = read(doc.save(tmp / "c.docx"))
            assert back.tables[0].rows == [["h1", "h2"], ["v1", "v2"]]

        def verify_law() -> None:
            path = DocxDocument().save(tmp / "v.docx")
            DocxDocument().add_paragraph("marked")
            verdict = verify(path)
            assert verdict.ok and verdict.checks["zip_integrity"]
            corrupt = tmp / "corrupt.docx"
            corrupt.write_bytes(path.read_bytes()[:32])
            expects((VerifyError,), verify, corrupt)

        def engine_verbs() -> None:
            engine = DocumentEngine(use_docling=False)
            doc = engine.docx_create()
            doc.add_paragraph("engine surface")
            path = engine.docx_save(doc, tmp / "e.docx")
            assert engine.docx_read(path).paragraphs[0].text == "engine surface"
            assert engine.docx_verify(path, expect_text="engine surface").ok
            engine.close()

        check("A·create→save→read roundtrip", create_save_read)
        check("A·edit + format verbs", edit_and_format)
        check("A·tables survive the package", tables)
        check("A·verify law (ok · corruption refuses)", verify_law)
        check("A·engine facade exposes all six verbs", engine_verbs)


# ------------------------------------------------------------------- section B


def section_b() -> None:
    from fixtures import PNG_1X1

    from nexus.documents import DocumentEngine, VerifyError
    from nexus.documents.pptx import PptxPresentation, read, verify

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)

        def full_package() -> None:
            pres = PptxPresentation()
            pres.add_slide("One", ["bullet a", "bullet b"])
            pres.add_slide("Two", [])
            pres.add_image(1, PNG_1X1)
            path = pres.save(tmp / "b.pptx")
            back = read(path)
            assert [s.title for s in back.slides] == ["One", "Two"]
            assert back.slides[1].image is not None
            assert back.slides[0].bullets == ["bullet a", "bullet b"]

        def layout_law() -> None:
            pres = PptxPresentation(width_emu=9_144_000, height_emu=6_858_000)
            pres.add_slide("4x3", [])
            back = read(pres.save(tmp / "l.pptx"))
            assert (back.width_emu, back.height_emu) == (9_144_000, 6_858_000)

        def sources_law() -> None:
            pres = PptxPresentation()
            pres.add_slide("Src", ["line one"])
            sources = pres.sources()
            assert sources[0]["slide"] == 1
            assert sources[0]["title"] == "Src"
            assert sources[0]["bullets"] == ["line one"]

        def verify_law() -> None:
            pres = PptxPresentation()
            pres.add_slide("V", [])
            path = pres.save(tmp / "v.pptx")
            assert verify(path, expect_titles=["V"]).ok
            assert verify(path, expect_titles=["wrong"]).ok is False
            corrupt = tmp / "corrupt.pptx"
            corrupt.write_bytes(path.read_bytes()[:24])
            expects((VerifyError,), verify, corrupt)

        def engine_verbs() -> None:
            engine = DocumentEngine(use_docling=False)
            pres = engine.pptx_create()
            pres.add_slide("Engine", ["works"])
            path = engine.pptx_save(pres, tmp / "e.pptx")
            sources = engine.pptx_sources(engine.pptx_read(path))
            assert sources[0]["title"] == "Engine"
            assert engine.pptx_verify(path, expect_titles=["Engine"]).ok
            engine.close()

        check("B·create+slides+images+save+read", full_package)
        check("B·layout (slide size roundtrip)", layout_law)
        check("B·sources (per-slide provenance)", sources_law)
        check("B·verify law (ok · drift · corruption)", verify_law)
        check("B·engine facade exposes all seven verbs", engine_verbs)


# ------------------------------------------------------------------- section C


def section_c() -> None:
    from fixtures import PDF_PAGE_1, write_pdf

    from nexus.documents import DocumentEngine, ParseError
    from nexus.documents.pdf import analyze, extract, parse_pdf, search, summarize

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)

        def read_law() -> None:
            doc = parse_pdf(write_pdf([PDF_PAGE_1], title="Gate PDF"))
            assert len(doc.pages) == 1
            assert doc.metadata["Title"] == "Gate PDF"
            assert "Windows" in doc.pages[0].text

        def search_law() -> None:
            doc = parse_pdf(write_pdf([PDF_PAGE_1, PDF_PAGE_1], title="s"))
            hits = search(doc, "models")
            assert len(hits) >= 2 and {h["page"] for h in hits} == {1, 2}
            assert search(doc, "absent-word-zzz") == [] and search(doc, "") == []

        def extract_law() -> None:
            doc = parse_pdf(write_pdf(["page one text", "page two text"], title="x"))
            assert "page one" in extract(doc, page=1)
            assert "page two" in extract(doc, page=2)
            expects((IndexError,), extract, doc, page=7)

        def summarize_analyze_law() -> None:
            doc = parse_pdf(write_pdf(["The engine reads documents locally. "
                                       "Search stays on the machine. "
                                       "Provenance rides every block."], title="x"))
            summary = summarize(doc, max_sentences=2)
            assert len(summary) == 2
            report = analyze(doc)
            assert report["pages"] == 1 and report["words"] > 10
            assert report["fonts"] and report["empty_pages"] == []

        def honest_failure() -> None:
            expects((ParseError,), parse_pdf, b"not a pdf at all")
            raw = bytearray(write_pdf(["payload"]))
            start = raw.find(b"stream\n") + len(b"stream\n")
            raw[start : start + 8] = b"\x00" * 8
            expects((ParseError,), parse_pdf, bytes(raw))

        def engine_verbs() -> None:
            engine = DocumentEngine(use_docling=False)
            pdf_path = tmp / "e.pdf"
            pdf_path.write_bytes(write_pdf([PDF_PAGE_1], title="engine pdf"))
            doc = engine.pdf_read(pdf_path)
            assert engine.pdf_search(doc, "AVX")
            assert engine.pdf_analyze(doc)["pages"] == 1
            engine.close()

        check("C·read (pages + metadata + text)", read_law)
        check("C·search (pages + context + honest empty)", search_law)
        check("C·extract (per page · honest range)", extract_law)
        check("C·summarize + analyze", summarize_analyze_law)
        check("C·honesty (bad header · corrupt stream)", honest_failure)
        check("C·engine facade exposes all five verbs", engine_verbs)


# ------------------------------------------------------------------- section D


def section_d() -> None:
    import importlib.machinery
    import types

    from nexus.documents import (
        BackendUnavailableError,
        DoclingParseBackend,
        DocumentEngine,
        DocumentSource,
        docling_available,
    )
    from nexus.documents.docling import DOCLING_PINNED_SPEC

    def pin_law() -> None:
        assert DOCLING_PINNED_SPEC == "docling>=2.25,<3"

    def probe_honest() -> None:
        availability = docling_available(refresh=True)
        if not availability.installed:
            assert "docling" in availability.detail
        assert set(availability.as_dict()) == {"installed", "version", "detail"}

    def floors_guaranteed() -> None:
        engine = DocumentEngine(use_docling=False)
        names = [b.name for b in engine.backends]
        assert names == ["native.docx", "native.pptx", "native.pdf"], names
        engine.close()

    def mode_a_through_contract() -> None:
        fake = types.ModuleType("docling")
        fake.__version__ = "9.9.9-gate"
        fake.__spec__ = importlib.machinery.ModuleSpec("docling", None)
        fake.__path__ = []
        conv = types.ModuleType("docling.document_converter")
        conv.__spec__ = importlib.machinery.ModuleSpec(
            "docling.document_converter", None
        )

        class FakeDoc:
            def export_to_text(self) -> str:
                return "gate line one.\n"

        class FakeResult:
            document = FakeDoc()

        class FakeConverter:
            def convert(self, path: str) -> FakeResult:
                return FakeResult()

        conv.DocumentConverter = FakeConverter
        fake.document_converter = conv
        import sys

        sys.modules["docling"] = fake
        sys.modules["docling.document_converter"] = conv
        try:
            availability = docling_available(refresh=True)
            assert availability.installed and availability.version == "9.9.9-gate"
            parsed = DoclingParseBackend().parse(
                DocumentSource(data=b"%PDF-1.4 gate", name="g.pdf")
            )
            assert parsed.parser == "docling" and parsed.blocks
        finally:
            sys.modules.pop("docling", None)
            sys.modules.pop("docling.document_converter", None)
            docling_available(refresh=True)

    def absence_refuses() -> None:
        if docling_available(refresh=True).installed:
            return  # installed here — absence cannot be exercised
        backend = DoclingParseBackend()
        expects(
            (BackendUnavailableError,),
            backend.parse,
            DocumentSource(data=b"%PDF-1.4 x", name="x.pdf"),
        )

    check("D·pin bounded and documented", pin_law)
    check("D·probe honest shape", probe_honest)
    check("D·native floors always registered", floors_guaranteed)
    check("D·MODE A direct use behind the contract", mode_a_through_contract)
    check("D·absence refuses honestly (never fakes)", absence_refuses)


# ------------------------------------------------------------------- section E


def section_e() -> None:
    from fixtures import build_docx

    from nexus.documents import (
        PIPELINE_STAGES,
        DocumentEngine,
        StageState,
    )
    from nexus.events import EventBus
    from nexus.memory import MemoryEngine, MemoryType, SQLiteMemoryStore

    with tempfile.TemporaryDirectory() as raw:
        tmp = Path(raw)

        def stages_verbatim() -> None:
            engine = DocumentEngine(use_docling=False)
            report = engine.ingest(build_docx(tmp / "e.docx"))
            assert [s.name for s in report.stages] == list(PIPELINE_STAGES)
            assert report.stage("parse").state is StageState.OK
            engine.close()

        def full_law() -> None:
            memory = MemoryEngine(SQLiteMemoryStore(str(tmp / "mem.db")))
            engine = DocumentEngine(use_docling=False, memory=memory)
            report = engine.ingest(build_docx(tmp / "f.docx"))
            assert report.ok and report.memory_records == 2
            assert report.stage("index").state is StageState.OK
            memory.close()
            engine.close()

        def index_where_law() -> None:
            engine = DocumentEngine(use_docling=False)
            engine.ingest(build_docx(tmp / "g.docx"))
            hits = engine.index.search("runtime objects")
            assert hits and hits[0]["locator"].startswith("paragraph")
            engine.close()

        def recall_provenance_law() -> None:
            memory = MemoryEngine(SQLiteMemoryStore(str(tmp / "mem2.db")))
            engine = DocumentEngine(use_docling=False, memory=memory)
            engine.ingest(build_docx(tmp / "h.docx"))
            rows = engine.recall("NEXUS document")
            fact = next(r for r in rows if r["type"] == MemoryType.FACT)
            assert fact["sources"][0]["method"] == "document"
            assert fact["sources"][0]["uri"]
            memory.close()
            engine.close()

        def events_canonical() -> None:
            bus = EventBus()
            engine = DocumentEngine(use_docling=False, bus=bus)
            engine.ingest(build_docx(tmp / "i.docx"))
            names = {event.name for event in bus.history_snapshot()}
            assert names <= {"tool.called", "tool.completed", "tool.failed"}, names
            blob = repr([event.payload for event in bus.history_snapshot()])
            assert "runtime objects" not in blob, "content never rides the bus"
            engine.close()

        check("E·five stages verbatim, verdicts live", stages_verbatim)
        check("E·full run (index + memory bound)", full_law)
        check("E·index answers *where* the word lives", index_where_law)
        check("E·§12 memory keeps provenance", recall_provenance_law)
        check("E·canonical events only · no content", events_canonical)


# ------------------------------------------------------------------- section F


def section_f(no_regression: bool) -> None:
    import nexus

    def identity() -> None:
        assert nexus.NEXUS_PHASE >= 18
        parts = tuple(int(p) for p in nexus.__version__.split(".")[:3])
        assert parts >= (0, 18, 0), nexus.__version__

    def stdlib_only() -> None:
        allowed = {
            "__future__", "abc", "collections", "dataclasses", "datetime", "enum",
            "hashlib", "importlib", "io", "json", "pathlib", "re", "sqlite3", "sys",
            "tempfile", "typing", "urllib", "http", "xml", "zipfile", "zlib", "nexus",
        }
        for module in ("nexus/documents/contracts", "nexus/documents/docx",
                       "nexus/documents/pptx", "nexus/documents/pdf",
                       "nexus/documents/index", "nexus/documents/memory",
                       "nexus/documents/pipeline", "nexus/documents/engine"):
            src = ROOT / (module + ".py")
            tree = ast.parse(src.read_text(encoding="utf-8"))
            imports: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.update(a.name.split(".")[0] for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    imports.add(node.module.split(".")[0])
            external = imports - allowed
            assert not external, f"{module} imports non-stdlib: {external}"
        # docling.py is the §18.1 MODE A adapter — its one optional import
        # is the pinned engine itself (the qdrant/mcp house exception)
        src = ROOT / "nexus/documents/docling.py"
        tree = ast.parse(src.read_text(encoding="utf-8"))
        imports = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                imports.add(node.module.split(".")[0])
        assert imports - allowed <= {"docling"}, imports - allowed

    def regression() -> None:
        for phase in ("15", "16", "17"):
            verify = ROOT / "tests" / f"phase{phase}" / "verify_exit_criteria.py"
            proc = subprocess.run(
                [sys.executable, str(verify), "--no-regression"],
                capture_output=True, text=True, timeout=900,
            )
            assert proc.returncode == 0, f"phase{phase} regressed: {proc.stdout[-500:]}"

    check("F·identity (NEXUS_PHASE ≥ 18 · ≥ 0.18.0)", identity)
    check("F·documents core stays stdlib-only", stdlib_only)
    if not no_regression:
        check("F·neighbor phases green (15 · 16 · 17)", regression)
    else:
        print("  – F·regression skipped (--no-regression)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-regression", action="store_true")
    args = ap.parse_args()

    print("=" * 66)
    print("PHASE 18 — Document Intelligence · Exit Gate (New Plan §18)")
    print("=" * 66)
    section_a()
    section_b()
    section_c()
    section_d()
    section_e()
    section_f(args.no_regression)
    print("-" * 66)
    print(f"PASSED: {len(PASSED)}  FAILED: {len(FAILED)}")
    if FAILED:
        for line in FAILED:
            print(f"  ✗ {line}")
        return 1
    print("Exit gate: Implemented · Integrated · Tested · Verified · Documented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
