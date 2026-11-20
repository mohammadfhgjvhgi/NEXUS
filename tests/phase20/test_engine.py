"""Engine tests — one run, one report, honest arithmetic, sealed proofs."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nexus.verification import (
    Criterion,
    Evidence,
    EvidenceStore,
    Result,
    ResultStatus,
    VerificationEngine,
    VerificationError,
    make_verifiers,
)
from nexus.verification.domains import BaseVerifier


class _Static(BaseVerifier):
    id = "static-verifier"
    domain = "system"

    def __init__(self, outcomes: dict[str, str], store=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(store)
        self._outcomes = outcomes

    def criteria(self):  # type: ignore[override]
        def make(expected: str):  # type: ignore[no-untyped-def]
            def check() -> str:
                if expected == "PASS":
                    return "holds"
                if expected == "SKIP":
                    from nexus.verification import CriterionSkipped

                    raise CriterionSkipped("not judgeable here")
                raise AssertionError(expected)

            return check

        return tuple(
            Criterion(id=f"system-static-{name.lower()}", domain="system", description="d", check=make(status))
            for name, status in self._outcomes.items()
        )


def test_full_run_report_and_tallies(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "proofs")
    engine = VerificationEngine(store=store)
    report = engine.run()
    assert set(report.tallies.keys()) == {v.domain for v in engine.verifiers}
    assert report.passed + report.failed + report.errored + report.skipped == report.total
    assert report.overall in {"PASS", "DEGRADED", "FAIL"}
    # every evidence artifact exists and reads back with its sha intact
    for result in report.results:
        for ev in result.evidence:
            if ev.artifact:
                store.read_back(ev.artifact)
    # the report itself is persisted
    doc = json.loads((store.root / "report.json").read_text(encoding="utf-8"))
    assert doc["report"]["overall"] == report.overall
    assert report.report_artifact == "report.json"


def test_overall_status_law(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "p")
    # all-pass → PASS
    engine = VerificationEngine(store=store, verifiers=(_Static({"A": "PASS"}),))
    assert engine.run().overall == "PASS"
    # a skip among passes → DEGRADED
    engine = VerificationEngine(store=store, verifiers=(_Static({"A": "PASS", "B": "SKIP"}),))
    assert engine.run().overall == "DEGRADED"
    # any FAIL → FAIL
    engine = VerificationEngine(store=store, verifiers=(_Static({"A": "PASS", "B": "FAIL"}),))
    assert engine.run().overall == "FAIL"
    # an ERROR is a FAIL — never smuggled through
    engine = VerificationEngine(store=store, verifiers=(_Static({"A": "PASS", "B": "ERROR"}),))
    assert engine.run().overall == "FAIL"
    # nothing passed → FAIL (no PASS, no verdict)
    engine = VerificationEngine(store=store, verifiers=(_Static({"A": "SKIP"}),))
    assert engine.run().overall == "FAIL"


def test_run_domain_focus_and_rejection(tmp_path: Path) -> None:
    engine = VerificationEngine()
    focused = engine.run_domain("system")
    assert all(r.criterion_id.startswith("system-") for r in focused.results)
    assert set(focused.tallies.keys()) == {"system"}
    with pytest.raises(VerificationError):
        engine.run(domains=("physics",))


def test_results_are_isolated_per_criterion(tmp_path: Path) -> None:
    """One criterion's failure must not silence its neighbours."""
    engine = VerificationEngine(store=EvidenceStore(tmp_path / "p"), verifiers=(_Static({
        "Good": "PASS",
        "Bad": "FAIL",
    }),))
    report = engine.run()
    by_id = {r.criterion_id: r for r in report.results}
    assert by_id["system-static-good"].passed
    assert by_id["system-static-bad"].status is ResultStatus.FAIL


def test_report_dict_roundtrip(tmp_path: Path) -> None:
    engine = VerificationEngine()
    doc = engine.run().as_dict()
    assert doc["total"] == len(doc["results"])
    for entry in doc["results"]:
        assert entry["status"] in {"PASS", "FAIL", "ERROR", "SKIP"}
        assert entry["evidence"], "every result in the report carries evidence"
