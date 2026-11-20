"""Native tools pack (Final Build Plan §8.3) — the nine, verbatim.

    filesystem · terminal · process · hardware · windows ·
    clipboard · screen · git · github

Each is one §8.1 ToolDefinition behind the §8.2 router. The
filesystem and screen tools resolve relative paths against the
injected workspace root. Platform-honest tools (windows/clipboard/
screen) stay registered even where unavailable — discovery reports
the reason; the tool never fakes a result.

الحزمة الأصلية — الأدوات التسع حرفيًا، كل واحدة سجلّ §8.1
خلف موجّه §8.2.

Stdlib only.
"""

from __future__ import annotations

from pathlib import Path

from ..registry import ToolRegistry
from .base import register_native_tool
from .clipboard import ClipboardTool
from .filesystem import FilesystemTool
from .git import GitTool
from .github import GithubTool
from .hardware import HardwareTool
from .process import ProcessTool
from .screen import ScreenTool
from .terminal import TerminalTool
from .windows import WindowsTool

#: The §8.3 tool names, verbatim order.
NATIVE_TOOL_NAMES: tuple[str, ...] = (
    "filesystem",
    "terminal",
    "process",
    "hardware",
    "windows",
    "clipboard",
    "screen",
    "git",
    "github",
)


def register_native_tools(
    registry: ToolRegistry, *, workspace_root: Path | None = None
) -> tuple[str, ...]:
    """Register the nine §8.3 tools; returns their dispatch names."""
    tools: list[tuple[str, object]] = [
        ("filesystem", FilesystemTool(workspace_root=workspace_root)),
        ("terminal", TerminalTool()),
        ("process", ProcessTool()),
        ("hardware", HardwareTool()),
        ("windows", WindowsTool()),
        ("clipboard", ClipboardTool()),
        ("screen", ScreenTool(workspace_root=workspace_root)),
        ("git", GitTool()),
        ("github", GithubTool()),
    ]
    for _name, tool in tools:
        register_native_tool(registry, tool)  # type: ignore[arg-type]
    return NATIVE_TOOL_NAMES
