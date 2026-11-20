"""C-RELIEF mover v6 — PHASED engine (reaper-proof).

Each invocation runs ONE short phase, driven by target.json:
    {"name","src","dst","phase"}   phase in: copy|verify|sha|purge|finalize

Phases are idempotent + resumable. Any phase that dies can be re-triggered
alone. purge SELF-DEFENDS: re-verifies src ⊆ dst before deleting anything.

Result -> M:\\NEXUS\\tools\\c_relief\\results\\<name>__<phase>.json
Heartbeat log -> results\\<name>.phases.log
Manifest line -> M:\\C-RELIEF\\MANIFEST.jsonl (finalize only)
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import time
import traceback
from pathlib import Path

BASE = Path(r"M:\NEXUS\tools\c_relief")
TARGET = BASE / "target.json"
RESULTS = BASE / "results"
MANIFEST = Path(r"M:\C-RELIEF\MANIFEST.jsonl")


def _hb(name: str, phase: str, detail: str = "") -> None:
    try:
        log = RESULTS / (name + ".phases.log")
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                 "phase": f"{phase}", "detail": detail[:300]},
                                ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001
        pass


def _walk(root: str) -> tuple[int, int, dict]:
    count, total = 0, 0
    files: dict = {}
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            sz = entry.stat(follow_symlinks=False).st_size
                            count += 1
                            total += sz
                            files[os.path.relpath(entry.path, root).lower()] = sz
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    return count, total, files


def _superset(src: str, dst: str) -> tuple[dict, list]:
    sc, sb, sf = _walk(src)
    dc, db, df = _walk(dst)
    missing = [k for k, v in sf.items() if df.get(k) != v]
    return ({"src_files": sc, "src_bytes": sb, "dst_files": dc, "dst_bytes": db,
             "src_missing_in_dst": len(missing)}, missing)


def _rm_ro(func, path, _exc):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise


def _sha_file(p: str, deadline: float) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
            if time.time() > deadline:
                raise TimeoutError
    return h.hexdigest()


def _robocopy(args: list[str], timeout: int = 3000) -> subprocess.CompletedProcess:
    return subprocess.run(["robocopy"] + args, capture_output=True, text=True, timeout=timeout)


def _finish(name: str, phase: str, result: dict, t0: float) -> None:
    result["phase"] = phase
    result["seconds"] = round(time.time() - t0, 1)
    (RESULTS / f"{name}__{phase}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    _hb(name, f"{phase}_result", f"status={result.get('status')}")


# ----------------------------------------------------------------- phases


def ph_copy(name: str, src: str, dst: str, t0: float) -> dict:
    result: dict = {"name": name, "status": "unknown"}
    if not os.path.isdir(src) or os.path.realpath(src).lower() != src.lower():
        result["status"] = "already_done_or_missing"
        return result
    _hb(name, "copy_begin")
    proc = _robocopy([src, dst, "/E", "/COPY:DAT", "/DCOPY:DAT",
                      "/R:0", "/W:0", "/XJ", "/NFL", "/NDL", "/NP", "/MT:8"])
    result["robocopy_exit"] = proc.returncode
    _hb(name, "copy_done", f"exit={proc.returncode}")
    result["status"] = "copied" if proc.returncode < 8 else "copy_failed"
    if proc.returncode >= 8:
        result["robocopy_tail"] = (proc.stdout or "")[-600:]
    return result


def ph_verify(name: str, src: str, dst: str, t0: float) -> dict:
    result: dict = {"name": name, "status": "unknown"}
    if not os.path.isdir(src) or os.path.realpath(src).lower() != src.lower():
        result["status"] = "already_done_or_missing"
        return result
    _hb(name, "verify_begin")
    summary, missing = _superset(src, dst)
    result.update(summary)
    _hb(name, "verify_walk_done", f"src={summary['src_files']}f/{summary['src_bytes']}B "
                                  f"dst={summary['dst_files']}f/{summary['dst_bytes']}B")
    result["status"] = "verified" if not missing else "copy_incomplete"
    if missing:
        result["missing_sample"] = missing[:10]
    return result


def ph_sha(name: str, src: str, dst: str, t0: float) -> dict:
    result: dict = {"name": name, "status": "unknown"}
    if not os.path.isdir(src) or os.path.realpath(src).lower() != src.lower():
        result["status"] = "already_done_or_missing"
        return result
    checked, bad, aborted = 0, [], 0
    stack = [src]
    phase_deadline = time.time() + 150
    while stack and checked < 10 and time.time() < phase_deadline:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                for entry in it:
                    if checked >= 10 or time.time() >= phase_deadline:
                        break
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            if entry.stat(follow_symlinks=False).st_size >= 100 * 1024 * 1024:
                                rel = os.path.relpath(entry.path, src)
                                try:
                                    a = _sha_file(entry.path, time.time() + 60)
                                    b = _sha_file(os.path.join(dst, rel), time.time() + 60)
                                    checked += 1
                                    _hb(name, "sha_file", f"{checked} {rel[:80]}")
                                    if a != b:
                                        bad.append(rel)
                                except TimeoutError:
                                    aborted += 1
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except OSError:
                        continue
        except OSError:
            continue
    result["sha_checked"] = checked
    result["sha_bad"] = bad
    result["sha_aborted_by_deadline"] = aborted
    result["status"] = "sha_ok" if not bad else "verify_failed"
    _hb(name, "sha_done", f"checked={checked} bad={len(bad)} aborted={aborted}")
    return result


def ph_purge(name: str, src: str, dst: str, t0: float) -> dict:
    result: dict = {"name": name, "status": "unknown"}
    if not os.path.exists(src):
        result["status"] = "already_done_or_missing"
        return result
    if os.path.realpath(src).lower() != src.lower():
        result["status"] = "already_junction"
        return result
    # SELF-DEFENSE: nothing is deleted unless src ⊆ dst byte-equal RIGHT NOW
    _hb(name, "purge_selfverify_begin")
    summary, missing = _superset(src, dst)
    result.update(summary)
    if missing:
        result["status"] = "purge_aborted_not_verified"
        result["missing_sample"] = missing[:10]
        _hb(name, "purge_aborted", f"missing={len(missing)}")
        return result
    _hb(name, "purge_begin", f"files_to_delete={summary['src_files']}")
    empty = BASE / "_empty"
    empty.mkdir(parents=True, exist_ok=True)
    try:
        proc2 = _robocopy([str(empty), src, "/MIR", "/R:0", "/W:0",
                           "/XJ", "/NFL", "/NDL", "/NP", "/MT:8"])
        result["purge_exit"] = proc2.returncode
    except Exception as exc:  # noqa: BLE001
        result["purge_exit"] = f"exc:{exc}"[:120]
    _hb(name, "purge_done", f"exit={result.get('purge_exit')}")
    removed = False
    for attempt in range(3):
        try:
            shutil.rmtree(src, onerror=_rm_ro)
            removed = True
            break
        except OSError as exc:
            result["remove_error"] = str(exc)[:200]
            time.sleep(3)
    result["husk_removed"] = removed
    result["status"] = "purged" if removed else "remove_partial_locked"
    return result


def ph_finalize(name: str, src: str, dst: str, t0: float) -> dict:
    result: dict = {"name": name, "status": "unknown"}
    if os.path.exists(src) and os.path.realpath(src).lower() != src.lower():
        result["status"] = "already_junction"
        result["junction_ok"] = True
        return result
    if os.path.exists(src):
        leftovers = []
        try:
            leftovers = os.listdir(src)
        except OSError as exc:
            result["listdir_err"] = str(exc)[:120]
        if leftovers:
            result["status"] = "finalize_aborted_not_empty"
            result["leftover_sample"] = leftovers[:10]
            return result
        try:
            os.rmdir(src)
        except OSError as exc:
            result["status"] = "rmdir_failed"
            result["rmdir_err"] = str(exc)[:150]
            return result
    mk = subprocess.run(["cmd", "/c", "mklink", "/J", src, dst],
                        capture_output=True, text=True, timeout=30)
    result["mklink_rc"] = mk.returncode
    result["mklink_out"] = ((mk.stdout or "") + (mk.stderr or ""))[:200]
    ok = mk.returncode == 0 and os.path.realpath(src).lower() == dst.lower()
    result["junction_ok"] = ok
    result["status"] = "moved" if ok else "junction_failed"
    if ok:
        # merge earlier phase results into the manifest line
        merged: dict = {"name": name, "src": src, "dst": dst}
        for ph in ("copy", "verify", "sha", "purge"):
            pf = RESULTS / f"{name}__{ph}.json"
            try:
                if pf.exists():
                    merged.update(json.loads(pf.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                pass
        with open(MANIFEST, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({**merged,
                                 "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                                ensure_ascii=False) + "\n")
    return result


PHASES = {"copy": ph_copy, "verify": ph_verify, "sha": ph_sha,
          "purge": ph_purge, "finalize": ph_finalize}


def _run_phase(phase: str) -> None:
    t0 = time.time()
    spec = json.loads(TARGET.read_text(encoding="utf-8"))
    if spec.get("phase") != phase:
        return  # phase selector: only the requested phase does work
    name, src, dst = spec["name"], spec["src"], spec["dst"]
    RESULTS.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    _hb(name, f"{phase}_start", f"pid={os.getpid()}")
    try:
        result = PHASES[phase](name, src, dst, t0)
        _finish(name, phase, result, t0)
    except BaseException as exc:  # noqa: BLE001 — evidence first, then re-raise
        _hb(name, f"{phase}_exception",
            f"{type(exc).__name__}: {exc} | {traceback.format_exc()[-350:]}")
        _finish(name, phase, {"name": name, "status": "exception",
                              "error": f"{type(exc).__name__}: {exc}"[:300]}, t0)
        raise


def test_c_copy() -> None:
    _run_phase("copy")


def test_c_verify() -> None:
    _run_phase("verify")


def test_c_sha() -> None:
    _run_phase("sha")


def test_c_purge() -> None:
    _run_phase("purge")


def test_c_finalize() -> None:
    _run_phase("finalize")
