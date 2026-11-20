"""Vision data models (Final Build Plan §12 — Phase 11 vocabulary).

The §12 sections, verbatim:

* §12.1 Screen Capture — ``full screen · window · region``
* §12.2 Vision Adapter — ``analyze · locate · classify · compare``
* §12.5 OCR — ``English · numbers · UI labels · documents``

Everything here is **data, not code**: capture receipts, vision
reports, located elements, classifications, comparisons, OCR lines
and the benchmark ledger. One vocabulary shared by the capture
layer, the provider, the OCR engines, the §8.1 ``vision`` record and
the §9.5 vision rung — no second dialect.

Coordinate convention: every bounding box and point is in **absolute
pixels of the submitted image** (top-left origin). The provider
prompts instruct the model accordingly; the UI-TARS reference action
space (``click(start_box='(x,y)')``) is tolerated on parse
(Repository Round 8, REFERENCE — never a runtime dependency).

مفردات الرؤية — لقطة وتقرير وإحداثيات ونص، بلا لهجة ثانية.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: §12.1 capture modes, verbatim.
CAPTURE_MODES: tuple[str, ...] = ("full", "window", "region")

#: §12.5 OCR requirements, verbatim.
OCR_REQUIREMENTS: tuple[str, ...] = (
    "English",
    "numbers",
    "UI labels",
    "documents",
)

#: Benchmark corpus categories (§12.5 mapped to stable ids).
OCR_CATEGORIES: tuple[str, ...] = (
    "english",
    "numbers",
    "ui_labels",
    "documents",
)


@dataclass(slots=True)
class ScreenRegion:
    """One rectangle of the screen (top-left origin, inclusive size)."""

    x: int
    y: int
    width: int
    height: int

    def clamp_to(self, bounds: ScreenRegion) -> ScreenRegion:
        """Intersect with ``bounds`` — captures never leave the screen."""
        x = max(self.x, bounds.x)
        y = max(self.y, bounds.y)
        right = min(self.x + self.width, bounds.x + bounds.width)
        bottom = min(self.y + self.height, bounds.y + bounds.height)
        width = max(0, right - x)
        height = max(0, bottom - y)
        return ScreenRegion(x, y, width, height)

    def to_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y, "w": self.width, "h": self.height}


@dataclass(slots=True)
class CaptureResult:
    """One §12.1 capture receipt — a real PNG plus its provenance.

    ``source`` is ``"screen"`` for full/region captures and
    ``f"hwnd:{hwnd}"`` for window captures; ``region`` is where the
    capture came from (for windows: the screen-space bounds).
    """

    mode: str  # one of CAPTURE_MODES
    png: bytes
    width: int
    height: int
    source: str = "screen"
    region: ScreenRegion | None = None

    @property
    def bytes_size(self) -> int:
        return len(self.png)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "width": self.width,
            "height": self.height,
            "source": self.source,
            "region": self.region.to_dict() if self.region else None,
            "bytes": len(self.png),
        }


@dataclass(slots=True)
class VisionReport:
    """§12.2 ``analyze`` — what the provider understood of one image."""

    description: str = ""
    elements: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.0
    raw: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "elements": list(self.elements),
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class LocatedElement:
    """§12.2 ``locate`` — one element found by description, in pixels."""

    description: str
    x: int
    y: int
    width: int
    height: int
    confidence: float = 0.0

    def center(self) -> tuple[int, int]:
        """The §9.5 hand-off point (mouse-clickable center)."""
        return (self.x + self.width // 2, self.y + self.height // 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "description": self.description,
            "bbox": [self.x, self.y, self.width, self.height],
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class Classification:
    """§12.2 ``classify`` — the image's category out of a given set."""

    category: str
    confidence: float = 0.0
    ranking: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category,
            "confidence": self.confidence,
            "ranking": list(self.ranking),
        }


@dataclass(slots=True)
class ComparisonReport:
    """§12.2 ``compare`` — two images, judged against each other."""

    same: bool = False
    similarity: float = 0.0
    differences: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "same": self.same,
            "similarity": self.similarity,
            "differences": list(self.differences),
        }


@dataclass(slots=True)
class OcrLine:
    """One recognized text line with its pixel box (§12.5)."""

    text: str
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "bbox": [self.x, self.y, self.width, self.height],
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class OcrResult:
    """One ``recognize`` receipt — the full text, line boxes, engine."""

    text: str = ""
    lines: list[OcrLine] = field(default_factory=list)
    engine: str = ""

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "engine": self.engine,
            "lines": [line.to_dict() for line in self.lines],
            "words": self.word_count,
        }


@dataclass(slots=True)
class OcrCase:
    """One benchmark case (§12.5): a category, a truth, an image."""

    category: str  # one of OCR_CATEGORIES
    expected: str
    png: bytes = b""

    @property
    def label(self) -> str:
        return f"{self.category}:{self.expected[:24]}"


@dataclass(slots=True)
class OcrEngineScore:
    """One engine's benchmark aggregate (§12.5 — device-run)."""

    engine: str
    mean_cer: float = 0.0
    total_seconds: float = 0.0
    per_category: dict[str, float] = field(default_factory=dict)
    cases: int = 0
    supported_requirements: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "engine": self.engine,
            "mean_cer": self.mean_cer,
            "total_seconds": self.total_seconds,
            "per_category": dict(self.per_category),
            "cases": self.cases,
            "supported_requirements": list(self.supported_requirements),
        }


@dataclass(slots=True)
class OcrBenchmarkReport:
    """The §12.5 device benchmark verdict — the OCR decision record."""

    scores: list[OcrEngineScore] = field(default_factory=list)
    winner: str = ""
    decided: bool = False
    reason: str = ""
    at: str = ""
    device: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scores": [score.to_dict() for score in self.scores],
            "winner": self.winner,
            "decided": self.decided,
            "reason": self.reason,
            "at": self.at,
            "device": self.device,
        }


#: Every result dataclass above carries ``to_dict`` — the artifacts
#: that ride §8.1 tool outputs and §2.2 events stay plain JSON.
__all__ = [
    "CAPTURE_MODES",
    "OCR_CATEGORIES",
    "OCR_REQUIREMENTS",
    "CaptureResult",
    "Classification",
    "ComparisonReport",
    "LocatedElement",
    "OcrBenchmarkReport",
    "OcrCase",
    "OcrEngineScore",
    "OcrLine",
    "OcrResult",
    "ScreenRegion",
    "VisionReport",
]
