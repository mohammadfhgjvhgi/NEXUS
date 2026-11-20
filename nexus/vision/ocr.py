"""OCR engines (Final Build Plan §12.5, verbatim).

The requirements, verbatim::

    English
    numbers
    UI labels
    documents

The final engine choice is **made by the device benchmark** (Plan
§12.5: «اختيار OCR النهائي يجب أن يتم بالـbenchmark على جهازك») —
this module ships the *candidates*, the honest probes, and the
scoring math; :mod:`nexus.vision.benchmark` runs the decision.

Candidates (pluggable, all honestly unavailable without their
extras — the NEXUS degradation ladder, never a fake):

* **winrt** — ``Windows.Media.Ocr``, the OS-native engine (zero
  model, offline, excellent English/numbers on UI labels). Lazy
  ``winsdk``/``winrt`` import; needs win10+ and the extra.
* **tesseract** — the classic (``pytesseract`` + Pillow; needs the
  ``tesseract`` binary — MODE A optional ``[ocr]`` extra).
* **model** — the local VLM through the §12.2 provider (documents
  and layout-heavy text; zero *new* dependencies when a vision
  model already runs).

محرّكات التعرّف — المرشّحات صادقة عن غيابها، والاختيار النهائي
على الجهاز بالمعيار، لا بالتخمين.

Stdlib only at the core (engines are lazy extras).
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any

from .models import OCR_REQUIREMENTS, OcrLine, OcrResult

#: Engine candidate order for ``"auto"`` (§12.5 — the OS first, the
#: classic second, the model always last as the NEXUS-native floor).
OCR_ENGINE_ORDER: tuple[str, ...] = ("winrt", "tesseract", "model")

#: The §12.5 requirement → which engine class serves it (documented,
#: refined by the device benchmark — see docs/PHASE-11-REPORT.md).
REQUIREMENT_COVERAGE: Mapping[str, tuple[str, ...]] = {
    "English": ("winrt", "tesseract", "model"),
    "numbers": ("winrt", "tesseract", "model"),
    "UI labels": ("winrt", "model"),
    "documents": ("tesseract", "model"),
}


class OcrError(Exception):
    """An OCR attempt failed — honest, with the engine that failed."""


class OcrEngine(ABC):
    """One OCR engine's contract (§12.5)."""

    #: stable engine id (reported in receipts and benchmarks).
    name: str = "abstract"

    @abstractmethod
    def available(self) -> tuple[bool, str]:
        """Honest probe — the extra/binary/model present or not."""

    @abstractmethod
    def recognize(self, png: bytes) -> OcrResult:
        """Recognize one PNG → text + per-line boxes (§12.5)."""

    def supports(self, requirement: str) -> bool:
        """Whether this engine family serves one §12.5 requirement."""
        return self.name in REQUIREMENT_COVERAGE.get(requirement, ())


# ------------------------------------------------------------------ winrt


class WinrtOcrEngine(OcrEngine):
    """``Windows.Media.Ocr`` — the OS-native candidate (lazy extra).

    Uses the ``winsdk``/``winrt`` Python projection when installed;
    honest unavailability otherwise (Linux CI, clean venvs). The
    engine needs no model download and runs offline — the natural
    NEXUS-native first candidate on the operator's box.
    """

    name = "winrt"

    def _projection(self) -> Any:
        try:
            import winsdk.windows.media.ocr as ocr  # type: ignore[import-not-found]
        except ImportError:
            try:  # the newer split packages
                import winrt.windows.media.ocr as ocr  # type: ignore[import-not-found]
            except ImportError:
                return None
        return ocr

    def available(self) -> tuple[bool, str]:
        projection = self._projection()
        if projection is None:
            return False, "no winsdk/winrt projection installed ([ocr] extra)"
        return True, "Windows.Media.Ocr (OS-native, offline)"

    def recognize(self, png: bytes) -> OcrResult:
        projection = self._projection()
        if projection is None:
            raise OcrError(
                "winrt OCR unavailable — install the [ocr] extra on Windows"
            )
        from . import _winrt_support

        return _winrt_support.recognize_png(png)


# -------------------------------------------------------------- tesseract


class TesseractOcrEngine(OcrEngine):
    """Tesseract — the classic candidate (MODE A optional extra).

    ``pytesseract`` + Pillow, lazily; needs the ``tesseract`` binary
    on PATH. Honest unavailability without them (the CI story).
    """

    name = "tesseract"

    def _modules(self) -> tuple[Any, Any] | None:
        try:
            import pytesseract  # type: ignore[import-not-found]
            from PIL import Image  # type: ignore[import-not-found]
        except ImportError:
            return None
        return pytesseract, Image

    def available(self) -> tuple[bool, str]:
        modules = self._modules()
        if modules is None:
            return False, "no pytesseract/Pillow installed ([ocr] extra)"
        pytesseract, _image = modules
        try:
            # pytesseract raises its own TesseractNotFoundError when the
            # binary is absent — the probe NEVER crashes (house law):
            version = pytesseract.get_tesseract_version()
        except Exception:  # noqa: BLE001 — the honest-unavailable path
            return False, (
                "pytesseract present but the tesseract binary is missing "
                "(apt tesseract-ocr / winget UB-Mannheim.TesseractOCR)"
            )
        if version is None:  # pragma: no cover — defensive
            return False, "tesseract binary not found"
        return True, f"tesseract {version} via pytesseract (binary on PATH)"

    def recognize(self, png: bytes) -> OcrResult:
        modules = self._modules()
        if modules is None:
            raise OcrError(
                "tesseract OCR unavailable — install the [ocr] extra"
            )
        import io

        pytesseract, image_module = modules
        image = image_module.open(io.BytesIO(png))
        try:
            data = pytesseract.image_to_data(
                image, output_type=pytesseract.Output.DICT
            )
        except OcrError:
            raise
        except Exception as exc:  # noqa: BLE001 — binary missing/crashed
            raise OcrError(f"tesseract failed: {exc}") from exc
        lines: list[OcrLine] = []
        words_by_line: dict[tuple[int, int, int], dict[str, Any]] = {}
        rows = range(len(data["text"]))
        for index in rows:
            text = str(data["text"][index]).strip()
            if not text or int(data["conf"][index]) < 0:
                continue
            key = int(data["block_num"][index]), int(
                data["par_num"][index]
            ), int(data["line_num"][index])
            slot = words_by_line.setdefault(
                key, {"words": [], "x": None, "y": None, "conf": []}
            )
            slot["words"].append(text)
            left = int(data["left"][index])
            top = int(data["top"][index])
            width = int(data["width"][index])
            height = int(data["height"][index])
            if slot["x"] is None:
                slot["box"] = [left, top, width, height]
            else:  # widen the line box as words arrive
                box = slot["box"]
                right = box[0] + box[2]
                bottom = box[1] + box[3]
                slot["box"] = [
                    min(box[0], left),
                    min(box[1], top),
                    max(right, left + width) - min(box[0], left),
                    max(bottom, top + height) - min(box[1], top),
                ]
            slot["conf"].append(float(data["conf"][index]) / 100.0)
        for slot in words_by_line.values():
            lines.append(
                OcrLine(
                    text=" ".join(slot["words"]),
                    x=slot["box"][0],
                    y=slot["box"][1],
                    width=slot["box"][2],
                    height=slot["box"][3],
                    confidence=(
                        sum(slot["conf"]) / len(slot["conf"])
                        if slot["conf"]
                        else 0.0
                    ),
                )
            )
        text = "\n".join(line.text for line in lines)
        return OcrResult(text=text, lines=lines, engine=self.name)


# ------------------------------------------------------------------- model


class ModelOcrEngine(OcrEngine):
    """The local VLM as OCR — the NEXUS-native floor candidate.

    Zero *new* dependencies when a vision model already runs; reads
    the §12.2 provider's ``analyze`` with a transcription prompt.
    """

    name = "model"

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    def available(self) -> tuple[bool, str]:
        if self._provider is None:
            return False, "no §12.2 vision provider wired"
        ok, reason = self._provider.available()
        if not ok:
            return False, f"vision provider unavailable: {reason}"
        return True, "local VLM through the §12.2 provider"

    def recognize(self, png: bytes) -> OcrResult:
        from .provider import VisionError

        if self._provider is None:
            raise OcrError("model OCR unavailable — no vision provider wired")
        try:
            report = self._provider.analyze(
                png,
                "Transcribe ALL text in this image exactly, line by line, "
                "nothing else.",
            )
        except VisionError as exc:
            raise OcrError(f"model OCR failed: {exc}") from exc
        lines = [
            OcrLine(text=piece.strip())
            for piece in report.description.splitlines()
            if piece.strip()
        ]
        text = "\n".join(line.text for line in lines)
        return OcrResult(text=text, lines=lines, engine=self.name)


# -------------------------------------------------------------- resolution


def resolve_ocr_engine(
    preference: str = "auto",
    *,
    winrt: OcrEngine | None = None,
    tesseract: OcrEngine | None = None,
    model: OcrEngine | None = None,
) -> tuple[OcrEngine | None, str]:
    """Resolve one engine from a preference (§12.5).

    ``"auto"`` walks :data:`OCR_ENGINE_ORDER` and returns the first
    *available* engine; a named engine is returned as-is (the caller
    gets its honest ``available()`` verdict). Returns
    ``(None, reason)`` when nothing is available — never a fake.
    """
    engines: dict[str, OcrEngine | None] = {
        "winrt": winrt if winrt is not None else WinrtOcrEngine(),
        "tesseract": tesseract if tesseract is not None else TesseractOcrEngine(),
        "model": model,
    }
    if preference != "auto" and preference not in engines:
        raise OcrError(
            f"unknown OCR engine {preference!r} "
            f"(expected 'auto' or one of {list(engines)})"
        )
    if preference != "auto":
        engine = engines[preference]
        if engine is None:
            return None, f"engine {preference!r} not wired in this runtime"
        return engine, "named preference"
    for name in OCR_ENGINE_ORDER:
        engine = engines.get(name)
        if engine is None:
            continue
        ok, _reason = engine.available()
        if ok:
            return engine, f"auto → {name}"
    return None, "no OCR engine available on this runtime (honest)"


def character_error_rate(expected: str, recognized: str) -> float:
    """Levenshtein CER (pure) — the §12.5 benchmark metric.

    Case- and whitespace-normalized (OCR reads glyphs, not cases);
    0.0 is perfect, 1.0 is total mismatch.
    """
    left = _normalize(expected)
    right = _normalize(recognized)
    if not left:
        return 0.0 if not right else 1.0
    if not right:
        return 1.0
    if left == right:
        return 0.0
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            cost = 0 if left_char == right_char else 1
            current.append(
                min(
                    previous[j] + 1,      # deletion
                    current[j - 1] + 1,   # insertion
                    previous[j - 1] + cost,  # substitution
                )
            )
        previous = current
    return previous[-1] / len(left)


def _normalize(text: str) -> str:
    return " ".join(text.casefold().split())


def timed_recognize(
    engine: OcrEngine, png: bytes
) -> tuple[OcrResult, float]:
    """One timed recognition (the benchmark's atom — pure plumbing)."""
    started = time.perf_counter()
    result = engine.recognize(png)
    elapsed = time.perf_counter() - started
    return result, elapsed


def requirements_satisfied(engine: OcrEngine) -> tuple[str, ...]:
    """The §12.5 requirements one engine family covers (documented)."""
    return tuple(
        requirement
        for requirement in OCR_REQUIREMENTS
        if engine.supports(requirement)
    )


def parse_requirement_list(raw: Sequence[str]) -> tuple[str, ...]:
    """Validate §12.5 requirement names against the verbatim set."""
    unknown = [item for item in raw if item not in OCR_REQUIREMENTS]
    if unknown:
        raise OcrError(
            f"unknown OCR requirements {unknown} "
            f"(expected {list(OCR_REQUIREMENTS)})"
        )
    return tuple(raw)


__all__ = [
    "OCR_ENGINE_ORDER",
    "OcrEngine",
    "OcrError",
    "REQUIREMENT_COVERAGE",
    "ModelOcrEngine",
    "TesseractOcrEngine",
    "WinrtOcrEngine",
    "character_error_rate",
    "parse_requirement_list",
    "requirements_satisfied",
    "resolve_ocr_engine",
    "timed_recognize",
]
