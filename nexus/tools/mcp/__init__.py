"""MCP interop layer (Final Build Plan §8.4/§8.5).

Repository: **modelcontextprotocol** — the interoperability layer.
NEXUS uses the **official Python SDK** (the v2 stable line, MODE A
pinned optional dependency ``nexus[mcp]``) *behind the NEXUS Tool
Router*, exactly as the plan mandates: every MCP tool is registered
as a §8.1 ToolDefinition and every call passes the §8.2 gates
(permission · scope · resource) **before** any stdio byte reaches
the server (Spec §71: كل MCP tool يمر بـNEXUS gate).

§8.5: clone only what the task needs — ``filesystem`` · ``git`` ·
``fetch`` · ``memory`` · ``database`` — every server declared in
``config/tools/mcp.toml`` behind NEXUS permission + NEXUS scope.

* :mod:`nexus.tools.mcp.config` — server declarations + loader;
* :mod:`nexus.tools.mcp.adapter` — the SDK adapter (session thread,
  tools/list → registry, tools/call, honest failure + respawn).

طبقة التوافق — الـSDK الرسمي خلف موجّه NEXUS، وكل أداة MCP
تسجل كسجلّ §8.1 وتخضع للبوابات قبل أي اتصال.

Stdlib core; the official ``mcp`` SDK is an optional MODE A extra.
"""

from .adapter import McpAdapter, sdk_available, sdk_version
from .config import McpServerConfig, load_mcp_servers

__all__ = [
    "McpServerConfig",
    "load_mcp_servers",
    "McpAdapter",
    "sdk_available",
    "sdk_version",
]
