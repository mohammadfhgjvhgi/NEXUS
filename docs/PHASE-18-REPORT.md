# PHASE 18 — Document Intelligence · Delivery Report

> **Plan reference:** Final Build Plan v3 (New Plan §18) — 18.1 Docling ·
> 18.2 Pipeline · 18.3 DOCX · 18.4 PPTX · 18.5 PDF
> **Identity:** `nexus-core 0.18.0` · `NEXUS_PHASE = 18` · stdlib-only core
> **Status:** Implemented · Integrated · Tested · Verified · Documented

## 1. What was built

### §18.1 — Docling (MODE A/B)

`nexus/documents/docling.py` — `docling-project/docling` behind the
NEXUS `ParseBackend` contract:

* **MODE A (direct use)** — when docling is importable, the adapter
  converts through `DocumentConverter` directly;
* **MODE B (adapt)** — the NEXUS contract is the only surface the
  pipeline ever sees; the vendor type never leaks;
* **honest availability** — `docling_available()` probes the host and
  reports `(installed, version, detail)`; when absent the adapter
  raises `BackendUnavailableError` and the native floors take over;
* **one documented pin** — `docling>=2.25,<3` (house pinning law);
* **the Windows law kept** — conversion temp files are closed and
  removed in `finally` (WinError 32, learned on the real box).

### §18.2 — Pipeline

`nexus/documents/pipeline.py` + `index.py` + `memory.py`:

* `Document → Parse → Structure → Extract → Index → Memory` verbatim,
  a `StageTrace` verdict per stage (`ok · failed · skipped` — a skip
  is honest, never a silent pass);
* parse: the first serving backend wins; backend crashes are recorded
  as parse failures, never hidden;
* `DocumentIndex` — a real inverted SQLite index (`documents` ·
  `blocks` · `postings`) whose search answers *where* a word lives
  (`page 3`, `slide 2`, `paragraph 7`) with ranked hits and snippets;
  explicit `close()` and context-manager support;
* `DocumentMemory` — the §12 bridge: one FACT per document
  (`MemoryEvidence(method="document", uri, snippet)` riding it), one
  SUMMARY per ingest session, `recall` keeps sources.

### §18.3 — DOCX

`nexus/documents/docx.py` — the six verbs over real OOXML:
read · create · edit · format · save · verify. Minimal valid packages
(`[Content_Types].xml` + `_rels/.rels` + `word/document.xml`) that
Word/LibreOffice open; paragraphs, runs, Heading1–6, bold/italic/
underline, half-point sizes, four alignments, tables; namespace-
correct reading of Word-written files; verify re-opens the saved
package (zip integrity · main part · XML parse · text roundtrip) and
refuses corruption honestly.

### §18.4 — PPTX

`nexus/documents/pptx.py` — the seven verbs:
create · slides · images · layout · sources · save · verify. A real
minimal package (presentation + slide master + slide layout + theme +
slides + slide rels + media); embedded real images (magic-byte sniffed
png/jpeg/gif/bmp) with EMU placement; slide size round-trips; `sources()`
extracts per-slide text provenance; verify catches title drift and
corruption.

### §18.5 — PDF

`nexus/documents/pdf.py` — the five verbs:
read · search · extract · summarize · analyze. A stdlib object parser:
object scan, trailer `/Root` resolution, catalog → page tree walk,
content streams with FlateDecode (`zlib`), the show-text operators
(`Tj · TJ · ' · "`), literal-string escapes (nesting, octal, line
continuation), hex strings, cp1252 text. Case-insensitive search with
page numbers and ±40-char context; extractive summarization (word
frequency, document order preserved); analyze reports pages, words,
chars, per-page stats, fonts referenced, empty pages. **Honest
limitations:** CID/Type0 cmaps, encryption and XFA are refused, not
invented.

## 2. Evidence (no ✅ without proof)

| Check | Result |
|---|---|
| pytest (`tests/phase18/`) | **80/80** |
| Exit gate (`verify_exit_criteria.py`) | **29/29**, zero regression on 15·16·17 |
| ruff 0.16.6 (`nexus/` + `tests/phase18/`) | clean |
| pyright 1.1.411 (`nexus/documents/`) | 0 errors |
| Live proof (`live_documents_ci.py`) | **7/7 rungs** |
| CI | Phase 18 step + `documents-live` job |
| Identity | `0.18.0` / `NEXUS_PHASE=18` (`nexus/__init__.py`, `pyproject.toml`) |

## 3. Design decisions (the honest ones)

1. **The floor is always present.** docling is heavy (torch, models);
   the native stdlib backends guarantee every document flows. The
   capability matrix claims only what each backend proves.
2. **A skip is not a pass.** Unbound index/memory report `skipped`
   with a reason; `ok` means "nothing failed and the document was
   parsed" — optional stages were never promised, failed ones always
   count.
3. **Provenance everywhere.** Index hits carry locator + snippet;
   memory records carry `file://` URIs and evidence snippets; the
   events carry counts only.
4. **Sniff, don't trust.** Document kind comes from magic bytes and
   the OOXML main part, not from the extension; image formats are
   sniffed, never extension-guessed.
5. **The WinError-32 law.** Every temp file and SQLite handle is
   closed before cleanup — the phase-17 real-Windows lesson is now a
   design rule in this module.

## 4. Files

```
nexus/documents/
  __init__.py    exports — the §18 surface
  contracts.py   §18.2 stages · kinds · ParseBackend · ParsedDocument · verification
  docling.py     §18.1 MODE A/B adapter · pin · availability probe
  docx.py        §18.3 six verbs + DocxParseBackend
  pptx.py        §18.4 seven verbs + PptxParseBackend
  pdf.py         §18.5 five verbs + PdfParseBackend
  index.py       §18.2 inverted SQLite index (WinError-32-safe close)
  memory.py      §18.2 → §12 bridge (provenance rides every record)
  pipeline.py    §18.2 five-stage pipeline with StageTrace verdicts
  engine.py      the DocumentEngine facade
tests/phase18/
  fixtures.py        real DOCX/PPTX builders + a real minimal PDF writer
  test_contracts.py  vocab verbatim + honest shapes (10)
  test_docx.py       the six verbs (14)
  test_pptx.py       the seven verbs (13)
  test_pdf.py        the five verbs (13)
  test_docling.py    pin · probe · MODE A · honest absence (6)
  test_pipeline.py   stages · verdicts · canonical events (8)
  test_memory.py     §12 bridge with provenance (6)
  test_engine.py     the facade end-to-end (10)
  live_documents_ci.py   7 rungs, real files
  test_device_proof.py   device wrapper → proofs/phase18_live.json
  verify_exit_criteria.py  the §18 gate (29 checks)
```

## 5. Next

**PHASE 19 — Speech System** (19.1 Speech API · 19.2 sherpa-onnx
MODE A/B · 19.3 Benchmark · 19.4 Voice → NEXUS).
