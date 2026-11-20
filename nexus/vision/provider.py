"""Vision Adapter (Final Build Plan §12.2, verbatim).

.. code-block:: text

    VisionProvider
    ├── analyze
    ├── locate
    ├── classify
    └── compare

The interface is the four verbs, nothing more. The production
backend is :class:`ModelVisionProvider` — the Phase 4 Local Model
Runtime behind the §5.7 router, selecting a **vision-capable**
model and submitting the image with the request (the §5.1
``GenerateRequest`` gains an optional ``images`` field — additive,
default empty, the Phase 4 text-only contract unchanged).

Everything model-shaped is built from **pure functions** (prompt
builders + tolerant parsers), so the contract is CI-testable
without any model: the JSON extraction survives prose-wrapped
answers, markdown fences, and — as the Repository Round 8
REFERENCE adoption — the UI-TARS action space
(``click(start_box='(197,525)')``) parses to the same bbox pixels
(the convention is *documented tolerance*, never a dependency).

Availability is honest: no manager, no vision model in the pool, or
a backend without image support → the §9.5 chain skips this rung.

مزوّد الرؤية — أربعة أفعال خلف موجه النماذج، والصورة داخل الطلب،
والتوفّر صادق بلا نماذج.

Stdlib only.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from .models import (
    Classification,
    ComparisonReport,
    LocatedElement,
    VisionReport,
)

#: The §5.7 capability a vision model advertises in the Model Pool.
VISION_CAPABILITY = "vision"

_DEFAULT_MAX_TOKENS = 512

_LOCATE_SYSTEM = (
    "You are a GUI grounding model. Answer ONLY with JSON. "
    "Coordinates are absolute pixels in the submitted image, "
    "top-left origin: {\"bbox\": [x, y, width, height], "
    "\"confidence\": 0.0-1.0, \"description\": \"...\"}. "
    "If the target is absent, answer {\"found\": false}."
)


class VisionError(Exception):
    """A vision operation failed — honest, with the verb that failed."""


# ------------------------------------------------------------ the adapter


class VisionProvider(ABC):
    """The §12.2 contract — four verbs, verbatim."""

    #: backend identity (reported in receipts and probes).
    name: str = "abstract"

    @abstractmethod
    def available(self) -> tuple[bool, str]:
        """Honest probe — never a guess (the §9.5 chain asks)."""

    @abstractmethod
    def analyze(self, image: bytes, question: str) -> VisionReport:
        """Describe/understand one PNG image for a given question."""

    @abstractmethod
    def locate(
        self, image: bytes, description: str
    ) -> LocatedElement | None:
        """Find one element by description → pixels, or ``None``."""

    @abstractmethod
    def classify(
        self, image: bytes, categories: Sequence[str]
    ) -> Classification:
        """Pick the image's category out of the given set."""

    @abstractmethod
    def compare(self, image_a: bytes, image_b: bytes) -> ComparisonReport:
        """Judge two images against each other."""


# ------------------------------------------------- the model-backed backend


class ModelVisionProvider(VisionProvider):
    """The production adapter — the Phase 4 Model Runtime as vision.

    ``manager`` is the §5.4 ModelManager; every verb routes through
    ``manager.select`` (``required_capability="vision"``) so the §5.7
    router picks the pool's vision model, then ``manager.generate``
    carries the PNG with the request. The parsing layer turns the
    model's prose into the §12.2 dataclasses — tolerantly, because
    local models are models.
    """

    name = "model-runtime"

    def __init__(self, manager: Any, *, model_id: str | None = None) -> None:
        self._manager = manager
        self._model_id = model_id

    # ------------------------------------------------------------ probe

    def available(self) -> tuple[bool, str]:
        if self._manager is None:
            return False, "no model manager wired (provider is stub-only)"
        if self._model_id is not None:
            return True, f"model runtime pinned to {self._model_id}"
        return (
            True,
            "model runtime behind the §5.7 router (vision capability)",
        )

    # ------------------------------------------------------------ verbs

    def analyze(self, image: bytes, question: str) -> VisionReport:
        if not question.strip():
            raise VisionError("analyze requires a non-empty question")
        prompt = analyze_prompt(question)
        text = self._generate(image, prompt, system=_ANALYZE_SYSTEM)
        return parse_analyze(text)

    def locate(
        self, image: bytes, description: str
    ) -> LocatedElement | None:
        if not description.strip():
            raise VisionError("locate requires a non-empty description")
        prompt = locate_prompt(description)
        text = self._generate(image, prompt, system=_LOCATE_SYSTEM)
        return parse_locate(text, description)

    def classify(
        self, image: bytes, categories: Sequence[str]
    ) -> Classification:
        choices = [category for category in categories if str(category).strip()]
        if not choices:
            raise VisionError("classify requires at least one category")
        prompt = classify_prompt(choices)
        text = self._generate(image, prompt, system=_CLASSIFY_SYSTEM)
        return parse_classify(text, choices)

    def compare(self, image_a: bytes, image_b: bytes) -> ComparisonReport:
        prompt = compare_prompt()
        text = self._generate(
            image_a, prompt, system=_COMPARE_SYSTEM, extra_images=(image_b,)
        )
        return parse_compare(text)

    # ----------------------------------------------------------- engine

    def _generate(
        self,
        image: bytes,
        prompt: str,
        *,
        system: str,
        extra_images: tuple[bytes, ...] = (),
    ) -> str:
        """One vision generation through the §5.4 manager."""
        from ..models.provider import GenerateRequest
        from ..models.router import RoutingRequest

        if self._manager is None:
            raise VisionError("no model manager wired")
        model_id = self._model_id
        if model_id is None:
            decision = self._manager.select(
                RoutingRequest(required_capability=VISION_CAPABILITY)
            )
            model_id = decision.selected_model_id or ""
            if not model_id:
                raise VisionError(
                    "the §5.7 router found no vision-capable model in the pool"
                )
        request = GenerateRequest(
            model_id=model_id,
            prompt=prompt,
            system=system,
            max_tokens=_DEFAULT_MAX_TOKENS,
            images=(image, *extra_images),
            auto_load=True,
        )
        result = self._manager.generate(request)
        return str(result.text)


# -------------------------------------------------------- prompt builders


_ANALYZE_SYSTEM = (
    "You are a screen-understanding engine. Describe what you see "
    "precisely and answer the question. Structure the answer as JSON: "
    "{\"description\": \"...\", \"elements\": [{\"label\": \"...\", "
    "\"bbox\": [x, y, w, h]}], \"confidence\": 0.0-1.0}. "
    "Bounding boxes are absolute pixels of the image."
)

_CLASSIFY_SYSTEM = (
    "You are an image classifier. Answer ONLY with JSON: "
    "{\"category\": \"<one of the given categories>\", "
    "\"confidence\": 0.0-1.0, \"ranking\": [{\"category\": \"...\", "
    "\"confidence\": 0.0}]}."
)

_COMPARE_SYSTEM = (
    "You compare two images (the first, then the second). Answer ONLY "
    "with JSON: {\"same\": true|false, \"similarity\": 0.0-1.0, "
    "\"differences\": [\"...\"]} — \"similarity\" is 1.0 for identical."
)


def analyze_prompt(question: str) -> str:
    """§12.2 ``analyze`` prompt (pure)."""
    return f"Analyze the image and answer: {question.strip()}"


def locate_prompt(description: str) -> str:
    """§12.2 ``locate`` prompt (pure)."""
    return (
        "Locate exactly one UI element matching this description in the "
        f"image: {description.strip()}. Return its bounding box in pixels."
    )


def classify_prompt(categories: Sequence[str]) -> str:
    """§12.2 ``classify`` prompt (pure)."""
    listed = " · ".join(str(category) for category in categories)
    return f"Classify the image into exactly one category: {listed}."


def compare_prompt() -> str:
    """§12.2 ``compare`` prompt (pure)."""
    return "Compare the two images. Are they the same scene/state?"


# --------------------------------------------------------- tolerant parsing


def parse_json_block(text: str) -> dict[str, Any]:
    """Extract the first JSON object from a model answer (pure).

    Survives prose around the object, markdown fences, and trailing
    commas-free single quotes are NOT converted — malformed JSON falls
    back to ``{}`` (callers treat missing keys honestly).
    """
    stripped = text.strip()
    if stripped.startswith("```"):
        # markdown fence — keep the inner content only
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
    start = stripped.find("{")
    if start < 0:
        return {}
    depth = 0
    for index in range(start, len(stripped)):
        if stripped[index] == "{":
            depth += 1
        elif stripped[index] == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start : index + 1]
                try:
                    parsed = json.loads(candidate)
                except json.JSONDecodeError:
                    break
                if isinstance(parsed, dict):
                    return parsed
                break
    return {}


def _bbox_from(value: Any) -> tuple[int, int, int, int] | None:
    """Coerce a bbox value (list/tuple/dict) to (x, y, w, h) pixels."""
    if isinstance(value, (list, tuple)) and len(value) == 4:
        try:
            box = tuple(int(float(item)) for item in value)
        except (TypeError, ValueError):
            return None
        return box  # type: ignore[return-value]
    if isinstance(value, dict):
        keys = ("x", "y", "w", "h")
        if all(key in value for key in keys):
            try:
                return (
                    int(float(value["x"])), int(float(value["y"])),
                    int(float(value["w"])), int(float(value["h"])),
                )
            except (TypeError, ValueError):
                return None
    return None


#: The UI-TARS reference action space, tolerated (Round 8 — the
#: ``click(start_box='(x,y)')`` family; REFERENCE, never imported).
_TARS_BOX = re.compile(
    r"(?:start_box|end_box)\s*=\s*['\"]?\((\d+)\s*,\s*(\d+)\)"
)


def parse_bbox(text: str) -> tuple[int, int, int, int] | None:
    """Parse a bbox from JSON, a bare list, or the UI-TARS box form.

    ``[x, y, w, h]`` is the house dialect; ``[x1, y1, x2, y2]``
    models get normalized (x2 > x1 heuristics keep w/h positive).
    """
    payload = parse_json_block(text)
    box = _bbox_from(payload.get("bbox") or payload.get("box"))
    if box is None:
        # bare-list answers like "[12, 34, 56, 78]"
        bare = re.search(r"\[\s*\d+\s*,\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\]", text)
        if bare:
            box = _bbox_from(json.loads(bare.group(0)))
    if box is not None and (box[2] < 0 or box[3] < 0):
        return None
    if box is not None and (box[2] == 0 or box[3] == 0) and (box[2] or box[3]):
        # likely x2,y2 semantics — convert
        box = (box[0], box[1], max(box[2] - box[0], 0), max(box[3] - box[1], 0))
    if box is not None:
        return box
    match = _TARS_BOX.search(text)
    if match:
        x, y = int(match.group(1)), int(match.group(2))
        return (x, y, 0, 0)  # a point-box — locate() widens it
    return None


def parse_analyze(text: str) -> VisionReport:
    """§12.2 ``analyze`` parser (pure, tolerant)."""
    payload = parse_json_block(text)
    description = str(payload.get("description") or text.strip()[:400])
    elements_raw = payload.get("elements")
    elements: list[dict[str, Any]] = []
    if isinstance(elements_raw, list):
        for element in elements_raw:
            if not isinstance(element, dict):
                continue
            box = _bbox_from(element.get("bbox"))
            entry: dict[str, Any] = {
                "label": str(element.get("label") or element.get("name") or ""),
            }
            if box is not None:
                entry["bbox"] = list(box)
            elements.append(entry)
    confidence = _clamp01(payload.get("confidence"))
    raw = text.strip()
    return VisionReport(
        description=description, elements=elements,
        confidence=confidence, raw=raw,
    )


def parse_locate(text: str, description: str) -> LocatedElement | None:
    """§12.2 ``locate`` parser (pure, tolerant) — ``None`` when absent."""
    payload = parse_json_block(text)
    if payload.get("found") is False:
        return None
    box = _bbox_from(payload.get("bbox") or payload.get("box"))
    if box is None:
        box = parse_bbox(text)
    if box is None:
        return None
    x, y, width, height = box
    if width <= 0 and height <= 0:
        # a point-box (UI-TARS click coordinates) — widen to a
        # 1×1 target the §9.5 hand-off can still click
        width, height = 1, 1
    if x < 0 or y < 0:
        return None
    return LocatedElement(
        description=description,
        x=x, y=y, width=width, height=height,
        confidence=_clamp01(payload.get("confidence")),
    )


def parse_classify(text: str, categories: Sequence[str]) -> Classification:
    """§12.2 ``classify`` parser (pure) — never invents a category."""
    allowed = {str(category) for category in categories}
    payload = parse_json_block(text)
    category = str(payload.get("category") or "").strip()
    if category not in allowed:
        # the model answered outside the set — first allowed token win
        lowered = text.lower()
        category = next(
            (str(option) for option in allowed if str(option).lower() in lowered),
            "",
        )
    ranking: list[dict[str, Any]] = []
    ranking_raw = payload.get("ranking")
    if isinstance(ranking_raw, list):
        for row in ranking_raw:
            if isinstance(row, dict) and str(row.get("category")) in allowed:
                ranking.append(
                    {
                        "category": str(row.get("category")),
                        "confidence": _clamp01(row.get("confidence")),
                    }
                )
    return Classification(
        category=category,
        confidence=_clamp01(payload.get("confidence")),
        ranking=ranking,
    )


def parse_compare(text: str) -> ComparisonReport:
    """§12.2 ``compare`` parser (pure, tolerant)."""
    payload = parse_json_block(text)
    same = payload.get("same")
    if not isinstance(same, bool):
        lowered = text.lower()
        same = "not same" not in lowered and "different" not in lowered
    similarity = payload.get("similarity")
    similarity = (
        _clamp01(similarity)
        if isinstance(similarity, (int, float))
        else (1.0 if same else 0.0)
    )
    differences: list[str] = []
    raw_diffs = payload.get("differences")
    if isinstance(raw_diffs, list):
        differences = [str(item) for item in raw_diffs if str(item).strip()]
    return ComparisonReport(
        same=same, similarity=similarity, differences=differences
    )


def _clamp01(value: Any) -> float:
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return 0.0


__all__ = [
    "ModelVisionProvider",
    "VISION_CAPABILITY",
    "VisionError",
    "VisionProvider",
    "analyze_prompt",
    "classify_prompt",
    "compare_prompt",
    "locate_prompt",
    "parse_analyze",
    "parse_bbox",
    "parse_classify",
    "parse_compare",
    "parse_json_block",
    "parse_locate",
]
