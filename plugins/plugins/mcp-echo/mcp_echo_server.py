# -*- coding: utf-8 -*-
"""Sample MCP plugin — a REAL MCP server over stdio (one JSON-RPC per line).

Handshake: initialize -> notifications/initialized -> tools/list ->
tools/call. Protocol version 2024-11-05 (spec 79: NEXUS puts MCP behind
its Tool Router — registration here is the connector contract).
"""
import json
import sys
from pathlib import Path

TOOLS = [{
    "name": "echo",
    "description": "Echo a message back with a prefix",
    "inputSchema": {"type": "object",
                    "properties": {"message": {"type": "string"}},
                    "required": ["message"]},
}]


def register(ctx):
    """Connector contract: register this server as an NEXUS MCP plugin."""
    ctx.register_mcp_server({
        "id": "echo",
        "transport": "stdio",
        "command": sys.executable,
        "args": [str(Path(__file__).resolve())],
        "protocol": "2024-11-05",
        "tools": [t["name"] for t in TOOLS],
    })


def main() -> None:
    for raw in sys.stdin:
        raw = raw.strip()
        if not raw:
            continue
        try:
            req = json.loads(raw)
        except BaseException:
            continue
        rid = req.get("id")
        if rid is None:
            continue                      # notification — no response
        method = req.get("method")
        if method == "initialize":
            result = {"protocolVersion": "2024-11-05",
                      "capabilities": {"tools": {}},
                      "serverInfo": {"name": "echo-mcp", "version": "1.0.0"}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            args = (req.get("params") or {}).get("arguments") or {}
            text = "echo: " + str(args.get("message") or "")
            result = {"content": [{"type": "text", "text": text}]}
        elif method == "ping":
            result = {}
        else:
            sys.stdout.write(json.dumps({
                "jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": "method_not_found"}}) + "\n")
            sys.stdout.flush()
            continue
        sys.stdout.write(json.dumps(
            {"jsonrpc": "2.0", "id": rid, "result": result}) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    main()
