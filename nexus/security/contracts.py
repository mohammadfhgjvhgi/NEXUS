"""Security-system contracts (New Plan §21.1–§21.10).

The plan's central claim, verbatim:

    Full capability + controlled execution.

The ten sections, verbatim::

    21.1  Scope Engine Integration
    21.2  Permission Engine
    21.3  Tool Gate
    21.4  MCP Gate
    21.5  Plugin Gate
    21.6  Secret Handling
    21.7  Redaction
    21.8  Audit
    21.9  Trivy (aquasecurity/trivy) — dependency · secret · license ·
          vulnerability scanning
    21.10 Security Rules — لا يصل secret إلى: Memory · Normal chat ·
          Logs · Activity

The model is the Spec §156 triad — *Scope + Permission + Execution
Gate* — walked in the v0.1 §57 order::

    Agent wants: delete file
    ↓ Scope check → Permission check → Policy check → Execute → Log

and bound by the Blueprint §79 law — security is never an obstacle:
``Security → Task Scope → Policy → Execution`` (allowed) — never an
``Ask User`` chain on every step.  Every decision lands as a
:class:`GateDecision` (the audit record — there is no hidden
enforcement), every credential is handed out as a :class:`Credential`
*reference* — the agent never receives the secret text itself (Spec
§160) — and the §21.10 rule is structural: the four protected sinks
(Memory · Normal chat · Logs · Activity) are guarded at their doors,
not by caller discipline.

عقود نظام الأمن — قدر كامل وتنفيذ محكوم: النطاق ثم الإذن ثم البوابة،
وكل قرار مسجَّل، وكل سر بمرجع لا بنص، والأبواب الأربعة محروسة.

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..verification.contracts import utc_now_iso

# ----------------------------------------------------------------- errors


class SecurityError(Exception):
    """Security-system misuse or operation failure."""


class PermissionDeniedError(SecurityError):
    """An action was denied by an explicit rule — execution refused."""


class SecretError(SecurityError):
    """Secret-handling misuse — unknown reference, empty secret."""


class SecretLeakError(SecurityError):
    """A secret would reach a protected sink — the §21.10 hard stop.

    Raised only when a guard cannot clean a payload; the normal path
    redacts silently and records the finding count.
    """


class TrivyUnavailable(SecurityError):  # noqa: N818 — the plan names it verbatim
    """The trivy binary (aquasecurity/trivy) is not usable on this host."""


# ------------------------------------------------------- §21 vocabulary


class RiskLevel(StrEnum):
    """Spec §163 tool-risk classification — three levels, verbatim.

    ``Read file = low · Edit file = medium · Delete file = high ·
    Run unrestricted command = high · Push release = high`` — and L4
    (FULL autonomy) may execute even the high ones when they sit
    inside the task and its policy.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class GateVerdict(StrEnum):
    """One gate's outcome — the same three words the policy engine
    speaks (:class:`nexus.core.policy.engine.PolicyDecision.verdict`)."""

    ALLOW = "allow"
    CONFIRM = "confirm"
    DENY = "deny"


#: §21.10 — the four protected sinks, verbatim from the plan and in
#: its order.  A secret reaches none of them — guarded at the door.
PROTECTED_SINKS: tuple[str, ...] = (
    "memory",
    "normal_chat",
    "logs",
    "activity",
)

#: §21.9 — the four scan kinds trivy (aquasecurity/trivy) is used for,
#: verbatim from the plan and in its order.
SCAN_KINDS: tuple[str, ...] = (
    "dependency",
    "secret",
    "license",
    "vulnerability",
)

#: §21.9 — the scanned repository, verbatim.
TRIVY_REPOSITORY = "aquasecurity/trivy"

#: The action kinds the security pipeline admits (the §21.3–§21.5
#: gates own ``tool`` / ``mcp`` / ``plugin``; the rest ride the
#: §21.2 permission engine on top of the §3.2/§3.5 scope+policy).
ACTION_KINDS: tuple[str, ...] = (
    "file",
    "command",
    "tool",
    "mcp",
    "plugin",
    "network",
    "git",
    "app",
    "browser",
    "external_ai",
    "cross_workspace",
)


# ------------------------------------------------------------ §21 nouns


@dataclass(frozen=True, slots=True)
class SecurityAction:
    """One action asking for admission — the subject of every gate.

    ``kind`` is one of :data:`ACTION_KINDS`, ``name`` the concrete
    subject (tool name, ``"server:tool"`` for MCP, plugin id,
    ``read``/``write``/``delete`` for files, the command line for
    ``command``), ``target`` its object (path, host, branch,
    repository).  ``actor`` is the §164 *who* (default ``"agent"``)
    and ``task_id`` ties the decision to a task.
    """

    kind: str
    name: str
    target: str = ""
    actor: str = "agent"
    task_id: str = ""
    detail: str = ""
    risk_hint: RiskLevel | None = None

    def __post_init__(self) -> None:
        if self.kind not in ACTION_KINDS:
            raise SecurityError(
                f"action.kind {self.kind!r} is not one of {ACTION_KINDS}"
            )
        if not self.name:
            raise SecurityError("action.name is empty — what is being admitted?")

    def as_dict(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "name": self.name,
            "target": self.target,
            "actor": self.actor,
            "task_id": self.task_id,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class GateDecision:
    """One gate's verdict — the audit record (there is no hidden
    enforcement; callers execute only what a decision allows).

    ``gate`` names the decider (``"permission"`` · ``"tool"`` ·
    ``"mcp"`` · ``"plugin"``), ``rule`` the rule that fired, ``risk``
    the classified §163 risk of the action.
    """

    action: SecurityAction
    verdict: GateVerdict
    risk: RiskLevel
    gate: str
    rule: str
    reason: str = ""
    timestamp: str = field(default_factory=utc_now_iso)

    @property
    def allowed(self) -> bool:
        return self.verdict is not GateVerdict.DENY

    @property
    def requires_confirmation(self) -> bool:
        return self.verdict is GateVerdict.CONFIRM

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": self.action.kind,
            "name": self.action.name,
            "target": self.action.target,
            "actor": self.action.actor,
            "task_id": self.action.task_id,
            "verdict": self.verdict.value,
            "risk": self.risk.value,
            "gate": self.gate,
            "rule": self.rule,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


#: Spec §160 — the credential's six fields, verbatim and in order:
#: ``ID | Provider | Scope | Reference | Created | last-used``.
CREDENTIAL_FIELDS: tuple[str, ...] = (
    "id",
    "provider",
    "scope",
    "reference",
    "created",
    "last_used",
)


@dataclass(frozen=True, slots=True)
class Credential:
    """One §160 credential — a *reference*, never the secret text.

    The reference law (Spec §160, verbatim): **الـAgent يحصل على
    reference — ليس النص السري نفسه** — the agent receives the
    reference, not the secret itself.  ``as_dict``/``repr`` surface
    only the six fields; the text lives inside the vault alone.
    """

    id: str
    provider: str
    scope: str
    reference: str
    created: str = field(default_factory=utc_now_iso)
    last_used: str = ""

    def __post_init__(self) -> None:
        if not self.id or not self.provider or not self.reference:
            raise SecretError("credential needs id, provider and reference")

    def as_dict(self) -> dict[str, str]:
        """The six §160 fields — and nothing else."""
        return {
            "id": self.id,
            "provider": self.provider,
            "scope": self.scope,
            "reference": self.reference,
            "created": self.created,
            "last_used": self.last_used,
        }

    def __repr__(self) -> str:  # noqa: RUF012 — keep the text out of reprs
        return (
            f"Credential(id={self.id!r}, provider={self.provider!r}, "
            f"reference={self.reference!r})"
        )


def redact_preview(
    mapping: Mapping[str, Any], keys: tuple[str, ...] = ("secret",)
) -> dict[str, Any]:
    """A mapping copy whose secret-ish values are replaced by their
    lengths (used by the vault's audit trail — the text never leaves)."""
    cleaned: dict[str, Any] = {}
    for key, value in mapping.items():
        if key in keys and isinstance(value, str) and value:
            cleaned[key] = f"<str len={len(value)}>"
        else:
            cleaned[key] = value
    return cleaned
