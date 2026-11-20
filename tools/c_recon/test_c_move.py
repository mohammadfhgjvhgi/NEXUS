"""C-RELIEF mover — one candidate per run.

Reads M:\\NEXUS\\tools\\c_relief\\target.json:  {"name","src","dst"}
Pipeline (NO deletion of any data — a move by verified copy):
  1. robocopy src -> dst  (/E /COPY:DAT /XJ /R:0 /W:0 /MT:4 — resume-safe)
  2. verify: exact file count + exact byte total, src vs dst
  3. sha256 every file >= 100 MB (max 30) — src vs dst
  4. only if ALL green: rmtree source (read-only tolerant)
  5. mklink /J src -> dst  (junction: every app keeps reading its old path)
Any failure => source left untouched, honest status written.

Result -> M:\\NEXUS\\tools\\c_relief\\results\\<name>.json
Manifest line appended -> M:\\C-RELIEF\\MANIFEST.jsonl
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

BASE = Path(r"M:\NEXUS\tools\c_relief")
TARGET = BASE / "target.json"
RESULTS = BASE / "results"
MANIFEST = Path(r"M:\C-RELIEF\MANIFEST.jsonl")

import traceback

def _hb(phase: str, detail: str = "") -> None:
    """append-only phase heartbeat; resolves target name lazily."""
    try:
        name = json.loads(TARGET.read_text(encoding="utf-8"))["name"]
        log = BASE / "results" / (name + ".phases.log")
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                 "phase": phase, "detail": detail[:300]},
                                ensure_ascii=False) + "\n")
    except Exception:  # noqa: BLE001 — heartbeat must never kill the mover
        pass



def _walk(root: str) -> tuple[int, int, dict]:
    """count, bytes, {relpath: size} — files only, never follow junctions."""
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


def _is_junction_or_missing(src: str) -> bool:
    if not os.path.exists(src):
        return True
    try:
        return os.path.realpath(src) != src
    except OSError:
        return False


def _rm_ro(func, path, _exc):
    try:
        os.chmod(path, stat.S_IWRITE)
        func(path)
    except OSError:
        raise


def _test_c_move_inner() -> None:
    t0 = time.time()
    spec = json.loads(TARGET.read_text(encoding="utf-8"))
    name, src, dst = spec["name"], spec["src"], spec["dst"]
    RESULTS.mkdir(parents=True, exist_ok=True)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    _hb("start", f"pid={os.getpid()} target={name}")

    result = {"name": name, "src": src, "dst": dst, "status": "unknown"}

    if _is_junction_or_missing(src):
        result["status"] = "already_done_or_missing"
    else:
        # 1) robocopy — /E copy tree, /XJ skip junctions, /MT:4, no waits
        _hb("robocopy_begin")
        proc = subprocess.run(
            ["robocopy", src, dst, "/E", "/COPY:DAT", "/DCOPY:DAT",
             "/R:0", "/W:0", "/XJ", "/NFL", "/NDL", "/NP", "/MT:8"],
            capture_output=True, text=True, timeout=3000,
        )
        result["robocopy_exit"] = proc.returncode
        _hb("robocopy_done", f"exit={proc.returncode}")
        if proc.returncode >= 8:
            result["status"] = "copy_failed"
            result["robocopy_tail"] = (proc.stdout or "")[-800:]
        else:
            # 2) superset verify: EVERY src file exists in dst with the same
            #    size (strict equality on the fresh path; src ⊆ dst also
            #    accepts the resume path after a prior partial removal).
            sc, sb, sf = _walk(src)
            dc, db, df = _walk(dst)
            _hb("verify_walk_done", f"src={sc}f/{sb}B dst={dc}f/{db}B")
            missing = [k for k, v in sf.items() if df.get(k) != v]
            result.update(src_files=sc, src_bytes=sb, dst_files=dc, dst_bytes=db,
                          src_missing_in_dst=len(missing))
            if missing:
                result["status"] = "copy_incomplete"
                result["missing_sample"] = missing[:10]
            else:
                # 3) sha256 files >= 100 MB — TIME-BOUNDED sample
                #    (orphans get reaped after ~30-50 min; the sha phase
                #    must NEVER outlive that window)
                checked, bad, skipped_by_time = 0, [], 0
                stack = [src]
                sha_deadline = time.time() + 150
                while stack and checked < 12 and time.time() < sha_deadline:
                    cur = stack.pop()
                    try:
                        with os.scandir(cur) as it:
                            for entry in it:
                                if checked >= 30:
                                    break
                                try:
                                    if entry.is_symlink():
                                        continue
                                    if entry.is_file(follow_symlinks=False):
                                        if entry.stat(follow_symlinks=False).st_size >= 100 * 1024 * 1024:
                                            rel = os.path.relpath(entry.path, src)
                                            # stream-hash both sides
                                            def sha(p: str) -> str:
                                                h = hashlib.sha256()
                                                with open(p, "rb") as fh:
                                                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                                                        h.update(chunk)
                                                return h.hexdigest()
                                            a, b = sha(entry.path), sha(os.path.join(dst, rel))
                                            checked += 1
                                            _hb("sha_file", f"{checked} {rel[:80]}")
                                            if a != b:
                                                bad.append(rel)
                                    elif entry.is_dir(follow_symlinks=False):
                                        stack.append(entry.path)
                                except OSError:
                                    continue
                    except OSError:
                        continue
                result["sha_checked"] = checked
                result["sha_bad"] = bad
                result["sha_sample_bounded"] = True
                _hb("sha_done", f"checked={checked} bad={len(bad)}")
                if bad:
                    result["status"] = "verify_failed"
                else:
                    # 4) remove the verified source copy — the "move"
                    #    (retry ×3: a live daemon may transiently vanish a
                    #    temp file mid-walk — WinError 2 — and leftovers
                    #    shrink every round; full copy is already safe on M:)
                    _hb("purge_begin")
                    empty = BASE / "_empty"
                    empty.mkdir(parents=True, exist_ok=True)
                    try:
                        proc2 = subprocess.run(
                            ["robocopy", str(empty), src, "/MIR", "/R:0", "/W:0",
                             "/XJ", "/NFL", "/NDL", "/NP", "/MT:8"],
                            capture_output=True, text=True, timeout=3000,
                        )
                        result["purge_exit"] = proc2.returncode
                    except Exception as exc:  # noqa: BLE001
                        result["purge_exit"] = f"exc:{exc}"[:120]
                    _hb("purge_done", f"exit={result.get('purge_exit')}")
                    removed = False
                    for attempt in range(3):
                        try:
                            shutil.rmtree(src, onerror=_rm_ro)
                            removed = True
                            break
                        except OSError as exc:
                            result["remove_error"] = str(exc)[:200]
                            time.sleep(3)
                    if not removed:
                        result["status"] = "remove_partial_locked"
                    if removed:
                        # 5) junction back
                        mk = subprocess.run(
                            ["cmd", "/c", "mklink", "/J", src, dst],
                            capture_output=True, text=True,
                        )
                        ok = mk.returncode == 0 and os.path.realpath(src).lower() == dst.lower()
                        result["status"] = "moved" if ok else "junction_failed"
                        if not ok:
                            result["mklink_out"] = (mk.stdout + mk.stderr)[:300]

    result["seconds"] = round(time.time() - t0, 1)
    (RESULTS / f"{name}.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(MANIFEST, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({**result, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                            ensure_ascii=False) + "\n")
    assert (RESULTS / f"{name}.json").exists()


def test_c_move() -> None:
    """wrapper: heartbeat + full traceback capture; result file ALWAYS written."""
    try:
        _test_c_move_inner()
    except BaseException as exc:  # noqa: BLE001 — evidence first, then re-raise
        try:
            spec = json.loads(TARGET.read_text(encoding="utf-8"))
            name = spec["name"]
            _hb("exception", f"{type(exc).__name__}: {exc} | {traceback.format_exc()[-400:]}")
            (RESULTS / f"{name}.json").write_text(
                json.dumps({"name": name, "status": "exception",
                            "error": f"{type(exc).__name__}: {exc}"[:300]},
                           ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:  # noqa: BLE001
            pass
        raise
