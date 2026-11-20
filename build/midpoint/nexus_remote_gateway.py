# -*- coding: utf-8 -*-
"""NEXUS Remote Gateway — PHASE 28 (Remote Web) — stdlib only.

The phone talks to this; this talks to the real NEXUS core. No mockups:

  28.1  Static frontend   served from remote\\web (same files deploy to
                          GitHub Pages unchanged — relative paths only)
  28.2  Remote Gateway    ThreadingHTTPServer on 127.0.0.1 (loopback — a
                          cloudflared tunnel adds the public HTTPS leg),
                          Bearer-token auth on every /api route except
                          /api/health, CORS open for GitHub Pages
  28.3  Tasks/commands    phone → commands.json (atomic) → executor thread
                          → REAL effects: pause/resume (state.json + UI
                          tray hooks), checkpoint (real snapshot with
                          sha256 manifest), task (the launcher's real M4
                          loop via lm.run_task), chat (real model ladder,
                          honest offline)
  28.4  File transfer     authorized push (phone→inbox) / pull (outbox→
                          phone), sha256 on both sides, path-traversal
                          rejection is a tested verdict, not a promise

Evidence or silence: every route's verdict lands in
proofs\\phase28_remote.json via --phase28-selftest.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

P28_TYPES = ("chat", "task", "pause", "resume", "checkpoint")
P28_MAX_BODY = 16 * 1024 * 1024          # 16 MB raw (≈12 MB file b64)
P28_COMMANDS_CAP = 200


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _atomic_json(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    with open(tmp, "ab") as fh:
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


class RemoteGateway:
    """The PHASE 28 gateway — start() serves HTTP + runs the executor."""

    def __init__(self, lm, app=None, notify=None) -> None:
        self.lm = lm
        self.app = app                        # optional NEXUS26App hooks
        self.notify = notify                  # optional callable(dict)
        self.root = Path(lm.NEXUS_ROOT)
        self.rdir = self.root / "remote"
        self.web_dir = self.rdir / "web"
        self.inbox = self.rdir / "inbox"
        self.outbox = self.rdir / "outbox"
        self.cp_dir = self.root / "checkpoints"
        self.token_path = self.rdir / "token.txt"
        self.commands_path = self.rdir / "commands.json"
        self.state_path = self.rdir / "state.json"
        self.info_path = self.rdir / "gateway.json"
        self.log_path = self.rdir / "gateway.log"
        for d in (self.rdir, self.inbox, self.outbox, self.web_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.token = self._ensure_token()
        self.commands: list = self._load_commands()
        self.info: dict = {}
        self.httpd = None
        self.port = None
        self.http_thread = None
        self.executor_thread = None
        self._stop = threading.Event()
        self.started_utc = None
        self.executed_count = 0
        self.model_status = "…"
        self._lock = threading.Lock()

    # ------------------------------------------------------------ disk state
    def _ensure_token(self) -> str:
        if self.token_path.is_file():
            t = self.token_path.read_text(encoding="utf-8").strip()
            if t:
                return t
        tok = os.urandom(16).hex()
        self.token_path.write_text(tok, encoding="utf-8")
        return tok

    def _load_commands(self) -> list:
        try:
            return json.loads(self.commands_path.read_text(
                encoding="utf-8")).get("commands", [])
        except BaseException:  # noqa: BLE001
            return []

    def _save_commands(self) -> None:
        if len(self.commands) > P28_COMMANDS_CAP:
            self.commands = self.commands[-P28_COMMANDS_CAP:]
        _atomic_json(self.commands_path, {"commands": self.commands})

    def _state(self) -> dict:
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except BaseException:  # noqa: BLE001
            return {"paused": False}

    def _log(self, line: str) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%H:%M:%S')} {line}\n")
        except OSError:
            pass

    # ------------------------------------------------------------ lifecycle
    def start(self, port: int = 0) -> dict:
        if self.httpd is not None:
            return self.info
        if port == 0:
            port = 8899
            s = socket.socket()
            try:
                s.bind(("127.0.0.1", port))
            except OSError:
                s.bind(("127.0.0.1", 0))
                port = s.getsockname()[1]
            finally:
                s.close()
        self.port = port
        self.started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), self._handler())
        self.httpd.daemon_threads = True
        self.http_thread = threading.Thread(target=self.httpd.serve_forever,
                                            name="nexus-remote-http",
                                            daemon=True)
        self.executor_thread = threading.Thread(target=self._executor_loop,
                                                name="nexus-remote-exec",
                                                daemon=True)
        self.http_thread.start()
        self.executor_thread.start()
        self.info = {"port": port, "pid": os.getpid(),
                     "utc": self.started_utc, "running": True,
                     "service": "nexus-remote", "version": self.lm.VERSION}
        _atomic_json(self.info_path, self.info)
        self._log(f"gateway started on 127.0.0.1:{port}")
        return self.info

    def stop(self) -> dict:
        self._stop.set()
        out = {"stopped": True}
        if self.httpd is not None:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except BaseException:  # noqa: BLE001
                pass
            self.httpd = None
        try:
            info = dict(self.info or {})
            info["running"] = False
            info["utc_stop"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime())
            _atomic_json(self.info_path, info)
        except BaseException:  # noqa: BLE001
            pass
        self._log("gateway stopped")
        return out

    # ------------------------------------------------------------ executor
    def _executor_loop(self) -> None:
        last_model = 0.0
        while not self._stop.is_set():
            try:
                if time.time() - last_model > 15:
                    last_model = time.time()
                    try:
                        engine, base = self.lm.pick_runtime(
                            "http://127.0.0.1:8080")
                        self.model_status = (f"{engine} at {base}" if engine
                                             else "offline")
                    except BaseException:  # noqa: BLE001
                        self.model_status = "offline"
                for cmd in list(self.commands):
                    if cmd.get("state") == "queued":
                        self._execute(cmd)
                        break            # one at a time, oldest first
            except BaseException as exc:  # noqa: BLE001
                self._log(f"executor error: {type(exc).__name__}: {exc}")
            self._stop.wait(1.5)

    def _execute(self, cmd: dict) -> None:
        cmd["state"] = "running"
        self._save_commands()
        ctype = cmd.get("type")
        payload = cmd.get("payload") or {}
        try:
            if ctype == "pause":
                _atomic_json(self.state_path,
                             {"paused": True,
                              "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                   time.gmtime()),
                              "by": "remote"})
                if self.notify:
                    self.notify({"action": "pause"})
                cmd["result"] = {"paused": True,
                                 "honest": "no new work until resume"}
            elif ctype == "resume":
                _atomic_json(self.state_path,
                             {"paused": False,
                              "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                   time.gmtime()),
                              "by": "remote"})
                if self.notify:
                    self.notify({"action": "resume"})
                cmd["result"] = {"paused": False}
            elif ctype == "checkpoint":
                cmd["result"] = self._checkpoint()
            elif ctype == "task":
                cmd["result"] = self._run_task(str(payload.get("goal", "")))
            elif ctype == "chat":
                cmd["result"] = self._chat(str(payload.get("text", "")))
            else:
                cmd["state"] = "failed"
                cmd["result"] = {"error": f"unknown type {ctype}"}
                self._save_commands()
                return
            cmd["state"] = "done"
            self.executed_count += 1
        except BaseException as exc:  # noqa: BLE001
            cmd["state"] = "failed"
            cmd["result"] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
        cmd["utc_done"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self._save_commands()

    def _checkpoint(self) -> dict:
        stamp = time.strftime("%Y%m%d_%H%M%S")
        target = self.cp_dir / f"remote_cp_{stamp}"
        target.mkdir(parents=True, exist_ok=True)
        copied: list = []
        sources = [
            (self.root / "tasks", "tasks"),
            (self.root / "ui_memory.json", "ui_memory.json"),
            (self.root / "ui_settings.json", "ui_settings.json"),
        ]
        for src, label in sources:
            try:
                if src.is_dir():
                    dst = target / label
                    shutil.copytree(src, dst, dirs_exist_ok=True)
                    for f in dst.rglob("*"):
                        if f.is_file():
                            copied.append({"file": f"{label}/{f.relative_to(dst)}",
                                           "sha256": _sha256_file(f)[:16],
                                           "size": f.stat().st_size})
                elif src.is_file():
                    dst = target / label
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    copied.append({"file": label,
                                   "sha256": _sha256_file(dst)[:16],
                                   "size": dst.stat().st_size})
            except BaseException as exc:  # noqa: BLE001
                copied.append({"file": label, "error": f"{exc}"[:120]})
        manifest = {"checkpoint": target.name,
                    "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "by": "remote", "files": copied, "count": len(copied)}
        (target / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=1),
            encoding="utf-8")
        if self.notify:
            self.notify({"action": "activity",
                         "line": f"[remote] نقطة حفظ عن بُعد — {len(copied)} ملف"})
        return {"checkpoint": target.name, "count": len(copied),
                "dir": str(target)}

    def _run_task(self, goal: str) -> dict:
        if not goal.strip():
            return {"error": "empty goal"}
        # preserve the gate5 cert before a remote task overwrites it
        gate5 = Path(self.lm.PROOFS) / "midpoint_task.json"
        backup = None
        try:
            if gate5.is_file():
                backup = {"sha_before": _sha256_file(gate5),
                          "backed_up_to": str(self.rdir / "gate5_task_backup.json")}
                shutil.copy2(gate5, self.rdir / "gate5_task_backup.json")
        except BaseException:  # noqa: BLE001
            pass
        rc = self.lm.run_task(goal)
        cert = {}
        try:
            cert = json.loads(gate5.read_text(encoding="utf-8"))
        except BaseException:  # noqa: BLE001
            pass
        if self.notify:
            self.notify({"action": "activity",
                         "line": f"[remote] مهمة عن بُعد: {goal[:60]} → rc={rc}"})
        return {"rc": rc, "task_id": str(cert.get("task_id", "")),
                "verdict": cert.get("verdict"), "gate5_cert_backup": backup,
                "goal": goal[:160]}

    def _chat(self, text: str) -> dict:
        if not text.strip():
            return {"error": "empty text"}
        try:
            engine, base = self.lm.pick_runtime("http://127.0.0.1:8080")
            if not engine:
                return {"reply": None,
                        "honest": "النموذج المحلي غير مشغّل الآن",
                        "model": "offline"}
            reply = self.lm.generate_once(engine, base, text, "qwen3:0.6b")
            return {"reply": (reply or "")[:900],
                    "model": f"{engine} at {base}"}
        except BaseException as exc:  # noqa: BLE001
            return {"error": f"{type(exc).__name__}: {exc}"[:200]}

    # ------------------------------------------------------------ tasks api
    def _tasks_summary(self) -> list:
        try:
            from nexus.core.persistence.repository import TaskRepository
            repo = TaskRepository(self.root / "tasks", create=False)
            out = []
            for s in repo.list_summaries():
                out.append({
                    "id": str(getattr(s, "id", ""))[:40],
                    "goal": str(getattr(s, "goal", ""))[:160],
                    "state": str(getattr(s, "state",
                                         getattr(s, "status", ""))),
                    "created": str(getattr(s, "created_at",
                                           getattr(s, "utc", "")))})
            return out
        except BaseException as exc:  # noqa: BLE001
            return [{"error": f"{type(exc).__name__}: {exc}"[:160]}]

    # ------------------------------------------------------------ security
    @staticmethod
    def safe_name(name: str):
        if not name or len(name) > 120:
            return None
        if ".." in name or "/" in name or "\\" in name:
            return None
        if not re.fullmatch(r"[A-Za-z0-9._\- ]+", name):
            return None
        return name

    # ------------------------------------------------------------ handler
    def _handler(self):
        gateway = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):  # noqa: N802
                gateway._log("http " + (fmt % args)[:160])

            def _cors(self):
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods",
                                 "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers",
                                 "Authorization, Content-Type")

            def _json(self, code, obj):
                body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type",
                                 "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self._cors()
                self.end_headers()
                self.wfile.write(body)

            def do_OPTIONS(self):  # noqa: N802
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self._cors()
                self.end_headers()

            def _authed(self) -> bool:
                h = self.headers.get("Authorization", "")
                return (h.startswith("Bearer ")
                        and hmac.compare_digest(h[7:].strip(), gateway.token))

            def _body(self) -> dict:
                n = int(self.headers.get("Content-Length") or 0)
                if n <= 0 or n > P28_MAX_BODY:
                    raise ValueError(f"bad body size {n}")
                return json.loads(self.rfile.read(n).decode("utf-8"))

            def do_GET(self):  # noqa: N802
                u = urlparse(self.path)
                path = u.path
                try:
                    if path == "/api/health":
                        return self._json(200, {"ok": True,
                                                "service": "nexus-remote",
                                                "version": gateway.lm.VERSION})
                    if path.startswith("/api/"):
                        if not self._authed():
                            return self._json(401, {"ok": False,
                                                    "error": "unauthorized"})
                        if path == "/api/status":
                            st = gateway._state()
                            up = 0
                            try:
                                up = int(time.time() - time.mktime(
                                    time.strptime(gateway.started_utc,
                                                  "%Y-%m-%dT%H:%M:%SZ")))
                            except BaseException:  # noqa: BLE001
                                up = 0
                            return self._json(200, {
                                "ok": True,
                                "product": gateway.lm.PRODUCT,
                                "version": gateway.lm.VERSION,
                                "paused": bool(st.get("paused")),
                                "tasks_count": len(gateway._tasks_summary()),
                                "model": gateway.model_status,
                                "uptime_s": up, "port": gateway.port,
                                "executed": gateway.executed_count,
                                "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                     time.gmtime())})
                        if path == "/api/tasks":
                            return self._json(200, {
                                "ok": True, "tasks": gateway._tasks_summary()})
                        if path == "/api/commands":
                            return self._json(200, {
                                "ok": True,
                                "commands": gateway.commands[-100:]})
                        if path.startswith("/api/commands/"):
                            cid = path.rsplit("/", 1)[-1]
                            for c in gateway.commands:
                                if c.get("id") == cid:
                                    return self._json(200, {"ok": True,
                                                            "command": c})
                            return self._json(404, {"ok": False,
                                                    "error": "no such command"})
                        if path == "/api/files":
                            items = []
                            for f in sorted(gateway.outbox.iterdir()):
                                if f.is_file():
                                    items.append({"name": f.name,
                                                  "size": f.stat().st_size,
                                                  "sha256": _sha256_file(f)})
                            return self._json(200, {"ok": True,
                                                    "files": items})
                        if path == "/api/files/get":
                            qs = parse_qs(u.query)
                            name = gateway.safe_name(
                                (qs.get("name") or [""])[0])
                            if not name:
                                return self._json(400, {
                                    "ok": False, "error": "unsafe filename"})
                            f = gateway.outbox / name
                            if not f.is_file():
                                return self._json(404, {
                                    "ok": False, "error": "no such file"})
                            data = f.read_bytes()
                            return self._json(200, {
                                "ok": True, "name": name, "size": len(data),
                                "sha256": _sha256_bytes(data),
                                "b64": base64.b64encode(data).decode("ascii")})
                        return self._json(404, {"ok": False,
                                                "error": "unknown api route"})
                    # static frontend (public shell — data is token-gated)
                    fname = {"/": "index.html",
                             "/index.html": "index.html",
                             "/app.css": "app.css",
                             "/app.js": "app.js"}.get(path)
                    if fname:
                        f = gateway.web_dir / fname
                        if f.is_file():
                            data = f.read_bytes()
                            ctype = ("text/html" if fname.endswith(".html")
                                     else "text/css"
                                     if fname.endswith(".css")
                                     else "application/javascript")
                            self.send_response(200)
                            self.send_header("Content-Type",
                                             f"{ctype}; charset=utf-8")
                            self.send_header("Content-Length", str(len(data)))
                            self._cors()
                            self.end_headers()
                            self.wfile.write(data)
                            return
                    return self._json(404, {"ok": False, "error": "not found"})
                except BaseException as exc:  # noqa: BLE001
                    return self._json(500, {"ok": False,
                                            "error": f"{type(exc).__name__}: {exc}"[:200]})

            def do_POST(self):  # noqa: N802
                u = urlparse(self.path)
                path = u.path
                try:
                    if not path.startswith("/api/"):
                        return self._json(404, {"ok": False,
                                                "error": "not found"})
                    if not self._authed():
                        return self._json(401, {"ok": False,
                                                "error": "unauthorized"})
                    body = self._body()
                    if path == "/api/commands":
                        ctype = str(body.get("type", ""))
                        if ctype not in P28_TYPES:
                            return self._json(400, {
                                "ok": False,
                                "error": f"type must be one of {P28_TYPES}"})
                        cmd = {"id": os.urandom(8).hex(), "type": ctype,
                               "payload": body.get("payload") or {},
                               "state": "queued",
                               "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                    time.gmtime())}
                        with gateway._lock:
                            gateway.commands.append(cmd)
                            gateway._save_commands()
                        return self._json(201, {"ok": True, "id": cmd["id"],
                                                "state": "queued"})
                    if path == "/api/files/push":
                        name = gateway.safe_name(str(body.get("name", "")))
                        if not name:
                            return self._json(400, {"ok": False,
                                                    "error": "unsafe filename"})
                        try:
                            data = base64.b64decode(str(body.get("b64", "")),
                                                    validate=True)
                        except BaseException as exc:  # noqa: BLE001
                            return self._json(400, {
                                "ok": False, "error": f"bad b64: {exc}"[:120]})
                        if len(data) > 8 * 1024 * 1024:
                            return self._json(400, {
                                "ok": False,
                                "error": "file too large (8MB cap)"})
                        dst = gateway.inbox / name
                        dst.write_bytes(data)
                        sha = _sha256_bytes(data)
                        return self._json(201, {"ok": True, "name": name,
                                                "size": len(data),
                                                "sha256": sha,
                                                "path": str(dst)})
                    return self._json(404, {"ok": False,
                                            "error": "unknown api route"})
                except BaseException as exc:  # noqa: BLE001
                    return self._json(500, {"ok": False,
                                            "error": f"{type(exc).__name__}: {exc}"[:200]})

        return Handler


# ================================================================ selftest

def phase28_selftest(lm) -> int:
    """PHASE 28 selftest — the whole remote loop over REAL localhost HTTP:
    auth enforcement (no token 401 · wrong token 401) · status · commands
    pause/resume (state.json truth) · checkpoint (real snapshot) · task
    (REAL M4 loop through the core) · chat (honest offline) · file push and
    pull (sha256 both sides) · traversal rejection · static frontend · CORS.
    Every verdict lands in proofs\\phase28_remote.json."""
    import urllib.error
    import urllib.request

    t0 = time.time()
    cert: dict = {"product": lm.PRODUCT, "version": lm.VERSION,
                  "check": "phase28-remote-web",
                  "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "pid": os.getpid(), "python": sys.version.split()[0],
                  "sections": {}}
    secs = cert["sections"]

    def _finish(verdict, **extra) -> int:
        cert["verdict"] = verdict
        cert["seconds"] = round(time.time() - t0, 2)
        cert.update(extra)
        p = Path(lm.PROOFS) / "phase28_remote.json"
        p.write_text(json.dumps(cert, ensure_ascii=False, indent=1),
                     encoding="utf-8")
        print(f"certificate: {p}")
        print(json.dumps({k: cert.get(k) for k in ("verdict", "sections_ok")},
                         ensure_ascii=False))
        return 0 if verdict == "PASS" else 1

    gw = RemoteGateway(lm)
    info = gw.start()
    cert["port"] = info["port"]
    base = f"http://127.0.0.1:{info['port']}"
    tok = gw.token

    def req(method, path, body=None, token=tok, timeout=30):
        r = urllib.request.Request(base + path, method=method)
        if token:
            r.add_header("Authorization", f"Bearer {token}")
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            r.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(r, data=data, timeout=timeout) as resp:
                return (resp.status,
                        json.loads(resp.read().decode("utf-8")),
                        dict(resp.headers))
        except urllib.error.HTTPError as e:
            try:
                payload = json.loads(e.read().decode("utf-8"))
            except BaseException:  # noqa: BLE001
                payload = {}
            return e.code, payload, dict(e.headers)

    def wait_command(cid, timeout=150):
        end = time.time() + timeout
        while time.time() < end:
            st, out, _ = req("GET", f"/api/commands/{cid}")
            if st == 200 and out.get("command", {}).get("state") in ("done",
                                                                     "failed"):
                return out["command"]
            time.sleep(1.0)
        return {"state": "timeout", "id": cid}

    try:
        # health (no token — the only open route)
        st, out, hdrs = req("GET", "/api/health", token=None)
        secs["health"] = {"ok": st == 200 and out.get("ok") is True,
                          "status": st, "body": out}

        # auth enforcement — no token and wrong token both rejected
        st1, _, _ = req("GET", "/api/status", token=None)
        st2, _, _ = req("GET", "/api/status", token="wrong-token-000")
        secs["auth"] = {"ok": (st1 == 401 and st2 == 401),
                        "no_token_status": st1, "wrong_token_status": st2,
                        "note": "401 both — the API is closed without pairing"}

        # status with the real token
        st, out, _ = req("GET", "/api/status")
        secs["status"] = {"ok": st == 200 and out.get("ok") is True,
                          "status": st,
                          "body": {k: out.get(k) for k in
                                   ("paused", "tasks_count", "model",
                                    "port", "version")}}

        # pause → state.json says paused=true
        st, out, _ = req("POST", "/api/commands", {"type": "pause"})
        cid = out.get("id", "")
        cmd = wait_command(cid) if cid else {"state": "no-id"}
        on_disk = json.loads(gw.state_path.read_text(encoding="utf-8"))
        secs["pause"] = {"ok": cmd.get("state") == "done"
                         and on_disk.get("paused") is True,
                         "command_state": cmd.get("state"),
                         "state_on_disk": on_disk}

        # resume → paused=false
        st, out, _ = req("POST", "/api/commands", {"type": "resume"})
        cid = out.get("id", "")
        cmd = wait_command(cid) if cid else {"state": "no-id"}
        on_disk = json.loads(gw.state_path.read_text(encoding="utf-8"))
        secs["resume"] = {"ok": cmd.get("state") == "done"
                          and on_disk.get("paused") is False,
                          "command_state": cmd.get("state"),
                          "state_on_disk": on_disk}

        # checkpoint from the phone
        before = set(p.name for p in gw.cp_dir.glob("remote_cp_*"))
        st, out, _ = req("POST", "/api/commands", {"type": "checkpoint"})
        cid = out.get("id", "")
        cmd = wait_command(cid, timeout=180) if cid else {"state": "no-id"}
        after = set(p.name for p in gw.cp_dir.glob("remote_cp_*"))
        new_cp = sorted(after - before)
        secs["checkpoint"] = {"ok": cmd.get("state") == "done" and bool(new_cp),
                              "command_state": cmd.get("state"),
                              "result": cmd.get("result"),
                              "new_checkpoint": new_cp[:1]}

        # task — the REAL M4 loop through the core
        goal = ("PHASE 28 remote task — اكتب ملف remote_28.txt "
                "يحتوي عملية نجاح في مساحة العمل")
        st, out, _ = req("POST", "/api/commands",
                         {"type": "task", "payload": {"goal": goal}})
        cid = out.get("id", "")
        cmd = wait_command(cid, timeout=240) if cid else {"state": "no-id"}
        res = cmd.get("result") or {}
        st2, tasks, _ = req("GET", "/api/tasks")
        tid = str(res.get("task_id", ""))
        listed = any(str(t.get("id", "")) == tid
                     for t in tasks.get("tasks", []))
        secs["task"] = {"ok": cmd.get("state") == "done"
                        and res.get("verdict") == "PASS" and listed,
                        "command_state": cmd.get("state"),
                        "task_id": tid, "rc": res.get("rc"),
                        "verdict": res.get("verdict"),
                        "listed_in_api": listed,
                        "tasks_count": len(tasks.get("tasks", []))}

        # chat — honest offline or real reply
        st, out, _ = req("POST", "/api/commands",
                         {"type": "chat",
                          "payload": {"text": "مرحبا يا NEXUS"}})
        cid = out.get("id", "")
        cmd = wait_command(cid, timeout=90) if cid else {"state": "no-id"}
        res = cmd.get("result") or {}
        secs["chat"] = {"ok": cmd.get("state") == "done"
                        and ("reply" in res or "error" in res
                             or "honest" in res),
                        "command_state": cmd.get("state"),
                        "model": res.get("model"),
                        "honest": res.get("honest"),
                        "reply_len": len(str(res.get("reply") or ""))}

        # file push phone→device (sha256 roundtrip)
        payload = f"PHASE 28 file transfer test — {cert['utc']}".encode("utf-8")
        want_sha = _sha256_bytes(payload)
        st, out, _ = req("POST", "/api/files/push",
                         {"name": "phone_to_device.txt",
                          "b64": base64.b64encode(payload).decode("ascii")})
        disk_ok = False
        if st == 201:
            f = gw.inbox / "phone_to_device.txt"
            disk_ok = f.is_file() and _sha256_file(f) == want_sha
        secs["files_push"] = {"ok": st == 201 and disk_ok, "status": st,
                              "api_sha": str(out.get("sha256", ""))[:20],
                              "disk_sha_match": disk_ok}

        # file pull device→phone
        report = gw.outbox / "p28_report.txt"
        report.write_text(f"NEXUS remote outbox proof — {cert['utc']}",
                          encoding="utf-8")
        want2 = _sha256_file(report)
        st, out, _ = req("GET", "/api/files/get?name=p28_report.txt")
        pulled = base64.b64decode(out.get("b64", "")) if st == 200 else b""
        secs["files_pull"] = {"ok": st == 200
                              and _sha256_bytes(pulled) == want2,
                              "status": st, "size": out.get("size"),
                              "sha_match": _sha256_bytes(pulled) == want2}

        # security — traversal rejected on pull AND push
        st1, _, _ = req("GET", "/api/files/get?name=..%5C..%5Cnexus_ui.py")
        st2, _, _ = req("POST", "/api/files/push",
                        {"name": "../evil.txt", "b64": "aGk="})
        st3, _, _ = req("GET", "/api/files/get?name=nexus_ui.py")
        secs["security"] = {"ok": st1 == 400 and st2 == 400 and st3 == 404,
                            "traversal_pull": st1, "traversal_push": st2,
                            "name_probe_outside_outbox": st3,
                            "note": "traversal rejected 400; outbox-only reads"}

        # static frontend served by the gateway
        with urllib.request.urlopen(base + "/", timeout=15) as resp:
            html = resp.read().decode("utf-8")
        with urllib.request.urlopen(base + "/app.js", timeout=15) as resp:
            js = resp.read().decode("utf-8")
        with urllib.request.urlopen(base + "/app.css", timeout=15) as resp:
            css = resp.read().decode("utf-8")
        secs["static"] = {"ok": ("NEXUS Remote" in html and "api(" in js
                                 and "background" in css),
                          "html_has_title": "NEXUS Remote" in html,
                          "js_bytes": len(js), "css_bytes": len(css),
                          "html_bytes": len(html)}

        # CORS for GitHub Pages
        st, out, hdrs = req("GET", "/api/health", token=None)
        opts_r = urllib.request.Request(base + "/api/status", method="OPTIONS")
        with urllib.request.urlopen(opts_r, timeout=15) as resp:
            opt_headers = dict(resp.headers)
        secs["cors"] = {"ok": hdrs.get("Access-Control-Allow-Origin") == "*"
                        and opt_headers.get("Access-Control-Allow-Origin") == "*",
                        "allow_origin": hdrs.get("Access-Control-Allow-Origin"),
                        "options_allow_origin":
                            opt_headers.get("Access-Control-Allow-Origin")}

        sections_ok = bool(secs
                           and all(s.get("ok") for s in secs.values())
                           and len(secs) == 13)
        cert["sections_ok"] = sections_ok
        ok = sections_ok
        return _finish("PASS" if ok else "FAIL",
                       error=None if ok
                       else "one or more PHASE 28 sections failed")
    except BaseException as exc:  # noqa: BLE001
        cert["sections_ok"] = False
        return _finish("FAIL", error=f"{type(exc).__name__}: {exc}"[:300])
    finally:
        try:
            gw.stop()
        except BaseException:  # noqa: BLE001
            pass
