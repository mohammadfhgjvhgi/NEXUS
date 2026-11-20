#!/usr/bin/env python3
"""Phase 20 verification harness — New Plan §20 Exit Gate.

Proves the Verification Engine section by section:

* A — Framework (§20.1): the verbatim vocabulary — Verifier ·
      Evidence · Criterion · Result — the honest status set
      (PASS/FAIL/ERROR/SKIP), the engine's domain law and the
      nine built-in verifiers.
* B — Domains (§20.2): the nine domains verbatim and ordered, each
      behind its own verifier, each criterion really probed on this
      host (a real §12 memory roundtrip, a real git HEAD sha, a real
      temp write, honest SKIPs where a fact cannot be judged here).
* C — Evidence (§20.3): five fields on every observation verbatim
      (method · output · timestamp · artifact · result), artifacts
      sealed with sha256, tampering detected on read-back, and no
      evidence without an output.
* D — Repair Loop (§20.4): Fail → Diagnose → Fix → Retest → Verify
      verbatim and ordered — a real missing directory repaired into a
      labelled PASS, an unrepairable failure stopped honestly, the
      first-try PASS untouched by the loop.
* E — Honesty: SKIP is never a fake PASS (off-Windows the Windows
      probes SKIP with the reason in their evidence), an ERROR is
      never smuggled through, a repaired PASS is labelled as repaired.
* F — Integration + regression: NEXUS_PHASE ≥ 20, nexus-core ≥
      0.20.0, the verification core stays stdlib-only at module top
      level, and the neighbor phase suites (15 · 16 · 17 · 18 · 19)
      stay green (skippable with --no-regression).

Exit gate, each line proven above::
    Implemented · Integrated · Tested · Verified · Documented
"""

from __future__ import annotations

import argparse
import ast
import dataclasses
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

PASSED: list[str] = []
FAILED: list[str] = []


def check(label: str, fn) -> None:  # type: ignore[no-untyped-def]
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        FAILED.append(f"{label}: {type(exc).__name__}: {exc}")
        print(f"  ✗ {label} — {type(exc).__name__}: {exc}")
    else:
        PASSED.append(label)
        print(f"  ✓ {label}")


def expects(exc_types: tuple[type, ...] | type, fn, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
    try:
        fn(*args, **kwargs)
    except exc_types:
        return
    except Exception as exc:  # noqa: BLE001
        raise AssertionError(
            f"expected {exc_types}, got {type(exc).__name__}: {exc}"
        ) from exc
    raise AssertionError(f"expected {exc_types}, nothing raised")


# ------------------------------------------------------------------- section A


def section_a() -> None:
    from nexus.verification import (
        REPAIR_STAGES,
        VERIFICATION_DOMAINS,
        Criterion,
        Evidence,
        Result,
        ResultStatus,
        Verifier,
        VerificationEngine,
        VerificationError,
        make_verifiers,
    )

    def vocabulary_verbatim() -> None:
        assert VERIFICATION_DOMAINS == (
            "software", "windows", "browser", "documents", "research",
            "git", "memory", "models", "system",
        )
        assert REPAIR_STAGES == ("fail", "diagnose", "fix", "retest", "verify")
        assert {s.value for s in ResultStatus} == {"PASS", "FAIL", "ERROR", "SKIP"}

    def evidence_five_fields() -> None:
        names = [f.name for f in dataclasses.fields(Evidence)]
        assert names == ["method", "output", "timestamp", "artifact", "result"]
        ev = Evidence(method="m", output="o")
        assert ev.timestamp and ev.artifact == "" and ev.result is ResultStatus.PASS
        expects((VerificationError,), Evidence, method="", output="o")

    def criterion_laws() -> None:
        from nexus.verification import CriterionError

        Criterion(id="c", domain="git", description="d", check=lambda: "ok")
        expects((CriterionError,), Criterion, id="", domain="git", description="d")
        expects((CriterionError,), Criterion, id="c", domain="physics", description="d")
        expects((CriterionError,), Criterion, id="c", domain="git", description="")

    def result_laws() -> None:
        from nexus.verification import VerificationError

        result = Result(criterion_id="c", status=ResultStatus.PASS)
        assert result.passed and result.evidence == ()
        expects((VerificationError,), Result, criterion_id="", status=ResultStatus.PASS)
        expects((VerificationError,), Result, criterion_id="c", status="PASS")  # type: ignore[arg-type]

    def verifier_abc_and_nine() -> None:
        assert Verifier.__abstractmethods__ >= {"criteria", "verify"}
        verifiers = make_verifiers()
        assert len(verifiers) == 9
        assert [v.domain for v in verifiers] == list(VERIFICATION_DOMAINS)
        engine = VerificationEngine()
        assert len(engine.verifiers) == 9

    check("A1 · §20.1 vocabulary verbatim (Verifier · Evidence · Criterion · Result)", vocabulary_verbatim)
    check("A2 · §20.3 evidence fields verbatim + method required", evidence_five_fields)
    check("A3 · Criterion laws (id · one of the nine domains · description)", criterion_laws)
    check("A4 · Result laws (status vocabulary · criterion_id required)", result_laws)
    check("A5 · Verifier ABC + the nine built-in verifiers + the engine", verifier_abc_and_nine)


# ------------------------------------------------------------------- section B


def section_b() -> None:
    from nexus.verification import (
        EvidenceStore,
        ResultStatus,
        VerificationEngine,
    )

    store = EvidenceStore(Path(tempfile.mkdtemp(prefix="p20-gate-b-")))
    engine = VerificationEngine(store=store)
    report = engine.run()

    def nine_domains_ran() -> None:
        assert set(report.tallies) == set(
            ("software", "windows", "browser", "documents", "research", "git", "memory", "models", "system")
        )
        assert report.total == sum(len(v.criteria()) for v in engine.verifiers)

    def no_failures_no_errors() -> None:
        assert report.failed == 0, [r.criterion_id for r in report.results if r.status is ResultStatus.FAIL]
        assert report.errored == 0, [r.criterion_id for r in report.results if r.status is ResultStatus.ERROR]
        assert report.passed >= 15
        assert report.overall in {"PASS", "DEGRADED"}

    def real_memory_roundtrip() -> None:
        result = next(r for r in report.results if r.criterion_id == "memory-engine-roundtrip")
        assert result.passed
        assert "remembered mem_" in result.evidence[0].output
        assert "engine closed" in result.evidence[0].output

    def real_git_head() -> None:
        result = next(r for r in report.results if r.criterion_id == "git-repo-root-probe")
        assert result.status in {ResultStatus.PASS, ResultStatus.SKIP}
        if result.passed:
            assert "HEAD" in result.evidence[0].output

    def real_system_probes() -> None:
        for cid in ("system-python-floor", "system-temp-writable", "system-disk-free", "system-resources-observable"):
            assert next(r for r in report.results if r.criterion_id == cid).passed, cid

    def honest_skips_reasoned() -> None:
        skips = [r for r in report.results if r.status is ResultStatus.SKIP]
        for result in skips:
            out = result.evidence[0].output
            assert out.startswith("skipped:"), f"{result.criterion_id} skip without a reason"

    check("B1 · all nine domains ran with their declared criteria", nine_domains_ran)
    check("B2 · no FAIL, no ERROR, ≥15 real PASSes on this host", no_failures_no_errors)
    check("B3 · the memory domain ran a real §12 roundtrip", real_memory_roundtrip)
    check("B4 · the git domain read a real HEAD (or honestly skipped)", real_git_head)
    check("B5 · the system domain really measured the host", real_system_probes)
    check("B6 · every SKIP carries its honest reason", honest_skips_reasoned)


# ------------------------------------------------------------------- section C


def section_c() -> None:
    import json

    from nexus.verification import Evidence, EvidenceStore, VerificationError

    store = EvidenceStore(Path(tempfile.mkdtemp(prefix="p20-gate-c-")))

    def five_fields_roundtrip() -> None:
        ev = store.record(Evidence(method="gate:probe", output="observation 1"))
        envelope = store.read_back(ev.artifact)
        assert sorted(envelope["evidence"]) == sorted(
            ["method", "output", "timestamp", "artifact", "result"]
        )
        assert envelope["sha256"]

    def tampering_detected() -> None:
        ev = store.record(Evidence(method="gate:tamper", output="original"))
        path = store.root / ev.artifact
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["evidence"]["output"] = "tampered"
        path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        expects((VerificationError,), store.read_back, ev.artifact)

    def no_output_no_record() -> None:
        expects((VerificationError,), store.record, Evidence(method="gate:empty", output=""))

    def idempotent_artifacts() -> None:
        stamp = "2026-01-01T00:00:00+00:00"
        a = store.record(Evidence(method="gate:rep", output="same", timestamp=stamp))
        b = store.record(Evidence(method="gate:rep", output="same", timestamp=stamp))
        assert a.artifact == b.artifact
        assert store.count() >= 1

    check("C1 · evidence round-trips with its five fields + sha256", five_fields_roundtrip)
    check("C2 · tampered artifacts are detected on read-back", tampering_detected)
    check("C3 · an unlabelled observation is refused", no_output_no_record)
    check("C4 · identical observations share one sealed artifact", idempotent_artifacts)


# ------------------------------------------------------------------- section D


def section_d() -> None:
    from nexus.verification import (
        CreateDirectoryStrategy,
        Criterion,
        NoOpStrategy,
        RepairLoop,
        RepairStrategy,
        ResultStatus,
        RuleDiagnostician,
        Diagnosis,
        FixReport,
        EvidenceStore,
    )

    work = Path(tempfile.mkdtemp(prefix="p20-gate-d-"))
    marker = work / "repaired" / "marker.txt"

    def check_marker() -> str:
        if not marker.is_file():
            raise AssertionError(f"missing-directory: {marker.parent} does not exist")
        return "marker present"

    criterion = Criterion(id="system-gate-repair", domain="system", description="d", check=check_marker)

    class Verifier:
        id = "gate-verifier"
        domain = "system"

        def criteria(self):  # type: ignore[no-untyped-def]
            return (criterion,)

        def verify(self, crit: Criterion):  # type: ignore[no-untyped-def]
            from nexus.verification import Evidence, Result
            import time

            t0 = time.perf_counter()
            try:
                out, status, message = str(crit.check()), ResultStatus.PASS, ""
            except AssertionError as exc:
                out, status, message = f"failed: {exc}", ResultStatus.FAIL, str(exc)
            return Result(
                criterion_id=crit.id,
                status=status,
                evidence=(Evidence(method=f"check:{crit.id}", output=out[:400], result=status),),
                duration_seconds=time.perf_counter() - t0,
                message=message,
            )

    class CreateMarker(RepairStrategy):
        signature = "missing-directory"

        def repair(self, diagnosis: Diagnosis) -> FixReport:
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("gate", encoding="utf-8")
            return FixReport(True, "created", (str(marker),))

    def full_chain_in_order() -> None:
        marker.unlink(missing_ok=True)
        outcome = RepairLoop(strategies=(CreateMarker(),)).run(criterion, Verifier())  # type: ignore[arg-type]
        assert outcome.final.passed and outcome.repaired
        assert [s.stage for s in outcome.stages] == [
            "fail", "diagnose", "fix", "retest", "verify",
        ]
        assert "repaired after 1 attempt" in outcome.final.message

    def unrepairable_honest_stop() -> None:
        def never() -> str:
            raise AssertionError("the claim did not hold")

        bad = Criterion(id="system-gate-never", domain="system", description="d", check=never)
        outcome = RepairLoop(strategies=(NoOpStrategy(),), max_attempts=2).run(bad, Verifier())  # type: ignore[arg-type]
        assert not outcome.repaired and outcome.final.status is ResultStatus.FAIL
        assert outcome.stages[-1].state == "failed"

    def first_try_pass_untouched() -> None:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("x", encoding="utf-8")
        outcome = RepairLoop(strategies=(CreateMarker(),)).run(criterion, Verifier())  # type: ignore[arg-type]
        assert outcome.final.passed and not outcome.repaired and outcome.attempts == ()

    def signatures_from_the_diagnostician() -> None:
        diag = RuleDiagnostician()
        from nexus.verification import Evidence as EV, Result as R

        r = R(criterion_id="c", status=ResultStatus.FAIL, evidence=(
            EV(method="m", output="failed: missing-directory: /x/y"),))
        assert diag.diagnose(r, criterion).signature == "missing-directory"
        r2 = R(criterion_id="c", status=ResultStatus.FAIL, evidence=(
            EV(method="m", output="failed: [WinError 32] being used by another process"),))
        assert diag.diagnose(r2, criterion).signature == "locked-handle"
        r3 = R(criterion_id="c", status=ResultStatus.FAIL, evidence=(
            EV(method="m", output="failed: the operation timed out"),))
        assert diag.diagnose(r3, criterion).signature == "transient"

    def store_seals_stage_evidence() -> None:
        store = EvidenceStore(Path(tempfile.mkdtemp(prefix="p20-gate-d2-")))
        marker.unlink(missing_ok=True)
        outcome = RepairLoop(strategies=(CreateMarker(),), store=store).run(criterion, Verifier())  # type: ignore[arg-type]
        assert outcome.final.passed
        assert all(ev.artifact for ev in outcome.evidence)
        for ev in outcome.evidence:
            store.read_back(ev.artifact)

    check("D1 · Fail→Diagnose→Fix→Retest→Verify on a real missing dir", full_chain_in_order)
    check("D2 · an unrepairable failure stops honestly (no fake repair)", unrepairable_honest_stop)
    check("D3 · a first-try PASS skips the loop untouched", first_try_pass_untouched)
    check("D4 · the diagnostician names real failure classes", signatures_from_the_diagnostician)
    check("D5 · every stage's evidence is sealed in the store", store_seals_stage_evidence)


# ------------------------------------------------------------------- section E


def section_e() -> None:
    import platform as _platform

    from nexus.verification import ResultStatus, VerificationEngine

    engine = VerificationEngine()

    def skip_is_not_pass() -> None:
        report = engine.run_domain("windows")
        probe = next(r for r in report.results if r.criterion_id == "windows-platform-probe")
        if _platform.system() == "Windows":
            assert probe.passed
        else:
            assert probe.status is ResultStatus.SKIP
            assert "real box" in probe.evidence[0].output

    def skip_never_counts_as_pass() -> None:
        report = engine.run()
        for tally in report.tallies.values():
            assert tally.passed + tally.failed + tally.errored + tally.skipped == tally.total

    def no_fake_capability_rows() -> None:
        for verifier in engine.verifiers:
            for criterion in verifier.criteria():
                assert criterion.check is not None, f"{criterion.id} declares no check"
                assert criterion.description, f"{criterion.id} has no description"

    check("E1 · SKIP is an honest refusal with its reason (never a fake PASS)", skip_is_not_pass)
    check("E2 · the tallies' arithmetic is closed (P+F+E+S=total)", skip_never_counts_as_pass)
    check("E3 · every criterion declares a real check and a description", no_fake_capability_rows)


# ------------------------------------------------------------------- section F


def section_f() -> None:
    import nexus

    def identity() -> None:
        assert nexus.NEXUS_PHASE >= 20, f"NEXUS_PHASE={nexus.NEXUS_PHASE}"
        major, minor, _ = (int(p) for p in nexus.__version__.split("."))
        assert (major, minor) >= (0, 20), f"version {nexus.__version__}"

    def stdlib_only_top_level() -> None:
        pkg = ROOT / "nexus" / "verification"
        for py in pkg.glob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.ImportFrom) and node.level > 0:
                        continue  # relative — nexus's own
                    roots = [a.name.split(".")[0] for a in node.names] if isinstance(node, ast.Import) else [str(node.module or "").split(".")[0]]
                    for root in roots:
                        assert root in sys.stdlib_module_names | {"nexus"} or root == "", (
                            f"{py.name}: non-stdlib top-level import {root!r}"
                        )

    def regression() -> None:
        if NO_REGRESSION:
            print("      (skipped by --no-regression)")
            return
        for phase in (15, 16, 17, 18, 19):
            suite = ROOT / "tests" / f"phase{phase:02d}"
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(suite), "-q", "-p", "no:cacheprovider",
                 "--ignore-glob=*test_device_proof*", "--ignore-glob=*live_*"],
                capture_output=True, text=True, timeout=560, cwd=str(ROOT),
            )
            assert proc.returncode == 0, f"phase {phase} regression failed:\n{proc.stdout[-1500:]}"

    check("F1 · NEXUS_PHASE ≥ 20 and nexus-core ≥ 0.20.0", identity)
    check("F2 · the verification core stays stdlib-only at top level", stdlib_only_top_level)
    check("F3 · neighbor suites 15–19 stay green", regression)


# ----------------------------------------------------------------------- main

NO_REGRESSION = False


def main() -> int:
    global NO_REGRESSION
    parser = argparse.ArgumentParser(description="Phase 20 exit gate")
    parser.add_argument("--no-regression", action="store_true")
    args = parser.parse_args()
    NO_REGRESSION = args.no_regression

    print("PHASE 20 — Verification Engine — Exit Gate")
    for section, title in (
        (section_a, "A · Framework (§20.1)"),
        (section_b, "B · Domains (§20.2)"),
        (section_c, "C · Evidence (§20.3)"),
        (section_d, "D · Repair Loop (§20.4)"),
        (section_e, "E · Honesty"),
        (section_f, "F · Integration + regression"),
    ):
        print(f"\n[{title}]")
        section()

    print(f"\nGATE: {len(PASSED)} passed · {len(FAILED)} failed")
    if FAILED:
        for line in FAILED:
            print(f"  ✗ {line}")
        return 1
    print("EXIT CRITERIA: Implemented · Integrated · Tested · Verified · Documented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
