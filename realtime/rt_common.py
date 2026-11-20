# -*- coding: utf-8 -*-
"""NEXUS Realtime Remote — PHASE 29 — shared layer (stdlib only).

Four SEPARATED channels, one shared fabric:
  rt_control.py  :9411  control plane (status/exec/admin)
  rt_events.py   :9412  event bus (pub/sub, long-poll stream)
  rt_screen.py   :9413  screen capture (PowerShell CopyFromScreen -> PNG)
  rt_files.py    :9414  chunked file transfer (sha256 both ends, path jail)

"Separated" means: independent module file, independent port, independent
ThreadingHTTPServer thread, independently startable (`python rt_control.py`).
What they share is deliberately small and explicit (auth token, audit log,
in-process event bus, config) — rt_common is the fabric, not the channels.

Evidence or silence: every route verdict lands in
proofs\\phase29_realtime.json via rt_worker.py --selftest.

PHASE 28 relation: remote\\ (port 8899) is the unified remote gateway —
PHASE 29 splits the REALTIME concerns into the four channels above.
"""
from __future__ import annotations

import collections
import hashlib
import hmac
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PHASE = 29
VERSION = "0.29.0"

DEFAULT_CONFIG = {
    "token": "ps1-stable-token-2026",
    "bind": "127.0.0.1",
    "ports": {"control": 9411, "events": 9412, "screen": 9413, "files": 9414},
    "files_root": "M:\\NEXUS",
    "files_max_chunk": 2097152,
    "control_allow_prefixes": ["echo", "git", "python", "py", "tasklist",
                               "type", "dir", "whoami", "hostname"],
    "control_timeout_s": 60,
    "events_ring": 1000,
    "max_body": 25165824,
    "stream_max_wait_s": 30,
}


def utcnow() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def load_config(rtdir: Path) -> dict:
    """Bootstrap rt_config.json with defaults on first run; keep user edits."""
    cfg_path = rtdir / "rt_config.json"
    cfg = dict(DEFAULT_CONFIG)
    if cfg_path.is_file():
        try:
            user = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(user, dict):
                cfg.update(user)
        except BaseException:
            pass  # honest default fallback
    atomic_json(cfg_path, cfg)
    tok = rtdir / "token.txt"
    if not tok.is_file():
        tok.write_text(cfg["token"], encoding="utf-8")
    return cfg


class EventBus:
    """In-process pub/sub with a monotonic cursor and a bounded ring.

    Channels publish lifecycle/operation events here; rt_events serves them.
    The bus is coordination fabric — each channel server stays independent.
    """

    def __init__(self, ring: int = 1000) -> None:
        self._buf = collections.deque(maxlen=max(100, int(ring)))
        self._cond = threading.Condition()
        self._cursor = 0
        self.total = 0
        self.started_utc = utcnow()

    def publish(self, etype: str, data=None) -> dict:
        with self._cond:
            self._cursor += 1
            self.total += 1
            ev = {"id": self._cursor, "utc": utcnow(), "type": str(etype),
                  "data": data if data is not None else {}}
            self._buf.append(ev)
            self._cond.notify_all()
            return ev

    def after(self, cursor: int, wait_s: float = 0.0):
        """Events with id > cursor. Blocks up to wait_s waiting for new ones."""
        deadline = time.monotonic() + max(0.0, float(wait_s))
        with self._cond:
            while True:
                got = [e for e in self._buf if e["id"] > cursor]
                if got:
                    return got, self._cursor, 0.0
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return [], self._cursor, round(max(0.0, float(wait_s)) * 1000, 1)
                self._cond.wait(timeout=min(remaining, 0.5))

    def status(self) -> dict:
        with self._cond:
            return {"cursor": self._cursor, "ring": len(self._buf),
                    "total_published": self.total,
                    "started_utc": self.started_utc}


class Audit:
    """JSONL audit log — one file per UTC day, process-wide lock."""

    def __init__(self, logdir: Path) -> None:
        self.logdir = logdir
        self.logdir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def write(self, channel: str, action: str, detail=None) -> str:
        day = time.strftime("%Y%m%d", time.gmtime())
        path = self.logdir / f"audit-{day}.log"
        line = json.dumps({"utc": utcnow(), "channel": channel,
                           "action": action,
                           "detail": detail if detail is not None else {}},
                          ensure_ascii=False)
        with self._lock:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        return str(path)

    def today_path(self) -> Path:
        day = time.strftime("%Y%m%d", time.gmtime())
        return self.logdir / f"audit-{day}.log"

    def tail_lines(self, n: int = 5) -> list:
        try:
            lines = self.today_path().read_text(encoding="utf-8").splitlines()
            return lines[-n:]
        except BaseException:
            return []


class ChannelContext:
    """Everything one channel needs — plus a gateway slot for admin ops."""

    def __init__(self, name: str, cfg: dict, rtdir: Path, bus: EventBus,
                 audit: Audit) -> None:
        self.name = name
        self.cfg = cfg
        self.rtdir = rtdir
        self.bus = bus
        self.audit = audit
        self.gateway = None            # set by rt_gateway (admin ops)
        self.started_utc = None
        self.port = int(cfg["ports"][name])

    def publish(self, etype: str, data=None) -> dict:
        data = dict(data or {})
        data["channel"] = self.name
        return self.bus.publish(etype, data)


def auth_ok(headers, token: str) -> bool:
    got = headers.get("X-NX-Token") or ""
    if not got:
        auth = headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            got = auth[7:].strip()
    if not got:
        return False
    return hmac.compare_digest(got.encode("utf-8"), token.encode("utf-8"))


def make_handler(ctx: ChannelContext, routes: dict):
    """Build a BaseHTTPRequestHandler subclass for one channel.

    routes: {(METHOD, "/path"): fn(ctx, body, qs, handler) -> (code, obj)}
    Every route requires the bearer token; nothing is anonymous.
    """

    class RtHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"
        server_version = f"NEXUS-RT/{VERSION} {ctx.name}"
        sys_version = ""

        def log_message(self, fmt, *args):  # silence stderr noise
            pass

        def _reply(self, code: int, obj) -> None:
            data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
            self.send_response(int(code))
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Nexus-Channel", ctx.name)
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _dispatch(self, method: str) -> None:
            try:
                if not auth_ok(self.headers, ctx.cfg["token"]):
                    ctx.audit.write(ctx.name, "auth_fail",
                                    {"ip": self.client_address[0]})
                    return self._reply(401, {"ok": False,
                                             "error": "unauthorized"})
                parsed = urlparse(self.path)
                qs = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                path = parsed.path.rstrip("/") or "/"
                fn = routes.get((method, path))
                if fn is None:
                    return self._reply(404, {"ok": False,
                                             "error": "no_route",
                                             "path": parsed.path})
                body = None
                if method == "POST":
                    n = int(self.headers.get("Content-Length") or 0)
                    cap = int(ctx.cfg.get("max_body", 25165824))
                    if n > cap:
                        return self._reply(413, {"ok": False,
                                                 "error": "body_too_large",
                                                 "limit": cap})
                    raw = self.rfile.read(n) if n > 0 else b""
                    if raw:
                        try:
                            body = json.loads(raw.decode("utf-8"))
                        except BaseException:
                            return self._reply(400, {"ok": False,
                                                     "error": "bad_json"})
                code, obj = fn(ctx, body, qs, self)
                return self._reply(code, obj)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except BaseException as exc:  # noqa: BLE001 — honest 500 envelope
                try:
                    return self._reply(500, {"ok": False, "error":
                                             f"{type(exc).__name__}: {exc}"})
                except BaseException:
                    pass

        def do_GET(self):  # noqa: N802
            self._dispatch("GET")

        def do_POST(self):  # noqa: N802
            self._dispatch("POST")

    return RtHandler


def build_server(ctx: ChannelContext, routes: dict) -> ThreadingHTTPServer:
    handler = make_handler(ctx, routes)
    httpd = ThreadingHTTPServer((ctx.cfg["bind"], ctx.port), handler)
    httpd.daemon_threads = True
    return httpd


def serve_forever_standalone(module_name: str, routes_builder) -> None:
    """Independent startup entry for one channel: `python rt_<ch>.py`."""
    here = Path(__file__).resolve().parent
    cfg = load_config(here)
    bus = EventBus(cfg["events_ring"])
    audit = Audit(here / "logs")
    ctx = ChannelContext(module_name, cfg, here, bus, audit)
    routes = routes_builder()
    ctx.started_utc = utcnow()
    httpd = build_server(ctx, routes)
    audit.write(module_name, "channel_started",
                {"port": ctx.port, "mode": "standalone"})
    bus.publish("channel_started", {"port": ctx.port, "mode": "standalone"})
    print(f"[{module_name}] serving on {cfg['bind']}:{ctx.port} "
          f"(phase {PHASE} v{VERSION})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        audit.write(module_name, "channel_stopped", {"port": ctx.port})
