"""Scope model (Final Build Plan §3.2 / Spec §18–§19).

Six dimensions, verbatim from Plan §3.2:

    filesystem paths · applications · browser sessions ·
    network permissions · tools · repositories

The Scope is **not a sandbox** (Spec §19): it is the logical and
policy boundary of the task. NEXUS *can* reach the rest of the
machine — it does not, because the rest is outside the task's
relation. Non-file operational resources (Chrome, VS Code, Word,
GitHub, the terminal, browser sessions — Spec §18's "Allowed" list)
are first-class scope dimensions, not afterthoughts.

The scope bridges to the Phase 1 ``Task.scope`` mapping
(:data:`nexus.core.session.models.ScopeMap`) through
``to_scope_map`` / ``from_scope_map`` — the same JSON-stable keys
the §2.5 persistence already round-trips.

نموذج النطاق — ستة أبعاد حرفيًا؛ حدود منطقية وسياساتية لا عزل تقني.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from ..workspace.models import Workspace, path_within

#: The six §3.2 dimensions, verbatim key order.
SCOPE_DIMENSIONS: tuple[str, ...] = (
    "filesystem_paths",
    "applications",
    "browser_sessions",
    "network_permissions",
    "tools",
    "repositories",
)

#: Wildcard entry: allows everything within a dimension.
ALL = "*"


def _clean(items: Iterable[str]) -> list[str]:
    """Strip, drop empties, preserve first occurrence (case-insensitive
    dedup — entries are matched case-insensitively everywhere)."""
    seen: list[str] = []
    seen_lower: set[str] = set()
    for item in items:
        text = str(item).strip()
        if text and text.lower() not in seen_lower:
            seen.append(text)
            seen_lower.add(text.lower())
    return seen


def _entry_matches(entry: str, target: str) -> bool:
    """Case-insensitive exact match, honoring the ``*`` wildcard entry."""
    return entry.strip().lower() == target.strip().lower()


def _name_allowed(entries: Iterable[str], target: str) -> bool:
    """True when *target* is allowed by an entry list ("*" or exact)."""
    lowered = target.strip().lower()
    if not lowered:
        return False
    for entry in entries:
        if entry.strip() == ALL or _entry_matches(entry, lowered):
            return True
    return False


def host_matches(entry: str, host: str) -> bool:
    """Host permission semantics: ``*``, exact, or ``*.domain`` wildcard.

    ``*.example.com`` covers ``api.example.com`` and the bare
    ``example.com``; ``example.com`` also covers ``api.example.com``
    (a domain permission includes its subdomains).
    """
    entry_norm = entry.strip().lower()
    host_norm = host.strip().lower()
    if not entry_norm or not host_norm:
        return False
    if entry_norm == ALL:
        return True
    if entry_norm.startswith("*."):
        suffix = entry_norm[1:]  # ".example.com"
        return host_norm.endswith(suffix) or host_norm == entry_norm[2:]
    return host_norm == entry_norm or host_norm.endswith("." + entry_norm)


@dataclass(slots=True)
class Scope:
    """The six-dimension boundary of a task (Plan §3.2 — verbatim)."""

    filesystem_paths: list[str] = field(default_factory=list)
    applications: list[str] = field(default_factory=list)
    browser_sessions: list[str] = field(default_factory=list)
    network_permissions: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    repositories: list[str] = field(default_factory=list)

    # ----------------------------------------------------------- factories

    @classmethod
    def empty(cls) -> Scope:
        return cls()

    @classmethod
    def create(cls, **dimensions: Iterable[str]) -> Scope:
        """Build a scope from per-dimension iterables (cleaned, deduped;
        unknown dimension keys are ignored)."""
        scope = cls.empty()
        for name in SCOPE_DIMENSIONS:
            if name in dimensions:
                setattr(scope, name, _clean(dimensions[name]))
        return scope

    @classmethod
    def from_workspace(cls, workspace: Workspace) -> Scope:
        """Derive a task scope from a workspace: the filesystem root, the
        git repository, and the operational dimensions declared in the
        workspace ``settings`` (``applications``, ``browser_sessions``,
        ``network_permissions``, ``tools`` — Spec §19 non-file
        resources)."""
        settings = workspace.settings or {}
        return cls(
            filesystem_paths=_clean([workspace.path]),
            applications=_clean(settings.get("applications", ())),
            browser_sessions=_clean(settings.get("browser_sessions", ())),
            network_permissions=_clean(settings.get("network_permissions", ())),
            tools=_clean(settings.get("tools", ())),
            repositories=_clean(
                [workspace.git_repository]
                if workspace.git_repository
                else ()
            ),
        )

    # ------------------------------------------------------------ coverage

    def covers_path(self, path: str) -> bool:
        """True when *path* lies under any declared filesystem root."""
        return any(path_within(path, root) for root in self.filesystem_paths)

    def covers_application(self, application: str) -> bool:
        return _name_allowed(self.applications, application)

    def covers_browser_session(self, session_id: str) -> bool:
        return _name_allowed(self.browser_sessions, session_id)

    def covers_host(self, host: str) -> bool:
        return any(host_matches(entry, host) for entry in self.network_permissions)

    def covers_tool(self, tool: str) -> bool:
        return _name_allowed(self.tools, tool)

    def covers_repository(self, repository: str) -> bool:
        return _name_allowed(self.repositories, repository)

    def is_empty(self) -> bool:
        return not any(getattr(self, name) for name in SCOPE_DIMENSIONS)

    # -------------------------------------------------------------- algebra

    def merge(self, other: Scope) -> Scope:
        """Union of two scopes (per dimension, order-preserving dedupe)."""
        return Scope(
            filesystem_paths=_clean(self.filesystem_paths + other.filesystem_paths),
            applications=_clean(self.applications + other.applications),
            browser_sessions=_clean(
                self.browser_sessions + other.browser_sessions
            ),
            network_permissions=_clean(
                self.network_permissions + other.network_permissions
            ),
            tools=_clean(self.tools + other.tools),
            repositories=_clean(self.repositories + other.repositories),
        )

    # -------------------------------------------------------- serialization

    def to_scope_map(self) -> dict[str, list[str]]:
        """Canonical mapping for the Phase 1 ``Task.scope`` field
        (:data:`ScopeMap`) — keys are the six §3.2 dimensions verbatim."""
        return {name: list(getattr(self, name)) for name in SCOPE_DIMENSIONS}

    to_dict = to_scope_map

    @classmethod
    def from_scope_map(cls, mapping: Mapping[str, Iterable[str]]) -> Scope:
        """Rebuild from a canonical scope mapping (unknown keys ignored,
        unknown-typed values coerced to strings)."""
        scope = cls.empty()
        for name in SCOPE_DIMENSIONS:
            if name in mapping:
                scope_attr = mapping[name]
                if isinstance(scope_attr, str):
                    values: list[str] = [scope_attr]
                else:
                    values = [str(item) for item in scope_attr]
                setattr(scope, name, _clean(values))
        return scope

    from_dict = from_scope_map
