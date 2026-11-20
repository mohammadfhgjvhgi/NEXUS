"""The §9.5 Vision rung (Final Build Plan §12 wiring).

``nexus/computer/hierarchy.py`` has carried the ``"vision"`` slot
since Phase 8 with *no provider* — the chain degraded honestly.
Phase 11 fills the fourth of five rungs:

* **inspect** → the provider's ``analyze`` (what am I looking at?).
* **click / invoke** → ``locate`` the target by description, then
  the real mouse click at the located center — through the router
  (the chain stays a chain of router clients, no second gate).
* **type / set_value** → locate, click, then keyboard ``type`` —
  exactly the §9.5 contract: elegant layers first, primitive last.

Availability is honest: win32 capture + a §12.2 provider + the
computer runtime's mouse/keyboard — or the rung reports why and
the chain falls to input.

الحلقة الرابعة — عيّن فوصف، وانقر فحدّد ثم أرسل، والصراحة
متى غاب المحرك.

Stdlib only.
"""

from __future__ import annotations

import sys
from typing import Any

from ..computer.hierarchy import (
    ActionTarget,
    LayerError,
    LayerProvider,
    LayerResult,
)
from .capture import CaptureError, capture_full_screen, capture_window
from .models import LocatedElement


class VisionLayer(LayerProvider):
    """The §9.5 ``vision`` rung over the §12.2 provider + capture."""

    name = "vision"

    def __init__(
        self,
        computer_runtime: Any,
        provider: Any,
        *,
        capture: Any = None,
    ) -> None:
        self._runtime = computer_runtime
        self._provider = provider
        self._capture = capture  # None → the production Win32Gdi path

    # ------------------------------------------------------------- probe

    def available(self) -> tuple[bool, str]:
        if sys.platform != "win32" and self._capture is None:
            return False, f"win32 capture required (this runtime is {sys.platform})"
        if self._provider is None:
            return False, "no §12.2 vision provider wired"
        ok, reason = self._provider.available()
        if not ok:
            return False, f"vision provider unavailable: {reason}"
        if self._runtime is None:
            return False, "no computer runtime (layer is chain-only)"
        return True, "§12.2 provider + GDI capture + router input"

    # --------------------------------------------------------------- act

    def act(self, target: ActionTarget) -> LayerResult | None:
        if target.action not in (
            "inspect", "click", "invoke", "type", "set_value",
        ):
            return None  # unsupported — the chain moves on
        try:
            image = self._screen_image(target.hwnd)
        except CaptureError as exc:
            raise LayerError(f"vision capture failed: {exc}") from exc

        if target.action == "inspect":
            return self._inspect(image)
        # click/invoke/type/set_value all start by locating the target
        description = target.name or ""
        if not description:
            raise LayerError(
                "vision layer requires target.name (the description to locate)"
            )
        element = self._locate(image, description)
        if element is None:
            raise LayerError(
                f"vision could not locate {description!r} on screen"
            )
        if target.action in ("click", "invoke"):
            return self._click(element)
        return self._type(element, target.value or "")

    # ------------------------------------------------------------ pieces

    def _screen_image(self, hwnd: int | None) -> bytes:
        """The §12.1 capture that feeds this action."""
        if hwnd and self._capture is None:
            result = capture_window(hwnd)
            return result.png
        if hwnd and self._capture is not None:
            result = capture_window(hwnd, backend=self._capture)
            return result.png
        if self._capture is not None:
            result = capture_full_screen(backend=self._capture)
        else:
            result = capture_full_screen()
        return result.png

    def _inspect(self, image: bytes) -> LayerResult:
        from .provider import VisionError

        try:
            report = self._provider.analyze(
                image, "Describe the UI: windows, controls, and state."
            )
        except VisionError as exc:
            raise LayerError(f"vision analyze failed: {exc}") from exc
        return LayerResult(
            layer=self.name,
            summary=f"vision inspect → {report.description[:80]}",
            artifacts={"report": report.to_dict()},
        )

    def _locate(self, image: bytes, description: str) -> LocatedElement | None:
        from .provider import VisionError

        try:
            return self._provider.locate(image, description)
        except VisionError as exc:
            raise LayerError(f"vision locate failed: {exc}") from exc

    def _click(self, element: LocatedElement) -> LayerResult:
        x, y = element.center()
        outcome = self._runtime.mouse("click", x=x, y=y)
        if not outcome.ok:
            raise LayerError(f"vision click failed: {outcome.error}")
        return LayerResult(
            layer=self.name,
            summary=(
                f"vision located {element.description[:40]!r} → "
                f"click ({x}, {y})"
            ),
            artifacts={"bbox": element.to_dict(), "point": [x, y]},
        )

    def _type(self, element: LocatedElement, value: str) -> LayerResult:
        x, y = element.center()
        click = self._runtime.mouse("click", x=x, y=y)
        if not click.ok:
            raise LayerError(f"vision focus click failed: {click.error}")
        typed = self._runtime.keyboard("type", text=value)
        if not typed.ok:
            raise LayerError(f"vision type failed: {typed.error}")
        return LayerResult(
            layer=self.name,
            summary=(
                f"vision located {element.description[:40]!r} → "
                f"click ({x}, {y}) + type {len(value)} chars"
            ),
            artifacts={
                "bbox": element.to_dict(),
                "point": [x, y],
                "typed": len(value),
            },
        )


__all__ = ["VisionLayer"]
