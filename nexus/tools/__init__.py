"""Tool System (Final Build Plan §8) — Registry · Router · Native · MCP.

* :mod:`nexus.tools.models`    — the §8.1 records (nine fields, risk 0..4,
                                  verification contracts, traces)
* :mod:`nexus.tools.registry`  — the §8.1 Tool Registry (validated,
                                  version-aware, freezable)
* :mod:`nexus.tools.router`    — the §8.2 Tool Router (the verbatim
                                  seven-stage pipeline) + the §6.2 sink
* :mod:`nexus.tools.native`    — the §8.3 nine native tools (stdlib)
* :mod:`nexus.tools.mcp`       — the §8.4 official-SDK interop behind
                                  the router; §8.5 server declarations

:func:`build_tool_system` composes one runtime's tool surface:
native tools (optional workspace root), MCP servers (optional,
config/tools/mcp.toml, enabled-only, per-server honest failure),
the router over the injected engines, and the :class:`RoutedToolSink`
the §6.2 Agent Loop dispatches through — the Phase-5 ``ToolSink``
aperture with the Phase-6 ``pre_tool_call`` veto still in front.

نظام الأدوات — سجلّ وموجّه وتسع أدوات أصلية وطبقة MCP،
وكلها خلف بوابة واحدة.

Stdlib only at the core (the official MCP SDK is MODE A optional).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .mcp import McpServerConfig, load_mcp_servers
from .mcp.adapter import McpAdapter, connect_from_config
from .models import (
    CapabilityReport,
    RouterTrace,
    ToolCallResult,
    ToolDefinition,
    ToolOutcome,
    VerificationReport,
    VerificationSpec,
)
from .native import register_native_tools
from .registry import RegisteredTool, RegistryError, ToolRegistry
from .router import ConfirmationRequest, RoutedToolSink, ToolRouter

logger = logging.getLogger("nexus.tools")

__all__ = [
    "build_tool_system",
    "CapabilityReport",
    "ConfirmationRequest",
    "McpAdapter",
    "McpServerConfig",
    "RegistryError",
    "RegisteredTool",
    "RouterTrace",
    "RoutedToolSink",
    "ToolCallResult",
    "ToolDefinition",
    "ToolOutcome",
    "ToolRegistry",
    "ToolRouter",
    "VerificationReport",
    "VerificationSpec",
    "load_mcp_servers",
    "register_native_tools",
]


def build_tool_system(
    *,
    registry: ToolRegistry | None = None,
    native: bool = True,
    computer: bool = False,
    browser: bool = False,
    vision: bool = False,
    workspace_root: Path | None = None,
    mcp_servers: tuple[McpServerConfig, ...] | None = None,
    mcp_config_file: Path | None = None,
    policy_engine: Any = None,
    resources: Any = None,
    bus: Any = None,
    confirm_danger_above: int = 2,
    confirmation_hook: Any = None,
    allow_network: bool = True,
) -> tuple[ToolRegistry, ToolRouter, McpAdapter | None, dict[str, Any]]:
    """Compose one tool surface: registry + router + native + MCP.

    Returns ``(registry, router, mcp_adapter, report)`` — the adapter
    is ``None`` when no MCP server is enabled/available (the native
    tools keep working; the report says why, honestly). ``computer``
    adds the three §9.1 mechanics records (mouse · keyboard · uia)
    on top of the §8.3 nine — **opt-in** here (the Phase-7 nine-only
    default stays byte for byte); the runtime passes
    ``tools.computer_enabled`` (default true) explicitly. ``browser``
    adds the §11.1 Playwright record (thirteenth, additive — the
    runtime passes ``tools.browser_enabled``). ``vision`` adds the
    §12 ``vision`` record (fourteenth, additive — the runtime passes
    ``tools.vision_enabled``).
    """
    tool_registry = registry if registry is not None else ToolRegistry()
    report: dict[str, Any] = {
        "native": False, "computer": False, "browser": False,
        "vision": False, "mcp": None,
    }
    if native:
        names = register_native_tools(tool_registry, workspace_root=workspace_root)
        report["native"] = list(names)
    if computer:
        # Imported lazily (§0.4): nexus.computer imports the tool pack
        # at module level — importing it here keeps the cycle closed
        # only at wiring time, exactly like the runtime does.
        from ..computer import register_computer_tools

        computer_names = register_computer_tools(tool_registry)
        report["computer"] = list(computer_names)
    if browser:
        # Imported lazily (§0.4): nexus.browser pulls the tool pack,
        # a module-level import would close a cycle at import time.
        from ..browser import register_browser_tools

        browser_names = register_browser_tools(tool_registry)
        report["browser"] = list(browser_names)
    if vision:
        # Imported lazily (§0.4): nexus.vision pulls the native tool
        # pack (and nexus.tools via the layer) — wiring-time only.
        from ..vision.tools import register_vision_tools

        vision_names = register_vision_tools(tool_registry)
        report["vision"] = list(vision_names)
    adapter: McpAdapter | None = None
    if mcp_servers is None and mcp_config_file is not None:
        mcp_servers = load_mcp_servers(mcp_config_file)
    if mcp_servers:
        adapter, mcp_report = connect_from_config(
            tool_registry, mcp_servers, mcp_toml=mcp_config_file
        )
        report["mcp"] = mcp_report
    router = ToolRouter(
        tool_registry,
        policy_engine=policy_engine,
        resources=resources,
        bus=bus,
        confirm_danger_above=confirm_danger_above,
        confirmation_hook=confirmation_hook,
        allow_network=allow_network,
    )
    return tool_registry, router, adapter, report
