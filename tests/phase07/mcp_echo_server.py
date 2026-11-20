#!/usr/bin/env python3
"""In-repo echo MCP server (tests/phase07 — Plan §8.4 proof fixture).

A real MCP server on the **official SDK's** server side (the v2
stable line: ``mcp.server.MCPServer``, stdio transport) with two
tools: ``echo(text) → text`` and ``add(a, b) → a + b``.

The Phase-7 harness spawns it exactly like any external server —
``StdioServerParameters(command=sys.executable, args=[this file])``
— so the whole chain is production-shaped: NEXUS Tool Router →
official SDK v2 client → stdio JSON-RPC → official SDK v2 server.

خادم صدى حقيقي بالـSDK الرسمي (خط v2) — يُطلق كأي خادم خارجي عبر stdio.

Requires the MODE A extra: pip install "nexus-core[mcp]".
"""

from mcp.server import MCPServer

mcp = MCPServer("echo")


@mcp.tool()
def echo(text: str) -> str:
    """Echo the text back."""
    return text


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


@mcp.tool()
def boom(text: str) -> str:
    """Always fails — the server returns an isError result."""
    raise RuntimeError(f"boom: {text}")


@mcp.tool()
def die() -> str:
    """Kill the server process immediately (crash-injection fixture)."""
    import os

    os._exit(1)


if __name__ == "__main__":
    mcp.run()
