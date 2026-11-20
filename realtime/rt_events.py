# -*- coding: utf-8 -*-
"""NEXUS Realtime Remote — PHASE 29 — EVENTS channel (port 9412).

Realtime event bus over HTTP long-poll (tunnel-friendly; the poll blocks on
a threading.Condition and wakes the instant an event is published).
Separated module/port/thread; startable standalone: `python rt_events.py`.

Routes (all Bearer-token protected):
  GET  /events/status   cursor, ring size, totals
  POST /events/pub      publish {type, data} -> {id, cursor}
  GET  /events/stream   ?cursor=N&wait_s=20 -> events after N (blocks)
"""
from __future__ import annotations

import time

from rt_common import (PHASE, VERSION, ChannelContext, serve_forever_standalone)

_t0 = time.time()


def _status(ctx: ChannelContext, body, qs, handler):
    st = ctx.bus.status()
    st.update({"ok": True, "channel": "events", "phase": PHASE,
               "version": VERSION, "uptime_s": round(time.time() - _t0, 1)})
    return 200, st


def _pub(ctx: ChannelContext, body, qs, handler):
    body = body or {}
    etype = str(body.get("type") or "").strip()
    if not etype:
        return 400, {"ok": False, "error": "type_required"}
    if len(etype) > 120:
        return 400, {"ok": False, "error": "type_too_long"}
    data = body.get("data")
    if data is not None and not isinstance(data, dict):
        data = {"value": data}
    ev = ctx.publish(etype, data)
    ctx.audit.write("events", "pub", {"id": ev["id"], "type": etype})
    return 200, {"ok": True, "id": ev["id"], "utc": ev["utc"],
                 "cursor": ctx.bus.status()["cursor"]}


def _stream(ctx: ChannelContext, body, qs, handler):
    try:
        cursor = int(str(qs.get("cursor", "0")))
    except (TypeError, ValueError):
        cursor = 0
    try:
        wait_s = float(str(qs.get("wait_s", "0") or 0))
    except (TypeError, ValueError):
        wait_s = 0.0
    wait_s = max(0.0, min(wait_s, float(ctx.cfg.get("stream_max_wait_s", 30))))
    t0 = time.perf_counter()
    events, new_cursor, waited_ms = ctx.bus.after(cursor, wait_s)
    dur_ms = round((time.perf_counter() - t0) * 1000, 1)
    return 200, {"ok": True, "events": events, "cursor": new_cursor,
                 "count": len(events), "waited_ms": waited_ms,
                 "roundtrip_ms": dur_ms}


def routes() -> dict:
    return {
        ("GET", "/events/status"): _status,
        ("POST", "/events/pub"): _pub,
        ("GET", "/events/stream"): _stream,
    }


if __name__ == "__main__":
    serve_forever_standalone("events", routes)
