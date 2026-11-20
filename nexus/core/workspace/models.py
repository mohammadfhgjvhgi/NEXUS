"""Workspace entities (Final Build Plan §3.1 / Spec §20, §22).

One workspace = one independent working context. The workspace anchors
the Phase 2 principle — *Full Control within Task Scope*: a task's
scope resolves to a workspace, and the policy engine evaluates every
action against that workspace's boundaries.

Seven fields, verbatim from Plan §3.1:

    id · name · path · project · memory_namespace · git_repository · settings

Each workspace owns an isolated memory namespace (Spec §22: GLOBAL →
USER → PROJECT → WORKSPACE → TASK → SESSION → AGENT — the WORKSPACE
level). Workspaces never mix history (Spec §21); cross-workspace
access is a scoped, audited request — never a merge.

The path helpers (``normalize_path`` / ``path_within`` /
``paths_equivalent``) live here because the workspace owns the
filesystem-root concept the Scope Engine (§3.2) matches against.

كيان مساحة العمل — الجذر الذي تُحلّ إليه حدود المهمة.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

WORKSPACE_ID_PREFIX = "wsp_"

#: Reserved id of the synthetic default workspace (never persistable).
DEFAULT_WORKSPACE_ID = "wsp_default0000"

_WS_ID_PATTERN = re.compile(r"^wsp_[0-9a-f]{12}$")

#: Default memory namespace pattern: ``nexus.memory.<name>``.
DEFAULT_MEMORY_NAMESPACE = "nexus.memory.{name}"


def new_workspace_id() -> str:
    """New workspace identity: ``wsp_`` + 12 hex chars."""
    return f"{WORKSPACE_ID_PREFIX}{uuid.uuid4().hex[:12]}"


def utc_now() -> datetime:
    return datetime.now(UTC)


class WorkspaceError(Exception):
    """Workspace registry misuse (duplicate name, unknown id, bad record)."""


def normalize_path(path: str) -> str:
    """Canonical comparable form of a filesystem path.

    Separators become ``/`` (Windows ``\\`` accepted), repeated
    separators collapse, trailing separators drop, and comparison is
    case-insensitive — pragmatic for Windows roots, harmless for
    POSIX roots declared by the user.
    """
    text = (path or "").strip()
    if not text:
        return ""
    text = text.replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    if len(text) > 1 and text.endswith("/"):
        text = text.rstrip("/") or "/"
    return text.lower()


def path_within(child: str, root: str) -> bool:
    """True when *child* equals *root* or lives underneath it."""
    child_norm = normalize_path(child)
    root_norm = normalize_path(root)
    if not child_norm or not root_norm:
        return False
    return child_norm == root_norm or child_norm.startswith(root_norm + "/")


def paths_equivalent(a: str, b: str) -> bool:
    """True when two path strings denote the same location (normalized)."""
    return normalize_path(a) == normalize_path(b)


@dataclass(slots=True)
class Workspace:
    """One independent working context (Plan §3.1 — seven fields verbatim)."""

    # §3.1 fields (verbatim)
    id: str
    name: str
    path: str
    project: str
    memory_namespace: str
    git_repository: str | None
    settings: dict[str, Any] = field(default_factory=dict)

    # bookkeeping
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        *,
        name: str,
        path: str,
        project: str | None = None,
        memory_namespace: str | None = None,
        git_repository: str | None = None,
        settings: Mapping[str, Any] | None = None,
        workspace_id: str | None = None,
    ) -> Workspace:
        """Build a workspace with validated fields and defaults.

        ``project`` defaults to the name; ``memory_namespace`` defaults
        to ``nexus.memory.<name>`` (Spec §22 WORKSPACE level).
        """
        clean_name = (name or "").strip()
        clean_path = (path or "").strip()
        if not clean_name:
            raise WorkspaceError("workspace name is required")
        if not clean_path:
            raise WorkspaceError(f"workspace {clean_name!r}: path is required")
        wid = workspace_id or new_workspace_id()
        if not _WS_ID_PATTERN.match(wid):
            raise WorkspaceError(f"invalid workspace id {wid!r} — expected wsp_<12 hex>")
        return cls(
            id=wid,
            name=clean_name,
            path=clean_path,
            project=(project or "").strip() or clean_name,
            memory_namespace=(memory_namespace or "").strip()
            or DEFAULT_MEMORY_NAMESPACE.format(name=clean_name.lower()),
            git_repository=(git_repository or "").strip() or None,
            settings=dict(settings or {}),
        )

    def touch(self) -> None:
        self.updated_at = utc_now()

    def contains(self, path: str) -> bool:
        """True when *path* lives inside this workspace's filesystem root."""
        return path_within(path, self.path)

    # -------------------------------------------------------- serialization

    def to_dict(self) -> dict[str, Any]:
        """Serializable record (registry format, JSON-safe)."""
        return {
            "id": self.id,
            "name": self.name,
            "path": self.path,
            "project": self.project,
            "memory_namespace": self.memory_namespace,
            "git_repository": self.git_repository,
            "settings": dict(self.settings),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Workspace:
        """Rebuild a workspace from its registry record."""
        try:
            name = str(data["name"])
            created = datetime.fromisoformat(str(data["created_at"]))
            updated = datetime.fromisoformat(str(data["updated_at"]))
            return cls(
                id=str(data["id"]),
                name=name,
                path=str(data["path"]),
                project=str(data.get("project") or name),
                memory_namespace=str(
                    data.get("memory_namespace")
                    or DEFAULT_MEMORY_NAMESPACE.format(name=name.lower())
                ),
                git_repository=data.get("git_repository"),
                settings=dict(data.get("settings") or {}),
                created_at=created,
                updated_at=updated,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkspaceError(f"corrupt workspace record: {exc}") from exc
