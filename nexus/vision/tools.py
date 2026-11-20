"""Vision tool registration + the §9.5 wiring (Plan §12 wiring).

* :func:`register_vision_tools` — the §8.1 ``vision`` record on the
  registry (additive: the Phase-10 thirteen records stay untouched —
  this is the fourteenth).
* :class:`VisionLayer` is re-exported from :mod:`nexus.vision.layer`
  (the §9.5 rung) — one import site for the runtime wiring.

Stdlib only.
"""

from __future__ import annotations

from ..tools.native.base import register_native_tool
from ..tools.native.vision import VisionTool
from ..tools.registry import ToolRegistry

#: The §8.1 vision tool name (verbatim).
VISION_TOOL_NAMES: tuple[str, ...] = ("vision",)


def register_vision_tools(registry: ToolRegistry) -> tuple[str, ...]:
    """Register the §12 ``vision`` record (fourteenth, additive).

    The Phase-7/8/9/10 records are **not** touched — additive, like
    every phase record since the eight.
    """
    register_native_tool(registry, VisionTool())
    return VISION_TOOL_NAMES


__all__ = ["VISION_TOOL_NAMES", "VisionTool", "register_vision_tools"]
