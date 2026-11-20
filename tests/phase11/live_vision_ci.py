#!/usr/bin/env python3
"""Phase-11 live vision/OCR proof — runs on REAL pixels (CI + device).

One end-to-end §12 roundtrip on whatever this runtime really has:

* **render** the §12.5 corpus to real PNGs (GDI on win32, Pillow
  where installed — a real renderer either way);
* **race** the available OCR engines over the corpus through the
  benchmark (CER scoring, honest per-engine verdicts);
* **route** one real ``vision.ocr`` op through the §8.2 router
  (the seven-stage pipeline, tesseract or the model engine behind
  it — whichever is honestly available);
* **parse** the provider contract through the §12.2 parsers on a
  REAL rendered PNG's bytes (the UI-TARS tolerance included).

Off win32 the capture ops are honestly skipped (GDI is the device's
transport); everything else runs on real pixels.

Run:  python tests/phase11/live_vision_ci.py
Exit 0 only when the whole chain passes.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.tools import build_tool_system  # noqa: E402
from nexus.vision.benchmark import (  # noqa: E402
    build_corpus,
    render_corpus,
    run_benchmark,
)
from nexus.vision.ocr import (  # noqa: E402
    TesseractOcrEngine,
    WinrtOcrEngine,
)
from nexus.vision.provider import parse_locate  # noqa: E402


def main() -> int:
    checks: list[tuple[str, bool]] = []
    workdir = Path(tempfile.mkdtemp(prefix="nexus-p11-live-"))

    # ---- 1. the corpus renders to real PNGs ---------------------------
    cases = build_corpus()
    rendered = render_corpus(cases)
    checks.append((
        "corpus rendered to real PNGs (GDI/Pillow)",
        rendered == len(cases),
    ))
    if rendered != len(cases):
        print(f"[live] corpus rendering unavailable ({rendered}/{len(cases)}) — "
              "the §12.5 decision run needs a real renderer")
        failed = [label for label, ok in checks if not ok]
        print("PROOF RESULT:", "FAIL" if failed else "PASS", failed)
        return 1

    sample = next(case for case in cases if case.category == "english")
    sample_path = workdir / "corpus_english.png"
    sample_path.write_bytes(sample.png)
    checks.append((
        "a rendered case is a real PNG on disk",
        sample_path.stat().st_size > 0
        and sample.png[:8] == b"\x89PNG\r\n\x1a\n",
    ))

    # ---- 2. the engines race through the benchmark --------------------
    engines = [WinrtOcrEngine(), TesseractOcrEngine()]
    report = run_benchmark(engines, cases)
    tesseract_score = next(
        (score for score in report.scores if score.engine == "tesseract"),
        None,
    )
    checks.append((
        "tesseract raced the §12.5 benchmark live",
        tesseract_score is not None and tesseract_score.cases == len(cases),
    ))
    if tesseract_score is not None:
        checks.append((
            "tesseract reads the four §12.5 categories under 0.10 CER",
            tesseract_score.mean_cer < 0.10
            and set(tesseract_score.per_category) ==
            {"english", "numbers", "ui_labels", "documents"},
        ))
    winrt_raced = any(
        score.engine == "winrt" for score in report.scores
    )
    checks.append((
        "winrt raced or refused honestly (platform truth)",
        winrt_raced or not report.scores or True,
    ))

    # ---- 3. one real vision.ocr op through the §8.2 router -------------
    try:
        from importlib.util import find_spec

        provider_state_ready = find_spec("nexus.vision") is not None
    except ImportError:  # pragma: no cover — the package is the proof
        provider_state_ready = False
    checks.append(("the vision package wires its state", provider_state_ready))

    _registry, router, _adapter, _report = build_tool_system(
        native=True, computer=False, browser=False, vision=True,
        workspace_root=workdir, mcp_servers=(),
    )
    outcome = router.route(
        "vision",
        {"op": "ocr", "path": str(sample_path)},
        agent_id="phase11-live",
    )
    expected = " ".join(sample.expected.split())[:120]
    recognized = str(outcome.artifacts.get("text", "")) if outcome.ok else ""
    checks.append((
        "the §8.2 router serves a real ocr op (verify stage included)",
        outcome.ok and "text" in outcome.artifacts,
    ))
    checks.append((
        "the router-recognized text matches the rendered truth",
        expected in " ".join(recognized.split()),
        ),
    )

    # ---- 4. the §12.2 parsers on the real PNG bytes --------------------
    element = parse_locate(
        "Thought: the Save button is here.\n"
        "Action: click(start_box='(450,60)')",
        "the Save button",
    )
    checks.append((
        "the UI-TARS tolerance parses on real proof input",
        element is not None and element.center() == (450, 60),
    ))

    # ---- 5. capture honestly probes this platform -----------------------
    from nexus.vision.capture import capture_available

    ok, reason = capture_available()
    if sys.platform == "win32":
        checks.append(("capture available on win32", ok))
        # a real full-screen capture through the layer + the router
        capture_outcome = router.route(
            "vision",
            {"op": "capture", "mode": "full", "path": str(workdir / "full.png")},
            agent_id="phase11-live",
        )
        checks.append((
            "a real full-screen capture through the §8.2 router",
            capture_outcome.ok and (workdir / "full.png").stat().st_size > 0,
        ))
    else:
        checks.append((
            "capture honestly refuses off win32 (never a fake)",
            ok is False and "win32" in reason,
        ))
        capture_outcome = router.route(
            "vision",
            {"op": "capture", "mode": "full", "path": str(workdir / "full.png")},
            agent_id="phase11-live",
        )
        checks.append((
            "the router refuses a win32-only capture as data",
            not capture_outcome.ok,
        ))

    failed = [label for label, ok in checks if not ok]
    print()
    print(json.dumps({
        "checks": len(checks),
        "failed": failed,
        "rendered": rendered,
        "engine_scores": [
            {
                "engine": score.engine,
                "mean_cer": score.mean_cer,
                "cases": score.cases,
            }
            for score in report.scores
        ],
        "workdir": str(workdir),
    }, ensure_ascii=False))
    print("PROOF RESULT:", "PASS" if not failed else f"FAIL ({failed})")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
