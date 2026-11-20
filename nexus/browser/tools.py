"""Browser tool registration + the §9.5 DOM layer (Plan §11 wiring).

* :func:`register_browser_tools` — the §8.1 ``browser`` record on the
  registry (additive: the Phase-9 twelve records stay untouched).
* :class:`BrowserDomLayer` — the **dom_a11y** rung of the §9.5 chain:
  browser-capable actions (click · type · set_value · inspect with a
  selector) resolve here, before vision or raw input ever fire. The
  layer routes through the §8.2 router — the chain stays a chain of
  router clients, not a second gate.

Stdlib only.
"""

from __future__ import annotations

from typing import Any

from ..computer.hierarchy import ActionTarget, LayerProvider, LayerResult
from ..tools.native.base import register_native_tool
from ..tools.native.browser import BrowserTool
from ..tools.registry import ToolRegistry

#: The §8.1 browser tool name (verbatim).
BROWSER_TOOL_NAMES: tuple[str, ...] = ("browser",)


def register_browser_tools(registry: ToolRegistry) -> tuple[str, ...]:
    """Register the §11.1 browser record (risk-rated §8.1).

    The twelve Phase-7/8/9 records are **not** touched — this is the
    thirteenth, additive, exactly like the Phase-8 mechanics records.
    """
    register_native_tool(registry, BrowserTool())
    return BROWSER_TOOL_NAMES


class BrowserDomLayer(LayerProvider):
    """The §9.5 ``dom_a11y`` rung over the browser tool.

    Availability is honest: it requires the Playwright library and a
    registered ``browser`` tool — otherwise the chain skips straight
    to vision/input, exactly as Phase 8 designed.
    """

    name = "dom_a11y"

    def __init__(self, router: Any = None) -> None:
        self._router = router

    def available(self) -> tuple[bool, str]:
        ok, reason = playwright_library()
        if not ok:
            return False, reason
        if self._router is None:
            return False, "no router wired (layer is chain-only)"
        registered = self._router.registry.get("browser")
        if registered is None:
            return False, "browser tool not registered"
        return True, "playwright + browser tool behind the §8.2 router"

    def act(self, target: ActionTarget) -> LayerResult | None:
        if target.action not in ("click", "invoke", "type", "set_value", "inspect"):
            return None  # unsupported for this layer — the chain moves on
        selector = target.name or ""
        if not selector:
            return None
        arguments: dict[str, Any] = {
            "op": "read" if target.action == "inspect"
            else "click" if target.action in ("click", "invoke")
            else "fill",
            "selector": selector,
            "session": "agent",
        }
        if target.action in ("type", "set_value") and target.value:
            arguments["text"] = target.value
        outcome = self._router.route(
            "browser", arguments, agent_id="dom-layer"
        )
        if not outcome.ok:
            from ..computer.hierarchy import LayerError

            raise LayerError(f"dom_a11y layer failed: {outcome.error}")
        return LayerResult(
            layer=self.name,
            summary=f"dom_a11y {target.action} → {selector[:60]}",
            artifacts={"output": outcome.output},
        )


def playwright_library() -> tuple[bool, str]:
    from .engine import PlaywrightEngine  # noqa: PLC0415 — lazy probe

    return PlaywrightEngine.library_available()


__all__ = [
    "BROWSER_TOOL_NAMES",
    "BrowserDomLayer",
    "register_browser_tools",
]
