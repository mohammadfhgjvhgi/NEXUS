"""Verification-engine contracts (New Plan §20.1–§20.4).

The plan's central claim, verbatim:

    لا يكفي أن NEXUS يعمل. يجب أن يثبت أنه يعمل.
    (It is not enough that NEXUS works. It must prove that it works.)

§20.1 — the framework's four nouns, verbatim::

    Verifier   Evidence   Criterion   Result

§20.2 — the nine verification domains, verbatim and ordered::

    Software   Windows   Browser   Documents   Research
    Git   Memory   Models   System

§20.3 — every criterion's evidence carries five fields, verbatim::

    method   output   timestamp   artifact   result

§20.4 — the repair loop, verbatim and ordered::

    Fail → Diagnose → Fix → Retest → Verify

NEXUS owns the verification semantics (Plan §61's law): every proof —
a probe of this host, a real §12 memory roundtrip, a git inspection,
an honest SKIP when a fact cannot be judged here — flows through one
contract, and every claim lands as :class:`Evidence` with a method, an
output, a timestamp, an artifact and a result.  Availability is probed,
never assumed; a criterion the host cannot judge reports SKIP honestly
and never invents a PASS — the capability-matrix law (no ✅ without
proof) applied to NEXUS itself.

عقود محرك التحقق — Verifier وEvidence وCriterion وResult حرفية،
التسع مجالات، حقول البرهان الخمسة، وحلقة الإصلاح كما في الخطة.

Stdlib only.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

# ----------------------------------------------------------------- errors


class VerificationError(Exception):
    """Verification-engine misuse or operation failure."""


class CriterionError(VerificationError):
    """A criterion is malformed — unknown domain, empty id, no check."""


class CriterionSkipped(RuntimeError):  # noqa: N818 — a skip is a signal, not an error
    """A criterion this host honestly cannot judge — never a fake PASS.

    Raised *inside* a check callable; the verifier converts it into a
    :data:`ResultStatus.SKIP` result whose evidence records the reason.
    """


# ---------------------------------------------------------------- helpers


def utc_now_iso() -> str:
    """UTC timestamp, ISO-8601 with microseconds (house format)."""
    return datetime.now(UTC).isoformat()


def check_sha256(data: bytes) -> str:
    """The artifact integrity hash (sha256 hex, house digest)."""
    import hashlib

    return hashlib.sha256(data).hexdigest()


# ------------------------------------------------------- §20.2 the domains


#: §20.2 — the nine verification domains, verbatim from the plan and in
#: its order.  Every :class:`Criterion` belongs to exactly one of these.
VERIFICATION_DOMAINS: tuple[str, ...] = (
    "software",
    "windows",
    "browser",
    "documents",
    "research",
    "git",
    "memory",
    "models",
    "system",
)


#: §20.4 — the repair loop, verbatim from the plan and in its order.
REPAIR_STAGES: tuple[str, ...] = (
    "fail",
    "diagnose",
    "fix",
    "retest",
    "verify",
)


# ------------------------------------------------------------ §20.1 nouns


class ResultStatus(StrEnum):
    """A criterion's honest outcome.

    ``PASS`` — the check ran and held.  ``FAIL`` — the check ran and
    did not hold.  ``ERROR`` — the check itself crashed (a bug or a
    broken host, never hidden as a FAIL or a SKIP).  ``SKIP`` — this
    host cannot judge the criterion at all (the honest refusal; the
    Windows facts are judged on the real Windows box, not here).
    """

    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"
    SKIP = "SKIP"


@dataclass(frozen=True, slots=True)
class Evidence:
    """One §20.3 observation — the plan's five fields, verbatim.

    ``method`` documents *how* the observation was made (a probe name,
    a ``check:<criterion>`` run, a ``diagnose``/``fix``/``retest``
    stage).  ``output`` is the raw observation (repr, digest, a real
    command's stdout).  ``timestamp`` is the UTC ISO-8601 moment.
    ``artifact`` is the persisted artifact holding this evidence (its
    EvidenceStore path, empty until recorded).  ``result`` is the
    outcome this evidence carries — the same vocabulary as
    :class:`ResultStatus`.
    """

    method: str
    output: str
    timestamp: str = field(default_factory=utc_now_iso)
    artifact: str = ""
    result: ResultStatus = ResultStatus.PASS

    def __post_init__(self) -> None:
        if not self.method:
            raise VerificationError("evidence.method is empty — how it was observed must be named")
        if self.result is not ResultStatus.PASS and not isinstance(self.result, ResultStatus):
            raise VerificationError(
                f"evidence.result must be a ResultStatus, got {type(self.result).__name__}"
            )

    def as_dict(self) -> dict[str, str]:
        return {
            "method": self.method,
            "output": self.output,
            "timestamp": self.timestamp,
            "artifact": self.artifact,
            "result": self.result.value,
        }


@dataclass(frozen=True, slots=True)
class Criterion:
    """One §20.1 claim to be proven — a domain, a description, a check.

    ``check`` is the executable that decides: returning normally means
    the criterion holds; raising :class:`CriterionSkipped` means this
    host honestly cannot judge it; raising anything else means it does
    not hold (or is broken — the verifier separates FAIL from ERROR).
    """

    id: str
    domain: str
    description: str
    check: Callable[[], Any] | None = None

    def __post_init__(self) -> None:
        if not self.id:
            raise CriterionError("criterion.id is empty")
        if self.domain not in VERIFICATION_DOMAINS:
            raise CriterionError(
                f"criterion.domain {self.domain!r} is not one of the "
                f"§20.2 domains {VERIFICATION_DOMAINS}"
            )
        if not self.description:
            raise CriterionError(f"criterion {self.id} has no description")

    def as_dict(self) -> dict[str, str]:
        return {
            "id": self.id,
            "domain": self.domain,
            "description": self.description,
            "check": "callable" if callable(self.check) else "none",
        }


@dataclass(frozen=True, slots=True)
class Result:
    """A criterion's verdict — status, duration, and its evidence chain.

    ``evidence`` is the tuple of :class:`Evidence` observations backing
    this verdict — at least one for every real run (the law: no claim
    without its five-field proof).
    """

    criterion_id: str
    status: ResultStatus
    evidence: tuple[Evidence, ...] = ()
    duration_seconds: float = 0.0
    message: str = ""

    def __post_init__(self) -> None:
        if not self.criterion_id:
            raise VerificationError("result.criterion_id is empty")
        if not isinstance(self.status, ResultStatus):
            raise VerificationError(
                f"result.status must be a ResultStatus, got {type(self.status).__name__}"
            )

    @property
    def passed(self) -> bool:
        return self.status is ResultStatus.PASS

    def as_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.criterion_id,
            "status": self.status.value,
            "evidence": [ev.as_dict() for ev in self.evidence],
            "duration_seconds": round(self.duration_seconds, 6),
            "message": self.message,
        }


class Verifier(ABC):
    """One §20.1 verifier — owns one domain's criteria and judges them.

    ``id`` is a stable name (reports, capability matrix) and ``domain``
    must be one of the §20.2 domains.  ``criteria()`` declares what
    this verifier proves; ``verify()`` runs one criterion honestly —
    PASS / FAIL / ERROR from the check itself, SKIP only through
    :class:`CriterionSkipped`.
    """

    id: str
    domain: str

    @abstractmethod
    def criteria(self) -> tuple[Criterion, ...]:
        """The criteria this verifier can judge — declared, not assumed."""

    @abstractmethod
    def verify(self, criterion: Criterion) -> Result:
        """One criterion → an honest Result with its evidence chain."""

    def verify_all(self) -> tuple[Result, ...]:
        """Every declared criterion, in declaration order."""
        return tuple(self.verify(criterion) for criterion in self.criteria())

    def describe(self) -> dict[str, Any]:
        """Capability-matrix rows — proven facts only, no invented ✅."""
        return {
            "id": self.id,
            "domain": self.domain,
            "criteria": [c.as_dict() for c in self.criteria()],
        }
