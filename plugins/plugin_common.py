# -*- coding: utf-8 -*-
"""NEXUS Plugin System — PHASE 30 — contracts & context (stdlib only).

Spec alignment (NEXUS Master Spec v1.0):
  §81  Plugin System: Agents/Tools/Skills/Models/MCP servers/Integrations/
       UI extensions — discovered and registered WITHOUT touching Core.
  §240 Developer API: registerAgent/registerTool/registerSkill/
       registerModel/subscribeEvent (integration) ... — this module IS
       that API surface for plugins.
  §241 Plugin Isolation: a plugin gets ONLY its declared permissions —
       the context enforces a filesystem jail (plugins\\selftest) and
       records every declared permission into the registry.
  §36/§76/§82: agent/tool/skill manifest fields validated on register.

Plugin layout on disk (M:\\NEXUS\\plugins\\plugins\\<name>\\):
  plugin.json   manifest {name,type,version,entry,description,permissions}
  <entry>.py    module exposing register(ctx) -> None
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from pathlib import Path

PHASE = 30
VERSION = "0.30.0"

TYPES = ("agent", "tool", "skill", "model", "mcp", "integration", "ui")
CORE_TYPES = ("agent", "tool", "skill", "mcp", "ui")     # must PASS
DEGRADABLE_TYPES = ("model", "integration")              # env-dependent
SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{2,31}$")


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


def validate_manifest(m, plugin_dir: Path):
    """Spec-shaped manifest validation. Returns (ok, errors[], manifest_sha)."""
    errors = []
    if not isinstance(m, dict):
        return False, ["manifest_not_object"], ""
    for k in ("name", "type", "version", "entry"):
        if not str(m.get(k) or "").strip():
            errors.append(f"missing_{k}")
    if errors:
        return False, errors, ""
    if not SLUG.match(str(m["name"])):
        errors.append("bad_name_slug")
    if m["type"] not in TYPES:
        errors.append("bad_type:" + str(m["type"]))
    entry = Path(str(m["entry"]))
    if entry.is_absolute() or ".." in entry.parts:
        errors.append("entry_escape")
    else:
        p = plugin_dir / entry
        if not p.is_file():
            errors.append("entry_missing")
    raw = json.dumps(m, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return (not errors), errors, sha256_bytes(raw)


class PluginContext:
    """The §240 Developer API — one instance per plugin, jailed per §241."""

    def __init__(self, plugin_name: str, permissions: list, fs_root: Path,
                 registry: dict) -> None:
        self.plugin_name = plugin_name
        self.permissions = list(permissions or [])
        self.fs_root = Path(fs_root)          # §241 isolation jail
        self._reg = registry
        self.registered: dict = {}

    # -- filesystem jail (declared "filesystem" permission required) -----
    def require_fs(self):
        if "filesystem" not in self.permissions:
            raise PermissionError(
                f"plugin '{self.plugin_name}' lacks 'filesystem' permission")
        self.fs_root.mkdir(parents=True, exist_ok=True)
        return self.fs_root

    def jailed_path(self, rel: str) -> Path:
        root = self.require_fs()
        p = Path(rel)
        if p.is_absolute():
            raise PermissionError("absolute_path_denied")
        p = Path(os.path.normpath(root / p))
        if not str(p).lower().startswith(str(root).lower() + os.sep):
            raise PermissionError("path_escape_denied")
        return p

    # -- §240 registration surface ---------------------------------------
    def register_agent(self, spec: dict) -> None:
        for k in ("id", "role", "tools", "input_schema", "output_schema",
                  "verification_rules"):
            if k not in spec:                      # §36 manifest fields
                raise ValueError(f"agent_spec_missing_{k}")
        if "run" not in spec or not callable(spec["run"]):
            raise ValueError("agent_run_callable_required")
        self._reg.setdefault("agents", {})[spec["id"]] = spec
        self.registered["agent"] = spec["id"]

    def register_tool(self, tool: dict) -> None:
        for k in ("name", "description", "input_schema", "version"):
            if k not in tool:                      # §76 tool fields
                raise ValueError(f"tool_missing_{k}")
        if not callable(tool.get("fn")):
            raise ValueError("tool_fn_callable_required")
        self._reg.setdefault("tools", {})[tool["name"]] = tool
        self.registered["tool"] = tool["name"]

    def register_skill(self, skill: dict) -> None:
        for k in ("id", "description", "inputs", "version"):
            if k not in skill:                     # §82 skill fields
                raise ValueError(f"skill_missing_{k}")
        if not callable(skill.get("render")):
            raise ValueError("skill_render_callable_required")
        self._reg.setdefault("skills", {})[skill["id"]] = skill
        self.registered["skill"] = skill["id"]

    def register_model(self, provider: dict) -> None:
        for k in ("id", "kind", "endpoint"):
            if k not in provider:
                raise ValueError(f"model_missing_{k}")
        self._reg.setdefault("models", {})[provider["id"]] = provider
        self.registered["model"] = provider["id"]

    def register_mcp_server(self, server: dict) -> None:
        for k in ("id", "transport", "command"):
            if k not in server:                    # §79 stdio/HTTP transports
                raise ValueError(f"mcp_missing_{k}")
        self._reg.setdefault("mcp_servers", {})[server["id"]] = server
        self.registered["mcp"] = server["id"]

    def register_integration(self, integ: dict) -> None:
        for k in ("id", "target"):
            if k not in integ:
                raise ValueError(f"integration_missing_{k}")
        if not callable(integ.get("relay")):
            raise ValueError("integration_relay_callable_required")
        self._reg.setdefault("integrations", {})[integ["id"]] = integ
        self.registered["integration"] = integ["id"]

    def register_ui_card(self, card: dict) -> None:
        for k in ("id", "slot"):
            if k not in card:
                raise ValueError(f"ui_card_missing_{k}")
        if not callable(card.get("render")):
            raise ValueError("ui_render_callable_required")
        self._reg.setdefault("ui_cards", {})[card["id"]] = card
        self.registered["ui"] = card["id"]


def empty_registry() -> dict:
    return {"plugins": {}, "order": []}
