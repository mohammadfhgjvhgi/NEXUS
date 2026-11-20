"""Vision + OCR + Screen Understanding (Final Build Plan §12 —
Phase 11 · UI-TARS/OpenCUA/Agent-S, Repository Round 8).

* :mod:`nexus.vision.models`     — the §12 vocabulary (data, not code)
* :mod:`nexus.vision.capture`    — §12.1 full screen · window · region
* :mod:`nexus.vision.provider`   — §12.2 VisionProvider (analyze ·
                                   locate · classify · compare) over
                                   the Phase 4 Model Runtime
* :mod:`nexus.vision.ocr`        — §12.5 the engine candidates +
                                   the CER metric (device benchmark
                                   decides)
* :mod:`nexus.vision.benchmark`  — the §12.5 device decision run
* :mod:`nexus.vision.layer`      — the §9.5 vision rung (the fourth
                                   of five layers)
* :mod:`nexus.vision.api`        — the façade over the §8.2 router
* :mod:`nexus.vision.provider_state` — the runtime-injected wiring

The §9.5 chain gains its **vision** rung: applications with no
useful UI structure resolve by *looking* — locate by description,
then real input. Repository Round 8 cloned UI-TARS, OpenCUA and
Agent-S as REFERENCE/RESEARCH ONLY (Plan §12.3/§12.4 — never the
production runtime); the UI-TARS action-space *tolerance* in the
locate parser is the single documented adoption.

الرؤية — الحلقة الرابعة في سلسلة التراجع، والتعرّف يُقرر على
الجهاز بالمعيار.

Stdlib only at the core (engines/projections are lazy extras).
"""

from __future__ import annotations

from . import provider_state
from .api import VISION_DOMAINS, VisionApiError, VisionRuntime
from .capture import (
    CaptureError,
    Win32Gdi,
    capture_available,
    capture_full_screen,
    capture_region,
    capture_window,
    png_dimensions,
    resolve_capture_mode,
)
from .layer import VisionLayer
from .models import (
    CAPTURE_MODES,
    OCR_REQUIREMENTS,
    CaptureResult,
    Classification,
    ComparisonReport,
    LocatedElement,
    OcrBenchmarkReport,
    OcrResult,
    ScreenRegion,
    VisionReport,
)
from .ocr import (
    OCR_ENGINE_ORDER,
    ModelOcrEngine,
    OcrEngine,
    OcrError,
    TesseractOcrEngine,
    WinrtOcrEngine,
    character_error_rate,
    resolve_ocr_engine,
)
from .provider import (
    ModelVisionProvider,
    VisionError,
    VisionProvider,
    parse_analyze,
    parse_bbox,
    parse_classify,
    parse_compare,
    parse_json_block,
    parse_locate,
)
from .tools import VISION_TOOL_NAMES, VisionTool, register_vision_tools

#: The §12 sections this package implements, verbatim.
VISION_SECTIONS: tuple[str, ...] = (
    "capture",   # §12.1 screen capture (full · window · region)
    "provider",  # §12.2 the Vision Adapter (four verbs)
    "reference", # §12.3 UI-TARS (REFERENCE/BENCHMARK — Round 8)
    "research",  # §12.4 computer-use research clones (not runtime)
    "ocr",       # §12.5 OCR — the device benchmark decides
)

__all__ = [
    "VISION_SECTIONS",
    # §12.1
    "CAPTURE_MODES",
    "CaptureError",
    "CaptureResult",
    "Win32Gdi",
    "capture_available",
    "capture_full_screen",
    "capture_region",
    "capture_window",
    "png_dimensions",
    "resolve_capture_mode",
    "ScreenRegion",
    # §12.2
    "ModelVisionProvider",
    "VisionError",
    "VisionProvider",
    "VisionReport",
    "LocatedElement",
    "Classification",
    "ComparisonReport",
    "parse_analyze",
    "parse_bbox",
    "parse_classify",
    "parse_compare",
    "parse_json_block",
    "parse_locate",
    # §12.5
    "OCR_ENGINE_ORDER",
    "OCR_REQUIREMENTS",
    "OcrEngine",
    "OcrError",
    "OcrResult",
    "OcrBenchmarkReport",
    "ModelOcrEngine",
    "TesseractOcrEngine",
    "WinrtOcrEngine",
    "character_error_rate",
    "resolve_ocr_engine",
    # §9.5 + façade
    "VisionLayer",
    "VISION_DOMAINS",
    "VisionApiError",
    "VisionRuntime",
    # the record + wiring
    "VISION_TOOL_NAMES",
    "VisionTool",
    "register_vision_tools",
    # wiring
    "provider_state",
]
