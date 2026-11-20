# -*- coding: utf-8 -*-
"""NEXUS Plugin System — PHASE 30 — discovery & loading.

Spec §81: plugins are discovered and registered WITHOUT changing Core.
The manager scans plugins\\plugins\\<name>\\plugin.json, validates the
manifest, imports the entry module under a UNIQUE per-plugin module name
(no cross-plugin module collisions), and calls register(ctx).
"""
from __future__ import annotations

import importlib.util
import json
import sys
import traceback
from pathlib import Path

from plugin_common import (PluginContext, atomic_json, sha256_file,
                           validate_manifest)

LOADED = "loaded"
ERROR = "error"


def discover(plugins_root: Path) -> list:
    """[(dir, manifest_dict, manifest_sha256, errors)] for every subdir."""
    found = []
    if not plugins_root.is_dir():
        return found
    for d in sorted(plugins_root.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        mf = d / "plugin.json"
        if not mf.is_file():
            found.append((d, None, "", ["no_plugin_json"]))
            continue
        try:
            manifest = json.loads(mf.read_text(encoding="utf-8"))
        except BaseException as exc:  # noqa: BLE001
            found.append((d, None, "", [f"bad_json: {exc}"[:120]]))
            continue
        ok, errors, sha = validate_manifest(manifest, d)
        found.append((d, manifest if ok else manifest, sha,
                      errors if not ok else []))
    return found


def load_plugin(root: Path, plugin_dir: Path, manifest: dict,
                fs_root: Path) -> dict:
    """Import + register one plugin. Honest record either way."""
    name = manifest["name"]
    record = {
        "name": name, "type": manifest.get("type"),
        "version": manifest.get("version"),
        "description": manifest.get("description", ""),
        "permissions": manifest.get("permissions", []),
        "manifest_sha256": sha256_file(plugin_dir / "plugin.json"),
        "files_sha256": {}, "registered": {}, "status": ERROR,
        "error": None, "module": None,
    }
    for f in sorted(plugin_dir.glob("*.py")) + sorted(
            plugin_dir.glob("*.json")):
        record["files_sha256"][f.name] = sha256_file(f)
    entry = plugin_dir / str(manifest["entry"])
    mod_name = f"nx_plugin_{name}"
    try:
        spec = importlib.util.spec_from_file_location(mod_name, entry)
        if spec is None or spec.loader is None:
            raise ImportError("spec_unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = module
        spec.loader.exec_module(module)
        if not hasattr(module, "register") or not callable(module.register):
            raise ValueError("register_callable_missing")
        registry: dict = {}
        ctx = PluginContext(name, manifest.get("permissions", []), fs_root,
                            registry)
        module.register(ctx)
        record["status"] = LOADED
        record["registered"] = ctx.registered
        record["module"] = mod_name
        record["registry"] = registry
    except BaseException as exc:  # noqa: BLE001 — honest error record
        record["error"] = f"{type(exc).__name__}: {exc}"[:300]
        record["traceback_tail"] = traceback.format_exc()[-800:]
    return record


def load_all(plugins_root: Path, fs_root: Path) -> dict:
    """Returns {name: record}. Invalid manifests get error records too."""
    out = {}
    for d, manifest, _sha, errors in discover(plugins_root):
        if errors:
            out[d.name] = {
                "name": d.name, "status": ERROR, "error": ";".join(errors),
                "manifest_sha256": "", "files_sha256": {}, "registered": {},
                "type": (manifest or {}).get("type"),
                "version": (manifest or {}).get("version"),
            }
            continue
        rec = load_plugin(plugins_root, d, manifest, fs_root)
        out[rec["name"]] = rec
    return out


def write_registry(path: Path, records: dict) -> dict:
    plugins = []
    counts = {t: 0 for t in ("agent", "tool", "skill", "model", "mcp",
                             "integration", "ui")}
    for name in sorted(records):
        r = records[name]
        plugins.append(r)
        if r.get("status") == LOADED and r.get("type") in counts:
            counts[r["type"]] += 1
    reg = {"generated_utc": __import__("plugin_common").utcnow(),
           "counts_by_type": counts,
           "loaded_total": sum(counts.values()),
           "plugins": plugins}
    atomic_json(path, reg)
    return reg
