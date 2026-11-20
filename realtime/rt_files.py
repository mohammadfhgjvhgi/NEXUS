# -*- coding: utf-8 -*-
"""NEXUS Realtime Remote — PHASE 29 — FILES channel (port 9414).

Chunked push/pull with sha256 on both ends and a hard path jail (default
root M:\\NEXUS — anything resolving outside is rejected 403; that rejection
is a tested verdict, not a promise). Separated module/port/thread;
startable standalone: `python rt_files.py`.

Routes (all Bearer-token protected):
  POST /files/put   {path, base64, append?} -> {size, sha256}
  GET  /files/get   ?path=&offset=&max_bytes=  -> slice + sha256_file/slice
  GET  /files/stat  ?path= -> size/sha256/mtime
  GET  /files/list  ?path= -> shallow dir listing
"""
from __future__ import annotations

import base64
import binascii
import os
import time
from pathlib import Path

from rt_common import (PHASE, VERSION, ChannelContext, serve_forever_standalone,
                       sha256_bytes, sha256_file)

_t0 = time.time()


def _jail(ctx: ChannelContext, raw: str):
    """Resolve a user path under files_root; None if it escapes the jail."""
    root = Path(ctx.cfg.get("files_root") or r"M:\NEXUS")
    if not raw:
        return None
    p = Path(str(raw))
    if not p.is_absolute():
        p = root / p
    try:
        p = Path(os.path.normpath(str(p)))
    except BaseException:
        return None
    root_s = os.path.normpath(str(root)).lower().rstrip("\\").rstrip("/")
    p_s = str(p).lower().rstrip("\\").rstrip("/")
    # Windows sep "\\", POSIX sep "/" — accept both for portability
    if (p_s == root_s or p_s.startswith(root_s + "\\")
            or p_s.startswith(root_s + "/")):
        return p
    return None


def _put(ctx: ChannelContext, body, qs, handler):
    body = body or {}
    p = _jail(ctx, str(body.get("path") or ""))
    if p is None:
        ctx.audit.write("files", "jail_reject_put",
                        {"path": str(body.get("path"))[:160]})
        return 403, {"ok": False, "error": "path_outside_jail",
                     "root": ctx.cfg.get("files_root")}
    b64 = str(body.get("base64") or "")
    if not b64:
        return 400, {"ok": False, "error": "base64_required"}
    try:
        data = base64.b64decode(b64, validate=True)
    except (binascii.Error, ValueError) as exc:
        return 400, {"ok": False, "error": f"bad_base64: {exc}"[:160]}
    append = bool(body.get("append"))
    p.parent.mkdir(parents=True, exist_ok=True)
    mode = "ab" if append else "wb"
    with open(p, mode) as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    detail = {"path": str(p), "written": len(data), "append": append,
              "size": p.stat().st_size}
    ctx.audit.write("files", "put", detail)
    ctx.publish("files.put", detail)
    return 200, {"ok": True, "path": str(p), "written": len(data),
                 "append": append, "size": p.stat().st_size,
                 "sha256_written": sha256_bytes(data),
                 "sha256_file": sha256_file(p)}


def _get(ctx: ChannelContext, body, qs, handler):
    p = _jail(ctx, str(qs.get("path") or ""))
    if p is None:
        ctx.audit.write("files", "jail_reject_get",
                        {"path": str(qs.get("path"))[:160]})
        return 403, {"ok": False, "error": "path_outside_jail",
                     "root": ctx.cfg.get("files_root")}
    if not p.is_file():
        return 404, {"ok": False, "error": "not_a_file", "path": str(p)}
    size = p.stat().st_size
    try:
        offset = max(0, int(str(qs.get("offset", "0")) or 0))
    except (TypeError, ValueError):
        offset = 0
    cap = int(ctx.cfg.get("files_max_chunk", 2097152))
    try:
        max_bytes = int(str(qs.get("max_bytes", str(cap)) or cap))
    except (TypeError, ValueError):
        max_bytes = cap
    max_bytes = max(1, min(max_bytes, cap))
    if offset >= size and size > 0:
        return 400, {"ok": False, "error": "offset_past_eof",
                     "size": size, "offset": offset}
    with open(p, "rb") as fh:
        fh.seek(offset)
        data = fh.read(max_bytes)
    ctx.audit.write("files", "get", {"path": str(p), "offset": offset,
                                     "returned": len(data), "size": size})
    return 200, {"ok": True, "path": str(p), "size": size,
                 "offset": offset, "returned": len(data),
                 "sha256_file": sha256_file(p),
                 "sha256_slice": sha256_bytes(data),
                 "base64": base64.b64encode(data).decode("ascii")}


def _stat(ctx: ChannelContext, body, qs, handler):
    p = _jail(ctx, str(qs.get("path") or ""))
    if p is None:
        return 403, {"ok": False, "error": "path_outside_jail",
                     "root": ctx.cfg.get("files_root")}
    if not p.exists():
        return 404, {"ok": False, "error": "not_found", "path": str(p)}
    if p.is_dir():
        return 200, {"ok": True, "path": str(p), "is_dir": True}
    mt = p.stat().st_mtime
    return 200, {"ok": True, "path": str(p), "is_dir": False,
                 "size": p.stat().st_size, "sha256": sha256_file(p),
                 "mtime_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                            time.gmtime(mt))}


def _list(ctx: ChannelContext, body, qs, handler):
    p = _jail(ctx, str(qs.get("path") or ""))
    if p is None:
        return 403, {"ok": False, "error": "path_outside_jail",
                     "root": ctx.cfg.get("files_root")}
    if not p.is_dir():
        return 404, {"ok": False, "error": "not_a_dir", "path": str(p)}
    items = []
    try:
        with os.scandir(p) as it:
            for entry in it:
                try:
                    items.append({"name": entry.name, "dir": entry.is_dir(),
                                  "size": (entry.stat().st_size
                                           if entry.is_file() else None)})
                except BaseException:
                    items.append({"name": entry.name, "dir": None,
                                  "size": None})
                if len(items) >= 200:
                    break
    except BaseException as exc:  # noqa: BLE001
        return 500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:160]}
    return 200, {"ok": True, "path": str(p), "count": len(items),
                 "items": items}


def routes() -> dict:
    return {
        ("POST", "/files/put"): _put,
        ("GET", "/files/get"): _get,
        ("GET", "/files/stat"): _stat,
        ("GET", "/files/list"): _list,
    }


if __name__ == "__main__":
    serve_forever_standalone("files", routes)
