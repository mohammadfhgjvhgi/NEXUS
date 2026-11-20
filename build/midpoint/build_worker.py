"""Detached MIDPOINT build worker — builds the first real NEXUS.exe on this machine.

Spawned detached (DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP) by
test_build_spawn.py so it survives MCP service restarts and tunnel
deaths (the Task 30 law: results live on disk, workers live alone).

Pipeline (all phases heartbeat to results\\build_exe.phases.log):
    1. ensure PyInstaller (pip show -> pip install if missing)
    2. PyInstaller --noconfirm --clean NEXUS.exe.spec   (onfile, console)
    3. sha256 + size of dist\\NEXUS.exe                  (GATE #2 evidence)
    4. run dist\\NEXUS.exe --check                       (GATE #3 evidence;
       the exe rewrites proofs\\midpoint_boot.json itself)

Never fakes anything: any failure writes verdict=FAIL with the real
tail into proofs\\midpoint_build.json.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent           # M:\\NEXUS\\build\\midpoint
NEXUS_ROOT = HERE.parent.parent                  # M:\\NEXUS
PROOFS = NEXUS_ROOT / "proofs"
RESULTS = HERE / "results"
PHASES = RESULTS / "build_exe.phases.log"
STDOUT_LOG = RESULTS / "build_stdout.log"
CERT = PROOFS / "midpoint_build.json"


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def hb(phase: str, detail: str = "") -> None:
    """Heartbeat — append one phase line, never raise."""
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        with open(PHASES, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"utc": _utc(), "phase": phase,
                                 "detail": str(detail)[:220]},
                                ensure_ascii=False) + "\n")
    except OSError:
        pass


def _log_stdout(cmd: list, rc: int, out: str, err: str) -> None:
    try:
        RESULTS.mkdir(parents=True, exist_ok=True)
        with open(STDOUT_LOG, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(f"\n===== {_utc()} $ {' '.join(map(str, cmd))}\n")
            fh.write(f"rc={rc}\n{(out or '')[-4000:]}\n{(err or '')[-2000:]}\n")
    except OSError:
        pass


def _run(cmd: list, cwd: Path | None = None, timeout: int = 1800) -> subprocess.CompletedProcess:
    hb("subprocess_start", " ".join(str(c) for c in cmd)[:200])
    p = subprocess.run(cmd, cwd=str(cwd or HERE), capture_output=True,
                       text=True, timeout=timeout)
    _log_stdout(cmd, p.returncode, p.stdout, p.stderr)
    hb("subprocess_done", f"rc={p.returncode}")
    return p


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _finish(cert: dict, t0: float) -> int:
    cert["build_seconds"] = round(time.time() - t0, 2)
    cert["utc_end"] = _utc()
    try:
        PROOFS.mkdir(parents=True, exist_ok=True)
        CERT.write_text(json.dumps(cert, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    except OSError as exc:
        cert["cert_write_error"] = str(exc)[:200]
        try:
            RESULTS.mkdir(parents=True, exist_ok=True)
            (RESULTS / "midpoint_build_fallback.json").write_text(
                json.dumps(cert, ensure_ascii=False, indent=1),
                encoding="utf-8")
        except OSError:
            pass
    hb("done", f"verdict={cert.get('verdict')}")
    try:
        print(json.dumps(cert, ensure_ascii=False)[:400])
    except OSError:
        pass
    return 0


def main() -> int:
    t0 = time.time()
    cert: dict = {
        "product": "NEXUS.exe build (MIDPOINT #2+#3)",
        "utc": _utc(), "pid": os.getpid(),
        "python": sys.version.split()[0],
    }
    try:
        py = sys.executable
        hb("start", f"worker pid={os.getpid()} py={py}")

        # 1) ensure PyInstaller — honest fail if pip cannot deliver it
        chk = _run([py, "-m", "pip", "show", "pyinstaller"], timeout=180)
        if chk.returncode == 0:
            cert["pyinstaller"] = "present"
            hb("pyinstaller_present")
        else:
            hb("pip_install_begin")
            inst = _run([py, "-m", "pip", "install", "--upgrade", "pyinstaller"],
                        timeout=900)
            if inst.returncode != 0:
                cert["verdict"] = "FAIL"
                cert["error"] = "pip install pyinstaller failed (honest)"
                cert["tail"] = ((inst.stderr or "") + (inst.stdout or ""))[-900:]
                return _finish(cert, t0)
            cert["pyinstaller"] = "installed_now"

        # 2) build the exe
        hb("build_begin", "PyInstaller --noconfirm --clean NEXUS.exe.spec")
        b = _run([py, "-m", "PyInstaller", "--noconfirm", "--clean",
                  "NEXUS.exe.spec"], cwd=HERE, timeout=2400)
        cert["build_rc"] = b.returncode
        exe = HERE / "dist" / "NEXUS.exe"
        if b.returncode != 0 or not exe.exists():
            cert["verdict"] = "FAIL"
            cert["error"] = "pyinstaller failed or exe missing (honest)"
            cert["tail"] = ((b.stderr or "") + (b.stdout or ""))[-900:]
            return _finish(cert, t0)
        cert["exe"] = str(exe)
        cert["exe_size_bytes"] = exe.stat().st_size
        cert["sha256"] = sha256_of(exe)
        hb("build_done", f"size={cert['exe_size_bytes']} sha256={cert['sha256'][:16]}...")

        # 3) first real run of the exe — its own --check (GATE #3)
        hb("exe_check_begin", "dist\\NEXUS.exe --check")
        r = _run([str(exe), "--check"], cwd=HERE, timeout=300)
        cert["check_rc"] = r.returncode
        cert["check_output"] = ((r.stdout or "") + (r.stderr or ""))[-1400:]
        cert["check_verdict"] = "PASS" if r.returncode == 0 else "FAIL"
        cert["verdict"] = "PASS" if r.returncode == 0 else "PARTIAL"
        hb("exe_check_done", f"rc={r.returncode} verdict={cert['check_verdict']}")
        return _finish(cert, t0)
    except BaseException as exc:  # noqa: BLE001 — the wrapper always writes
        cert["verdict"] = "FAIL"
        cert["error"] = f"{type(exc).__name__}: {exc}"[:300]
        return _finish(cert, t0)


if __name__ == "__main__":
    raise SystemExit(main())
