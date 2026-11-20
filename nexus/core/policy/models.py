"""Task Policy model (Final Build Plan §3.5).

Nine policy components, verbatim from Plan §3.5:

    autonomy_level · time_policy · network_policy · tool_policy ·
    workspace_scope · app_scope · git_policy · external_ai_policy ·
    resource_policy

The default policy encodes the Phase 2 goal — **Full Control within
Task Scope**: autonomy FULL, permissive-with-structure defaults, and
cross-workspace access allowed (Plan §3.4: outside-scope work is
scoped and confirmed, never walled).

Explicit negative settings (blocked tools/hosts, offline network,
git disabled, external AI disabled) still bind — "full control" is
control *within* the declared policy, not above it.

سياسة المهمة — تسعة مكونات حرفيًا؛ تحكم كامل داخل نطاق المهمة.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields
from datetime import UTC, datetime
from enum import IntEnum
from typing import Any

from ..workspace.models import Workspace


class AutonomyLevel(IntEnum):
    """How much NEXUS may do on its own.

    Ordered: OBSERVE < SUGGEST < ACT_CONFIRMED < FULL. The default is
    FULL — *Full Control within Task Scope* — bounded only by the
    declared policy components.
    """

    OBSERVE = 1  # read-only: mutations are refused
    SUGGEST = 2  # propose everything; a human confirms mutations
    ACT_CONFIRMED = 3  # act in-scope; out-of-scope/destructive → confirm
    FULL = 4  # full control within the declared policy


@dataclass(slots=True)
class TimePolicy:
    """Temporal bounds of a task (advisory limits, None = unlimited)."""

    max_duration_seconds: int | None = None
    idle_timeout_seconds: int | None = None
    deadline: str | None = None  # ISO-8601, advisory


@dataclass(slots=True)
class NetworkPolicy:
    """Network permissions: allow-list (``*`` = any), block-list, offline."""

    allowed_hosts: list[str] = field(default_factory=lambda: ["*"])
    blocked_hosts: list[str] = field(default_factory=list)
    offline: bool = False


@dataclass(slots=True)
class ToolPolicy:
    """Tool permissions: allowed (``*`` = any), blocked, confirm-first."""

    allowed_tools: list[str] = field(default_factory=lambda: ["*"])
    blocked_tools: list[str] = field(default_factory=list)
    confirm_tools: list[str] = field(default_factory=list)


@dataclass(slots=True)
class WorkspaceScope:
    """Which workspaces/paths the policy covers — and whether
    cross-workspace access may be exercised (Plan §3.4: default True;
    disabling it escalates to human confirmation, never a wall)."""

    workspace_ids: list[str] = field(default_factory=list)
    filesystem_paths: list[str] = field(default_factory=list)
    allow_cross_workspace: bool = True


@dataclass(slots=True)
class AppScope:
    """Application permissions (Spec §19 operational resources)."""

    applications: list[str] = field(default_factory=lambda: ["*"])
    launch_allowed: bool = True


@dataclass(slots=True)
class GitPolicy:
    """Git permissions and protected branches."""

    can_commit: bool = True
    can_push: bool = True
    can_pull: bool = True
    protected_branches: list[str] = field(default_factory=lambda: ["main"])


@dataclass(slots=True)
class ExternalAIPolicy:
    """Whether external AI providers may be consulted, and which."""

    allowed: bool = True
    providers: list[str] = field(default_factory=lambda: ["*"])


@dataclass(slots=True)
class ResourcePolicy:
    """Resource bounds (None = host-bound; 3 matches the §2.1
    ``agents.max_parallel`` default)."""

    max_parallel_agents: int = 3
    max_memory_mb: int | None = None
    max_disk_mb: int | None = None


#: The nine §3.5 components, verbatim key order.
POLICY_COMPONENTS: tuple[str, ...] = (
    "autonomy_level",
    "time_policy",
    "network_policy",
    "tool_policy",
    "workspace_scope",
    "app_scope",
    "git_policy",
    "external_ai_policy",
    "resource_policy",
)

_COMPONENT_TYPES: dict[str, type] = {
    "time_policy": TimePolicy,
    "network_policy": NetworkPolicy,
    "tool_policy": ToolPolicy,
    "workspace_scope": WorkspaceScope,
    "app_scope": AppScope,
    "git_policy": GitPolicy,
    "external_ai_policy": ExternalAIPolicy,
    "resource_policy": ResourcePolicy,
}

_BOOL_TRUE = {"1", "true", "yes", "on"}
_BOOL_FALSE = {"0", "false", "no", "off"}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in _BOOL_TRUE:
            return True
        if lowered in _BOOL_FALSE:
            return False
    raise ValueError(f"expected a boolean, got {value!r}")


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("expected an integer, got a boolean")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("+-").isdigit():
        return int(value.strip())
    raise ValueError(f"expected an integer, got {value!r}")


def _coerce_autonomy(value: Any) -> AutonomyLevel:
    if isinstance(value, AutonomyLevel):
        return value
    if isinstance(value, bool):
        raise ValueError("autonomy_level must be a name or an int 1..4")
    if isinstance(value, int):
        return AutonomyLevel(value)
    text = str(value).strip().upper()
    if text.isdigit():
        return AutonomyLevel(int(text))
    return AutonomyLevel[text]


def _annotation_kind(annotation: Any) -> str:
    """Coercion kind from a (possibly string) annotation.

    Handles both string annotations (``from __future__ import
    annotations``) and type objects, including ``int | None`` style
    optionals: the non-``None`` member decides the coercion.
    """
    text = str(annotation).replace("typing.", "").strip()
    parts = {part.strip() for part in text.split("|")} if "|" in text else {text}
    if "bool" in parts:
        return "bool"
    if "int" in parts:
        return "int"
    if any(part.startswith("list[") for part in parts):
        return "list"
    return "str"


def _build_component(name: str, values: Mapping[str, Any]) -> Any:
    """Rebuild one component dataclass from a mapping (unknown keys
    ignored, values coerced to their annotated types)."""
    component_type = _COMPONENT_TYPES[name]
    known = {f.name for f in fields(component_type)}
    kinds = {f.name: _annotation_kind(f.type) for f in fields(component_type)}
    kwargs: dict[str, Any] = {}
    for key, value in (values or {}).items():
        if key not in known:
            continue
        if value is None:
            kwargs[key] = None
            continue
        kind = kinds[key]
        if kind == "bool":
            kwargs[key] = _coerce_bool(value)
        elif kind == "int":
            kwargs[key] = _coerce_int(value)
        elif kind == "list":
            kwargs[key] = [str(item) for item in value]
        else:
            kwargs[key] = str(value)
    return component_type(**kwargs)


@dataclass(slots=True)
class TaskPolicy:
    """One task's policy — the nine §3.5 components, verbatim."""

    task_id: str | None = None
    autonomy_level: AutonomyLevel = AutonomyLevel.FULL
    time_policy: TimePolicy = field(default_factory=TimePolicy)
    network_policy: NetworkPolicy = field(default_factory=NetworkPolicy)
    tool_policy: ToolPolicy = field(default_factory=ToolPolicy)
    workspace_scope: WorkspaceScope = field(default_factory=WorkspaceScope)
    app_scope: AppScope = field(default_factory=AppScope)
    git_policy: GitPolicy = field(default_factory=GitPolicy)
    external_ai_policy: ExternalAIPolicy = field(default_factory=ExternalAIPolicy)
    resource_policy: ResourcePolicy = field(default_factory=ResourcePolicy)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    # ------------------------------------------------------------ factories

    @classmethod
    def default(cls, *, task_id: str | None = None) -> TaskPolicy:
        """The Full-Control-within-Task-Scope default policy."""
        return cls(task_id=task_id)

    @classmethod
    def from_overrides(
        cls, overrides: Mapping[str, Any], *, task_id: str | None = None
    ) -> TaskPolicy:
        """Build a policy from dotted-path overrides on top of the
        defaults, e.g. ``{"autonomy_level": "SUGGEST",
        "network_policy.offline": True}``. Unknown keys are ignored."""
        policy = cls.default(task_id=task_id)
        for key, value in (overrides or {}).items():
            parts = str(key).split(".")
            if len(parts) == 1:
                if key == "autonomy_level":
                    policy.autonomy_level = _coerce_autonomy(value)
                elif key == "task_id":
                    policy.task_id = str(value)
                elif key in _COMPONENT_TYPES and isinstance(value, Mapping):
                    setattr(policy, key, _build_component(key, value))
            elif len(parts) == 2 and parts[0] in _COMPONENT_TYPES:
                # dict union gives the RIGHT operand precedence — the
                # override must therefore sit on the right.
                setattr(
                    policy,
                    parts[0],
                    _build_component(
                        parts[0],
                        _as_mapping(getattr(policy, parts[0])) | {parts[1]: value},
                    ),
                )
        return policy

    @classmethod
    def for_workspace(cls, workspace: Workspace) -> TaskPolicy:
        """Policy seeded from a workspace's ``settings["policy"]``
        overrides (falls back to the default policy)."""
        settings = workspace.settings or {}
        overrides = settings.get("policy")
        if isinstance(overrides, Mapping):
            return cls.from_overrides(overrides)
        return cls.default()

    # -------------------------------------------------------- serialization

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe record of all nine components."""
        return {
            "task_id": self.task_id,
            "autonomy_level": int(self.autonomy_level),
            "time_policy": {
                "max_duration_seconds": self.time_policy.max_duration_seconds,
                "idle_timeout_seconds": self.time_policy.idle_timeout_seconds,
                "deadline": self.time_policy.deadline,
            },
            "network_policy": {
                "allowed_hosts": list(self.network_policy.allowed_hosts),
                "blocked_hosts": list(self.network_policy.blocked_hosts),
                "offline": self.network_policy.offline,
            },
            "tool_policy": {
                "allowed_tools": list(self.tool_policy.allowed_tools),
                "blocked_tools": list(self.tool_policy.blocked_tools),
                "confirm_tools": list(self.tool_policy.confirm_tools),
            },
            "workspace_scope": {
                "workspace_ids": list(self.workspace_scope.workspace_ids),
                "filesystem_paths": list(self.workspace_scope.filesystem_paths),
                "allow_cross_workspace": self.workspace_scope.allow_cross_workspace,
            },
            "app_scope": {
                "applications": list(self.app_scope.applications),
                "launch_allowed": self.app_scope.launch_allowed,
            },
            "git_policy": {
                "can_commit": self.git_policy.can_commit,
                "can_push": self.git_policy.can_push,
                "can_pull": self.git_policy.can_pull,
                "protected_branches": list(self.git_policy.protected_branches),
            },
            "external_ai_policy": {
                "allowed": self.external_ai_policy.allowed,
                "providers": list(self.external_ai_policy.providers),
            },
            "resource_policy": {
                "max_parallel_agents": self.resource_policy.max_parallel_agents,
                "max_memory_mb": self.resource_policy.max_memory_mb,
                "max_disk_mb": self.resource_policy.max_disk_mb,
            },
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TaskPolicy:
        """Rebuild a policy from its record (all nine components)."""
        policy = cls.default(task_id=data.get("task_id"))
        raw_level = data.get("autonomy_level", int(AutonomyLevel.FULL))
        policy.autonomy_level = _coerce_autonomy(raw_level)
        for name in _COMPONENT_TYPES:
            values = data.get(name)
            if isinstance(values, Mapping):
                setattr(policy, name, _build_component(name, values))
        return policy


def _as_mapping(component: Any) -> dict[str, Any]:
    """Component dataclass → plain mapping (for merging overrides)."""
    return {f.name: getattr(component, f.name) for f in fields(component)}
