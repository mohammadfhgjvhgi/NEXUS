"""Workspace registry manager (Final Build Plan §3.1).

Owns the persistent workspace registry: one JSON file under the
``workspaces`` runtime directory (``NexusPaths.workspaces``), written
atomically — temp file + ``os.replace`` + ``fsync``, the same crash
discipline as task persistence (§2.5).

* ``register``      — create + persist (names are unique);
* ``resolve_path``  — longest-root match (the §3.3 resolution primitive);
* ``find``          — by id **or** name;
* ``update``/``remove`` — mutate + persist atomically;
* ``default()``     — the configured default workspace
  (``WorkspacesConfig.default_workspace``, §2.1): the registered
  workspace of that name when present, otherwise a synthetic
  in-memory one — never auto-persisted, the registry stays
  write-explicit.

إدارة مساحات العمل — سجل دائم بمسار ذرّي القراءة والكتابة.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .models import (
    DEFAULT_WORKSPACE_ID,
    Workspace,
    WorkspaceError,
    normalize_path,
)

REGISTRY_SCHEMA = "nexus.workspaces.registry"
REGISTRY_VERSION = 1
REGISTRY_FILENAME = "workspaces.json"

DEFAULT_WORKSPACE_NAME = "main"


class _Unset:
    """Sentinel: "field not provided" (distinct from ``None``)."""


_UNSET = _Unset()

#: Fields ``update()`` accepts (settings are merged separately).
_EDITABLE_FIELDS = ("name", "path", "project", "memory_namespace")


def _atomic_write_json(path: Path, data: Mapping[str, Any]) -> None:
    tmp_path = path.with_name(path.name + ".tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.flush()
        os.fsync(handle.fileno())  # survive power loss before the rename
    os.replace(tmp_path, path)


class WorkspaceManager:
    """Filesystem-backed workspace registry (atomic, single-writer)."""

    def __init__(
        self,
        workspaces_dir: str | Path,
        *,
        default_workspace: str = DEFAULT_WORKSPACE_NAME,
        create: bool = True,
    ) -> None:
        self._dir = Path(workspaces_dir)
        if create:
            self._dir.mkdir(parents=True, exist_ok=True)
        self._default_name = (default_workspace or "").strip() or DEFAULT_WORKSPACE_NAME
        self._workspaces: dict[str, Workspace] = {}
        self._load()

    # ------------------------------------------------------------- internals

    @property
    def registry_path(self) -> Path:
        return self._dir / REGISTRY_FILENAME

    @property
    def default_name(self) -> str:
        return self._default_name

    def _load(self) -> None:
        path = self.registry_path
        if not path.is_file():
            return
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (json.JSONDecodeError, OSError) as exc:
            raise WorkspaceError(f"failed to read {path}: {exc}") from exc
        if not isinstance(data, dict) or data.get("schema") != REGISTRY_SCHEMA:
            raise WorkspaceError(f"{path}: not a {REGISTRY_SCHEMA} file")
        records = data.get("workspaces", [])
        if not isinstance(records, list):
            raise WorkspaceError(f"{path}: 'workspaces' must be a list")
        loaded: dict[str, Workspace] = {}
        for record in records:
            workspace = Workspace.from_dict(record)
            if workspace.id in loaded:
                raise WorkspaceError(f"{path}: duplicate id {workspace.id!r}")
            loaded[workspace.id] = workspace
        self._workspaces = loaded

    def _save(self) -> None:
        data = {
            "schema": REGISTRY_SCHEMA,
            "schema_version": REGISTRY_VERSION,
            "workspaces": [ws.to_dict() for ws in self._ordered()],
        }
        _atomic_write_json(self.registry_path, data)

    def _ordered(self) -> list[Workspace]:
        return sorted(self._workspaces.values(), key=lambda ws: ws.name.lower())

    def _require_unique_name(self, name: str, *, ignore_id: str | None = None) -> None:
        for existing in self._workspaces.values():
            if existing.id == ignore_id:
                continue
            if existing.name.lower() == name.lower():
                raise WorkspaceError(f"workspace name {name!r} already registered")

    def _require(self, workspace_id: str) -> Workspace:
        workspace = self._workspaces.get(workspace_id)
        if workspace is None:
            raise WorkspaceError(f"no workspace {workspace_id!r}")
        return workspace

    # ----------------------------------------------------------------- reads

    def list_workspaces(self) -> list[Workspace]:
        """All registered workspaces, sorted by name."""
        return self._ordered()

    def count(self) -> int:
        return len(self._workspaces)

    def get(self, workspace_id: str) -> Workspace:
        """Fetch by id (raises :class:`WorkspaceError` when unknown)."""
        return self._require(workspace_id)

    def get_by_name(self, name: str) -> Workspace | None:
        wanted = (name or "").strip().lower()
        if not wanted:
            return None
        for workspace in self._workspaces.values():
            if workspace.name.lower() == wanted:
                return workspace
        return None

    def find(self, reference: str) -> Workspace | None:
        """Find by id, then by name (case-insensitive)."""
        text = (reference or "").strip()
        if not text:
            return None
        if text in self._workspaces:
            return self._workspaces[text]
        return self.get_by_name(text)

    def resolve_path(self, path: str) -> Workspace | None:
        """Longest-root match: the most specific workspace containing *path*."""
        target = normalize_path(path)
        if not target:
            return None
        best: Workspace | None = None
        best_root = ""
        for workspace in self._workspaces.values():
            root = normalize_path(workspace.path)
            if not root:
                continue
            if target == root or target.startswith(root + "/"):
                if len(root) > len(best_root):
                    best, best_root = workspace, root
        return best

    def default(self) -> Workspace:
        """The default workspace: registered by name when present, else a
        synthetic in-memory one (reserved id, never persisted)."""
        registered = self.get_by_name(self._default_name)
        if registered is not None:
            return registered
        return Workspace(
            id=DEFAULT_WORKSPACE_ID,
            name=self._default_name,
            path=str(Path.cwd()),
            project=self._default_name,
            memory_namespace=f"nexus.memory.{self._default_name.lower()}",
            git_repository=None,
            settings={},
        )

    # ---------------------------------------------------------------- writes

    def register(
        self,
        *,
        name: str,
        path: str,
        project: str | None = None,
        memory_namespace: str | None = None,
        git_repository: str | None = None,
        settings: Mapping[str, Any] | None = None,
    ) -> Workspace:
        """Create + persist a workspace (unique name enforced)."""
        workspace = Workspace.create(
            name=name,
            path=path,
            project=project,
            memory_namespace=memory_namespace,
            git_repository=git_repository,
            settings=settings,
        )
        return self._adopt(workspace)

    def register_workspace(self, workspace: Workspace) -> Workspace:
        """Adopt an externally-built workspace (id must be free)."""
        if workspace.id in self._workspaces:
            raise WorkspaceError(f"workspace id {workspace.id!r} already registered")
        return self._adopt(workspace)

    def _adopt(self, workspace: Workspace) -> Workspace:
        self._require_unique_name(workspace.name)
        self._workspaces[workspace.id] = workspace
        self._save()
        return workspace

    def update(
        self,
        workspace_id: str,
        *,
        name: str | None = None,
        path: str | None = None,
        project: str | None = None,
        memory_namespace: str | None = None,
        git_repository: str | None | _Unset = _UNSET,
        settings: Mapping[str, Any] | None = None,
    ) -> Workspace:
        """Mutate a workspace and persist atomically (``None`` string
        arguments mean "unchanged"; ``git_repository=None`` clears it)."""
        workspace = self._require(workspace_id)
        if name is not None:
            clean = name.strip()
            if not clean:
                raise WorkspaceError("workspace name cannot be empty")
            self._require_unique_name(clean, ignore_id=workspace.id)
            workspace.name = clean
        if path is not None:
            clean_path = path.strip()
            if not clean_path:
                raise WorkspaceError("workspace path cannot be empty")
            workspace.path = clean_path
        if project is not None:
            workspace.project = project.strip() or workspace.name
        if memory_namespace is not None:
            workspace.memory_namespace = memory_namespace.strip()
        if not isinstance(git_repository, _Unset):
            workspace.git_repository = (
                git_repository.strip() if git_repository else None
            )
        if settings is not None:
            merged = dict(workspace.settings)
            merged.update(dict(settings))
            workspace.settings = merged
        workspace.touch()
        self._save()
        return workspace

    def remove(self, workspace_id: str) -> Workspace:
        """Remove a workspace from the registry (returns the removed one)."""
        workspace = self._require(workspace_id)
        del self._workspaces[workspace_id]
        self._save()
        return workspace

    # -------------------------------------------------------------- lifecycle

    def close(self) -> None:
        """Close the manager. Writes are atomic, so there is nothing to
        flush; provided for Runtime.shutdown symmetry."""
        return None


def registry_envelope() -> dict[str, Any]:
    """Envelope constants of the registry format (documentation aid)."""
    return {
        "schema": REGISTRY_SCHEMA,
        "schema_version": REGISTRY_VERSION,
        "filename": REGISTRY_FILENAME,
    }
