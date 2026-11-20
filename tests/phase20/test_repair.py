"""§20.4 repair-loop tests — Fail → Diagnose → Fix → Retest → Verify."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from nexus.verification import (
    REPAIR_STAGES,
    Attempt,
    CreateDirectoryStrategy,
    Criterion,
    CriterionSkipped,
    Diagnosis,
    Diagnostician,
    Evidence,
    EvidenceStore,
    FixReport,
    NoOpStrategy,
    Result,
    ResultStatus,
    RepairLoop,
    RepairOutcome,
    RepairStrategy,
    RuleDiagnostician,
    StageTrace,
    TransientRetryStrategy,
    UnlockRetryStrategy,
    VerificationEngine,
)
from nexus.verification.domains import BaseVerifier


# ----------------------------------------------------------------- helpers


class _Scripted(BaseVerifier):
    """A verifier whose answers are scripted per call count."""

    id = "scripted-verifier"
    domain = "system"

    def __init__(self, script: list[str], store=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(store)
        self._script = script
        self.calls = 0

    def criteria(self):  # type: ignore[override]
        return (
            Criterion(id="system-scripted", domain="system", description="scripted", check=self._check),
        )

    def _check(self) -> str:
        answer = self._script[min(self.calls, len(self._script) - 1)]
        self.calls += 1
        if answer == "PASS":
            return f"holds on call {self.calls}"
        raise AssertionError(answer)


def _criterion_for(tmp: Path) -> Criterion:
    def check() -> str:
        marker = tmp / "repaired" / "marker.txt"
        if not marker.is_file():
            raise AssertionError(f"missing-directory: {marker.parent} does not exist")
        return f"marker present: {marker}"

    return Criterion(id="system-repair-marker", domain="system", description="marker file exists", check=check)


class _MarkerVerifier(BaseVerifier):
    id = "marker-verifier"
    domain = "system"

    def __init__(self, criterion: Criterion, store=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(store)
        self._criterion = criterion

    def criteria(self):  # type: ignore[override]
        return (self._criterion,)


# ------------------------------------------------------------------ stages


def test_repair_stages_vocabulary_is_the_plan() -> None:
    assert REPAIR_STAGES == ("fail", "diagnose", "fix", "retest", "verify")
    loop = RepairLoop()
    assert loop.stages == REPAIR_STAGES


def test_stage_trace_validates_stage_names() -> None:
    StageTrace("fail", "recorded")
    with pytest.raises(ValueError, match="not one of"):
        StageTrace("teleport", "ok")


def test_diagnosis_and_fixreport_laws() -> None:
    with pytest.raises(ValueError):
        Diagnosis(signature="", detail="x")
    with pytest.raises(ValueError):
        FixReport(applied=True, detail="x", changed=())  # a fix must list changes
    fix = FixReport(applied=True, detail="x", changed=("a",))
    assert fix.as_dict()["changed"] == ["a"]


def test_diagnosis_signatures_from_real_failures() -> None:
    diag = RuleDiagnostician()
    ev = Evidence(method="check:c", output="failed: missing-directory: /tmp/nope does not exist", result=ResultStatus.FAIL)
    result = Result(criterion_id="c", status=ResultStatus.FAIL, evidence=(ev,), message="missing-directory: /tmp/nope")
    d = diag.diagnose(result, _criterion_for(Path("/tmp")))
    assert d.signature == "missing-directory"
    assert "/tmp/nope" in d.subject

    ev2 = Evidence(method="check:c", output="failed: [WinError 32] being used by another process", result=ResultStatus.FAIL)
    d2 = diag.diagnose(Result(criterion_id="c", status=ResultStatus.FAIL, evidence=(ev2,)), _criterion_for(Path("/tmp")))
    assert d2.signature == "locked-handle"

    ev3 = Evidence(method="check:c", output="failed: operation timed out", result=ResultStatus.FAIL)
    d3 = diag.diagnose(Result(criterion_id="c", status=ResultStatus.FAIL, evidence=(ev3,)), _criterion_for(Path("/tmp")))
    assert d3.signature == "transient"

    ev4 = Evidence(method="check:c", output="failed: the claim did not hold", result=ResultStatus.FAIL)
    d4 = diag.diagnose(Result(criterion_id="c", status=ResultStatus.FAIL, evidence=(ev4,)), _criterion_for(Path("/tmp")))
    assert d4.signature == "unknown"


# ------------------------------------------------------------ the real loop


def test_full_repair_chain_on_a_real_missing_directory(tmp_path: Path) -> None:
    """The canonical §20.4 chain, over a real filesystem."""
    marker = tmp_path / "repaired" / "marker.txt"
    assert not marker.exists()
    criterion = _criterion_for(tmp_path)
    verifier = _MarkerVerifier(criterion)

    # the fix: creating the parent directory (the marker file itself is
    # created by the criterion's check? no — the check only reads it, so
    # a directory strategy alone is not enough. We create the marker in
    # the strategy chain via a custom strategy.)
    class CreateMarkerStrategy(RepairStrategy):
        signature = "missing-directory"

        def repair(self, diagnosis: Diagnosis) -> FixReport:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("repaired", encoding="utf-8")
            return FixReport(True, "created dir + marker", (str(marker),))

    loop = RepairLoop(strategies=(CreateMarkerStrategy(),))
    outcome = loop.run(criterion, verifier)
    assert isinstance(outcome, RepairOutcome)
    assert outcome.final.passed
    assert outcome.repaired
    assert marker.is_file()
    stages = [s.stage for s in outcome.stages]
    assert stages == list(REPAIR_STAGES), f"all five stages, in order — got {stages}"
    assert [s.stage for s in outcome.stages].index("retest") > [s.stage for s in outcome.stages].index("fix")
    assert outcome.attempts and isinstance(outcome.attempts[0], Attempt)
    assert outcome.attempts[0].fix is not None and outcome.attempts[0].fix.applied
    assert "repaired after 1 attempt" in outcome.final.message
    # the chain's evidence carries the five stage methods
    methods = [ev.method for ev in outcome.evidence]
    assert methods[0] == "fail" and methods[-1] == "verify"
    assert any(m.startswith("fix:") for m in methods)


def test_repair_with_evidence_store_seals_every_stage(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path / "proofs")
    criterion = _criterion_for(tmp_path)
    verifier = _MarkerVerifier(criterion, store=store)

    class CreateMarkerStrategy(RepairStrategy):
        signature = "missing-directory"

        def repair(self, diagnosis: Diagnosis) -> FixReport:
            marker = tmp_path / "repaired" / "marker.txt"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("repaired", encoding="utf-8")
            return FixReport(True, "created dir + marker", (str(marker),))

    loop = RepairLoop(strategies=(CreateMarkerStrategy(),), store=store)
    outcome = loop.run(criterion, verifier)
    assert outcome.final.passed
    for ev in outcome.evidence:
        assert ev.artifact, "every stage's evidence is sealed in the store"
        store.read_back(ev.artifact)
    assert store.count() >= 5


def test_first_try_pass_skips_the_loop(tmp_path: Path) -> None:
    (tmp_path / "repaired").mkdir()
    (tmp_path / "repaired" / "marker.txt").write_text("x", encoding="utf-8")
    criterion = _criterion_for(tmp_path)
    verifier = _MarkerVerifier(criterion)
    loop = RepairLoop(strategies=(CreateDirectoryStrategy(),))
    outcome = loop.run(criterion, verifier)
    assert outcome.final.passed and not outcome.repaired
    assert outcome.attempts == ()
    assert [s.stage for s in outcome.stages] == ["verify"]


def test_unrepairable_stops_honestly(tmp_path: Path) -> None:
    """No matching strategy → the loop must not fake a repair."""
    calls = {"n": 0}

    def check() -> str:
        calls["n"] += 1
        raise AssertionError(f"the claim did not hold (call {calls['n']})")

    criterion = Criterion(id="system-never", domain="system", description="d", check=check)
    verifier = _MarkerVerifier(criterion)
    loop = RepairLoop(strategies=(NoOpStrategy(),), max_attempts=3)
    outcome = loop.run(criterion, verifier)
    assert not outcome.final.passed
    assert not outcome.repaired
    assert outcome.final.status is ResultStatus.FAIL
    assert calls["n"] == 1 + loop._max_attempts, (
        "the initial judgement + max_attempts retests, then the honest stop"
    )
    assert outcome.stages[-1].state == "failed"
    assert "honest stop" in outcome.stages[-1].detail


def test_max_attempts_bounds_the_loop(tmp_path: Path) -> None:
    def check() -> str:
        raise AssertionError("missing-directory: /tmp/never exists not")

    criterion = Criterion(id="system-never2", domain="system", description="d", check=check)
    verifier = _MarkerVerifier(criterion)
    loop = RepairLoop(strategies=(NoOpStrategy(),), max_attempts=2)
    outcome = loop.run(criterion, verifier)
    assert len(outcome.attempts) == 2
    assert not outcome.repaired


def test_repair_pass_is_labelled_not_hidden(tmp_path: Path) -> None:
    """A repaired PASS says so — the evidence chain distinguishes it."""
    script = _Scripted(["FAIL", "PASS"])
    criterion = script.criteria()[0]
    diag = Diagnosis(signature="transient", detail="blip")

    class Instant(Diagnostician):
        def diagnose(self, result: Result, criterion: Criterion) -> Diagnosis:
            return diag

    loop = RepairLoop(diagnostician=Instant(), strategies=(TransientRetryStrategy(backoff_seconds=0.01),))
    outcome = loop.run(criterion, script)
    assert outcome.repaired and outcome.final.passed
    assert outcome.final.message.startswith("repaired after 1 attempt")
    assert outcome.attempts[0].diagnosis.signature == "transient"


def test_builtin_strategies_behave(tmp_path: Path) -> None:
    # CreateDirectoryStrategy really creates the tree
    target = tmp_path / "a" / "b" / "c"
    report = CreateDirectoryStrategy().repair(Diagnosis("missing-directory", "d", str(target)))
    assert report.applied and target.is_dir()
    # ...and refuses without a subject
    report = CreateDirectoryStrategy().repair(Diagnosis("missing-directory", "d", ""))
    assert not report.applied
    # UnlockRetryStrategy collects and waits without raising
    report = UnlockRetryStrategy(backoff_seconds=0.01).repair(Diagnosis("locked-handle", "d"))
    assert report.applied
    # TransientRetryStrategy changes nothing but backs off
    t0 = time.perf_counter()
    report = TransientRetryStrategy(backoff_seconds=0.05).repair(Diagnosis("transient", "d"))
    assert time.perf_counter() - t0 >= 0.04
    assert report.applied
    # NoOpStrategy is the honest floor
    report = NoOpStrategy().repair(Diagnosis("unknown", "d"))
    assert not report.applied


def test_repair_outcome_document_shape(tmp_path: Path) -> None:
    criterion = _criterion_for(tmp_path)
    verifier = _MarkerVerifier(criterion)

    class CreateMarkerStrategy(RepairStrategy):
        signature = "missing-directory"

        def repair(self, diagnosis: Diagnosis) -> FixReport:
            marker = tmp_path / "repaired" / "marker.txt"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("x", encoding="utf-8")
            return FixReport(True, "ok", (str(marker),))

    outcome = RepairLoop(strategies=(CreateMarkerStrategy(),)).run(criterion, verifier)
    doc = outcome.as_dict()
    assert doc["repaired"] is True
    assert doc["final_status"] == "PASS"
    assert [s["stage"] for s in doc["stages"]] == list(REPAIR_STAGES)
    assert doc["attempts"][0]["fix"]["applied"] is True


def test_path_extraction_preserves_the_windows_drive() -> None:
    """Device discovery 8 — a naive colon-split lands the fix on the wrong disk."""
    from nexus.verification.repair import _first_path_in

    assert _first_path_in("missing-directory: C:\\Users\\op\\repaired does not exist") == (
        "C:\\Users\\op\\repaired"
    )
    assert _first_path_in("missing-directory: C:/Users/op/repaired does not exist") == (
        "C:/Users/op/repaired"
    )
    assert _first_path_in("missing-directory: /tmp/op/repaired does not exist") == (
        "/tmp/op/repaired"
    )
    assert _first_path_in("the claim did not hold") == ""


def test_windows_style_failure_repairs_to_the_right_place(tmp_path: Path) -> None:
    """A C:\\-style diagnosis creates the tree on C:\\, not relative to CWD."""
    made = {}
    criterion = Criterion(
        id="system-win-style",
        domain="system",
        description="d",
        check=lambda: (_ for _ in ()).throw(AssertionError("missing-directory: C:\\op\\repaired does not exist")),
    )

    class RecordingStrategy(RepairStrategy):
        signature = "missing-directory"

        def repair(self, diagnosis: Diagnosis) -> FixReport:
            made["subject"] = diagnosis.subject
            return FixReport(True, "recorded", (diagnosis.subject,))

    verifier = _MarkerVerifier(criterion)
    outcome = RepairLoop(strategies=(RecordingStrategy(),), max_attempts=1).run(criterion, verifier)
    assert not outcome.repaired  # nothing really created C:\op\repaired here
    assert made["subject"] == "C:\\op\\repaired", made


def test_engine_and_repair_live_together(tmp_path: Path) -> None:
    """The engine's report and the repair loop share one honest store."""
    store = EvidenceStore(tmp_path / "proofs")
    engine = VerificationEngine(store=store)
    report = engine.run()
    scripted = _Scripted(["FAIL", "PASS"], store=store)
    outcome = RepairLoop(
        diagnostician=RuleDiagnostician(),
        strategies=(NoOpStrategy(),),
        max_attempts=1,
        store=store,
    ).run(scripted.criteria()[0], scripted)
    assert report.total >= 20
    assert not outcome.repaired or outcome.final.passed
    assert store.count() > report.total  # engine + loop evidence, all sealed
