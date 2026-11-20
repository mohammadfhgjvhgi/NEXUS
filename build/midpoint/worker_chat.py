"""Detached MIDPOINT chat worker — GATE #4: first real local chat.

Chain (all on this machine, honest at every step):
    find llama-server.exe  ->  pick smallest local GGUF (models live on M:
    via junctions — zero deletion law)  ->  start llama-server MODE A on
    127.0.0.1:8080  ->  wait /health  ->  run the REAL NEXUS.exe --chat
    with a scripted prompt  ->  save the transcript + certificate.

Evidence:
    results\\chat_exe.phases.log      heartbeats
    results\\chat_transcript.txt      full --chat stdout
    proofs\\midpoint_chat.json        verdict + prompt + reply
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent           # M:\\NEXUS\\build\\midpoint
NEXUS_ROOT = HERE.parent.parent                  # M:\\NEXUS
PROOFS = NEXUS_ROOT / "proofs"
RESULTS = HERE / "results"
PHASES = RESULTS / "chat_exe.phases.log"
CERT = PROOFS / "midpoint_chat.json"
TRANSCRIPT = RESULTS / "chat_transcript.txt"
SERVER_LOG = RESULTS / "llama_server.log"
EXE = HERE / "dist" / "NEXUS.exe"

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


def hb(phase: str, detail: str = "") -> None:
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        with open(PHASES, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"utc": _utc(), "phase": phase,
                                 "detail": str(detail)[:220]},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass


def _finish(cert: dict, t0: float) -> int:
    cert["chat_seconds"] = round(time.time() - t0, 2)
    cert["utc_end"] = _utc()
    try:
        PROOFS.mkdir(parents=True, exist_ok=True)
        CERT.write_text(json.dumps(cert, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except OSError:
        pass
    hb("done", f"verdict={cert.get('verdict')}")
    return 0


def find_llama_server() -> tuple[list, str]:
    hb("find_begin")
    deadline = time.time() + 90
    for root in SEARCH_ROOTS:
        if not root.exists():
            hb("find_root_missing", str(root))
            continue
        hits: list = []
        for dirpath, dirs, files in os.walk(root):
            if time.time() > deadline:
                hb("find_deadline", str(root))
                break
            dirs[:] = [d for d in dirs if d not in PRUNE]
            for f in files:
                lf = f.lower()
                if lf.startswith("llama-server") and lf.endswith(".exe"):
                    hits.append(str(Path(dirpath) / f))
        if hits:
            hb("find_hit", hits[0])
            return hits, str(root)
        hb("find_root_empty", str(root))
    return [], ""


def pick_model() -> tuple | None:
    """Smallest GGUF under the .mimo_storage junction (fast boot, low RAM)."""
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
            if best[1] < 400_000_000:        # a sub-400MB model is ideal
                break
        if best:
            break
    return best


def wait_health(deadline_s: int = 180) -> bool:
    url = f"http://127.0.0.1:{PORT}/health"
    deadline = time.time() + deadline_s
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=3) as r:
                if r.status == 200:
                    return True
        except BaseException:
            pass
        time.sleep(3)
    return False


def run_chat() -> tuple:
    p = subprocess.Popen([str(EXE), "--chat"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace",
                         cwd=str(HERE))
    try:
        out, _ = p.communicate(input=PROMPT + "\nexit\n", timeout=420)
    except subprocess.TimeoutExpired:
        p.kill()
        out, _ = p.communicate()
        return -9, (out or "")
    return p.returncode, (out or "")


def main() -> int:
    t0 = time.time()
    cert: dict = {
        "product": "NEXUS first real chat (MIDPOINT #4)",
        "utc": _utc(), "pid": os.getpid(),
        "python": sys.version.split()[0], "prompt": PROMPT,
    }
    server: subprocess.Popen | None = None
    try:
        hb("start", f"worker pid={os.getpid()}")
        if not EXE.exists():
            cert["verdict"] = "FAIL"
            cert["error"] = "dist\\NEXUS.exe missing — build first (gate #2)"
            return _finish(cert, t0)

        hits, root = find_llama_server()
        cert["llama_server"] = hits[0] if hits else "NOT FOUND (honest)"
        cert["searched"] = [str(r) for r in SEARCH_ROOTS]
        if not hits:
            cert["verdict"] = "FAIL"
            cert["error"] = "llama-server.exe not found on this machine"
            return _finish(cert, t0)

        model = pick_model()
        if not model:
            cert["verdict"] = "FAIL"
            cert["error"] = "no .gguf model found under .mimo_storage junction"
            return _finish(cert, t0)
        cert["model"] = str(model[0])
        cert["model_mb"] = round(model[1] / 1e6, 1)
        hb("model_picked", f"{model[0]} ({cert['model_mb']} MB)")

        hb("server_start_begin")
        with open(SERVER_LOG, "ab") as fh:
            server = subprocess.Popen(
                [hits[0], "-m", str(model[0]), "--host", "127.0.0.1",
                 "--port", str(PORT), "-c", "2048"],
                stdout=fh, stderr=fh, stdin=subprocess.DEVNULL, cwd=str(HERE))
        up = wait_health()
        cert["server_health"] = "up" if up else "down (honest)"
        if not up:
            cert["verdict"] = "FAIL"
            cert["error"] = "llama-server did not become healthy in 180s"
            return _finish(cert, t0)
        hb("server_up")

        hb("chat_begin", "NEXUS.exe --chat (scripted prompt)")
        rc, out = run_chat()
        try:
            RESULTS.mkdir(parents=True, exist_ok=True)
            TRANSCRIPT.write_text(out or "", encoding="utf-8")
        except OSError:
            pass
        cert["chat_rc"] = rc
        cert["transcript_chars"] = len(out or "")
        reply = ""
        for line in (out or "").splitlines():
            ls = line.strip()
            if ls.startswith("nexus>") and len(ls) > 6:
                reply = ls[6:].strip()
        cert["reply"] = reply[:800]
        cert["verdict"] = "PASS" if reply else "FAIL"
        if not reply:
            cert["error"] = "no 'nexus>' reply line in --chat transcript (honest)"
        hb("chat_done", f"rc={rc} reply_chars={len(reply)}")
        return _finish(cert, t0)
    except BaseException as exc:  # noqa: BLE001 — wrapper always writes
        cert["verdict"] = "FAIL"
        cert["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return _finish(cert, t0)
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
            hb("server_stopped")


if __name__ == "__main__":
    raise SystemExit(main())
