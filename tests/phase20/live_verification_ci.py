#!/usr/bin/env python3
"""The phase-20 live proof — the engine proves itself on this host.

Ten rungs, each printed ``[PASS]``/``[FAIL]`` with its evidence:

1.  §20.1 vocabulary — Verifier · Evidence · Criterion · Result, verbatim;
2.  §20.2 vocabulary — the nine domains, verbatim and ordered;
3.  §20.3 vocabulary — the five evidence fields, verbatim;
4.  §20.4 vocabulary — the five repair stages, verbatim;
5.  the engine runs all nine domains on this host — no FAIL, no ERROR;
6.  every result carries five-field evidence, every artifact re-seals;
7.  the report is persisted with its integrity digest and read back;
8.  the repair loop walks Fail → Diagnose → Fix → Retest → Verify on a
    real missing directory and lands a repaired PASS;
9.  the repair loop's evidence is sealed per stage in the store;
10. an honest SKIP is observed (Windows facts off-Windows) — SKIP is
    never a fake PASS.

The verdict (all rungs + tallies + provenance) is written to
``$NEXUS_PROOF_DIR/phase20_live.json`` when the directory exists —
``M:\\NEXUS\\proofs`` on the real box, a temp dir in CI/sandbox.

Stdlib only.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexus import __version__ as NEXUS_VERSION  # noqa: E402
from nexus import NEXUS_PHASE  # noqa: E402
from nexus.verification import (  # noqa: E402
    REPAIR_STAGES,
    VERIFICATION_DOMAINS,
    CreateDirectoryStrategy,
    Criterion,
    Evidence,
    EvidenceStore,
    RepairLoop,
    Result,
    ResultStatus,
    VerificationEngine,
)

PASSED: list[str] = []
FAILED: list[str] = []
T0 = time.time()

VERDICT_DIR = os.environ.get("NEXUS_PROOF_DIR", "")


def rung(label: str, fn) -> None:  # type: ignore[no-untyped-def]
    try:
        detail = fn()
    except Exception as exc:  # noqa: BLE001
        FAILED.append(label)
        print(f"[FAIL] {label} — {type(exc).__name__}: {exc}")
    else:
        PASSED.append(label)
        print(f"[PASS] {label}" + (f" — {detail}" if detail else ""))


# ------------------------------------------------------------------- rungs


def rung_1_framework_vocab() -> str:
    from nexus.verification import Criterion, Result, ResultStatus, Verifier

    assert Verifier.__abstractmethods__ >= {"criteria", "verify"}
    assert {s.value for s in ResultStatus} == {"PASS", "FAIL", "ERROR", "SKIP"}
    names = [f.name for f in __import__("dataclasses").fields(Evidence)]
    assert names == ["method", "output", "timestamp", "artifact", "result"]
    assert Criterion(domain="software", id="x", description="d")
    assert Result(criterion_id="x", status=ResultStatus.PASS).passed
    return "Verifier · Evidence · Criterion · Result verbatim"


def rung_2_domains_vocab() -> str:
    assert VERIFICATION_DOMAINS == (
        "software", "windows", "browser", "documents", "research",
        "git", "memory", "models", "system",
    )
    verifiers = __import__("nexus.verification", fromlist=["make_verifiers"]).make_verifiers()
    assert [v.domain for v in verifiers] == list(VERIFICATION_DOMAINS)
    return f"nine domains · nine verifiers: {', '.join(v.domain for v in verifiers)}"


def rung_3_evidence_vocab() -> str:
    ev = Evidence(method="proof:live", output="observed")
    assert [f.name for f in __import__("dataclasses").fields(ev)] == [
        "method", "output", "timestamp", "artifact", "result",
    ]
    assert ev.as_dict()["result"] == "PASS"
    return "method · output · timestamp · artifact · result"


def rung_4_repair_vocab() -> str:
    assert REPAIR_STAGES == ("fail", "diagnose", "fix", "retest", "verify")
    loop = RepairLoop()
    assert loop.stages == REPAIR_STAGES
    return "Fail → Diagnose → Fix → Retest → Verify"


def rung_5_engine_nine_domains(store: EvidenceStore):  # type: ignore[no-untyped-def]
    engine = VerificationEngine(store=store)
    report = engine.run()
    assert report.failed == 0 and report.errored == 0, (
        f"failures: {[(r.criterion_id, r.evidence[0].output) for r in report.results if not r.passed and r.status is not ResultStatus.SKIP]}"
    )
    assert report.passed >= 15, f"only {report.passed} criteria passed"
    assert report.skipped >= 1, "an honest SKIP is expected somewhere (models/browser/windows)"
    rung_5_engine_nine_domains.report = report  # type: ignore[attr-defined]
    return (
        f"overall={report.overall} pass={report.passed} skip={report.skipped} "
        f"fail={report.failed} err={report.errored}"
    )


def rung_6_evidence_on_every_result(store: EvidenceStore) -> str:
    report = rung_5_engine_nine_domains.report  # type: ignore[attr-defined]
    for result in report.results:
        assert result.evidence, f"{result.criterion_id} unproven"
        for ev in result.evidence:
            assert ev.method and ev.output and ev.timestamp
            if ev.artifact:
                envelope = store.read_back(ev.artifact)
                assert envelope["sha256"]
    assert store.count() >= report.total
    return f"{store.count()} sealed evidence artifacts"


def rung_7_report_persisted(store: EvidenceStore) -> str:
    report = rung_5_engine_nine_domains.report  # type: ignore[attr-defined]
    assert report.report_artifact == "report.json"
    doc = json.loads((store.root / "report.json").read_text(encoding="utf-8"))
    assert doc["sha256"] and doc["report"]["total"] == report.total
    assert doc["report"]["overall"] == report.overall
    return f"report sealed · overall {report.overall}"


def rung_8_repair_loop_real_chain(store: EvidenceStore) -> str:
    work = Path(tempfile.mkdtemp(prefix="nexus-p20-repair-"))
    marker = work / "repaired" / "marker.txt"

    def check() -> str:
        if not marker.is_file():
            raise AssertionError(f"missing-directory: {marker.parent} does not exist")
        return f"marker present: {marker}"

    criterion = Criterion(id="system-live-repair", domain="system", description="live marker", check=check)

    class LiveVerifier:  # a minimal Verifier over one criterion
        id = "live-verifier"
        domain = "system"

        def criteria(self):  # type: ignore[no-untyped-def]
            return (criterion,)

        def verify(self, crit: Criterion):  # type: ignore[no-untyped-def]
            import time as _t

            t0 = _t.perf_counter()
            try:
                out = str(crit.check())
                status, message = ResultStatus.PASS, ""
            except AssertionError as exc:
                status, out, message = ResultStatus.FAIL, f"failed: {exc}", str(exc)
            from nexus.verification import Result as _R

            return _R(
                criterion_id=crit.id,
                status=status,
                evidence=(Evidence(method=f"check:{crit.id}", output=out[:400], result=status),),
                duration_seconds=_t.perf_counter() - t0,
                message=message,
            )

    class CreateMarker(CreateDirectoryStrategy):
        def repair(self, diagnosis):  # type: ignore[no-untyped-def]
            base = super().repair(diagnosis)
            if base.applied and not marker.exists():
                marker.write_text("repaired by the §20.4 loop", encoding="utf-8")
            return base

    loop = RepairLoop(strategies=(CreateMarker(),), store=store)
    outcome = loop.run(criterion, LiveVerifier())  # type: ignore[arg-type]
    assert outcome.final.passed and outcome.repaired, "the loop must land a repaired PASS"
    stages = [s.stage for s in outcome.stages]
    assert stages == list(REPAIR_STAGES), f"got {stages}"
    import shutil

    shutil.rmtree(work, ignore_errors=True)
    return " → ".join(stages) + " · repaired PASS"


def rung_9_repair_evidence_sealed(store: EvidenceStore) -> str:
    # the loop's stage evidence from rung 8 was recorded in the same store
    methods = set()
    for path in (store.root / "evidence").glob("ev-*.json"):
        doc = json.loads(path.read_text(encoding="utf-8"))
        methods.add(doc["evidence"]["method"])
    for stage in ("fail", "diagnose", "retest", "verify"):
        assert stage in methods, f"stage {stage} evidence missing"
    assert any(m.startswith("fix:") for m in methods)
    return "every §20.4 stage left a sealed observation"


def rung_10_honest_skip(store: EvidenceStore) -> str:
    engine = VerificationEngine(store=store)
    report = engine.run_domain("windows")
    probe = next(r for r in report.results if r.criterion_id == "windows-platform-probe")
    if platform.system() == "Windows":
        assert probe.passed
        return "on the real box: the platform probe PASSes"
    assert probe.status is ResultStatus.SKIP
    assert "judged on the real box" in probe.evidence[0].output
    return f"off-Windows SKIP is honest: {probe.evidence[0].output[:60]}"


def main() -> int:
    print(f"PHASE 20 live proof — nexus {NEXUS_VERSION} · phase {NEXUS_PHASE} · "
          f"{platform.system()} {platform.release()} · python {sys.version.split()[0]}")
    proofs = Path(tempfile.mkdtemp(prefix="nexus-p20-proof-"))
    store = EvidenceStore(proofs)
    rung("1 §20.1 framework vocabulary", rung_1_framework_vocab)
    rung("2 §20.2 nine domains verbatim", rung_2_domains_vocab)
    rung("3 §20.3 evidence five fields", rung_3_evidence_vocab)
    rung("4 §20.4 repair stages verbatim", rung_4_repair_vocab)
    rung("5 engine over nine domains", lambda: rung_5_engine_nine_domains(store))
    rung("6 evidence on every result", lambda: rung_6_evidence_on_every_result(store))
    rung("7 report persisted + sealed", lambda: rung_7_report_persisted(store))
    rung("8 repair loop real chain", lambda: rung_8_repair_loop_real_chain(store))
    rung("9 repair evidence sealed", lambda: rung_9_repair_evidence_sealed(store))
    rung("10 honest SKIP observed", lambda: rung_10_honest_skip(store))

    total = len(PASSED) + len(FAILED)
    verdict = {
        "phase": 20,
        "section": "Verification Engine",
        "version": NEXUS_VERSION,
        "nexus_phase": NEXUS_PHASE,
        "host": f"{platform.system()}-{platform.release()}",
        "python": sys.version.split()[0],
        "rungs_total": total,
        "rungs_passed": len(PASSED),
        "rungs_failed": len(FAILED),
        "passed": PASSED,
        "failed": FAILED,
        "verdict": "PASS" if not FAILED else "FAIL",
        "duration_seconds": round(time.time() - T0, 2),
    }
    print(f"VERDICT: {verdict['verdict']} — {len(PASSED)}/{total} rungs "
          f"in {verdict['duration_seconds']}s")
    if VERDICT_DIR:
        target = Path(VERDICT_DIR)
        if target.is_dir():
            out = target / "phase20_live.json"
            out.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"verdict written: {out}")
        else:
            print(f"NEXUS_PROOF_DIR={VERDICT_DIR} is not a real directory — verdict not written")
    return 0 if not FAILED else 1


if __name__ == "__main__":
    raise SystemExit(main())
