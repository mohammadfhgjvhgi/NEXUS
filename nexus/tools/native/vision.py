"""Native tool: ``vision`` (Final Build Plan §12 — the §8.1 record).

The fourteenth record, additive (the Phase-10 thirteen stay
untouched). The §12 surface behind the §8.2 choke point:

* **capture** — §12.1 ``full | window | region`` → one scope-checked
  PNG path (the only mutating op: it *writes* the evidence file).
* **analyze · locate · classify · compare** — §12.2 over the wired
  :class:`~nexus.vision.provider.VisionProvider`, reading the image
  from a scope-checked path.
* **ocr** — §12.5 through the resolved engine (the device
  benchmark's verdict), same path discipline.

Risk 1 — reading pixels and running inference; no input injection,
no mutation beyond the capture artifact. Verification contracts
bind to keys the handler **always** emits (the Phase-10 lesson).

الرؤية خلف الموجّه — لقطة وسؤال وتعرّف، والمسار خاضع للنطاق.

Stdlib only at this layer (provider/OCR engines wire lazily).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ..models import (
    CapabilityReport,
    ScopeRequirements,
    ToolCallResult,
    ToolDefinition,
    VerificationSpec,
)
from ..models import VerificationStrategy as V
from .base import (
    NativeTool,
    ToolArgError,
    object_schema,
    optional_str,
    output_schema,
    require_int,
    require_operation,
    require_str,
)

#: The §12.1/§12.2/§12.5 operations on the vision record.
_OPERATIONS: tuple[str, ...] = (
    "capture",
    "analyze",
    "locate",
    "classify",
    "compare",
    "ocr",
)

_MUTATING: frozenset[str] = frozenset({"capture"})

#: The §12.5 default OCR preference (the device benchmark may pin
#: a named engine via config ``tools.vision_ocr_engine``).
_DEFAULT_OCR_PREFERENCE = "auto"


def _provider() -> Any:
    """The process-wide §12.2 provider (set by the runtime wiring)."""
    from ...vision import provider_state

    return provider_state.get_provider()


def _ocr_preference() -> str:
    from ...vision import provider_state

    return provider_state.get_ocr_preference()


class VisionTool(NativeTool):
    """§12 ``vision`` — capture + the four verbs + OCR, risk 1."""

    name = "vision"

    def __init__(self, *, workspace_root: Any = None) -> None:
        self._root = workspace_root

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            id="native:vision",
            name=self.name,
            description=(
                "Vision capability (§12): capture(mode=full|window|"
                "region, path), analyze(path, question), locate(path, "
                "description), classify(path, categories), compare(path, "
                "path_b), ocr(path). PNG I/O, scope-checked paths."
            ),
            input_schema=object_schema(
                {
                    "op": {"type": "string", "enum": list(_OPERATIONS)},
                    "mode": {
                        "type": "string",
                        "enum": ["full", "window", "region"],
                        "description": "§12.1 capture mode",
                    },
                    "path": {
                        "type": "string",
                        "description": "image path (capture output / analysis input)",
                    },
                    "path_b": {
                        "type": "string",
                        "description": "second image (compare)",
                    },
                    "hwnd": {"type": "integer", "description": "window handle"},
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "w": {"type": "integer"},
                    "h": {"type": "integer"},
                    "question": {"type": "string"},
                    "description": {"type": "string"},
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                required=("op",),
            ),
            output_schema=output_schema(
                "capture receipt / vision report / located element / "
                "classification / comparison / ocr text"
            ),
            permissions=("screen.read", "vision.use"),
            scope_requirements=ScopeRequirements(
                path_arguments=("path", "path_b"),
                mutating_operations=("capture",),
                dimensions=("display",),
            ),
            risk=1,
            verification=VerificationSpec(V.NONE),
            version="1.0.0",
        )

    def verification_for(self, operation: str) -> VerificationSpec:
        # Contracts bind to artifact keys the handler ALWAYS emits
        # (the Phase-10 §8.2 lesson — never name a conditional key).
        contracts: dict[str, tuple[str, str]] = {
            "capture": ("path_size", ""),
            "analyze": ("json_field", "report"),
            "locate": ("json_field", "found"),
            "classify": ("json_field", "category"),
            "compare": ("json_field", "same"),
            "ocr": ("json_field", "text"),
        }
        strategy, argument = contracts.get(operation, ("none", ""))
        return VerificationSpec(getattr(V, strategy.upper()), argument)

    def handler(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        operation = require_operation(arguments, _OPERATIONS)
        if operation == "capture":
            return self._capture(arguments)
        return self._inference(operation, arguments)

    # ------------------------------------------------------------ capture

    def _capture(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        from pathlib import Path

        from ...vision.capture import (
            CaptureError,
            capture_full_screen,
            capture_region,
            capture_window,
        )
        from ...vision.models import ScreenRegion

        mode = require_str(arguments, "mode") if "mode" in arguments else "full"
        raw_path = optional_str(arguments, "path") or "vision_capture.png"
        path = Path(raw_path)
        if not path.is_absolute() and self._root is not None:
            path = self._root / path
        try:
            if mode == "full":
                result = capture_full_screen()
            elif mode == "window":
                hwnd = require_int(
                    arguments, "hwnd", default=0, low=1, high=1 << 48
                )
                result = capture_window(hwnd)
            elif mode == "region":
                region = ScreenRegion(
                    require_int(arguments, "x", default=0, low=-1 << 15, high=1 << 15),
                    require_int(arguments, "y", default=0, low=-1 << 15, high=1 << 15),
                    require_int(arguments, "w", default=0, low=0, high=1 << 15),
                    require_int(arguments, "h", default=0, low=0, high=1 << 15),
                )
                if region.width < 1 or region.height < 1:
                    raise CaptureError("region capture needs w and h ≥ 1")
                result = capture_region(region)
            else:
                raise CaptureError(f"unknown capture mode {mode!r}")
        except CaptureError as exc:
            raise ToolArgError("op", f"vision capture failed: {exc}") from exc
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(result.png)
        return ToolCallResult(
            output=(
                f"vision capture {mode} {result.width}x{result.height} → "
                f"{path} ({len(result.png)} bytes PNG)"
            ),
            artifacts={
                "path": str(path),
                "bytes": len(result.png),
                "size": {"width": result.width, "height": result.height},
                "capture": result.to_dict(),
            },
        )

    # ---------------------------------------------------------- inference

    def _inference(
        self, operation: str, arguments: Mapping[str, Any]
    ) -> ToolCallResult:
        from ...vision.provider import VisionError

        if operation == "ocr":
            return self._ocr(arguments)

        provider = _provider()
        if provider is None:
            raise ToolArgError(
                "op",
                "no §12.2 vision provider wired (vision inference needs "
                "the model runtime)",
            )
        png = self._read_image(arguments, "path")
        try:
            if operation == "analyze":
                question = require_str(arguments, "question")
                report = provider.analyze(png, question)
                return ToolCallResult(
                    output=f"analyze → {report.description[:120]}",
                    artifacts={"report": report.to_dict()},
                )
            if operation == "locate":
                description = require_str(arguments, "description")
                element = provider.locate(png, description)
                found = element is not None
                return ToolCallResult(
                    output=(
                        f"locate {description[:60]!r} → "
                        + (
                            f"bbox {element.x},{element.y},"
                            f"{element.width}x{element.height}"
                            if element
                            else "not found"
                        )
                    ),
                    artifacts={
                        "found": found,
                        "element": element.to_dict() if element else None,
                    },
                )
            if operation == "classify":
                categories = self._categories(arguments)
                verdict = provider.classify(png, categories)
                return ToolCallResult(
                    output=(
                        f"classify → {verdict.category or '(none)'} "
                        f"({verdict.confidence:.2f})"
                    ),
                    artifacts={"category": verdict.category,
                               "classification": verdict.to_dict()},
                )
            if operation == "compare":
                png_b = self._read_image(arguments, "path_b", required=True)
                comparison = provider.compare(png, png_b)
                return ToolCallResult(
                    output=(
                        f"compare → same={comparison.same} "
                        f"similarity={comparison.similarity:.2f}"
                    ),
                    artifacts={"same": comparison.same,
                               "comparison": comparison.to_dict()},
                )
        except VisionError as exc:
            raise ToolArgError("op", f"vision {operation} failed: {exc}") from exc
        raise ToolArgError("op", f"unknown vision operation {operation!r}")

    def _ocr(self, arguments: Mapping[str, Any]) -> ToolCallResult:
        from ...vision.ocr import OcrError, resolve_ocr_engine

        png = self._read_image(arguments, "path")
        engine, reason = resolve_ocr_engine(_ocr_preference())
        if engine is None:
            raise ToolArgError("op", f"no OCR engine available: {reason}")
        try:
            result = engine.recognize(png)
        except OcrError as exc:
            raise ToolArgError("op", f"ocr failed: {exc}") from exc
        return ToolCallResult(
            output=(
                f"ocr[{result.engine}] {result.word_count} words → "
                f"{result.text[:120]!r}"
            ),
            artifacts={"text": result.text, "ocr": result.to_dict()},
        )

    # ------------------------------------------------------------ helpers

    def _read_image(
        self,
        arguments: Mapping[str, Any],
        key: str,
        *,
        required: bool = False,
    ) -> bytes:
        from pathlib import Path

        raw = optional_str(arguments, key)
        if raw is None:
            if required:
                raise ToolArgError(key, f"the {key} image path is required")
            raise ToolArgError(
                key, "an image path is required (capture writes one first)"
            )
        path = Path(raw)
        if not path.is_absolute() and self._root is not None:
            path = self._root / path
        if not path.is_file():
            raise ToolArgError(key, f"no image at {path}")
        data = path.read_bytes()
        if not data:
            raise ToolArgError(key, f"empty image file {path}")
        return data

    @staticmethod
    def _categories(arguments: Mapping[str, Any]) -> list[str]:
        raw = arguments.get("categories")
        if isinstance(raw, str):
            raw = [piece.strip() for piece in raw.split(",")]
        if not isinstance(raw, Sequence) or isinstance(raw, (bytes, str)):
            raise ToolArgError(
                "categories", "a list of category strings is required"
            )
        categories = [str(item).strip() for item in raw]
        categories = [item for item in categories if item]
        if not categories:
            raise ToolArgError("categories", "at least one category is required")
        return categories

    def capabilities(self) -> CapabilityReport:
        """The §12 surface is per-op honest (partial capability counts).

        ``capture`` needs win32 GDI; the inference verbs need the
        wired §12.2 provider; ``ocr`` needs any resolvable §12.5
        engine — the tool is available when **any** of its families
        can serve, and the reason names exactly which (a capture
        refused at execute is data, not a platform lie).
        """
        from ...vision.capture import capture_available

        capture_ok, capture_reason = capture_available()
        parts: list[str] = []
        available = False
        if capture_ok:
            available = True
            parts.append(f"capture: {capture_reason}")
        else:
            parts.append(f"capture: {capture_reason}")
        provider = _provider()
        if provider is not None:
            provider_ok, provider_reason = provider.available()
            parts.append(f"inference: {provider_reason}")
            available = available or provider_ok
        else:
            parts.append("inference: no provider wired (verbs refuse)")
        try:
            from ...vision.ocr import resolve_ocr_engine

            engine, engine_reason = resolve_ocr_engine(_ocr_preference())
            if engine is not None:
                parts.append(f"ocr: {engine.name} ({engine_reason})")
                available = True
            else:
                parts.append(f"ocr: {engine_reason}")
        except Exception:  # noqa: BLE001 — the probe never crashes
            parts.append("ocr: probe failed")
        return CapabilityReport(available=available, reason="; ".join(parts))


__all__ = ["VisionTool"]
