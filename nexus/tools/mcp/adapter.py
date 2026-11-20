"""MCP SDK adapter (Final Build Plan §8.4) — USE behind the Tool Router.

The **official Python SDK** (v2 stable line; MODE A optional
``nexus[mcp]``, pinned ``mcp>=2.0,<3``) drives stdio MCP servers:

* one daemon thread per server owns an asyncio loop;
* ``initialize`` → ``tools/list`` → each MCP tool is wrapped as a
  §8.1 :class:`ToolDefinition` and registered — ``mcp.<server>.<tool>``
  — with the server's ``risk_ceiling`` clamp, its ``scope_paths``
  (path arguments the §8.2 Scope stage checks) and verification
  ``none`` (an external server's claims are not evidence — §71);
* ``tools/call`` bridges sync→async with
  :func:`asyncio.run_coroutine_threadsafe` and the per-server call
  timeout;
* the §8.5 gates fire **before any stdio write**: a blocked or
  non-allowlisted MCP tool never reaches the server;
* honest failure & recovery: a dead session fails *that* call
  honestly (no silent retry — a retry could double-apply a
  mutation); the transport respawns for the *next* call only.

The adapter degrades gracefully without the SDK: ``sdk_available``
is False → no MCP tools, the native nine keep working, and the
reason is reported — never a boot failure.

محول SDK الرسمي — جلسة لكل خادم، وكل أداة MCP تسجّل كسجلّ §8.1،
والبوابات قبل أي بايت، والفشل صادق بلا إعادة محاولة صامتة.

Stdlib core + the official ``mcp`` SDK (optional MODE A extra).
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import importlib.metadata
import importlib.util
import logging
import sys
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..models import (
    ScopeRequirements,
    ToolCallResult,
    ToolDefinition,
    VerificationSpec,
)
from ..registry import ToolRegistry
from .config import McpServerConfig

logger = logging.getLogger("nexus.tools.mcp")


class McpUnavailableError(Exception):
    """The official MCP SDK is not installed (MODE A extra missing)."""


class McpToolError(Exception):
    """The server answered with an error result — honest failure."""


class McpSessionDeadError(Exception):
    """The session thread/transport died — this call fails honestly."""


def sdk_available() -> bool:
    """Is the official ``mcp`` SDK importable?"""
    return importlib.util.find_spec("mcp") is not None


def sdk_version() -> str | None:
    try:
        return importlib.metadata.version("mcp")
    except importlib.metadata.PackageNotFoundError:
        return None


def _import_sdk() -> Any:
    if not sdk_available():
        raise McpUnavailableError(
            "the official MCP SDK is not installed — "
            "pip install 'nexus-core[mcp]' (mcp>=2.0,<3)"
        )
    import mcp  # MODE A — the official SDK, behind the router

    return mcp


class _ServerSession:
    """One stdio MCP server: a daemon thread with its own asyncio loop."""

    def __init__(self, config: McpServerConfig) -> None:
        self._config = config
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._session: Any = None
        self._tools_box: dict[str, Any] = {}
        self._ready = threading.Event()
        self._spawn_error: BaseException | None = None
        self._stop: Any = None

    # ------------------------------------------------------------ lifecycle

    def start(self, *, timeout: float = 30.0) -> None:
        """Spawn the thread; wait for initialize + tools/list (or fail)."""
        self._thread = threading.Thread(
            target=self._run, name=f"mcp:{self._config.name}", daemon=True
        )
        self._thread.start()
        if not self._ready.wait(timeout=timeout):
            self.close()
            raise McpSessionDeadError(
                f"mcp server {self._config.name!r} did not initialize "
                f"within {timeout}s"
            )
        if self._spawn_error is not None:
            self.close()
            raise McpSessionDeadError(
                f"mcp server {self._config.name!r} failed to start: "
                f"{self._spawn_error}"
            )

    def _run(self) -> None:
        mcp = _import_sdk()
        try:
            asyncio.run(self._session_loop(mcp))
        except BaseException as exc:  # noqa: BLE001 — surfaced via _spawn_error
            if not self._ready.is_set():
                self._spawn_error = exc
                self._ready.set()
            else:
                logger.warning("mcp session %s ended: %s", self._config.name, exc)

    async def _session_loop(self, mcp: Any) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self._loop = asyncio.get_running_loop()
        self._stop = asyncio.Event()
        params = StdioServerParameters(
            command=self._config.command,
            args=list(self._config.args),
            env=dict(self._config.env) if self._config.env else None,
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                self._session = session
                listing = await session.list_tools()
                self._tools_box["tools"] = listing.tools
                self._ready.set()
                await self._stop.wait()

    # -------------------------------------------------------------- probing

    @property
    def alive(self) -> bool:
        return (
            self._thread is not None
            and self._thread.is_alive()
            and self._session is not None
            and self._loop is not None
        )

    @property
    def tools(self) -> list[Any]:
        return list(self._tools_box.get("tools", []))

    # ---------------------------------------------------------------- calls

    def call(
        self, mcp_tool_name: str, arguments: Mapping[str, Any], *, timeout: int
    ) -> ToolCallResult:
        if not self.alive:
            raise McpSessionDeadError(
                f"mcp session {self._config.name!r} is not alive"
            )
        assert self._loop is not None
        coroutine = self._session.call_tool(mcp_tool_name, dict(arguments))
        future = asyncio.run_coroutine_threadsafe(coroutine, self._loop)
        try:
            result = future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise McpSessionDeadError(
                f"mcp call {self._config.name}.{mcp_tool_name} timed out "
                f"after {timeout}s"
            ) from exc
        if getattr(result, "is_error", None) or getattr(result, "isError", False):
            # v2 names it is_error; v1 named it isError — accept both
            raise McpToolError(
                f"mcp {self._config.name}.{mcp_tool_name} returned an error "
                f"result: {_content_text(result)}"
            )
        return ToolCallResult(
            output=_content_text(result),
            artifacts={
                "server": self._config.name,
                "mcp_tool": mcp_tool_name,
                "content_blocks": len(getattr(result, "content", []) or []),
            },
        )

    def close(self) -> None:
        loop = self._loop
        if loop is not None and self._stop is not None:
            loop.call_soon_threadsafe(self._stop.set)
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=10)
        self._session = None
        self._loop = None


def _content_text(result: Any) -> str:
    """Flatten MCP content blocks into text (TextContent .text first)."""
    blocks = getattr(result, "content", None) or []
    parts: list[str] = []
    for block in blocks:
        text = getattr(block, "text", None)
        if isinstance(text, str):
            parts.append(text)
        else:
            parts.append(str(block))
    return "\n".join(parts)


class McpAdapter:
    """The §8.4 USE integration: official SDK behind the NEXUS router."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._sessions: dict[str, _ServerSession] = {}
        self._configs: dict[str, McpServerConfig] = {}

    # ------------------------------------------------------------- lifecycle

    def connect(self, config: McpServerConfig) -> dict[str, Any]:
        """Start one server and register its tools; honest per-server
        failure (a broken server never breaks the runtime)."""
        if not sdk_available():
            raise McpUnavailableError(
                "the official MCP SDK is not installed "
                "(pip install 'nexus-core[mcp]')"
            )
        self._configs[config.name] = config
        session = self._spawn(config)
        report = self._register_tools(config, session)
        return report

    def _spawn(self, config: McpServerConfig) -> _ServerSession:
        session = _ServerSession(config)
        session.start()
        self._sessions[config.name] = session
        return session

    def _register_tools(
        self, config: McpServerConfig, session: _ServerSession
    ) -> dict[str, Any]:
        registered: list[str] = []
        for mcp_tool in session.tools:
            mcp_name = str(getattr(mcp_tool, "name", "")).strip()
            if not mcp_name or not config.allows(mcp_name):
                continue
            definition = self._definition_for(config, mcp_tool)
            handler = self._make_handler(config, mcp_name)
            self._registry.register(definition, handler)
            registered.append(definition.name)
        return {
            "server": config.name,
            "tools": registered,
            "count": len(registered),
        }

    def _definition_for(
        self, config: McpServerConfig, mcp_tool: Any
    ) -> ToolDefinition:
        mcp_name = str(getattr(mcp_tool, "name", ""))
        raw_schema = getattr(mcp_tool, "inputSchema", None)
        schema = (
            dict(raw_schema)
            if isinstance(raw_schema, Mapping) and raw_schema.get("type") == "object"
            else {
                "type": "object",
                "properties": {},
                "description": "raw MCP schema (not an object schema)",
            }
        )
        description = str(
            getattr(mcp_tool, "description", "") or f"MCP tool {mcp_name!r}"
        )
        return ToolDefinition(
            id=f"mcp:{config.name}:{mcp_name}",
            name=f"mcp.{config.name}.{mcp_name}",
            description=description,
            input_schema=schema,
            output_schema={
                "type": "object",
                "description": "MCP content blocks (text flattened)",
            },
            permissions=(f"mcp.{config.name}.call",),
            scope_requirements=ScopeRequirements(
                path_arguments=tuple(config.scope_paths),
                # unknown server semantics → conservatively mutating
                mutating_operations=(),
                dimensions=("external", "network"),
            ),
            # §8.5: the server's risk ceiling clamps every tool
            risk=config.risk_ceiling,
            # §71: an external server's claim is not evidence
            verification=VerificationSpec("none"),
            version="1.0.0",
        )

    def _make_handler(
        self, config: McpServerConfig, mcp_name: str
    ) -> Any:
        def handler(arguments: Mapping[str, Any]) -> ToolCallResult:
            # §8.5 gates — BEFORE any stdio write
            if not config.allows(mcp_name):
                raise McpToolError(
                    f"mcp tool {config.name}.{mcp_name} is blocked by the "
                    "NEXUS server gates (allowed/blocked lists)"
                )
            session = self._sessions.get(config.name)
            if session is None or not session.alive:
                # the transport died earlier (or never started): respawn
                # it for THIS call — the previously failed call already
                # returned its honest failure; nothing is retried here.
                self._drop(config.name)
                session = self._respawn(config)
            try:
                return session.call(
                    mcp_name, arguments, timeout=config.call_timeout
                )
            except McpToolError:
                # a healthy server answering with isError — honest data
                raise
            except Exception as exc:  # noqa: BLE001 — transport death is data
                # the session is suspect: drop it, fail THIS call
                # honestly (no silent retry — a retry could double-apply
                # a mutation); the NEXT call respawns the transport.
                self._drop(config.name)
                raise McpSessionDeadError(
                    f"mcp session {config.name!r} failed during "
                    f"{mcp_name!r}: {type(exc).__name__}: {exc}"
                ) from exc

        return handler

    def _respawn(self, config: McpServerConfig) -> _ServerSession:
        session = _ServerSession(config)
        session.start()
        self._sessions[config.name] = session
        return session

    def _drop(self, name: str) -> None:
        session = self._sessions.pop(name, None)
        if session is not None:
            session.close()

    def shutdown(self) -> None:
        for name in list(self._sessions):
            self._drop(name)

    # -------------------------------------------------------------- reports

    def status(self) -> dict[str, Any]:
        return {
            "sdk": {"available": sdk_available(), "version": sdk_version()},
            "servers": {
                name: {
                    "alive": session.alive,
                    "tools": len(session.tools),
                }
                for name, session in self._sessions.items()
            },
        }


def connect_from_config(
    registry: ToolRegistry,
    configs: tuple[McpServerConfig, ...],
    *,
    mcp_toml: Path | None = None,
) -> tuple[McpAdapter, dict[str, Any]]:
    """Wire the adapter over ``[[servers]]`` declarations (enabled only).

    Per-server failure is honest and isolated: the report carries the
    error and the runtime keeps every other tool.
    """
    adapter = McpAdapter(registry)
    report: dict[str, Any] = {"servers": {}, "sdk": sdk_available()}
    for config in configs:
        if not config.enabled:
            report["servers"][config.name] = {"enabled": False}
            continue
        if not sdk_available():
            report["servers"][config.name] = {
                "error": "official MCP SDK not installed (nexus[mcp])"
            }
            continue
        try:
            server_report = adapter.connect(config)
            report["servers"][config.name] = server_report
        except Exception as exc:  # noqa: BLE001 — isolated per-server honesty
            report["servers"][config.name] = {"error": f"{type(exc).__name__}: {exc}"}
            logger.warning("mcp server %s failed to connect: %s", config.name, exc)
    _ = mcp_toml
    return adapter, report


def echo_server_argv(script: Path) -> list[str]:
    """The stdio argv for an in-repo Python MCP server (tests/deploy)."""
    return [sys.executable, str(script)]
