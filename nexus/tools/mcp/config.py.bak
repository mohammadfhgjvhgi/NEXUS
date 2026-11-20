"""MCP server declarations (Final Build Plan §8.5).

``config/tools/mcp.toml`` — array-of-tables ``[[servers]]``, each:

===================  ====================================================
``name``             dispatch family (filesystem, git, fetch, memory, …)
``command``          the stdio launch binary (npx / uvx / python…)
``args``             argv list (never a shell string)
``enabled``          default true — false skips the server entirely
``risk_ceiling``     0..3 clamp applied to every tool of this server
``allowed_tools``    ``["*"]`` or an explicit MCP tool-name list
``blocked_tools``    MCP tool names refused *before* any stdio write
``scope_paths``      path arguments NEXUS scope-checks per call
``call_timeout``     seconds per tools/call (default 60)
===================  ====================================================

The five §8.5 names ship as the commented defaults — **clone only
what the task needs**: the launch commands reference the audited
official servers (modelcontextprotocol/servers @ pinned commits —
see docs/REPOSITORY-INTEGRATION.md, Round 4); ``database`` is the
archived sqlite server. Every entry is behind NEXUS permission +
NEXUS scope by construction (the router owns the gates).

إعلانات خوادم MCP — جدول لكل خادم، والخمسة المسمّاة هي
الافتراضية المُعلّقة، وكل خادم خلف صلاحية ونطاق NEXUS.

Stdlib only.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

#: The five §8.5 server names, verbatim.
CANONICAL_SERVER_NAMES: tuple[str, ...] = (
    "filesystem",
    "git",
    "fetch",
    "memory",
    "database",
)

_DEFAULT_TIMEOUT = 60


class McpConfigError(Exception):
    """Invalid MCP server declaration."""


@dataclass(frozen=True, slots=True)
class McpServerConfig:
    """One stdio MCP server declaration (§8.5) behind NEXUS gates."""

    name: str
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    risk_ceiling: int = 2
    allowed_tools: tuple[str, ...] = ("*",)
    blocked_tools: tuple[str, ...] = ()
    scope_paths: tuple[str, ...] = ()
    call_timeout: int = _DEFAULT_TIMEOUT

    def allows(self, mcp_tool_name: str) -> bool:
        """§8.5 gate — the blocklist wins; the allowlist bounds."""
        if mcp_tool_name in self.blocked_tools:
            return False
        return "*" in self.allowed_tools or mcp_tool_name in self.allowed_tools

    def argv(self) -> list[str]:
        return [self.command, *self.args]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "command": self.command,
            "args": list(self.args),
            "enabled": self.enabled,
            "risk_ceiling": self.risk_ceiling,
            "allowed_tools": list(self.allowed_tools),
            "blocked_tools": list(self.blocked_tools),
            "scope_paths": list(self.scope_paths),
            "call_timeout": self.call_timeout,
        }


def build_server_config(values: dict[str, object], *, origin: str) -> McpServerConfig:
    """Validate one ``[[servers]]`` table → :class:`McpServerConfig`."""
    name = values.get("name")
    command = values.get("command")
    if not isinstance(name, str) or not name.strip():
        raise McpConfigError(f"{origin}: server 'name' must be a non-empty string")
    if not isinstance(command, str) or not command.strip():
        raise McpConfigError(f"{origin}: server {name!r} needs a 'command' string")
    raw_args = values.get("args", [])
    if not isinstance(raw_args, list) or any(
        not isinstance(item, str) for item in raw_args
    ):
        raise McpConfigError(f"{origin}: server {name!r} 'args' must be a list of strings")
    risk = values.get("risk_ceiling", 2)
    if isinstance(risk, bool) or not isinstance(risk, int) or not 0 <= risk <= 3:
        raise McpConfigError(f"{origin}: server {name!r} 'risk_ceiling' must be 0..3")
    timeout = values.get("call_timeout", _DEFAULT_TIMEOUT)
    if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 600:
        raise McpConfigError(f"{origin}: server {name!r} 'call_timeout' must be 1..600")
    for key in ("allowed_tools", "blocked_tools", "scope_paths"):
        raw = values.get(key, [] if key != "allowed_tools" else ["*"])
        if isinstance(raw, tuple):
            raw = list(raw)
        if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
            raise McpConfigError(f"{origin}: server {name!r} {key!r} must be a string list")
    env = values.get("env", {})
    if not isinstance(env, dict) or any(
        not isinstance(k, str) or not isinstance(v, str) for k, v in env.items()
    ):
        raise McpConfigError(f"{origin}: server {name!r} 'env' must be a string map")
    return McpServerConfig(
        name=name,
        command=command,
        args=tuple(raw_args),
        env=dict(env),
        enabled=bool(values.get("enabled", True)),
        risk_ceiling=risk,
        allowed_tools=tuple(values.get("allowed_tools", ["*"])),  # type: ignore[arg-type]
        blocked_tools=tuple(values.get("blocked_tools", [])),  # type: ignore[arg-type]
        scope_paths=tuple(values.get("scope_paths", [])),  # type: ignore[arg-type]
        call_timeout=timeout,
    )


def load_mcp_servers(path: Path) -> tuple[McpServerConfig, ...]:
    """Load ``[[servers]]`` from an mcp.toml file (missing → empty)."""
    if not path.is_file():
        return ()
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    raw_servers = data.get("servers")
    if raw_servers is None:
        raise McpConfigError(f"{path}: missing the [[servers]] tables")
    if not isinstance(raw_servers, list):
        raise McpConfigError(f"{path}: 'servers' must be an array of tables")
    servers: list[McpServerConfig] = []
    seen: set[str] = set()
    for index, entry in enumerate(raw_servers):
        if not isinstance(entry, dict):
            raise McpConfigError(f"{path}: servers[{index}] must be a table")
        config = build_server_config(entry, origin=f"{path} servers[{index}]")
        if config.name in seen:
            raise McpConfigError(f"{path}: duplicate server {config.name!r}")
        seen.add(config.name)
        servers.append(config)
    return tuple(servers)
