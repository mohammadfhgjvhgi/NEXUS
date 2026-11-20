"""Policy Engine — decisions for proposed actions (Final Build Plan §3.5).

Evaluates a :class:`PolicyAction` against a :class:`TaskPolicy` (and
the registered workspaces) and returns a :class:`PolicyDecision`:

* **explicit negative policy** → denied (blocked tool/host, offline
  network, git disabled, external AI disabled, app launch disabled,
  OBSERVE autonomy mutations);
* **within scope**             → allowed (autonomy permitting);
* **outside scope**            → never an absolute wall (Plan §3.4):
  cross-workspace **reads** stay allowed (scoped, audited — Spec
  §21); cross-workspace mutations and destructive operations
  escalate to confirmation; ``allow_cross_workspace=False`` routes
  the escalation to the human instead of blocking.

The decision *is* the audit record — there is no hidden enforcement;
callers execute only what a decision allows.

محرّك السياسة — قرار لكل فعل مقترح؛ منع صريح فقط، وتصعيد لا جدار.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from ..scope.models import Scope, host_matches
from ..workspace.manager import WorkspaceManager
from ..workspace.models import path_within
from .models import AutonomyLevel, TaskPolicy

#: Starts like an absolute path (drive letter, UNC or POSIX root).
_PATHLIKE_RE = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")


class ActionType(StrEnum):
    """The action families the engine decides about."""

    READ = "read"  # filesystem read
    WRITE = "write"  # filesystem write
    DELETE = "delete"  # destructive filesystem change
    EXECUTE = "execute"  # run a file/command inside the scope
    TOOL = "tool"  # use a named tool (terminal, browser, git…)
    NETWORK = "network"  # reach a host
    GIT_COMMIT = "git.commit"
    GIT_PUSH = "git.push"
    GIT_PULL = "git.pull"
    APP_LAUNCH = "app.launch"  # start an application (Spec §19)
    BROWSER_SESSION = "browser.session"  # open/reuse a browser session
    EXTERNAL_AI = "external_ai"  # consult an external AI provider
    CROSS_WORKSPACE = "cross_workspace"  # mutation in another workspace


#: Actions that change the world — gated by autonomy level.
MUTATION_ACTIONS: frozenset[ActionType] = frozenset(
    {
        ActionType.WRITE,
        ActionType.DELETE,
        ActionType.EXECUTE,
        ActionType.TOOL,
        ActionType.NETWORK,
        ActionType.GIT_COMMIT,
        ActionType.GIT_PUSH,
        ActionType.GIT_PULL,
        ActionType.APP_LAUNCH,
        ActionType.BROWSER_SESSION,
        ActionType.EXTERNAL_AI,
        ActionType.CROSS_WORKSPACE,
    }
)


@dataclass(frozen=True, slots=True)
class PolicyAction:
    """One proposed action: type + target (+ owning workspace).

    Target semantics per type: path (READ/WRITE/DELETE/EXECUTE),
    tool name (TOOL), host (NETWORK), branch (GIT_*), application
    (APP_LAUNCH), session id (BROWSER_SESSION), provider
    (EXTERNAL_AI), ``"<workspace>:<part>"`` (CROSS_WORKSPACE).
    """

    action_type: ActionType
    target: str = ""
    workspace_id: str | None = None
    detail: str = ""


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Outcome of one evaluation — the audit record.

    ``allowed=True, requires_confirmation=True`` means "permitted
    after a human confirms"; ``allowed=False`` is a denial by
    explicit policy only.
    """

    action: PolicyAction
    allowed: bool
    requires_confirmation: bool
    reason: str
    autonomy_level: AutonomyLevel
    in_scope: bool

    @property
    def verdict(self) -> str:
        """"allow" | "confirm" | "deny"."""
        if not self.allowed:
            return "deny"
        return "confirm" if self.requires_confirmation else "allow"


def _is_pathlike(target: str) -> bool:
    return bool(_PATHLIKE_RE.match(target)) or "/" in target or "\\" in target


def _name_in(entries: list[str], target: str) -> bool:
    lowered = (target or "").strip().lower()
    if not lowered:
        return False
    for entry in entries:
        entry_clean = entry.strip()
        if entry_clean == "*" or entry_clean.lower() == lowered:
            return True
    return False


def _host_in(entries: list[str], host: str) -> bool:
    return any(host_matches(entry, host) for entry in entries)


class PolicyEngine:
    """Decides proposed actions against a task policy."""

    def __init__(self, manager: WorkspaceManager | None = None) -> None:
        self._manager = manager

    # ----------------------------------------------------------------- API

    def decide(
        self,
        action: PolicyAction,
        policy: TaskPolicy,
        *,
        manager: WorkspaceManager | None = None,
        task_scope: Scope | None = None,
    ) -> PolicyDecision:
        """Evaluate *action* under *policy*.

        ``task_scope`` is the resolved Scope (§3.3) of the acting
        task; ``manager`` supplies workspace boundaries for
        cross-workspace detection.
        """
        registry = manager if manager is not None else self._manager
        level = policy.autonomy_level
        action_type = action.action_type

        # 1. explicit negative policies → deny
        denied = self._explicit_deny(action, policy)
        if denied is not None:
            return PolicyDecision(
                action=action,
                allowed=False,
                requires_confirmation=False,
                reason=denied,
                autonomy_level=level,
                in_scope=True,
            )

        # 2. OBSERVE autonomy is read-only
        if action_type in MUTATION_ACTIONS and level is AutonomyLevel.OBSERVE:
            return PolicyDecision(
                action=action,
                allowed=False,
                requires_confirmation=False,
                reason=f"autonomy OBSERVE forbids mutations ({action_type.value})",
                autonomy_level=level,
                in_scope=True,
            )

        # 3. where does the action land?
        in_scope, is_cross = self._placement(action, policy, registry, task_scope)

        # 4. confirm-first tools → escalate
        if action_type is ActionType.TOOL and _name_in(
            policy.tool_policy.confirm_tools, action.target
        ):
            return self._confirm(
                action, level, "tool marked confirm-first by policy", in_scope
            )

        # 5. SUGGEST autonomy: every mutation waits for a human
        if action_type in MUTATION_ACTIONS and level is AutonomyLevel.SUGGEST:
            return self._confirm(
                action,
                level,
                "autonomy SUGGEST: mutation awaits human confirmation",
                in_scope,
            )

        # 6. destructive DELETE: confirm below FULL autonomy
        if (
            action_type is ActionType.DELETE
            and level is AutonomyLevel.ACT_CONFIRMED
            and in_scope
        ):
            return self._confirm(
                action, level, "destructive DELETE requires confirmation", in_scope
            )

        # 7. protected git branches: always a confirmation
        if action_type in (ActionType.GIT_COMMIT, ActionType.GIT_PUSH):
            branch = (action.target or "").strip().lower()
            if branch and branch in {
                protected.lower()
                for protected in policy.git_policy.protected_branches
            }:
                return self._confirm(
                    action, level, f"protected branch {action.target!r}"
                )

        # 8. outside the declared scope — never an absolute wall (§3.4)
        if not in_scope:
            return self._out_of_scope(action, policy, is_cross, task_scope)

        # 9. within scope → allowed
        return PolicyDecision(
            action=action,
            allowed=True,
            requires_confirmation=False,
            reason="within task scope",
            autonomy_level=level,
            in_scope=True,
        )

    # ------------------------------------------------------------ internals

    def _explicit_deny(self, action: PolicyAction, policy: TaskPolicy) -> str | None:
        """Explicit negative policy → denial reason (or None)."""
        action_type = action.action_type
        target = (action.target or "").strip()
        if action_type is ActionType.TOOL and target:
            if _name_in(policy.tool_policy.blocked_tools, target):
                return f"tool {target!r} blocked by policy"
        if action_type is ActionType.NETWORK and target:
            if policy.network_policy.offline:
                return "network is offline by policy"
            if _host_in(policy.network_policy.blocked_hosts, target):
                return f"host {target!r} blocked by policy"
        if action_type is ActionType.GIT_COMMIT and not policy.git_policy.can_commit:
            return "git commits disabled by policy"
        if action_type is ActionType.GIT_PUSH and not policy.git_policy.can_push:
            return "git pushes disabled by policy"
        if action_type is ActionType.GIT_PULL and not policy.git_policy.can_pull:
            return "git pulls disabled by policy"
        if (
            action_type is ActionType.EXTERNAL_AI
            and not policy.external_ai_policy.allowed
        ):
            return "external AI disabled by policy"
        if action_type is ActionType.APP_LAUNCH and not policy.app_scope.launch_allowed:
            return "app launch disabled by policy"
        return None

    def _placement(
        self,
        action: PolicyAction,
        policy: TaskPolicy,
        manager: WorkspaceManager | None,
        task_scope: Scope | None,
    ) -> tuple[bool, bool]:
        """Where the action lands: (in_scope, is_cross_workspace)."""
        action_type = action.action_type
        target = (action.target or "").strip()

        if action_type in (ActionType.READ, ActionType.WRITE, ActionType.DELETE,
                           ActionType.EXECUTE) and target and _is_pathlike(target):
            if task_scope is not None and task_scope.covers_path(target):
                return (True, False)
            if any(
                path_within(target, declared)
                for declared in policy.workspace_scope.filesystem_paths
            ):
                return (True, False)
            if action.workspace_id and action.workspace_id in (
                policy.workspace_scope.workspace_ids
            ):
                return (True, False)
            if manager is not None and manager.resolve_path(target) is not None:
                return (False, True)  # path lives in another registered workspace
            return (False, False)

        if action_type is ActionType.NETWORK and target:
            return (_host_in(policy.network_policy.allowed_hosts, target), False)

        if action_type is ActionType.TOOL and target:
            return (_name_in(policy.tool_policy.allowed_tools, target), False)

        if action_type is ActionType.APP_LAUNCH and target:
            return (_name_in(policy.app_scope.applications, target), False)

        if action_type is ActionType.EXTERNAL_AI and target:
            return (_name_in(policy.external_ai_policy.providers, target), False)

        if (
            action_type is ActionType.BROWSER_SESSION
            and target
            and task_scope is not None
        ):
            return (task_scope.covers_browser_session(target), False)

        if action_type is ActionType.CROSS_WORKSPACE:
            return (False, True)

        return (True, False)

    def _out_of_scope(
        self,
        action: PolicyAction,
        policy: TaskPolicy,
        is_cross: bool,
        task_scope: Scope | None,
    ) -> PolicyDecision:
        """Outside the declared scope — scoped/escalated, never walled."""
        level = policy.autonomy_level
        action_type = action.action_type

        if is_cross:
            if action_type is ActionType.READ:
                # Spec §21 flow: cross-workspace retrieval is a read —
                # allowed, scoped to the needed part, audited.
                return PolicyDecision(
                    action=action,
                    allowed=True,
                    requires_confirmation=False,
                    reason=(
                        "cross-workspace read: scoped access granted "
                        "(never blocked, audit recorded)"
                    ),
                    autonomy_level=level,
                    in_scope=False,
                )
            if not policy.workspace_scope.allow_cross_workspace:
                return self._confirm(
                    action,
                    level,
                    "cross-workspace access disabled by policy — "
                    "human approval required (not an absolute block)",
                    in_scope=False,
                )
            if level is AutonomyLevel.FULL:
                return PolicyDecision(
                    action=action,
                    allowed=True,
                    requires_confirmation=False,
                    reason=(
                        "full autonomy: cross-workspace mutation allowed "
                        "(scoped, audited)"
                    ),
                    autonomy_level=level,
                    in_scope=False,
                )
            return self._confirm(
                action,
                level,
                "cross-workspace mutation outside the declared scope",
                in_scope=False,
            )

        # Unregistered/undeclared target
        if level is AutonomyLevel.FULL and action_type in MUTATION_ACTIONS:
            return PolicyDecision(
                action=action,
                allowed=True,
                requires_confirmation=False,
                reason="outside declared scope at FULL autonomy (flagged)",
                autonomy_level=level,
                in_scope=False,
            )
        if action_type not in MUTATION_ACTIONS:
            return PolicyDecision(
                action=action,
                allowed=True,
                requires_confirmation=False,
                reason="read outside declared scope: allowed and flagged",
                autonomy_level=level,
                in_scope=False,
            )
        scope_note = (
            " (no task scope resolved)" if task_scope is None else ""
        )
        return self._confirm(
            action,
            level,
            f"outside declared scope — confirmation required{scope_note}",
            in_scope=False,
        )

    def _confirm(
        self,
        action: PolicyAction,
        level: AutonomyLevel,
        reason: str,
        in_scope: bool = True,
    ) -> PolicyDecision:
        return PolicyDecision(
            action=action,
            allowed=True,
            requires_confirmation=True,
            reason=reason,
            autonomy_level=level,
            in_scope=in_scope,
        )
