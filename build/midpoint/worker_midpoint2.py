"""Detached MIDPOINT worker v2 — REBUILD the exe (no-proxy launcher) then
run GATE #4: the first real local chat.

Why v2: attempt 1 failed honestly — llama-server health never came up and
the boot probe had shown `URLError: timed out` (timeout, NOT refused) for
127.0.0.1 — the signature of a system proxy swallowing localhost calls.
This worker: records system proxies as evidence, rebuilds NEXUS.exe from
the no-proxy launcher, then finds ALL llama-server backends and tries each
with a socket-first, proxy-immune health check before the scripted chat.

Evidence (all on disk, honest):
    results\\build_exe.phases.log      build heartbeats
    results\\chat_exe.phases.log       chat heartbeats
    results\\llama_server.log          server stdout/stderr (buffered!)
    results\\chat_transcript.txt       full --chat transcript
    proofs\\midpoint_build.json        build + --check verdict
    proofs\\midpoint_chat.json         chat verdict + prompt + reply
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent           # M:\\NEXUS\\build\\midpoint
NEXUS_ROOT = HERE.parent.parent                  # M:\\NEXUS
PROOFS = NEXUS_ROOT / "proofs"
RESULTS = HERE / "results"
EXE = HERE / "dist" / "NEXUS.exe"
CERT_BUILD = PROOFS / "midpoint_build.json"
CERT_CHAT = PROOFS / "midpoint_chat.json"
TRANSCRIPT = RESULTS / "chat_transcript.txt"
SERVER_LOG = RESULTS / "llama_server.log"

MODEL_ROOT = Path(r"C:\Users\MohandsMohammad\.mimo_storage")   # junction -> M:
SEARCH_ROOTS = [
    Path(r"C:\Users\MohandsMohammad\.lmstudio"),               # junction -> M:
    Path(r"C:\Users\MohandsMohammad\AppData\Local\LM-Studio"),
    Path(r"C:\Users\MohandsMohammad\AppData\Local\Programs\LM Studio"),
    Path(r"M:\C-RELIEF\mohands\.lmstudio"),
]
PRUNE = {".cache", "logs", "app-data", "__pycache__", "snapshots"}
PORT = 8080
PROMPT = "مرحبًا يا NEXUS، عرّف عن نفسك بجملة واحدة."


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def hb(log: Path, phase: str, detail: str = "") -> None:
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"utc": _utc(), "phase": phase,
                                 "detail": str(detail)[:220]},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass


BUILD_LOG = RESULTS / "build_exe.phases.log"
CHAT_LOG = RESULTS / "chat_exe.phases.log"


def _write_json(path: Path, obj: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except OSError:
        pass


def _run(cmd: list, cwd: Path | None = None, timeout: int = 1800):
    hb(BUILD_LOG, "subprocess_start", " ".join(str(c) for c in cmd)[:200])
    p = subprocess.run(cmd, cwd=str(cwd or HERE), capture_output=True,
                       text=True, timeout=timeout)
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        with open(RESULTS / "build_stdout.log", "a", encoding="utf-8",
                  errors="replace") as fh:
            fh.write(f"\n===== {_utc()} $ {' '.join(map(str, cmd))}\n")
            fh.write(f"rc={p.returncode}\n{(p.stdout or '')[-4000:]}\n"
                     f"{(p.stderr or '')[-2000:]}\n")
    except OSError:
        pass
    hb(BUILD_LOG, "subprocess_done", f"rc={p.returncode}")
    return p


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------ stage: BUILD

def stage_build() -> dict:
    t0 = time.time()
    cert: dict = {"product": "NEXUS.exe rebuild (no-proxy launcher)",
                  "utc": _utc(), "pid": os.getpid(),
                  "python": sys.version.split()[0]}
    try:
        py = sys.executable
        hb(BUILD_LOG, "build_stage_begin", f"pid={os.getpid()}")
        chk = _run([py, "-m", "pip", "show", "pyinstaller"], timeout=180)
        if chk.returncode != 0:
            inst = _run([py, "-m", "pip", "install", "--upgrade",
                         "pyinstaller"], timeout=900)
            if inst.returncode != 0:
                cert["verdict"] = "FAIL"
                cert["error"] = "pip install pyinstaller failed (honest)"
                cert["tail"] = ((inst.stderr or "") + (inst.stdout or ""))[-900:]
                return cert
        hb(BUILD_LOG, "build_begin")
        b = _run([py, "-m", "PyInstaller", "--noconfirm", "--clean",
                  "NEXUS.exe.spec"], cwd=HERE, timeout=2400)
        cert["build_rc"] = b.returncode
        if b.returncode != 0 or not EXE.exists():
            cert["verdict"] = "FAIL"
            cert["error"] = "pyinstaller failed or exe missing (honest)"
            cert["tail"] = ((b.stderr or "") + (b.stdout or ""))[-900:]
            return cert
        cert["exe"] = str(EXE)
        cert["exe_size_bytes"] = EXE.stat().st_size
        cert["sha256"] = sha256_of(EXE)
        hb(BUILD_LOG, "build_done",
           f"size={cert['exe_size_bytes']} sha256={cert['sha256'][:16]}...")
        r = _run([str(EXE), "--check"], cwd=HERE, timeout=300)
        cert["check_rc"] = r.returncode
        cert["check_verdict"] = "PASS" if r.returncode == 0 else "FAIL"
        cert["verdict"] = cert["check_verdict"]
        hb(BUILD_LOG, "exe_check_done", f"rc={r.returncode}")
        return cert
    except BaseException as exc:  # noqa: BLE001
        cert["verdict"] = "FAIL"
        cert["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return cert
    finally:
        cert["build_seconds"] = round(time.time() - t0, 2)
        cert["utc_end"] = _utc()
        _write_json(CERT_BUILD, cert)
        hb(BUILD_LOG, "build_stage_done", f"verdict={cert.get('verdict')}")


# ------------------------------------------------------------- stage: CHAT

def port_open(timeout: float = 3.0) -> bool:
    """Proxy-immune TCP probe — sockets never consult system proxies."""
    try:
        with socket.create_connection(("127.0.0.1", PORT), timeout=timeout):
            return True
    except OSError:
        return False


def http_health() -> bool:
    try:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with op.open(f"http://127.0.0.1:{PORT}/health", timeout=4) as r:
            return r.status == 200
    except BaseException:
        return False


def wait_health(deadline_s: int = 150) -> bool:
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        if port_open() and http_health():
            return True
        time.sleep(3)
    return False


def find_all_llama_servers() -> list:
    hb(CHAT_LOG, "find_begin")
    deadline = time.time() + 90
    hits: list = []
    for root in SEARCH_ROOTS:
        if not root.exists():
            continue
        for dirpath, dirs, files in os.walk(root):
            if time.time() > deadline:
                hb(CHAT_LOG, "find_deadline", str(root))
                break
            dirs[:] = [d for d in dirs if d not in PRUNE]
            for f in files:
                lf = f.lower()
                if lf.startswith("llama-server") and lf.endswith(".exe"):
                    hits.append(str(Path(dirpath) / f))
    hits = sorted(set(hits))
    for h in hits:
        hb(CHAT_LOG, "find_hit", h)
    return hits


def pick_model() -> tuple | None:
    best = None
    snaps = MODEL_ROOT / "snapshots"
    for base in (snaps, MODEL_ROOT):
        if not base.exists():
            continue
        for p in base.rglob("*.gguf"):
            try:
                sz = p.stat().st_size
            except OSError:
                continue
            if best is None or sz < best[1]:
                best = (p, sz)
            if best[1] < 400_000_000:
                break
        if best:
            break
    return best


def stage_chat() -> dict:
    t0 = time.time()
    cert: dict = {"product": "NEXUS first real chat (MIDPOINT #4)",
                  "utc": _utc(), "pid": os.getpid(), "prompt": PROMPT,
                  "system_proxies": urllib.request.getproxies(),
                  "attempts": []}
    server: subprocess.Popen | None = None
    try:
        hb(CHAT_LOG, "chat_stage_begin", f"pid={os.getpid()}")
        if not EXE.exists():
            cert["verdict"] = "FAIL"
            cert["error"] = "dist\\NEXUS.exe missing — build stage failed"
            return cert

        hits = find_all_llama_servers()
        cert["llama_servers_found"] = hits
        if not hits:
            cert["verdict"] = "FAIL"
            cert["error"] = "llama-server.exe not found on this machine"
            return cert

        model = pick_model()
        if not model:
            cert["verdict"] = "FAIL"
            cert["error"] = "no .gguf model found under .mimo_storage junction"
            return cert
        cert["model"] = str(model[0])
        cert["model_mb"] = round(model[1] / 1e6, 1)
        hb(CHAT_LOG, "model_picked", f"{model[0]} ({cert['model_mb']} MB)")

        healthy_server = None
        for i, srv in enumerate(hits):
            hb(CHAT_LOG, "server_try", f"{i + 1}/{len(hits)} {srv}")
            with open(SERVER_LOG, "ab") as fh:
                server = subprocess.Popen(
                    [srv, "-m", str(model[0]), "--host", "127.0.0.1",
                     "--port", str(PORT), "-c", "2048"],
                    stdout=fh, stderr=fh, stdin=subprocess.DEVNULL,
                    cwd=str(HERE))
            time.sleep(5)
            if server.poll() is not None:
                hb(CHAT_LOG, "server_died_instantly", f"rc={server.returncode}")
                cert["attempts"].append({"path": srv,
                                         "result": f"died rc={server.returncode}"})
                server = None
                continue
            if wait_health(150):
                hb(CHAT_LOG, "server_up", srv)
                healthy_server = srv
                break
            cert["attempts"].append({"path": srv, "result": "no health in 150s"})
            try:
                server.terminate()
                server.wait(timeout=15)
            except Exception:  # noqa: BLE001
                try:
                    server.kill()
                except Exception:  # noqa: BLE001
                    pass
            server = None
            hb(CHAT_LOG, "server_stopped_unhealthy")

        cert["server"] = healthy_server or "NONE healthy (honest)"
        if not healthy_server:
            cert["verdict"] = "FAIL"
            cert["error"] = "no llama-server backend became healthy"
            return cert

        hb(CHAT_LOG, "chat_begin", "NEXUS.exe --chat (scripted prompt)")
        p = subprocess.Popen([str(EXE), "--chat"], stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, encoding="utf-8", errors="replace",
                             cwd=str(HERE))
        try:
            out, _ = p.communicate(input=PROMPT + "\nexit\n", timeout=420)
        except subprocess.TimeoutExpired:
            p.kill()
            out, _ = p.communicate()
        try:
            TRANSCRIPT.write_text(out or "", encoding="utf-8")
        except OSError:
            pass
        cert["transcript_chars"] = len(out or "")
        reply = ""
        for line in (out or "").splitlines():
            ls = line.strip()
            if ls.startswith("nexus>") and len(ls) > 6:
                reply = ls[6:].strip()
        cert["reply"] = reply[:800]
        cert["verdict"] = "PASS" if reply else "FAIL"
        if not reply:
            cert["error"] = "no 'nexus>' reply line in transcript (honest)"
        hb(CHAT_LOG, "chat_done", f"reply_chars={len(reply)}")
        return cert
    except BaseException as exc:  # noqa: BLE001
        cert["verdict"] = "FAIL"
        cert["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return cert
    finally:
        if server is not None:
            try:
                server.terminate()
                server.wait(timeout=15)
            except Exception:  # noqa: BLE001
                try:
                    server.kill()
                except Exception:  # noqa: BLE001
                    pass
            hb(CHAT_LOG, "server_stopped")
        cert["chat_seconds"] = round(time.time() - t0, 2)
        cert["utc_end"] = _utc()
        _write_json(CERT_CHAT, cert)
        hb(CHAT_LOG, "chat_stage_done", f"verdict={cert.get('verdict')}")


def main() -> int:
    hb(CHAT_LOG, "worker_v2_start",
       f"proxies={json.dumps(urllib.request.getproxies())[:180]}")
    b = stage_build()
    if b.get("verdict") == "PASS":
        stage_chat()
    else:
        hb(CHAT_LOG, "chat_skipped", "build failed — see midpoint_build.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
