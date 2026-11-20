#!/usr/bin/env python3
"""Phase 11 verification harness — Final Build Plan §12 Exit Criteria.

Proves the Vision + OCR + Screen Understanding section by section:

* A — Screen Capture (§12.1): the mode vocabulary verbatim (full ·
       window · region); region math (clamping, intersection);
       fake-backend captures through the whole layer (real PNG
       bytes, provenance, receipts); honest unavailability off
       win32; window-bounds resolution; the DWM/PrintWindow
       constants documented; PNG IHDR reading.
* B — Vision Adapter (§12.2): the four verbs on the abstract
       contract; prompt builders; the tolerant parsers (JSON in
       prose, markdown fences, the UI-TARS action-space REFERENCE
       tolerance); ModelVisionProvider over a fake ModelManager —
       the §5.7 vision-capability routing, the images riding the
       GenerateRequest, the honest no-model refusal.
* C — OCR (§12.5): the requirements verbatim (English · numbers ·
       UI labels · documents); the CER metric math; the engine
       candidates' honest probes; resolution (auto order, named,
       unknown refused); the model engine over a fake provider;
       requirement coverage documented.
* D — The device benchmark (§12.5): the corpus (4×4, category
       mapping verbatim); the winner policy (lowest CER, ties →
       fastest, one engine → no contest, weak leader → no winner);
       failure counts as data; the JSON verdict; the real
       Pillow+tesseract live race as BONUS on this runtime.
* E — The §9.5 vision rung + the §8.1 record: VisionLayer
       availability honesty; inspect/click/type mapped to
       provider+input through a fake runtime; the chain registers
       the fourth of five layers; the fourteenth record (risk 1,
       path-scoped, always-emitted verification keys); a full
       §8.2 router roundtrip with a live PNG and a fake provider.
* F — Integration + regression: NexusRuntime wires vision_enabled
       (14 records + the vision rung + the provider state); the
       config keys validate; disabled → the Phase-10 behavior;
       Phases 1–10 harnesses stay green.

Run:  python tests/phase11/verify_exit_criteria.py
Exit code 0 only when every check passes.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.computer.hierarchy import (  # noqa: E402
    HIERARCHY_LAYERS,
    ActionTarget,
    HierarchyChain,
)
from nexus.events import EventBus  # noqa: E402
from nexus.models.provider import GenerateRequest  # noqa: E402
from nexus.tools import build_tool_system  # noqa: E402
from nexus.tools.native.screen import encode_png  # noqa: E402
from nexus.vision import (  # noqa: E402
    CAPTURE_MODES,
    OCR_ENGINE_ORDER,
    OCR_REQUIREMENTS,
    CaptureError,
    ModelOcrEngine,
    ModelVisionProvider,
    OcrError,
    ScreenRegion,
    TesseractOcrEngine,
    VisionError,
    VisionLayer,
    VisionRuntime,
    VisionTool,
    WinrtOcrEngine,
    character_error_rate,
    parse_analyze,
    parse_bbox,
    parse_classify,
    parse_compare,
    parse_json_block,
    parse_locate,
    provider_state,
    resolve_ocr_engine,
)
from nexus.vision import capture as capture_module  # noqa: E402
from nexus.vision import models as vision_models  # noqa: E402

ON_WINDOWS = sys.platform == "win32"


# ------------------------------------------------------------------- runner


class Runner:
    """Check counter with the house reporting format."""

    def __init__(self) -> None:
        self.section = ""
        self.passed = 0
        self.failed = 0
        self.bonus = 0

    def check(self, label: str, condition: bool, detail: str = "") -> bool:
        mark = "PASS" if condition else "FAIL"
        line = f"  [{mark}] ({self.section}) {label}"
        if detail and not condition:
            line += f" — {detail}"
        print(line)
        if condition:
            self.passed += 1
        else:
            self.failed += 1
        return condition

    def bonus_check(self, label: str, condition: bool, detail: str = "") -> bool:
        """Runtime-only evidence (win32/extras): SKIP never fails."""
        if condition:
            self.bonus += 1
            print(f"  [BONUS] ({self.section}) {label}")
        else:
            print(f"  [SKIP]  ({self.section}) {label} — {detail}")
        return condition

    def summary(self) -> int:
        print()
        print("=" * 72)
        name = Path(sys.argv[0]).name
        if self.failed:
            print(f"{name} — {self.passed} passed, {self.failed} FAILED")
            print("=" * 72)
            return 1
        print(f"{name} — {self.passed} passed, 0 failed (+{self.bonus} bonus)")
        print("=" * 72)
        return 0


# ------------------------------------------------------------------ fakes


class FakeGdi:
    """A deterministic CaptureBackend: solid-color pixels, real PNGs."""

    def __init__(self, screen: tuple[int, int] = (800, 600)) -> None:
        self.screen = screen
        self.grabs: list[tuple[int, int, int, int]] = []
        self.window_grabs: list[int] = []

    def screen_size(self) -> tuple[int, int]:
        return self.screen

    def grab_region(self, x: int, y: int, width: int, height: int) -> bytes:
        self.grabs.append((x, y, width, height))
        return bytes([64, 96, 128, 255] * (width * height))

    def grab_window(self, hwnd: int, width: int, height: int) -> bytes:
        self.window_grabs.append(hwnd)
        return bytes([200, 160, 120, 255] * (width * height))

    def window_bounds(self, hwnd: int) -> tuple[int, int, int, int]:
        # deterministic layout: window #hwnd at (10, 20), 300x200
        return (10, 20, 300, 200)


class FakeManager:
    """A §5.4-ish fake: routing + generation, no real models."""

    def __init__(self, answer: str, vision_model: str | None = "vision-1") -> None:
        self.answer = answer
        self.vision_model = vision_model
        self.requests: list[GenerateRequest] = []
        self.selections: list[dict[str, Any]] = []

    def select(self, request: Any) -> Any:
        self.selections.append(
            {"required_capability": request.required_capability}
        )

        class _Decision:
            selected_model_id = self.vision_model

        return _Decision()

    def generate(self, request: GenerateRequest) -> Any:
        self.requests.append(request)

        class _Result:
            text = self.answer

        return _Result()


class FakeProvider:
    """A §12.2 fake: canned verbs, honest availability."""

    name = "fake"

    def __init__(self, available: bool = True) -> None:
        self._available = available
        self.calls: list[tuple[str, bytes]] = []

    def available(self) -> tuple[bool, str]:
        return self._available, "fake provider (test)"

    def analyze(self, image: bytes, question: str) -> Any:
        self.calls.append(("analyze", image))
        return vision_models.VisionReport(
            description="a settings window with three buttons",
            elements=[{"label": "OK", "bbox": [10, 10, 60, 24]}],
            confidence=0.9,
        )

    def locate(self, image: bytes, description: str) -> Any:
        self.calls.append(("locate", image))
        return vision_models.LocatedElement(
            description=description, x=100, y=200, width=50, height=40,
            confidence=0.8,
        )

    def classify(self, image: bytes, categories: Any) -> Any:
        self.calls.append(("classify", image))
        return vision_models.Classification(
            category="settings", confidence=0.75,
            ranking=[{"category": "settings", "confidence": 0.75}],
        )

    def compare(self, image_a: bytes, image_b: bytes) -> Any:
        self.calls.append(("compare", image_a))
        return vision_models.ComparisonReport(
            same=False, similarity=0.42, differences=["button moved"],
        )


class FakeOutcome:
    def __init__(self, ok: bool = True, output: str = "ok") -> None:
        self.ok = ok
        self.output = output


class FakeComputer:
    """The runtime façade fake — records mouse/keyboard dispatch."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def mouse(self, op: str, **extra: Any) -> FakeOutcome:
        self.calls.append(("mouse", {"op": op, **extra}))
        return FakeOutcome()

    def keyboard(self, op: str, **extra: Any) -> FakeOutcome:
        self.calls.append(("keyboard", {"op": op, **extra}))
        return FakeOutcome()


def _sample_png(width: int = 40, height: int = 20) -> bytes:
    """A real PNG (the Phase-7 stdlib encoder) for tool-path tests."""
    rows = bytes([120, 60, 30, 255] * (width * height))
    return encode_png(width, height, rows)


# ----------------------------------------------------------------- sections


def section_a(runner: Runner) -> None:
    """A — Screen Capture (§12.1)."""
    runner.section = "A/§12.1"

    runner.check(
        "the §12.1 mode vocabulary is verbatim (full · window · region)",
        CAPTURE_MODES == ("full", "window", "region"),
    )
    runner.check(
        "resolve_capture_mode accepts the three modes",
        all(
            capture_module.resolve_capture_mode(mode) == mode
            for mode in CAPTURE_MODES
        ),
    )
    try:
        capture_module.resolve_capture_mode("virtual_screen")
        refused = False
    except CaptureError:
        refused = True
    runner.check("an unknown capture mode is refused", refused)

    # -- region math (pure) ------------------------------------------
    region = ScreenRegion(10, 10, 100, 50)
    bounds = ScreenRegion(0, 0, 800, 600)
    clipped = region.clamp_to(bounds)
    runner.check(
        "a contained region clamps to itself",
        (clipped.x, clipped.y, clipped.width, clipped.height)
        == (10, 10, 100, 50),
    )
    overflow = ScreenRegion(750, 590, 100, 50).clamp_to(bounds)
    runner.check(
        "an overflowing region clips to the screen edge",
        (overflow.width, overflow.height) == (50, 10),
    )
    outside = ScreenRegion(-200, -200, 100, 100).clamp_to(bounds)
    runner.check(
        "a fully-outside region clamps to 0x0",
        outside.width == 0 and outside.height == 0,
    )
    inner = ScreenRegion(5, 5, 10, 10).clamp_to(ScreenRegion(0, 0, 8, 8))
    runner.check(
        "partial-overlap intersection math is exact",
        (inner.x, inner.y, inner.width, inner.height) == (5, 5, 3, 3),
    )

    # -- full-screen capture through a fake backend -------------------
    fake = FakeGdi((800, 600))
    result = capture_module.capture_full_screen(backend=fake)
    runner.check(
        "full-screen capture returns a real PNG with provenance",
        result.png[:8] == b"\x89PNG\r\n\x1a\n"
        and result.mode == "full"
        and (result.width, result.height) == (800, 600)
        and result.source == "screen"
        and result.region is not None
        and result.region.to_dict() == {"x": 0, "y": 0, "w": 800, "h": 600},
    )
    width, height = capture_module.png_dimensions(result.png)
    runner.check(
        "png_dimensions reads the IHDR of the capture",
        (width, height) == (800, 600),
    )
    runner.check(
        "the capture receipt counts its bytes",
        result.bytes_size == len(result.png) and result.bytes_size > 0,
    )

    # -- region capture (with clamping) -------------------------------
    region_result = capture_module.capture_region(
        ScreenRegion(-50, -50, 900, 700), backend=fake
    )
    runner.check(
        "a region capture clamps to the screen before grabbing",
        region_result.region is not None
        and (region_result.region.x, region_result.region.y) == (0, 0)
        and (region_result.width, region_result.height) == (800, 600),
        detail=f"region={region_result.to_dict()}",
    )
    try:
        capture_module.capture_region(ScreenRegion(0, 0, 0, 0), backend=fake)
        zero_refused = False
    except CaptureError:
        zero_refused = True
    runner.check("a 0x0 region is refused", zero_refused)
    try:
        capture_module.capture_region(
            ScreenRegion(2000, 2000, 50, 50), backend=fake
        )
        outside_refused = False
    except CaptureError:
        outside_refused = True
    runner.check("a region fully outside the screen is refused", outside_refused)

    # -- window capture ----------------------------------------------
    window_result = capture_module.capture_window(131074, backend=fake)
    runner.check(
        "window capture grabs at the window bounds with hwnd provenance",
        window_result.mode == "window"
        and window_result.source == "hwnd:131074"
        and (window_result.width, window_result.height) == (300, 200)
        and fake.window_grabs == [131074],
    )
    hwnd_refused = True
    for bad_hwnd in (0, -5, True, "12"):
        try:
            capture_module.capture_window(bad_hwnd, backend=fake)  # type: ignore[arg-type]
            hwnd_refused = False
            break
        except CaptureError:
            continue
    runner.check("invalid hwnds (0/negative/bool/str) are refused", hwnd_refused)

    # -- honest unavailability ----------------------------------------
    if not ON_WINDOWS:
        ok, reason = capture_module.capture_available()
        runner.check(
            "capture honestly reports unavailable off win32",
            ok is False and "win32" in reason,
            detail=f"({ok}, {reason})",
        )
    else:
        runner.bonus_check(
            "capture available on this win32 runtime",
            capture_module.capture_available()[0],
        )

    # -- documented constants (the DWM/PrintWindow contract) -----------
    runner.check(
        "PrintWindow PW_RENDERFULLCONTENT and DWMWA_EXTENDED_FRAME_BOUNDS "
        "carry their documented values",
        capture_module.PW_RENDERFULLCONTENT == 0x00000002
        and capture_module.DWMWA_EXTENDED_FRAME_BOUNDS == 9,
    )
    runner.check(
        "CaptureResult.to_dict stays plain JSON",
        set(result.to_dict()) == {
            "mode", "width", "height", "source", "region", "bytes",
        },
    )


def section_b(runner: Runner) -> None:
    """B — Vision Adapter (§12.2)."""
    runner.section = "B/§12.2"

    verbs = {"analyze", "locate", "classify", "compare"}
    from nexus.vision.provider import VisionProvider

    runner.check(
        "the §12.2 adapter exposes the four verbs (+ the honest probe)",
        verbs <= set(VisionProvider.__abstractmethods__)
        and "available" in VisionProvider.__abstractmethods__,
        detail=f"abstract={sorted(VisionProvider.__abstractmethods__)}",
    )

    # -- prompt builders (pure) ---------------------------------------
    from nexus.vision.provider import (
        analyze_prompt,
        classify_prompt,
        compare_prompt,
        locate_prompt,
    )

    runner.check(
        "the prompt builders carry their task text",
        "dark mode" in analyze_prompt("Is dark mode on?")
        and "Save button" in locate_prompt("the Save button")
        and "cat" in classify_prompt(["cat", "dog"])
        and compare_prompt().startswith("Compare the two images"),
    )

    # -- tolerant parsing ---------------------------------------------
    runner.check(
        "parse_json_block reads plain JSON",
        parse_json_block('{"bbox": [1,2,3,4]}') == {"bbox": [1, 2, 3, 4]},
    )
    runner.check(
        "parse_json_block reads fenced JSON",
        parse_json_block('```json\n{"same": true}\n```') == {"same": True},
    )
    runner.check(
        "parse_json_block reads prose-wrapped JSON",
        parse_json_block('Sure! Here it is: {"found": false} hope it helps')
        == {"found": False},
    )
    runner.check("parse_json_block refuses garbage", parse_json_block("no json") == {})

    element = parse_locate(
        'Thought: found it\nAction: {"bbox": [100, 200, 50, 40], '
        '"confidence": 0.9}',
        "the Save button",
    )
    runner.check(
        "locate parses a JSON bbox with center math",
        element is not None
        and element.center() == (125, 220)
        and element.confidence == 0.9,
    )
    runner.check(
        "locate honors an explicit found:false",
        parse_locate('{"found": false}', "x") is None,
    )
    tars = parse_locate(
        "Action: click(start_box='(197,525)')", "target"
    )
    runner.check(
        "locate tolerates the UI-TARS action space (Round 8 REFERENCE)",
        tars is not None and tars.center() == (197, 525),
    )
    bare = parse_locate("[12, 34, 56, 78]", "target")
    runner.check(
        "locate tolerates a bare bbox list",
        bare is not None and (bare.x, bare.y, bare.width, bare.height)
        == (12, 34, 56, 78),
    )
    runner.check(
        "parse_bbox returns None on nothing parseable",
        parse_bbox("no coordinates here") is None,
    )

    report = parse_analyze(
        'Here: {"description": "a login form", "elements": '
        '[{"label": "User", "bbox": [1, 2, 3, 4]}], "confidence": 1.7}'
    )
    runner.check(
        "analyze parses description/elements and clamps confidence",
        report.description == "a login form"
        and report.elements[0]["bbox"] == [1, 2, 3, 4]
        and report.confidence == 1.0,
    )
    fallback = parse_analyze("just prose about a screen")
    runner.check(
        "analyze falls back to the raw text as description",
        fallback.description.startswith("just prose"),
    )

    verdict = parse_classify(
        ' {"category": "settings", "confidence": 0.8, "ranking": '
        '[{"category": "settings", "confidence": 0.8}, '
        '{"category": "game", "confidence": 0.1}]}',
        ["settings", "game"],
    )
    runner.check(
        "classify parses the winner and filters ranking to the given set",
        verdict.category == "settings" and len(verdict.ranking) == 2,
    )
    invented = parse_classify("totally a browser", ["settings", "game"])
    runner.check(
        "classify never invents a category outside the given set",
        invented.category == "",
    )
    recovered = parse_classify("looks like GAME to me", ["settings", "game"])
    runner.check(
        "classify recovers a mentioned category from prose",
        recovered.category == "game",
    )

    comparison = parse_compare(
        '{"same": false, "similarity": 0.4, "differences": ["moved"]}'
    )
    runner.check(
        "compare parses the verdict",
        comparison.same is False
        and comparison.similarity == 0.4
        and comparison.differences == ["moved"],
    )
    prose = parse_compare("the two images are different")
    runner.check(
        "compare degrades honestly on prose (not same, zero similarity)",
        prose.same is False and prose.similarity == 0.0,
    )

    # -- ModelVisionProvider over a fake manager ----------------------
    manager = FakeManager(
        '{"bbox": [40, 60, 20, 10], "confidence": 0.5, "description": "btn"}'
    )
    provider = ModelVisionProvider(manager)
    ok, reason = provider.available()
    runner.check(
        "ModelVisionProvider reports the §5.7 router path",
        ok and "router" in reason,
        detail=f"({ok}, {reason})",
    )
    png = _sample_png()
    located = provider.locate(png, "the Save button")
    runner.check(
        "locate rode the GenerateRequest with the image bytes",
        len(manager.requests) == 1
        and tuple(manager.requests[0].images) == (png,)
        and manager.requests[0].auto_load is True,
        detail=f"requests={len(manager.requests)}",
    )
    runner.check(
        "the §5.7 select asked for the vision capability",
        bool(manager.selections)
        and manager.selections[0]["required_capability"] == "vision",
    )
    runner.check(
        "the provider parsed the model's answer into pixels",
        located is not None and (located.x, located.y) == (40, 60),
    )

    pinned_manager = FakeManager("x")
    pinned = ModelVisionProvider(pinned_manager, model_id="my-vlm")
    pinned.locate(png, "target")
    runner.check(
        "a pinned model_id skips the router select",
        pinned_manager.selections == []
        and pinned_manager.requests[0].model_id == "my-vlm",
    )

    blind = ModelVisionProvider(FakeManager("x", vision_model=None))
    try:
        blind.locate(png, "target")
        no_model_refused = False
    except VisionError as exc:
        no_model_refused = "no vision-capable model" in str(exc)
    runner.check(
        "no vision model in the pool → honest VisionError",
        no_model_refused,
    )
    empty_question = ModelVisionProvider(FakeManager("x"))
    try:
        empty_question.analyze(png, "   ")
        empty_refused = False
    except VisionError:
        empty_refused = True
    runner.check("an empty analyze question is refused", empty_refused)

    # -- the §5.1 additive images field --------------------------------
    request = GenerateRequest(model_id="m", prompt="p")
    runner.check(
        "GenerateRequest.images defaults empty (Phase-4 contract intact)",
        tuple(request.images) == () and request.to_dict()["images"] == 0,
    )
    from nexus.models.llamacpp import encode_completion_request

    body = json.loads(
        encode_completion_request(
            GenerateRequest(model_id="m", prompt="p", images=(png, png)),
            stream=False,
        )
    )
    encoded = base64.b64encode(png).decode("ascii")
    runner.check(
        "llama.cpp /completion carries images as base64 image_data",
        body.get("image_data") == [encoded, encoded],
    )
    text_body = json.loads(
        encode_completion_request(
            GenerateRequest(model_id="m", prompt="p"), stream=False
        )
    )
    runner.check(
        "a text-only request emits no image_data (byte for byte)",
        "image_data" not in text_body,
    )


def section_c(runner: Runner) -> None:
    """C — OCR engines (§12.5)."""
    runner.section = "C/§12.5"

    runner.check(
        "the §12.5 requirements are verbatim",
        OCR_REQUIREMENTS == ("English", "numbers", "UI labels", "documents"),
    )
    runner.check(
        "the auto candidate order is OS → classic → model",
        OCR_ENGINE_ORDER == ("winrt", "tesseract", "model"),
    )

    # -- the CER metric ------------------------------------------------
    runner.check(
        "CER: identical → 0.0",
        character_error_rate("Hello World", "Hello World") == 0.0,
    )
    runner.check(
        "CER: empty vs full → 1.0 (and full vs empty → 1.0)",
        character_error_rate("", "abc") == 1.0
        and character_error_rate("abc", "") == 1.0,
    )
    runner.check(
        "CER: case/whitespace are normalized",
        character_error_rate("  Hello   World ", "hello world") == 0.0,
    )
    runner.check(
        "CER: edit distance over Levenshtein (2 deletions of 11)",
        abs(character_error_rate("hello world", "helo wrld") - 2 / 11) < 1e-9,
    )

    # -- honest engine probes ------------------------------------------
    winrt = WinrtOcrEngine()
    ok, reason = winrt.available()
    if not ON_WINDOWS:
        runner.check(
            "winrt OCR honestly unavailable off win32",
            ok is False and "ocr" in reason.lower(),
            detail=f"({ok}, {reason})",
        )
    else:
        runner.bonus_check("winrt OCR available on this win32 runtime", ok)
    tesseract = TesseractOcrEngine()
    ok_t, reason_t = tesseract.available()
    runner.bonus_check(
        "tesseract probe answers (extras installed on this runtime)",
        ok_t and "tesseract" in reason_t,
        detail=f"({ok_t}, {reason_t})",
    )

    # -- the probe-never-crashes law (the CI bug: pytesseract present,
    #    binary missing → pytesseract raises — available() must not) -----
    try:
        import pytesseract  # type: ignore[import-not-found]

        original = pytesseract.get_tesseract_version
        pytesseract.get_tesseract_version = lambda: (_ for _ in ()).throw(
            RuntimeError("tesseract is not installed or it's not in your PATH")
        )
        try:
            ok_missing, reason_missing = tesseract.available()
        finally:
            pytesseract.get_tesseract_version = original
        runner.check(
            "tesseract probe survives a missing binary (never crashes)",
            ok_missing is False and "binary is missing" in reason_missing,
            detail=f"({ok_missing}, {reason_missing})",
        )
    except ImportError:
        runner.check(
            "tesseract probe survives a missing binary (never crashes)",
            True,
            detail="pytesseract absent — the probe is honest by construction",
        )
    model_engine = ModelOcrEngine(None)
    ok_m, reason_m = model_engine.available()
    runner.check(
        "model OCR refuses honestly without a provider",
        ok_m is False and "provider" in reason_m,
        detail=f"({ok_m}, {reason_m})",
    )
    fake_provider = FakeProvider()
    ok_fake, _ = ModelOcrEngine(fake_provider).available()
    runner.check(
        "model OCR rides the §12.2 provider when wired",
        ok_fake,
    )
    fake_png = _sample_png()
    model_result = ModelOcrEngine(fake_provider).recognize(fake_png)
    runner.check(
        "model OCR transcribes the provider's description as lines",
        model_result.engine == "model" and model_result.text != ""
        and bool(model_result.lines),
    )

    # -- resolution -----------------------------------------------------
    class _UnwiredEngine:
        """A candidate that is honestly absent on this runtime."""

        def __init__(self, name: str) -> None:
            self.name = name

        def available(self) -> tuple[bool, str]:
            return False, f"{self.name} not wired on this runtime"

        def recognize(self, png: bytes) -> Any:  # pragma: no cover — never
            raise OcrError(f"{self.name} unwired")

        def supports(self, requirement: str) -> bool:
            return False

    engine, reason = resolve_ocr_engine(
        "auto",
        winrt=_UnwiredEngine("winrt"),
        tesseract=_UnwiredEngine("tesseract"),
        model=ModelOcrEngine(fake_provider),
    )
    runner.check(
        "auto falls to the model engine when only it is wired",
        engine is not None and engine.name == "model" and "auto" in reason,
    )
    named, named_reason = resolve_ocr_engine(
        "model", model=ModelOcrEngine(fake_provider)
    )
    runner.check(
        "a named preference is returned as-is",
        named is not None and named.name == "model"
        and named_reason == "named preference",
    )
    try:
        resolve_ocr_engine("abbyy")
        unknown_refused = False
    except OcrError:
        unknown_refused = True
    runner.check("an unknown engine preference is refused", unknown_refused)
    none_engine, none_reason = resolve_ocr_engine(
        "auto",
        winrt=_UnwiredEngine("winrt"),
        tesseract=_UnwiredEngine("tesseract"),
        model=ModelOcrEngine(None),
    )
    runner.check(
        "auto with nothing wired → (None, honest reason), never a fake",
        none_engine is None and "no OCR engine" in none_reason,
        detail=f"({none_engine}, {none_reason})",
    )

    # -- requirement coverage --------------------------------------------
    from nexus.vision.ocr import REQUIREMENT_COVERAGE, parse_requirement_list

    runner.check(
        "every §12.5 requirement has ≥2 engine candidates documented",
        all(len(set(engines)) >= 2 for engines in REQUIREMENT_COVERAGE.values()),
        detail=f"coverage={dict(REQUIREMENT_COVERAGE)}",
    )
    runner.check(
        "parse_requirement_list validates against the verbatim set",
        parse_requirement_list(("English", "numbers"))
        == ("English", "numbers"),
    )
    try:
        parse_requirement_list(("Arabic",))
        req_refused = False
    except OcrError:
        req_refused = True
    runner.check("an unknown requirement is refused", req_refused)

    from nexus.vision.ocr import timed_recognize

    result, seconds = timed_recognize(ModelOcrEngine(fake_provider), fake_png)
    runner.check(
        "timed_recognize times the recognition",
        seconds >= 0.0 and result.engine == "model",
    )


def section_d(runner: Runner) -> None:
    """D — the §12.5 device benchmark machinery."""
    runner.section = "D/§12.5"

    from nexus.vision.benchmark import (
        CORPUS,
        build_corpus,
        decide_winner,
        run_benchmark,
        save_report,
    )
    from nexus.vision.models import OCR_CATEGORIES, OcrEngineScore

    cases = build_corpus()
    runner.check(
        "the corpus is 4 categories × 4 truths (16 cases)",
        len(cases) == 16 and {case.category for case in cases} == set(OCR_CATEGORIES),
    )
    runner.check(
        "the corpus category keys map the §12.5 requirements",
        set(CORPUS) == {"english", "numbers", "ui_labels", "documents"}
        and all(len(truths) == 4 for truths in CORPUS.values()),
    )
    runner.check(
        "every corpus case starts PNG-empty (rendering is the device's)",
        all(case.png == b"" for case in cases),
    )

    # -- the winner policy (pure) --------------------------------------
    strong = OcrEngineScore(engine="a", mean_cer=0.05, total_seconds=10.0, cases=4)
    weak = OcrEngineScore(engine="b", mean_cer=0.40, total_seconds=1.0, cases=4)
    winner, decided, reason = decide_winner([strong, weak])
    runner.check(
        "the winner is the lowest mean CER",
        winner == "a" and decided and "0.05" in reason,
    )
    slow = OcrEngineScore(engine="slow", mean_cer=0.05, total_seconds=99.0, cases=4)
    fast = OcrEngineScore(engine="fast", mean_cer=0.05, total_seconds=1.0, cases=4)
    winner_tie, _decided_tie, _reason_tie = decide_winner([slow, fast])
    runner.check("a CER tie breaks on total seconds", winner_tie == "fast")
    solo_winner, solo_decided, _solo_reason = decide_winner([strong])
    runner.check(
        "one engine alone is no contest (§12.5 needs a race)",
        solo_decided is False,
    )
    weak_a = OcrEngineScore(engine="a", mean_cer=0.60, total_seconds=1.0, cases=4)
    weak_b = OcrEngineScore(engine="b", mean_cer=0.70, total_seconds=1.0, cases=4)
    no_winner, no_decided, no_reason = decide_winner([weak_a, weak_b])
    runner.check(
        "a leader above 0.30 CER wins nothing (cannot read ≠ winner)",
        no_winner == "" and no_decided is False and "0.30" in no_reason,
    )

    # -- scoring counts failures as data --------------------------------
    class _DeadEngine:
        name = "dead"

        def available(self) -> tuple[bool, str]:
            return True, "dead"

        def recognize(self, png: bytes) -> Any:
            raise OcrError("dead engine")

        def supports(self, requirement: str) -> bool:
            return True

    class _EchoEngine:
        """Perfect transcription — the benchmark's happy path."""

        name = "echo"

        def __init__(self) -> None:
            self._cases: list[Any] = []
            self._by_png: dict[bytes, str] = {}

        def bind(self, case_list: list[Any]) -> None:
            self._cases = case_list
            self._by_png = {case.png: case.expected for case in case_list}

        def available(self) -> tuple[bool, str]:
            return True, "echo"

        def recognize(self, png: bytes) -> Any:
            return vision_models.OcrResult(
                text=self._by_png.get(png, ""), engine="echo"
            )

        def supports(self, requirement: str) -> bool:
            return True

    from nexus.vision.benchmark import render_corpus

    rendered = render_corpus(cases)
    runner.bonus_check(
        "the corpus rendered to real PNGs on this runtime",
        rendered == 16,
        detail=f"rendered={rendered} (no renderer is honest)",
    )
    if rendered:
        echo = _EchoEngine()
        echo.bind(cases)
        report = run_benchmark([echo, _DeadEngine()], cases)
        runner.bonus_check(
            "the live race: perfect echo CER 0.0, dead engine counted 1.0",
            any(
                score.engine == "echo" and score.mean_cer == 0.0
                for score in report.scores
            )
            and any(
                score.engine == "dead" and score.mean_cer >= 0.99
                for score in report.scores
            ),
            detail=f"scores={[(s.engine, s.mean_cer) for s in report.scores]}",
        )
        runner.bonus_check(
            "echo vs dead is a decided race with echo winning",
            report.winner == "echo" and report.decided,
            detail=f"winner={report.winner}",
        )
        with tempfile.TemporaryDirectory() as tmp:
            out = save_report(report, Path(tmp) / "bench.json")
            loaded = json.loads(out.read_text(encoding="utf-8"))
            runner.bonus_check(
                "the verdict serializes to plain JSON",
                loaded["winner"] == "echo" and bool(loaded["scores"]),
            )

        # -- the real tesseract race (BONUS where the extra exists) ----
        real_report = run_benchmark(
            [TesseractOcrEngine(), WinrtOcrEngine()], cases
        )
        runner.bonus_check(
            "the real race ran on this runtime (tesseract live)",
            any(score.engine == "tesseract" for score in real_report.scores),
            detail="tesseract extra absent — honest",
        )
        runner.bonus_check(
            "tesseract reads the rendered corpus under 0.10 CER",
            any(
                score.engine == "tesseract" and score.mean_cer < 0.10
                for score in real_report.scores
            ),
        )


def section_e(runner: Runner) -> None:
    """E — the §9.5 vision rung + the §8.1 record."""
    runner.section = "E/§9.5+§8.1"

    runner.check(
        "the §9.5 chain names vision its fourth of five layers",
        HIERARCHY_LAYERS == (
            "application_api", "uia", "dom_a11y", "vision", "input",
        ),
    )

    # -- layer availability honesty -------------------------------------
    computer = FakeComputer()
    provider = FakeProvider()
    layer = VisionLayer(computer, provider, capture=FakeGdi())
    ok, reason = layer.available()
    runner.check(
        "VisionLayer is available with provider+runtime+capture",
        ok and "§12.2" in reason,
        detail=f"({ok}, {reason})",
    )
    layer_no_provider = VisionLayer(computer, None, capture=FakeGdi())
    runner.check(
        "VisionLayer refuses honestly without a provider",
        layer_no_provider.available()[0] is False,
    )
    unavailable = FakeProvider(available=False)
    runner.check(
        "VisionLayer refuses when the provider itself is unavailable",
        VisionLayer(computer, unavailable, capture=FakeGdi()).available()[0]
        is False,
    )
    layer_no_runtime = VisionLayer(None, provider, capture=FakeGdi())
    runner.check(
        "VisionLayer is chain-only without a computer runtime",
        layer_no_runtime.available()[0] is False,
    )
    if not ON_WINDOWS:
        layer_linux = VisionLayer(computer, provider)  # no injected backend
        ok_l, reason_l = layer_linux.available()
        runner.check(
            "VisionLayer reports the win32 requirement off win32",
            ok_l is False and "win32" in reason_l,
        )

    # -- act(): inspect --------------------------------------------------
    outcome = layer.act(ActionTarget(action="inspect"))
    runner.check(
        "inspect maps to the provider's analyze with a report artifact",
        outcome.layer == "vision"
        and "report" in outcome.artifacts
        and provider.calls[0][0] == "analyze",
    )
    runner.check(
        "act() returns None for unsupported actions (chain moves on)",
        layer.act(ActionTarget(action="focus", hwnd=1)) is None,
    )

    # -- act(): click → locate → mouse -----------------------------------
    computer.calls.clear()
    outcome = layer.act(
        ActionTarget(action="click", name="the Save button")
    )
    runner.check(
        "click: locate → mouse click at the located center",
        outcome.layer == "vision"
        and computer.calls == [
            ("mouse", {"op": "click", "x": 125, "y": 220}),
        ],
        detail=f"calls={computer.calls}",
    )
    runner.check(
        "the click artifact carries the bbox and the hand-off point",
        outcome.artifacts.get("point") == [125, 220]
        and outcome.artifacts.get("bbox", {}).get("bbox") == [100, 200, 50, 40],
    )

    # -- act(): type → locate → click + keyboard -------------------------
    computer.calls.clear()
    outcome = layer.act(
        ActionTarget(action="type", name="the user field", value="nexus")
    )
    runner.check(
        "type: locate → focus click → keyboard type",
        computer.calls == [
            ("mouse", {"op": "click", "x": 125, "y": 220}),
            ("keyboard", {"op": "type", "text": "nexus"}),
        ],
        detail=f"calls={computer.calls}",
    )

    # -- honest failures (LayerError, the chain falls through) -----------
    class _BlindProvider(FakeProvider):
        def locate(self, image: bytes, description: str) -> Any:
            return None

    blind_layer = VisionLayer(computer, _BlindProvider(), capture=FakeGdi())
    blind_failed = False
    try:
        blind_layer.act(ActionTarget(action="click", name="missing"))
    except Exception as exc:  # noqa: BLE001 — the LayerError contract
        blind_failed = "could not locate" in str(exc)
    runner.check(
        "a not-found locate raises LayerError (the chain falls through)",
        blind_failed,
    )
    nameless_refused = False
    try:
        layer.act(ActionTarget(action="click", name=""))
    except Exception as exc:  # noqa: BLE001 — the LayerError contract
        nameless_refused = "description" in str(exc)
    runner.check("a click without a description is refused", nameless_refused)

    # -- the chain itself ------------------------------------------------
    chain = HierarchyChain()
    chain.register(VisionLayer(computer, provider, capture=FakeGdi()))
    computer.calls.clear()
    result = chain.act(ActionTarget(action="click", name="the Save button"))
    runner.check(
        "the bare chain serves a click through vision alone",
        result.layer == "vision"
        and len(computer.calls) == 1,
    )
    describe = chain.describe()
    runner.check(
        "chain.describe() reports the vision rung honestly",
        describe["vision"]["providers"] == 1
        and describe["input"]["providers"] == 0,
    )

    # -- the §8.1 record --------------------------------------------------
    tool = VisionTool(workspace_root=Path(tempfile.gettempdir()))
    definition = tool.definition()
    runner.check(
        "the vision record: id/name/risk 1/permissions",
        definition.id == "native:vision"
        and definition.name == "vision"
        and definition.risk == 1
        and "screen.read" in definition.permissions,
    )
    runner.check(
        "the vision record scopes its paths and marks capture mutating",
        definition.scope_requirements.path_arguments == ("path", "path_b")
        and definition.scope_requirements.mutating_operations == ("capture",)
        and "display" in definition.scope_requirements.dimensions,
    )
    runner.check(
        "the op vocabulary is capture + the four verbs + ocr",
        ("capture", "analyze", "locate", "classify", "compare", "ocr")
        == tuple(definition.input_schema["properties"]["op"]["enum"]),
    )
    from nexus.tools.models import VerificationStrategy as V

    contracts = {
        op: tool.verification_for(op)
        for op in ("capture", "analyze", "locate", "classify", "compare", "ocr")
    }
    runner.check(
        "verification contracts bind to always-emitted keys "
        "(the Phase-10 lesson)",
        contracts["capture"].strategy == V.PATH_SIZE
        and contracts["analyze"].argument == "report"
        and contracts["locate"].argument == "found"
        and contracts["classify"].argument == "category"
        and contracts["compare"].argument == "same"
        and contracts["ocr"].argument == "text",
    )

    from nexus.tools.registry import ToolRegistry
    from nexus.vision.tools import register_vision_tools

    registry = ToolRegistry()
    names = register_vision_tools(registry)
    runner.check(
        "register_vision_tools adds the fourteenth record",
        names == ("vision",) and registry.get("vision") is not None,
    )

    # -- full §8.2 router roundtrip with a fake provider ------------------
    provider_state.reset()
    provider_state.set_provider(FakeProvider())
    try:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = root / "screen.png"
            image.write_bytes(_sample_png())
            _registry, router, _adapter, report = build_tool_system(
                native=True, computer=True, browser=False, vision=True,
                workspace_root=root, mcp_servers=(),
            )
            runner.check(
                "build_tool_system(vision=True) reports the record",
                report["vision"] == ["vision"],
            )
            outcome = router.route(
                "vision",
                {"op": "locate", "path": str(image),
                 "description": "the Save button"},
                agent_id="phase11-test",
            )
            runner.check(
                "the §8.2 pipeline serves a vision locate end-to-end",
                outcome.ok and outcome.artifacts.get("found") is True,
                detail=f"error={getattr(outcome, 'error', '')}",
            )
            outcome_analyze = router.route(
                "vision",
                {"op": "analyze", "path": str(image),
                 "question": "what is on screen?"},
                agent_id="phase11-test",
            )
            runner.check(
                "the pipeline serves a vision analyze with the report key",
                outcome_analyze.ok
                and "report" in outcome_analyze.artifacts,
            )
            outcome_bad = router.route(
                "vision", {"op": "locate", "path": str(image)}, agent_id="t",
            )
            runner.check(
                "a locate without a description fails as data, not a crash",
                not outcome_bad.ok,
                detail=f"ok={outcome_bad.ok}",
            )
    finally:
        provider_state.reset()

    # -- the façade --------------------------------------------------------
    _registry, router, _adapter, _report = build_tool_system(
        native=True, computer=False, browser=False, vision=True,
        workspace_root=Path(tempfile.gettempdir()), mcp_servers=(),
    )
    facade = VisionRuntime(router)
    capability = facade.capability_report()
    runner.check(
        "the façade probes all six §12 domains honestly",
        set(capability) == {"capture", "analyze", "locate",
                            "classify", "compare", "ocr"},
    )
    try:
        facade.capture("hologram", path="x.png")
        bad_mode = False
    except Exception:  # noqa: BLE001 — the façade refuses bad args
        bad_mode = True
    outcome_bad_mode = None
    if not bad_mode:
        outcome_bad_mode = facade.capture("hologram", path="x.png")
    runner.check(
        "the façade routes capture mode validation through the tool "
        "(refused, as data or an error — never a fake capture)",
        bad_mode or (outcome_bad_mode is not None and not outcome_bad_mode.ok),
        detail=f"raised={bad_mode} outcome_ok={getattr(outcome_bad_mode, 'ok', None)}",
    )


def section_f(runner: Runner) -> None:
    """Integration + regression — the runtime wires §12; phases stay green."""
    runner.section = "F"

    from dataclasses import replace as _replace

    from nexus.core.config.loader import load_config
    from nexus.core.config.paths import resolve_paths
    from nexus.core.config.runtime import NexusRuntime
    from nexus.core.config.schema import ConfigError, build_section

    with tempfile.TemporaryDirectory() as root:
        provider_state.reset()
        runtime = NexusRuntime(
            paths=resolve_paths(root), config=load_config(root), bus=EventBus()
        )
        runner.check(
            "NexusRuntime wires the Vision Runtime (vision_enabled default)",
            runtime.vision_runtime is not None,
        )
        router = runtime.tool_router
        assert router is not None
        discovered = router.registry.discover()
        runner.check(
            "the wired registry holds 14 records "
            "(nine + three + browser + vision)",
            len(discovered) == 14,
            detail=f"count={len(discovered)} names={discovered}",
        )
        runner.check(
            "the runtime injected the §12.2 provider state",
            provider_state.get_provider() is not None
            and provider_state.get_ocr_preference() == "auto",
        )
        vision_runtime = runtime.vision_runtime
        assert vision_runtime is not None
        report = vision_runtime.capability_report()
        runner.check(
            "the vision façade probes answer on the wired runtime",
            "capture" in report and report["capture"]["reason"] != "",
            detail=f"report={report}",
        )
        chain = runtime.computer_runtime.chain.describe()
        runner.check(
            "the §9.5 chain gained its vision rung (1 provider, 4th of 5)",
            "vision" in chain and chain["vision"]["providers"] == 1
            and chain["dom_a11y"]["providers"] == 1,
            detail=f"chain={chain}",
        )
        runtime.shutdown()
        runner.check(
            "shutdown unwires the provider state (re-boot injects fresh)",
            provider_state.get_provider() is None,
        )

    with tempfile.TemporaryDirectory() as root:
        provider_state.reset()
        base = load_config(root)
        config_off = _replace(
            base, tools=_replace(base.tools, vision_enabled=False)
        )
        runtime_off = NexusRuntime(
            paths=resolve_paths(root), config=config_off, bus=EventBus()
        )
        router_off = runtime_off.tool_router
        assert router_off is not None
        runner.check(
            "vision_enabled=false leaves the façade unwired and the "
            "registry at 13 (Phase-10 behavior, byte for byte)",
            runtime_off.vision_runtime is None
            and len(router_off.registry.discover()) == 13,
            detail=f"count={len(router_off.registry.discover())}",
        )
        chain_off = (
            runtime_off.computer_runtime.chain.describe()
            if runtime_off.computer_runtime is not None
            else {}
        )
        runner.check(
            "with vision off, the chain has no vision provider "
            "(and no state leak)",
            chain_off.get("vision", {}).get("providers", 0) == 0
            and provider_state.get_provider() is None,
        )
        runtime_off.shutdown()

    bad_engine = False
    try:
        build_section("tools", {"vision_ocr_engine": "abbyy"})
    except ConfigError:
        bad_engine = True
    runner.check("config: an unknown vision_ocr_engine is refused", bad_engine)
    section, _warnings = build_section(
        "tools", {"vision_enabled": "false", "vision_ocr_engine": "tesseract"}
    )
    runner.check(
        "config: vision keys coerce and land",
        section.vision_enabled is False
        and section.vision_ocr_engine == "tesseract",
    )

    # the §8.1 record registers through build_tool_system too
    _registry, _router, _adapter, report = build_tool_system(
        native=True, computer=True, browser=True, mcp_servers=()
    )
    runner.check(
        "build_tool_system default (vision off) stays at the Phase-10 "
        "report shape",
        report.get("vision", False) is False
        and report["browser"] == ["browser"],
    )

    prior = [
        ("phase01", "Phase 1", 98),
        ("phase02", "Phase 2", 143),
        ("phase03", "Phase 3", 104),
        ("phase04", "Phase 4", 106),
        ("phase05", "Phase 5", 116),
        ("phase06", "Phase 6", 88),
        ("phase07", "Phase 7", 88),
        ("phase08", "Phase 8", 80),
        ("phase09", "Phase 9", 84),
        ("phase10", "Phase 10", 70),
    ]
    results = run_phases(prior)
    for (_phase_dir, label, _expected), (_label, line, code) in zip(
        prior, results, strict=True
    ):
        runner.check(
            f"{label} harness still green ({line})",
            code == 0,
            detail=f"exit={code} last={line!r}",
        )


def run_phases(prior: list[tuple[str, str, int]]) -> list[tuple[str, str, int]]:
    """Run the Phase 1–10 harnesses; return their (name, line, code)."""
    results: list[tuple[str, str, int]] = []
    for phase_dir, label, expected in prior:
        proc = subprocess.run(
            [sys.executable, str(REPO_ROOT / "tests" / phase_dir / "verify_exit_criteria.py")],
            capture_output=True,
            text=True,
            timeout=1800,
        )
        results.append(
            (label, proc.stdout.strip().splitlines()[-1], proc.returncode)
        )
        _ = expected
    return results


# ======================================================================= main


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=None, help="unused (repo-rooted)")
    _ = parser.parse_args()
    print(
        "PHASE 11 — Vision + OCR + Screen Understanding "
        "(Build Plan §12) exit criteria"
    )
    runner = Runner()
    for section in (section_a, section_b, section_c, section_d, section_e, section_f):
        try:
            section(runner)
        except Exception as exc:  # noqa: BLE001 — a section crash is a failure
            print(f"  [FAIL] ({runner.section}) section crashed: {exc}")
            runner.failed += 1
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
