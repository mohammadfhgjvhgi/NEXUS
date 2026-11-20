"""Phase-11 live proof — runs ON the real Windows box (via the t1 bridge).

Proves the §12 surface against the operator's real machine:

* **§12.1** — real captures: a real window (PrintWindow with
  DWM bounds), the full screen, and a region — PNGs on disk with
  honest sizes, all through the §8.2 router;
* **§12.2** — the provider contract on this box: the §5.7 router
  asked for a vision-capable model (or the honest no-model
  refusal), the parsers proven on the real capture bytes;
* **§12.5** — **the device decision run**: the §12.5 benchmark —
  GDI-drawn corpus (English · numbers · UI labels · documents),
  every candidate engine that exists on this box in the race
  (winrt · tesseract · model), CER scoring, the strict winner
  policy, the JSON verdict in ``proofs\\phase11_ocr_benchmark.json``
  — this run IS the OCR engine decision the plan demands;
* **§9.5** — the vision rung on the live chain: locate → the
  router dispatch recorded (a fake provider rides the chain to
  prove the wiring without moving the real mouse).

Run:  python -X utf8 tests\\phase11\\live_proof_device.py   (from M:\\NEXUS)
Writes: proofs\\phase11_live.json · phase11_capture_full.png ·
        phase11_capture_window.png · phase11_capture_region.png ·
        phase11_ocr_benchmark.json
"""

from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

sys.path.insert(0, r"M:\NEXUS")

print("python:", sys.version.split()[0], "| platform:", sys.platform)
PROOFS = Path(r"M:\NEXUS\proofs")
PROOFS.mkdir(parents=True, exist_ok=True)
report: dict = {
    "python": sys.version.split()[0],
    "machine": f"{platform.node()} · {platform.system()} {platform.release()}",
}
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    mark = "PASS" if ok else "FAIL"
    print(f"  [{mark}] {name}" + (f" — {detail}" if detail and not ok else ""))
    report[name] = {"ok": bool(ok), "detail": detail[:200]}
    if not ok:
        failures.append(name)
    return ok


from nexus.events import EventBus  # noqa: E402
from nexus.tools import build_tool_system  # noqa: E402
from nexus.vision.capture import (  # noqa: E402
    Win32Gdi,
    capture_available,
    png_dimensions,
)
from nexus.vision.ocr import (  # noqa: E402
    ModelOcrEngine,
    TesseractOcrEngine,
    WinrtOcrEngine,
)
from nexus.vision.provider import (  # noqa: E402
    ModelVisionProvider,
    parse_locate,
)

bus = EventBus()
_registry, router, _adapter, _build = build_tool_system(
    native=True, computer=True, browser=False, vision=True, mcp_servers=(), bus=bus
)

WORK = PROOFS / "phase11-work"
WORK.mkdir(parents=True, exist_ok=True)


def call(op: str, **arguments: object):
    outcome = router.route("vision", {"op": op, **arguments}, task_id="phase11-live")
    print(
        f"  {op:<10} ok={outcome.ok} {str(outcome.output)[:70]}"
    )
    return outcome


# ---- §12.1: the three capture modes, for real ----------------------------
ok, reason = capture_available()
check("capture available on the device (GDI)", ok, reason)

full = call("capture", mode="full", path=str(PROOFS / "phase11_capture_full.png"))
full_path = PROOFS / "phase11_capture_full.png"
check(
    "full-screen capture through the router",
    full.ok and full_path.is_file() and full_path.stat().st_size > 1000,
    str(getattr(full, "error", "")),
)
if full_path.is_file():
    w, h = png_dimensions(full_path.read_bytes())
    report["capture_full"] = {"ok": True, "size": f"{w}x{h}", "bytes": full_path.stat().st_size}
    print(f"    full: {w}x{h}, {full_path.stat().st_size} bytes")

# a real window: the foreground window (whatever the operator has)
user32 = Win32Gdi()
import ctypes  # noqa: E402

hwnd = ctypes.windll.user32.GetForegroundWindow()  # type: ignore[attr-defined]
window = call(
    "capture", mode="window", hwnd=int(hwnd),
    path=str(PROOFS / "phase11_capture_window.png"),
)
window_path = PROOFS / "phase11_capture_window.png"
check(
    "window capture (PrintWindow/DWM) through the router",
    window.ok and window_path.is_file() and window_path.stat().st_size > 1000,
    str(getattr(window, "error", "")),
)
if window_path.is_file():
    w, h = png_dimensions(window_path.read_bytes())
    bounds = user32.window_bounds(int(hwnd))
    report["capture_window"] = {
        "ok": True, "hwnd": int(hwnd),
        "size": f"{w}x{h}", "dwm_bounds": bounds,
    }
    print(f"    window: {w}x{h} @ DWM bounds {bounds}")

# a region: the center quarter of the screen
region = call(
    "capture", mode="region", x=200, y=150, w=400, h=250,
    path=str(PROOFS / "phase11_capture_region.png"),
)
region_path = PROOFS / "phase11_capture_region.png"
check(
    "region capture (clamped) through the router",
    region.ok and region_path.is_file(),
    str(getattr(region, "error", "")),
)

# ---- §12.5: THE DEVICE DECISION RUN --------------------------------------
from nexus.vision.benchmark import (  # noqa: E402
    build_corpus,
    render_corpus,
    run_benchmark,
    save_report,
)

cases = build_corpus()
rendered = render_corpus(cases)
check(
    "the §12.5 corpus rendered by the OS (GDI DrawTextW)",
    rendered == len(cases),
    f"rendered {rendered}/{len(cases)}",
)

engines = [WinrtOcrEngine(), TesseractOcrEngine()]
provider = ModelVisionProvider(None)  # honest stub unless a manager is wired
try:
    from nexus.core.config.runtime import NexusRuntime  # noqa: F401

    wired = True
except Exception:
    wired = False
model_engine = ModelOcrEngine(provider)
ok_m, _reason_m = model_engine.available()
if ok_m:
    engines.append(model_engine)
benchmark = run_benchmark(engines, cases)
bench_path = save_report(benchmark, PROOFS / "phase11_ocr_benchmark.json")
report["ocr_benchmark"] = {
    "engines": [score.engine for score in benchmark.scores],
    "winner": benchmark.winner,
    "decided": benchmark.decided,
    "reason": benchmark.reason,
    "scores": [
        {
            "engine": score.engine,
            "mean_cer": score.mean_cer,
            "per_category": score.per_category,
            "total_seconds": score.total_seconds,
        }
        for score in benchmark.scores
    ],
}
check(
    "the §12.5 benchmark raced ≥2 engines on the device",
    len(benchmark.scores) >= 2,
    f"engines={[s.engine for s in benchmark.scores]}",
)
check(
    "the benchmark verdict is recorded (decided or honestly not)",
    benchmark.decided or "no contest" in benchmark.reason or "cannot read" in benchmark.reason,
    benchmark.reason,
)
for score in benchmark.scores:
    print(
        f"    {score.engine:<10} mean CER {score.mean_cer} · "
        f"{score.cases} cases · {score.total_seconds}s · {score.per_category}"
    )

# ---- §12.2: the provider contract on this box ----------------------------
ok_p, reason_p = ModelVisionProvider(None).available()
report["provider_probe"] = {"ok": ok_p, "reason": reason_p}
print(f"  provider (no live manager wired): ok={ok_p} — {reason_p}")
element = parse_locate(
    "Thought: found it\nAction: click(start_box='(197,525)')", "target"
)
check(
    "the §12.2 parsers hold on the device (UI-TARS tolerance)",
    element is not None and element.center() == (197, 525),
)

# ---- §12.5: one real ocr op through the router ---------------------------
ocr_target = PROOFS / "phase11_capture_region.png"
if not ocr_target.is_file():
    ocr_target = full_path
ocr_out = call("ocr", path=str(ocr_target))
check(
    "a real ocr op through the §8.2 router",
    ocr_out.ok and "text" in ocr_out.artifacts,
    str(getattr(ocr_out, "error", "")),
)
if ocr_out.ok:
    report["ocr_route"] = {
        "ok": True,
        "engine": str(ocr_out.artifacts.get("ocr", {}).get("engine", "?")),
        "words": str(ocr_out.artifacts.get("ocr", {}).get("words", 0)),
    }

# ---- §9.5: the vision rung on the live chain ------------------------------
from nexus.computer.hierarchy import ActionTarget, HierarchyChain  # noqa: E402
from nexus.vision.layer import VisionLayer  # noqa: E402


class _ProofProvider:
    """A deterministic provider — proves the rung WITHOUT moving the mouse."""

    name = "proof"

    def available(self) -> tuple[bool, str]:
        return True, "proof provider (device wiring check)"

    def analyze(self, image: bytes, question: str):
        from nexus.vision.models import VisionReport

        return VisionReport(description="proof window", confidence=1.0)

    def locate(self, image: bytes, description: str):
        from nexus.vision.models import LocatedElement

        return LocatedElement(description=description, x=10, y=10, width=20, height=20)

    def classify(self, image: bytes, categories):
        from nexus.vision.models import Classification

        return Classification(category=str(categories[0]), confidence=1.0)

    def compare(self, image_a: bytes, image_b: bytes):
        from nexus.vision.models import ComparisonReport

        return ComparisonReport(same=True, similarity=1.0)


class _ProofComputer:
    """Records input dispatch — the §9.5 hand-off, provable safely."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def mouse(self, op: str, **extra):
        self.calls.append(("mouse", {"op": op, **extra}))

        class _O:
            ok = True
            output = "proof"

        return _O()

    def keyboard(self, op: str, **extra):
        self.calls.append(("keyboard", {"op": op, **extra}))

        class _O:
            ok = True
            output = "proof"

        return _O()


proof_computer = _ProofComputer()
chain = HierarchyChain()
chain.register(VisionLayer(proof_computer, _ProofProvider(), capture=Win32Gdi()))
try:
    result = chain.act(ActionTarget(action="click", name="the proof button"))
    handed_off = proof_computer.calls == [
        ("mouse", {"op": "click", "x": 20, "y": 20}),
    ]
    check(
        "the §9.5 vision rung hands off to real input (locate → click)",
        result.layer == "vision" and handed_off,
        f"calls={proof_computer.calls}",
    )
except Exception as exc:  # noqa: BLE001 — a crash is a failed proof
    check("the §9.5 vision rung hands off to real input", False, str(exc))

# ---- verdict ---------------------------------------------------------------
out = PROOFS / "phase11_live.json"
out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
print()
print(f"report → {out}")
print("PROOF RESULT:", "PASS" if not failures else f"FAIL ({failures})")
sys.exit(0 if not failures else 1)
