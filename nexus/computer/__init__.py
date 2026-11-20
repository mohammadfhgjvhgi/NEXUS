"""Windows Computer Runtime (Final Build Plan §9).

* :mod:`nexus.computer.api`          — §9.1 Computer API (eight
                                       domains, thin router clients)
* :mod:`nexus.computer.hierarchy`    — §9.5 fallback chain (five
                                       layers, honest traces)
* :mod:`nexus.computer.uia_native`   — §9.4 native UIA client
                                       (ctypes COM, first layer)
* :mod:`nexus.computer.input_engine` — §9.2 transports (ADAPTed from
                                       windows-harness: foreground +
                                       message, honest refusal)
* :mod:`nexus.computer.adapters`     — §9.3 pywinauto backend (MODE
                                       A «USE», optional extra)

:func:`register_computer_tools` adds the three §9.1 mechanics records
(``mouse`` · ``keyboard`` · ``uia``) to a registry — the §8.3 nine
stay untouched (Phase 7, byte for byte). :func:`build_computer_runtime`
composes the §9.1 façade over a live router.

Everything the computer does passes the §8.2 router — one choke point
per effect, the §9.5 chain for orchestration only.

زمن تشغيل الحاسوب — الواجهة والسلسلة والطبقات الثلاث،
وكل تأثير حقيقي خلف الموجّه نفسه.

Stdlib only at the core (pywinauto is MODE A optional).
"""

from __future__ import annotations

from typing import Any

from ..tools.models import CapabilityReport
from ..tools.native.base import register_native_tool
from ..tools.native.keyboard import KeyboardTool
from ..tools.native.mouse import MouseTool
from ..tools.native.uia import UiaTool
from ..tools.registry import ToolRegistry
from . import uia_native
from .api import COMPUTER_DOMAINS, ComputerError, ComputerRuntime
from .hierarchy import (
    HIERARCHY_LAYERS,
    ActionTarget,
    HierarchyChain,
    HierarchyError,
    LayerError,
    LayerProvider,
    LayerResult,
)

#: The §9.1 mechanics tools, verbatim order.
COMPUTER_TOOL_NAMES: tuple[str, ...] = ("mouse", "keyboard", "uia")

__all__ = [
    "COMPUTER_DOMAINS",
    "COMPUTER_TOOL_NAMES",
    "HIERARCHY_LAYERS",
    "ActionTarget",
    "ComputerError",
    "ComputerRuntime",
    "HierarchyChain",
    "HierarchyError",
    "LayerError",
    "LayerProvider",
    "LayerResult",
    "build_computer_runtime",
    "register_computer_tools",
    "uia_native",
]


def register_computer_tools(registry: ToolRegistry) -> tuple[str, ...]:
    """Register the three §9.1 mechanics records (risk-rated §8.1).

    The nine §8.3 tools are **not** touched — Phase 7 behaviour stays
    byte for byte; these are additive records on the same registry.
    """
    for tool in (MouseTool(), KeyboardTool(), UiaTool()):
        register_native_tool(registry, tool)
    return COMPUTER_TOOL_NAMES


def build_computer_runtime(
    router: Any,
    *,
    policy: Any = None,
    workspace_id: str | None = None,
    agent_id: str = "computer",
) -> ComputerRuntime:
    """Compose the §9.1 Computer API over a live §8.2 router."""
    return ComputerRuntime(
        router, policy=policy, workspace_id=workspace_id, agent_id=agent_id
    )


def capability_summary() -> dict[str, Any]:
    """A static summary (probes live on the tools, not the package)."""
    return {
        "domains": list(COMPUTER_DOMAINS),
        "layers": list(HIERARCHY_LAYERS),
        "tools": list(COMPUTER_TOOL_NAMES),
        "uia_native": CapabilityReport(
            available=uia_native.available(),
            reason="ctypes COM client" if uia_native.available() else "win32-only",
        ).to_dict(),
    }
