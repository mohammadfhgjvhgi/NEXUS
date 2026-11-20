"""The verification engine (New Plan §20.1/§20.2).

Runs the nine §20.2 verifiers against the host and produces one
:class:`VerificationReport` — per-domain tallies, an honest overall
status, and every criterion's §20.3 evidence persisted as artifacts.

The overall status law:

* **PASS** — no FAIL, no ERROR, and at least one criterion really
  passed on this host;
* **DEGRADED** — nothing failed, but parts of the truth live elsewhere
  (the Windows facts SKIP here and are judged on the real box);
* **FAIL** — any criterion failed or any probe errored.  ERROR is never
  smuggled through as SKIP: a broken probe is a broken probe.

المحرك — يشغّل التسع مجالات، يجمع الأرقام، ويصدر حكماً صادقاً كاملاً
بتقريره وبرهانه المحفوظ.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import (
    VERIFICATION_DOMAINS,
    Result,
    ResultStatus,
    VerificationError,
    Verifier,
    utc_now_iso,
)
from .domains import make_verifiers
from .evidence import EvidenceStore

#: The report's honest overall statuses.
OVERALL_PASS = "PASS"
OVERALL_DEGRADED = "DEGRADED"
OVERALL_FAIL = "FAIL"


@dataclass(slots=True)
class DomainTally:
    """One domain's honest arithmetic (mutable while the engine counts)."""

    domain: str
    passed: int = 0
    failed: int = 0
    errored: int = 0
    skipped: int = 0

    @property
    def total(self) -> int:
        return self.passed + self.failed + self.errored + self.skipped

    def as_dict(self) -> dict[str, str | int]:
        return {
            "domain": self.domain,
            "passed": self.passed,
            "failed": self.failed,
            "errored": self.errored,
            "skipped": self.skipped,
            "total": self.total,
        }


@dataclass(frozen=True, slots=True)
class VerificationReport:
    """One engine run — results per domain, tallies, overall verdict."""

    results: tuple[Result, ...]
    tallies: dict[str, DomainTally] = field(default_factory=dict)
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str = ""
    report_artifact: str = ""

    # -------------------------------------------------------- arithmetic

    @property
    def passed(self) -> int:
        return sum(t.passed for t in self.tallies.values())

    @property
    def failed(self) -> int:
        return sum(t.failed for t in self.tallies.values())

    @property
    def errored(self) -> int:
        return sum(t.errored for t in self.tallies.values())

    @property
    def skipped(self) -> int:
        return sum(t.skipped for t in self.tallies.values())

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def overall(self) -> str:
        if self.failed or self.errored:
            return OVERALL_FAIL
        if self.passed == 0:
            return OVERALL_FAIL  # nothing proven — no PASS, no verdict
        if self.skipped:
            return OVERALL_DEGRADED
        return OVERALL_PASS

    def for_domain(self, domain: str) -> tuple[Result, ...]:
        if domain not in VERIFICATION_DOMAINS:
            raise VerificationError(f"{domain!r} is not one of the §20.2 domains")
        return tuple(r for r in self.results if r.criterion_id.startswith(f"{domain}-"))

    # ---------------------------------------------------------- document

    def as_dict(self) -> dict[str, Any]:
        return {
            "overall": self.overall,
            "tallies": {d: t.as_dict() for d, t in self.tallies.items()},
            "passed": self.passed,
            "failed": self.failed,
            "errored": self.errored,
            "skipped": self.skipped,
            "total": self.total,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "report_artifact": self.report_artifact,
            "results": [r.as_dict() for r in self.results],
        }


class VerificationEngine:
    """Runs the nine §20.2 verifiers and one honest report out."""

    def __init__(
        self,
        store: EvidenceStore | None = None,
        verifiers: tuple[Verifier, ...] | None = None,
    ) -> None:
        self._store = store
        self._verifiers = verifiers if verifiers is not None else make_verifiers(store)
        seen: set[str] = set()
        for verifier in self._verifiers:
            if verifier.domain not in VERIFICATION_DOMAINS:
                raise VerificationError(
                    f"verifier {verifier.id!r} claims domain "
                    f"{verifier.domain!r} — not a §20.2 domain"
                )
            if verifier.domain in seen:
                raise VerificationError(f"two verifiers claim the {verifier.domain!r} domain")
            seen.add(verifier.domain)

    # ------------------------------------------------------------------

    @property
    def verifiers(self) -> tuple[Verifier, ...]:
        return self._verifiers

    def run(self, domains: tuple[str, ...] | None = None) -> VerificationReport:
        """Verify all (or the selected) domains; every proof persisted."""
        wanted = set(domains) if domains is not None else set(VERIFICATION_DOMAINS)
        unknown = wanted - set(VERIFICATION_DOMAINS)
        if unknown:
            raise VerificationError(f"unknown domains: {sorted(unknown)}")
        results: list[Result] = []
        tallies: dict[str, DomainTally] = {}
        started = utc_now_iso()
        for verifier in self._verifiers:
            if verifier.domain not in wanted:
                continue
            tally = DomainTally(domain=verifier.domain)
            for criterion in verifier.criteria():
                result = verifier.verify(criterion)
                results.append(result)
                if result.status is ResultStatus.PASS:
                    tally.passed += 1
                elif result.status is ResultStatus.FAIL:
                    tally.failed += 1
                elif result.status is ResultStatus.ERROR:
                    tally.errored += 1
                else:
                    tally.skipped += 1
            tallies[verifier.domain] = tally
        report = VerificationReport(
            results=tuple(results),
            tallies=tallies,
            started_at=started,
            finished_at=utc_now_iso(),
        )
        if self._store is not None:
            artifact = self._store.persist_report(report.as_dict(), name="report.json")
            report = _with_artifact(report, artifact)
        return report

    def run_domain(self, domain: str) -> VerificationReport:
        """One domain only — the focused probe."""
        return self.run(domains=(domain,))


def _with_artifact(report: VerificationReport, artifact: str) -> VerificationReport:
    """Rebuild the frozen report with its persisted artifact recorded."""
    return VerificationReport(
        results=report.results,
        tallies=report.tallies,
        started_at=report.started_at,
        finished_at=report.finished_at,
        report_artifact=artifact,
    )


__all__ = [
    "DomainTally",
    "OVERALL_DEGRADED",
    "OVERALL_FAIL",
    "OVERALL_PASS",
    "VerificationEngine",
    "VerificationReport",
]
