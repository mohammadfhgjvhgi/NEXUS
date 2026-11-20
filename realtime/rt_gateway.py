# -*- coding: utf-8 -*-
"""NEXUS Realtime Remote — PHASE 29 — gateway (composition layer).

Composes the four SEPARATED channel servers:
  control :9411 · events :9412 · screen :9413 · files :9414

Separation is real, not cosmetic: each channel owns its module file, its
port, its ThreadingHTTPServer and its thread — so the gateway can STOP one
channel and prove the other three still answer (isolation verdict, tested
by rt_worker selftest), then restart it. Channels also start standalone
(`python rt_events.py`) without this file at all.
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rt_common import (PHASE, VERSION, Audit, ChannelContext, EventBus,
                       atomic_json, build_server, load_config, utcnow)  # noqa: E402

CHANNELS = ("control", "events", "screen", "files")


class RealtimeGateway:
    def __init__(self, rtdir: Path) -> None:
        self.rtdir = Path(rtdir)
        self.cfg = load_config(self.rtdir)
        self.bus = EventBus(self.cfg.get("events_ring", 1000))
        self.audit = Audit(self.rtdir / "logs")
        self.pid = None
        self.started_utc = None
        self.stop_event = threading.Event()
        self._ctxs = {}
        self._servers = {}
        self._threads = {}
        self._lock = threading.Lock()
        self._modules = {}

    # -- module loading -------------------------------------------------
    def _module(self, name: str):
        with self._lock:
            if name in self._modules:
                return self._modules[name]
        import importlib
        mod = importlib.import_module(f"rt_{name}")
        with self._lock:
            self._modules[name] = mod
        return mod

    def _routes(self, name: str) -> dict:
        return self._module(name).routes()

    # -- lifecycle ------------------------------------------------------
    def start_channel(self, name: str) -> dict:
        # Import + route-building MUST stay outside self._lock — _module
        # takes the same non-reentrant lock, and start_channel used to hold
        # it here (deadlock found by local smoke test before deployment).
        routes = self._routes(name)
        with self._lock:
            if name in self._servers and self._servers[name] is not None:
                return {"ok": True, "channel": name, "note": "already_up",
                        "port": self._ctxs[name].port}
            ctx = self._ctxs.get(name)
            if ctx is None:
                ctx = ChannelContext(name, self.cfg, self.rtdir, self.bus,
                                     self.audit)
                ctx.gateway = self
                self._ctxs[name] = ctx
            try:
                srv = build_server(ctx, routes)
            except OSError as exc:
                self.audit.write(name, "bind_failed",
                                 {"port": ctx.port,
                                  "error": str(exc)[:160]})
                self.bus.publish("channel_bind_failed",
                                 {"channel": name, "port": ctx.port,
                                  "error": str(exc)[:160]})
                return {"ok": False, "channel": name, "port": ctx.port,
                        "error": str(exc)[:200]}
            ctx.started_utc = utcnow()
            th = threading.Thread(target=self._serve, name=f"rt-{name}",
                                  args=(name, srv), daemon=True)
            self._servers[name] = srv
            self._threads[name] = th
            th.start()
        self.audit.write(name, "channel_started",
                         {"port": ctx.port, "mode": "gateway"})
        self.bus.publish("channel_started",
                         {"channel": name, "port": ctx.port})
        return {"ok": True, "channel": name, "port": ctx.port}

    def _serve(self, name: str, srv) -> None:
        try:
            srv.serve_forever()
        except BaseException as exc:  # noqa: BLE001
            self.audit.write(name, "server_thread_error",
                             {"error": f"{type(exc).__name__}: {exc}"[:200]})

    def channel_stop(self, name: str) -> dict:
        with self._lock:
            srv = self._servers.get(name)
            if srv is None:
                return {"ok": False, "channel": name, "error": "not_up"}
            self._servers[name] = None
        srv.shutdown()          # serve_forever loop exits
        srv.server_close()
        self.audit.write(name, "channel_stopped", {"port": self._ctxs[name].port})
        self.bus.publish("channel_stopped", {"channel": name})
        return {"ok": True, "channel": name, "port": self._ctxs[name].port}

    def channel_restart(self, name: str) -> dict:
        t0 = time.perf_counter()
        stopped = self.channel_stop(name)
        if not stopped.get("ok") and stopped.get("error") != "not_up":
            return {"ok": False, "stop": stopped}
        started = self.start_channel(name)
        return {"ok": bool(started.get("ok")), "stop": stopped,
                "start": started,
                "downtime_ms": round((time.perf_counter() - t0) * 1000, 1)}

    def start_all(self) -> dict:
        self.pid = None
        import os
        self.pid = os.getpid()
        self.started_utc = utcnow()
        res = {}
        for name in CHANNELS:
            res[name] = self.start_channel(name)
        self._write_gateway_state(running=True)
        self.bus.publish("gateway_started",
                         {"phase": PHASE, "version": VERSION,
                          "ports": {n: self._ctxs[n].port for n in CHANNELS}})
        return res

    def stop_all(self) -> dict:
        res = {}
        for name in CHANNELS:
            try:
                res[name] = self.channel_stop(name)
            except BaseException as exc:  # noqa: BLE001
                res[name] = {"ok": False, "error": str(exc)[:160]}
        self._write_gateway_state(running=False)
        self.bus.publish("gateway_stopped", {"utc": utcnow()})
        return res

    def request_shutdown(self) -> None:
        self.stop_event.set()

    def channels_state(self) -> dict:
        with self._lock:
            out = {}
            for name in CHANNELS:
                ctx = self._ctxs.get(name)
                up = self._servers.get(name) is not None
                out[name] = {"up": bool(up),
                             "port": ctx.port if ctx else None,
                             "started_utc": ctx.started_utc if ctx else None}
            return out

    def _write_gateway_state(self, running: bool) -> None:
        obj = {"service": "nexus-realtime", "phase": PHASE,
               "version": VERSION, "pid": self.pid,
               "utc": utcnow(), "running": bool(running),
               "ports": self.cfg["ports"]}
        if not running:
            obj["utc_stop"] = utcnow()
        atomic_json(self.rtdir / "gateway.json", obj)


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    gw = RealtimeGateway(here)
    res = gw.start_all()
    print(json.dumps(res, ensure_ascii=False, indent=1))
    try:
        while not gw.stop_event.wait(1.0):
            pass
    except KeyboardInterrupt:
        pass
    gw.stop_all()
    print("gateway stopped cleanly")
