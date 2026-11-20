"""The repair loop (New Plan §20.4).

The plan's chain, verbatim and ordered::

    Fail → Diagnose → Fix → Retest → Verify

A failed criterion is not a verdict — it is the *beginning* of a proof.
The loop runs a failing check through five honest stages:

1. **fail** — the initial run failed (recorded, never hidden);
2. **diagnose** — a :class:`Diagnostician` turns the failure into a
   :class:`Diagnosis` with a stable signature;
3. **fix** — the first matching :class:`RepairStrategy` applies a real
   change and reports exactly what it did;
4. **retest** — the *same* verifier runs the *same* criterion again;
5. **verify** — only a retest that holds becomes the final PASS — and
   even then the whole repair chain rides inside the outcome as
   evidence, so a repaired PASS is never mistaken for a first-try PASS.

Nothing is invented: when no strategy matches the diagnosis the loop
stops honestly (``repaired=False``) and returns the failure with the
diagnosis attached; when attempts run out, the last honest failure is
the answer.

حلقة الإصلاح — Fail ثم Diagnose ثم Fix ثم Retest ثم Verify، حرفياً
وبالترتيب، وكل مرحلة ببرهانها.

Stdlib only.
"""

from __future__ import annotations

import gc
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .contracts import (
    REPAIR_STAGES,
    Criterion,
    Evidence,
    Result,
    ResultStatus,
    Verifier,
    utc_now_iso,
)

#: How many fail→…→retest rounds the loop may attempt (default).
DEFAULT_MAX_ATTEMPTS = 3


# ---------------------------------------------------------------- records


@dataclass(frozen=True, slots=True)
class Diagnosis:
    """One stage-2 product — what failed, why, under a stable signature.

    ``signature`` keys the repair strategies (``missing-directory``,
    ``locked-handle``, ``transient``, ``unknown``); ``detail`` carries
    the honest explanation; ``subject`` is the optional path/resource
    the strategies act on.
    """

    signature: str
    detail: str
    subject: str = ""
    stage: str = "diagnose"

    def __post_init__(self) -> None:
        if not self.signature:
            raise ValueError("diagnosis.signature is empty — name the failure class")

    def as_dict(self) -> dict[str, str]:
        return {
            "signature": self.signature,
            "detail": self.detail,
            "subject": self.subject,
            "stage": self.stage,
        }


@dataclass(frozen=True, slots=True)
class FixReport:
    """One stage-3 product — what the strategy actually changed."""

    applied: bool
    detail: str
    changed: tuple[str, ...] = ()
    stage: str = "fix"

    def __post_init__(self) -> None:
        if self.applied and not self.changed:
            raise ValueError("a fix that claims to be applied must list what it changed")

    def as_dict(self) -> dict[str, Any]:
        return {
            "applied": self.applied,
            "detail": self.detail,
            "changed": list(self.changed),
            "stage": self.stage,
        }


@dataclass(frozen=True, slots=True)
class Attempt:
    """One round of the loop — the failure, the diagnosis, the fix, the retest."""

    number: int
    failure: Result
    diagnosis: Diagnosis
    fix: FixReport | None
    retest: Result

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "failure": self.failure.as_dict(),
            "diagnosis": self.diagnosis.as_dict(),
            "fix": self.fix.as_dict() if self.fix else None,
            "retest": self.retest.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class StageTrace:
    """One §20.4 stage, recorded — name, state, an honest detail line."""

    stage: str
    state: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.stage not in REPAIR_STAGES:
            raise ValueError(
                f"stage {self.stage!r} is not one of the §20.4 stages {REPAIR_STAGES}"
            )

    def as_dict(self) -> dict[str, str]:
        return {"stage": self.stage, "state": self.state, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class RepairOutcome:
    """The loop's product — final result plus the full honest chain."""

    final: Result
    repaired: bool
    attempts: tuple[Attempt, ...] = ()
    stages: tuple[StageTrace, ...] = ()
    evidence: tuple[Evidence, ...] = ()
    started_at: str = field(default_factory=utc_now_iso)

    @property
    def passed(self) -> bool:
        return self.final.passed

    def as_dict(self) -> dict[str, Any]:
        return {
            "criterion_id": self.final.criterion_id,
            "repaired": self.repaired,
            "final_status": self.final.status.value,
            "attempts": [a.as_dict() for a in self.attempts],
            "stages": [s.as_dict() for s in self.stages],
            "evidence": [e.as_dict() for e in self.evidence],
            "started_at": self.started_at,
        }


# ----------------------------------------------------------- stage 2: who


class Diagnostician(ABC):
    """Turns a failure :class:`Result` into a :class:`Diagnosis`."""

    @abstractmethod
    def diagnose(self, result: Result, criterion: Criterion) -> Diagnosis:
        """Read the failure honestly and name its class."""


class RuleDiagnostician(Diagnostician):
    """Signature rules over the failure's message and evidence.

    The rules are ordered; the first match wins; ``unknown`` is the
    honest floor — a failure that fits no rule is still diagnosed,
    just without a repair promise.
    """

    def diagnose(self, result: Result, criterion: Criterion) -> Diagnosis:
        text = " ".join([result.message, *[e.output for e in result.evidence]])
        lowered = text.lower()
        subject = _first_path_in(text)
        if "missing-directory" in lowered or "no such or not a directory" in lowered:
            return Diagnosis("missing-directory", text[:300], subject)
        if "permission" in lowered and "denied" in lowered:
            return Diagnosis("locked-handle", text[:300], subject)
        if "winerror 32" in lowered or "being used by another process" in lowered:
            return Diagnosis("locked-handle", text[:300], subject)
        if "timeout" in lowered or "timed out" in lowered:
            return Diagnosis("transient", text[:300], subject)
        if "file not found" in lowered or "no such file" in lowered:
            return Diagnosis("missing-file", text[:300], subject)
        return Diagnosis("unknown", text[:300], subject)


# ----------------------------------------------------------- stage 3: how


class RepairStrategy(ABC):
    """One repair the loop may apply — declared by its signature."""

    signature: str

    @abstractmethod
    def repair(self, diagnosis: Diagnosis) -> FixReport:
        """Apply the repair for real and report exactly what changed."""


class CreateDirectoryStrategy(RepairStrategy):
    """``missing-directory`` — create the directory tree that is absent."""

    signature = "missing-directory"

    def repair(self, diagnosis: Diagnosis) -> FixReport:
        if not diagnosis.subject:
            return FixReport(False, "no subject path in the diagnosis — nothing to create")
        path = Path(diagnosis.subject)
        path.mkdir(parents=True, exist_ok=True)
        return FixReport(True, f"created directory tree {path}", (str(path),))


class UnlockRetryStrategy(RepairStrategy):
    """``locked-handle`` — collect Python-side handles, then wait.

    The generalised Windows lesson (WinError 32 / phase-17 / phase-19):
    an open handle keeps a file locked; ``gc.collect()`` drops the
    handles Python still owns and a short backoff lets the rest go.
    """

    signature = "locked-handle"

    def __init__(self, backoff_seconds: float = 0.2) -> None:
        self._backoff = backoff_seconds

    def repair(self, diagnosis: Diagnosis) -> FixReport:
        collected = gc.collect()
        time.sleep(self._backoff)
        return FixReport(
            True,
            f"gc collected {collected} objects · backed off {self._backoff}s",
            ("gc",),
        )


class TransientRetryStrategy(RepairStrategy):
    """``transient`` — change nothing, back off, and let the retest judge."""

    signature = "transient"

    def __init__(self, backoff_seconds: float = 0.5) -> None:
        self._backoff = backoff_seconds

    def repair(self, diagnosis: Diagnosis) -> FixReport:
        time.sleep(self._backoff)
        return FixReport(
            True, f"backed off {self._backoff}s before the retest", ("backoff",)
        )


class NoOpStrategy(RepairStrategy):
    """The honest floor for ``unknown`` — matches, changes nothing, says so."""

    signature = "unknown"

    def repair(self, diagnosis: Diagnosis) -> FixReport:
        return FixReport(False, f"no repair for {diagnosis.signature!r} — the honest stop", ())


# ---------------------------------------------------------------- the loop


class RepairLoop:
    """Fail → Diagnose → Fix → Retest → Verify — with evidence per stage."""

    def __init__(
        self,
        diagnostician: Diagnostician | None = None,
        strategies: tuple[RepairStrategy, ...] = (),
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
        store: Any = None,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._diagnostician = diagnostician or RuleDiagnostician()
        self._strategies = strategies or (
            CreateDirectoryStrategy(),
            UnlockRetryStrategy(),
            TransientRetryStrategy(),
            NoOpStrategy(),
        )
        self._max_attempts = max_attempts
        self._store = store

    # ------------------------------------------------------------------

    @property
    def stages(self) -> tuple[str, ...]:
        return REPAIR_STAGES

    def run(self, criterion: Criterion, verifier: Verifier) -> RepairOutcome:
        """Judge one criterion; repair it while the chain stays honest."""
        stages: list[StageTrace] = []
        evidence: list[Evidence] = []
        attempts: list[Attempt] = []

        first = verifier.verify(criterion)
        if first.passed:
            stages.append(
                StageTrace("verify", "ok", f"{criterion.id} passed on the first judgement")
            )
            evidence.append(
                self._record(
                    Evidence(
                        method="verify",
                        output=first.message or f"{criterion.id} passed",
                        result=ResultStatus.PASS,
                    )
                )
            )
            return RepairOutcome(
                final=first,
                repaired=False,
                attempts=(),
                stages=tuple(stages),
                evidence=tuple(evidence),
            )

        stages.append(
            StageTrace(
                "fail",
                "recorded",
                f"{criterion.id} failed: {first.message or first.status.value}",
            )
        )
        evidence.append(
            self._record(
                Evidence(
                    method="fail",
                    output=first.message or first.status.value,
                    result=ResultStatus.FAIL,
                )
            )
        )

        final = first
        for number in range(1, self._max_attempts + 1):
            diagnosis = self._diagnostician.diagnose(first if number == 1 else final, criterion)
            stages.append(
                StageTrace("diagnose", "ok", f"{diagnosis.signature}: {diagnosis.detail[:120]}")
            )
            evidence.append(
                self._record(
                    Evidence(
                        method="diagnose",
                        output=f"{diagnosis.signature}: {diagnosis.detail}",
                        result=ResultStatus.FAIL,
                    )
                )
            )

            fix: FixReport | None = None
            strategy = self._match(diagnosis)
            if strategy is not None:
                fix = strategy.repair(diagnosis)
                stages.append(
                    StageTrace("fix", "applied" if fix.applied else "refused", fix.detail)
                )
                evidence.append(
                    self._record(
                        Evidence(
                            method=f"fix:{strategy.signature}",
                            output=fix.detail,
                            result=ResultStatus.PASS if fix.applied else ResultStatus.SKIP,
                        )
                    )
                )

            retest = verifier.verify(criterion)
            attempts.append(
                Attempt(number=number, failure=final, diagnosis=diagnosis, fix=fix, retest=retest)
            )
            if retest.passed:
                stages.append(
                    StageTrace("retest", "ok", f"{criterion.id} holds after attempt {number}")
                )
                evidence.append(
                    self._record(
                        Evidence(
                            method="retest",
                            output=retest.message or f"{criterion.id} holds after attempt {number}",
                            result=ResultStatus.PASS,
                        )
                    )
                )
                stages.append(
                    StageTrace(
                        "verify", "ok",
                        f"repaired PASS for {criterion.id} (attempt {number})",
                    )
                )
                evidence.append(
                    self._record(
                        Evidence(
                            method="verify",
                            output=(
                                f"repaired after {number} attempt(s): "
                                f"{retest.message or criterion.id}"
                            ),
                            result=ResultStatus.PASS,
                        )
                    )
                )
                message = retest.message or criterion.id
                final = Result(
                    criterion_id=retest.criterion_id,
                    status=ResultStatus.PASS,
                    evidence=retest.evidence,
                    duration_seconds=retest.duration_seconds,
                    message=f"repaired after {number} attempt(s): {message}",
                )
                return RepairOutcome(
                    final=final,
                    repaired=True,
                    attempts=tuple(attempts),
                    stages=tuple(stages),
                    evidence=tuple(evidence),
                )
            stages.append(
                StageTrace(
                    "retest",
                    "failed",
                    f"attempt {number} still failing: {retest.message or 'no message'}",
                )
            )
            evidence.append(
                self._record(
                    Evidence(
                        method="retest",
                        output=retest.message or retest.status.value,
                        result=ResultStatus.FAIL,
                    )
                )
            )
            final = retest

        stages.append(
            StageTrace(
                "verify",
                "failed",
                f"{criterion.id} still failing after "
                f"{self._max_attempts} attempt(s) — the honest stop",
            )
        )
        evidence.append(
            self._record(
                Evidence(
                    method="verify",
                    output=f"still failing after {self._max_attempts} attempt(s)",
                    result=ResultStatus.FAIL,
                )
            )
        )
        return RepairOutcome(
            final=final,
            repaired=False,
            attempts=tuple(attempts),
            stages=tuple(stages),
            evidence=tuple(evidence),
        )

    # ------------------------------------------------------------------

    def _match(self, diagnosis: Diagnosis) -> RepairStrategy | None:
        for strategy in self._strategies:
            if strategy.signature == diagnosis.signature:
                return strategy
        return None

    def _record(self, evidence: Evidence) -> Evidence:
        if self._store is not None:
            return self._store.record(evidence)
        return evidence


#: Absolute-path shapes: a Windows drive path (``C:\...`` / ``C:/...``)
#: or a POSIX absolute path (``/...``).  The drive letter's colon must
#: survive extraction — destroying colons (the naive split) turns
#: ``C:\Users\...`` into a drive-less path that resolves against the
#: current drive, and a "fixed" tree lands on the wrong disk (found by
#: the real box, phase-20 device discovery 8).
_PATH_PATTERN = re.compile(
    r"[A-Za-z]:[\\/][^\s'\"|<>:*?]+"
    r"|(?:/[^\s'\"|<>:*?]+)+"
)


def _first_path_in(text: str) -> str:
    """Extract the first plausible absolute path from a message."""
    match = _PATH_PATTERN.search(text)
    if match is None:
        return ""
    candidate = match.group(0).rstrip(".,;)")
    return candidate if any(ch.isalpha() for ch in candidate) else ""


__all__ = [
    "Attempt",
    "CreateDirectoryStrategy",
    "DEFAULT_MAX_ATTEMPTS",
    "Diagnosis",
    "Diagnostician",
    "FixReport",
    "NoOpStrategy",
    "RepairLoop",
    "RepairOutcome",
    "RepairStrategy",
    "RuleDiagnostician",
    "StageTrace",
    "TransientRetryStrategy",
    "UnlockRetryStrategy",
]
