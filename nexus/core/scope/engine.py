"""Scope Engine — resolution + cross-workspace access (Plan §3.3/§3.4, Spec §21).

**§3.3 Scope Resolution** — turn a natural-language request into a
workspace + scope::

    "اشتغل على M:\\Client"
        → workspace = Client
        → filesystem scope = M:\\Client

Resolution order (first hit wins, confidence recorded):

1. **path token**   — a drive/UNC/POSIX path inside a registered
   workspace root (confidence 1.0);
2. **name**         — a registered workspace's name appears in the
   request (0.8);
3. **project**      — a workspace's project label appears (0.7);
4. **default**      — the configured default workspace (0.3).

**§3.4 Cross-workspace Access** — *never an absolute block*. When a
task needs something from another workspace ("خذ قرار authentication
من المشروع الثاني"), the engine carves a **sub-scope** out of the
target workspace containing only the requested part (keyword-matched
paths, tools, repositories — Spec §21: *return only the needed
information*). Histories are never merged: the
:class:`CrossWorkspaceAccess` audit record is the only bridge.

محرك النطاق — حلّ الطلب إلى مساحة عمل، ووصول عبر المساحات بلا منع مطلق.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..workspace.manager import WorkspaceManager
from ..workspace.models import Workspace, WorkspaceError, normalize_path
from .models import Scope, _clean

#: Path-shaped tokens inside free text: Windows drive (``M:\\Client``),
#: UNC (``\\\\server\\share``) and POSIX (``/home/user``) roots.
PATH_TOKEN_RE = re.compile(
    r"[A-Za-z]:[\\/][\w.\-\\/~]*"
    r"|\\\\[\w.\-]+(?:\\[\w.\-]+)+"
    r"|/[\w.\-/~]*"
)

#: Trailing punctuation that may cling to a token at sentence end.
_TOKEN_TRIM = ".,;:!؟?!\"'»«()[]{}"

#: Concept keyword associations for cross-workspace carving (§3.4).
KEYWORD_ASSOCIATIONS: dict[str, tuple[str, ...]] = {
    "authentication": (
        "auth", "login", "credential", "token", "session", "security",
        "oauth", "jwt", "identity",
    ),
    "authorization": (
        "auth", "permission", "rbac", "acl", "policy", "guard", "role",
    ),
    "database": (
        "db", "database", "sql", "schema", "migration", "model", "orm",
        "prisma",
    ),
    "ui": (
        "ui", "component", "view", "page", "template", "frontend", "layout",
    ),
    "api": (
        "api", "route", "endpoint", "controller", "handler", "rest",
        "graphql",
    ),
    "config": ("config", "settings", "env", "toml", "yaml", "ini"),
    "tests": ("test", "tests", "spec", "harness", "verify", "assert"),
    "docs": ("doc", "docs", "readme", "report", "guide", "manual"),
    "git": ("git", "commit", "branch", "merge", "rebase"),
    "build": ("build", "make", "compile", "dist", "target"),
}


def keywords_for(part: str) -> tuple[str, ...]:
    """Keyword set used to carve a sub-scope for a requested *part*.

    Exact concept names expand with their associations ("authentication"
    → auth/login/token/…); unknown parts keep the raw keyword plus any
    concept whose name appears inside the request.
    """
    key = (part or "").strip().lower()
    if not key:
        return ()
    if key in KEYWORD_ASSOCIATIONS:
        return (key, *KEYWORD_ASSOCIATIONS[key])
    matched: list[str] = [key]
    for concept, aliases in KEYWORD_ASSOCIATIONS.items():
        if concept in key:
            matched.append(concept)
            matched.extend(aliases)
    return tuple(dict.fromkeys(matched))


def path_tokens(text: str) -> list[str]:
    """Extract path-shaped tokens from free text (order preserved)."""
    tokens: list[str] = []
    for match in PATH_TOKEN_RE.findall(text or ""):
        token = match.strip(_TOKEN_TRIM)
        if token and token not in tokens:
            tokens.append(token)
    return tokens


def _mentions(text_lower: str, label: str) -> bool:
    """Whole-word mention test (word boundaries, case-insensitive by
    construction) — ``ClientWebsite`` must not match the name
    ``Client``."""
    return re.search(rf"\b{re.escape(label.lower())}\b", text_lower) is not None


@dataclass(frozen=True, slots=True)
class ScopeResolution:
    """Outcome of §3.3 resolution: one workspace + its derived scope."""

    workspace: Workspace
    scope: Scope
    matched: str  # "path" | "name" | "project" | "default"
    confidence: float
    request: str

    def to_dict(self) -> dict[str, object]:
        return {
            "workspace_id": self.workspace.id,
            "workspace_name": self.workspace.name,
            "matched": self.matched,
            "confidence": self.confidence,
            "scope": self.scope.to_scope_map(),
            "request": self.request,
        }


@dataclass(frozen=True, slots=True)
class CrossWorkspaceAccess:
    """§3.4 audit record: scoped access from one workspace into another.

    ``granted`` is False **only** when the target workspace is not
    registered (nothing to search — that is nonexistence, not a
    denial). When the target exists, access is granted by design,
    scoped to the requested part, and the access record is the only
    bridge between the two histories (Spec §21).
    """

    id: str
    source_workspace_id: str
    target_workspace_id: str
    requested_part: str
    granted: bool
    reason: str
    resolved_scope: Scope
    keywords: tuple[str, ...] = field(default_factory=tuple)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "source_workspace_id": self.source_workspace_id,
            "target_workspace_id": self.target_workspace_id,
            "requested_part": self.requested_part,
            "granted": self.granted,
            "reason": self.reason,
            "resolved_scope": self.resolved_scope.to_scope_map(),
            "keywords": list(self.keywords),
            "created_at": self.created_at.isoformat(),
        }


def _new_access_id() -> str:
    return f"cwa_{uuid.uuid4().hex[:12]}"


class ScopeEngine:
    """Resolves requests into scopes (§3.3) and brokers scoped
    cross-workspace access (§3.4)."""

    def __init__(self, manager: WorkspaceManager | None = None) -> None:
        self._manager = manager
        self._access_log: list[CrossWorkspaceAccess] = []

    # ---------------------------------------------------------- §3.3 resolve

    def resolve(
        self,
        request: str,
        *,
        manager: WorkspaceManager | None = None,
    ) -> ScopeResolution:
        """Resolve a natural-language request to workspace + scope."""
        registry = manager if manager is not None else self._manager
        if registry is None:
            raise WorkspaceError("scope resolution requires a workspace manager")
        text = request or ""

        # 1. path tokens — first token that lands inside a registered root
        for token in path_tokens(text):
            workspace = registry.resolve_path(token)
            if workspace is not None:
                return ScopeResolution(
                    workspace=workspace,
                    scope=Scope.from_workspace(workspace),
                    matched="path",
                    confidence=1.0,
                    request=text,
                )

        lowered = text.lower()
        # 2. workspace name (whole-word mention)
        for workspace in registry.list_workspaces():
            if workspace.name and _mentions(lowered, workspace.name):
                return ScopeResolution(
                    workspace=workspace,
                    scope=Scope.from_workspace(workspace),
                    matched="name",
                    confidence=0.8,
                    request=text,
                )

        # 3. project label (whole-word mention, distinct from the name)
        for workspace in registry.list_workspaces():
            project = workspace.project
            if (
                project
                and project.lower() != workspace.name.lower()
                and _mentions(lowered, project)
            ):
                return ScopeResolution(
                    workspace=workspace,
                    scope=Scope.from_workspace(workspace),
                    matched="project",
                    confidence=0.7,
                    request=text,
                )

        # 4. default workspace
        workspace = registry.default()
        return ScopeResolution(
            workspace=workspace,
            scope=Scope.from_workspace(workspace),
            matched="default",
            confidence=0.3,
            request=text,
        )

    # ------------------------------------------------- §3.4 cross-workspace

    def request_cross_workspace(
        self,
        source: Workspace | str,
        target: Workspace | str,
        part: str,
        *,
        lister: Callable[[str], Iterable[str]] | None = None,
        manager: WorkspaceManager | None = None,
    ) -> CrossWorkspaceAccess:
        """Request scoped access from *source* into *target* for *part*.

        Never an absolute block (Plan §3.4): when the target is
        registered, access is granted and carved down to the requested
        part only. ``lister`` (optional) enumerates candidate paths
        under the target root — without it the carve yields scoped
        glob patterns.
        """
        registry = manager if manager is not None else self._manager
        if registry is None:
            raise WorkspaceError("cross-workspace access requires a workspace manager")

        source_ws = self._resolve_reference(source, registry)
        target_ws = self._resolve_reference(target, registry)
        requested = (part or "").strip()
        keywords = keywords_for(requested)

        if target_ws is None:
            reference = target if isinstance(target, str) else target.id
            return CrossWorkspaceAccess(
                id=_new_access_id(),
                source_workspace_id=source_ws.id if source_ws else str(source),
                target_workspace_id=str(reference),
                requested_part=requested,
                granted=False,
                reason=(
                    f"target workspace {reference!r} is not registered "
                    "(nothing to search — not a denial)"
                ),
                resolved_scope=Scope.empty(),
                keywords=keywords,
            )

        sub_scope = self._carve(target_ws, keywords, lister)
        return self._record(
            CrossWorkspaceAccess(
                id=_new_access_id(),
                source_workspace_id=source_ws.id if source_ws else str(source),
                target_workspace_id=target_ws.id,
                requested_part=requested,
                granted=True,
                reason=(
                    f"scoped access granted: only {requested!r}-related "
                    f"resources of workspace {target_ws.name!r} "
                    "(histories stay separate — Spec §21)"
                ),
                resolved_scope=sub_scope,
                keywords=keywords,
            )
        )

    def _resolve_reference(
        self, reference: Workspace | str, registry: WorkspaceManager
    ) -> Workspace | None:
        if isinstance(reference, Workspace):
            return reference
        return registry.find(reference)

    def _carve(
        self,
        target: Workspace,
        keywords: tuple[str, ...],
        lister: Callable[[str], Iterable[str]] | None,
    ) -> Scope:
        """Carve the sub-scope of *target* matching *keywords* only —
        never the whole workspace (Spec §21: return only the needed
        information)."""
        if not keywords:
            # Unknown part: still scoped — a shallow pattern, not the root.
            keywords = (target.name.lower(),)

        if lister is not None:
            candidates = [str(p) for p in lister(target.path)]
            paths = [
                candidate
                for candidate in candidates
                if any(keyword in normalize_path(candidate) for keyword in keywords)
            ]
        else:
            separator = "\\" if "\\" in target.path else "/"
            root = target.path.rstrip("\\/")
            paths = [
                f"{root}{separator}**{separator}*{keyword}*"
                for keyword in keywords
            ]

        settings = target.settings or {}
        return Scope(
            filesystem_paths=_clean(paths),
            applications=_clean(
                item
                for item in settings.get("applications", ())
                if _mentions_keyword(item, keywords)
            ),
            browser_sessions=[],
            network_permissions=[],
            tools=_clean(
                item
                for item in settings.get("tools", ())
                if _mentions_keyword(item, keywords)
            ),
            repositories=_clean(
                item
                for item in ([target.git_repository] if target.git_repository else ())
                if _mentions_keyword(item, keywords)
            ),
        )

    def _record(self, access: CrossWorkspaceAccess) -> CrossWorkspaceAccess:
        self._access_log.append(access)
        return access

    # ---------------------------------------------------------------- audit

    def access_history(self) -> tuple[CrossWorkspaceAccess, ...]:
        """All cross-workspace access records of this engine instance."""
        return tuple(self._access_log)

    def clear_history(self) -> None:
        self._access_log.clear()


def _mentions_keyword(item: str, keywords: tuple[str, ...]) -> bool:
    lowered = str(item).lower()
    return any(keyword in lowered for keyword in keywords)
