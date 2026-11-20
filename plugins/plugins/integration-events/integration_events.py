# -*- coding: utf-8 -*-
"""Sample INTEGRATION plugin — bridges to PHASE 29 realtime events.

Reads the bearer token from realtime\token.txt (device-local file), posts
to the loopback events channel, and verify() reads the stream back to
confirm delivery round-trip.
"""
import json
import urllib.request
from pathlib import Path

TOKEN_FILE = Path(__file__).resolve().parents[2] / "realtime" / "token.txt"
PUB = "http://127.0.0.1:9412/events/pub"
STREAM = "http://127.0.0.1:9412/events/stream"


def _token() -> str:
    try:
        return TOKEN_FILE.read_text(encoding="utf-8").strip()
    except BaseException:
        return "ps1-stable-token-2026"


def relay(event: dict, timeout=10):
    body = json.dumps(event).encode("utf-8")
    req = urllib.request.Request(PUB, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer " + _token()}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def verify(event_id: int, etype: str, timeout=10):
    url = f"{STREAM}?cursor={max(0, event_id - 1)}&wait_s=3"
    req = urllib.request.Request(url, headers={
        "Authorization": "Bearer " + _token()})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    hit = any(e.get("id") == event_id and e.get("type") == etype
              for e in data.get("events", []))
    return {"ok": hit, "count": len(data.get("events", [])),
            "cursor": data.get("cursor")}


def register(ctx):
    ctx.register_integration({
        "id": "events-relay-9412",
        "target": "nexus-realtime/events:9412",
        "transport": "http-loopback",
        "relay": relay,
        "verify": verify,
    })
