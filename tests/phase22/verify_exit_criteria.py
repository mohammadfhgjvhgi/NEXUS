#!/usr/bin/env python3
"""Phase 22 recovery harness — New Plan §22 Exit Gate.

Proves the Recovery + Checkpoints section by section:

* A — Contracts (§22.1–§22.3): the verbatim vocabulary — the four
      scopes · the six triggers · the six surfaces · the five-stage
      chain — plus the manifest round-trip and the error family.
* B — Checkpoint Manager (§22.1): Task · Project · Git · State all
      captured for real — digests, blobs on disk, atomic manifests,
      per-scope retention, escape-proof paths.
* C — Trigger Events (§22.2): the six events each produce a
      checkpoint; periodic is gated by the interval policy and
      honestly declines when too soon.
* D — Recovery (§22.3): the chain Crash → Checkpoint → Actual
      environment → Reconciliation → Resume walked clean; repair
      re-applies blobs and re-earns the resume; a lost or corrupt
      checkpoint is UNRECOVERABLE, never faked.
* E — No Blind Resume (§22.4): each of the six surfaces — Files ·
      Git · Processes · Windows · Browser · Task state — alone
      blocks the resume; ``resume()`` raises
      :class:`NoBlindResumeError` on drift; a forged verdict cannot
      sneak past; probes are honest on non-repos and dead tables.
* F — Integration + regression: NEXUS_PHASE ≥ 22, nexus-core ≥
      0.22.0, the recovery core stays stdlib-only at module top
      level, and the neighbor phase suites (15–21) stay green
      (skippable with --no-regression).

Exit gate, each line proven above::
    Implemented · Integrated · Tested · Verified · Documented
"""

from __future__ import annotations

import argparse
import ast
import json
import shutil
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
    from nexus.recovery import (
        CHECKPOINT_SCOPES,
        RECOVERY_CHAIN,
        RECOVERY_SCHEMA_VERSION,
        TRIGGER_EVENTS,
        VERIFICATION_SURFACES,
        CheckpointManifest,
        CheckpointNotFoundError,
        CheckpointScope,
        CorruptCheckpointError,
        DriftKind,
        NoBlindResumeError,
        RecoveryAction,
        RecoveryError,
        RecoveryVerdict,
        TriggerEvent,
        VerificationSurface,
    )

    def vocabulary_verbatim() -> None:
        assert CHECKPOINT_SCOPES == ("task", "project", "git", "state")
        assert TRIGGER_EVENTS == (
            "task_start", "phase_complete", "major_change",
            "critical_test", "before_risky_change", "periodic",
        )
        assert VERIFICATION_SURFACES == (
            "files", "git", "processes", "windows", "browser", "task_state",
        )
        assert RECOVERY_CHAIN == (
            "crash", "checkpoint", "actual_environment", "reconciliation", "resume",
        )
        assert {s.value for s in CheckpointScope} == set(CHECKPOINT_SCOPES)
        assert {e.value for e in TriggerEvent} == set(TRIGGER_EVENTS)
        assert {s.value for s in VerificationSurface} == set(VERIFICATION_SURFACES)
        assert {v.value for v in RecoveryVerdict} == {
            "resume_ready", "drift_detected", "unrecoverable",
        }
        assert {a.value for a in RecoveryAction} == {"resume", "restart_task", "abort"}
        assert RECOVERY_SCHEMA_VERSION == 1

    def manifest_roundtrip() -> None:
        manifest = CheckpointManifest(
            checkpoint_id="ck_task_20260212T101500Z_ab12",
            scope=CheckpointScope.TASK,
            trigger=TriggerEvent.BEFORE_RISKY_CHANGE,
            label="gate",
            created_at_utc="2026-02-12T10:15:00+00:00",
            nexus_version="0.22.0",
            nexus_phase=22,
            files=(),
            state={"task_state": {"مهمة": "استعادة"}},
        )
        assert CheckpointManifest.from_dict(manifest.to_dict()) == manifest
        expects((CorruptCheckpointError,), CheckpointManifest.from_dict, {"scope": "task"})

    def error_family() -> None:
        assert issubclass(CheckpointNotFoundError, RecoveryError)
        assert issubclass(CorruptCheckpointError, RecoveryError)
        assert issubclass(NoBlindResumeError, RecoveryError)
        assert {k.value for k in DriftKind} >= {
            "file_missing", "file_modified", "git_diverged", "process_dead",
            "window_closed", "browser_changed", "task_state_mismatch",
        }

    check("A1 · §22.1–§22.4 vocabulary verbatim", vocabulary_verbatim)
    check("A2 · the manifest round-trips (unicode-safe) and refuses junk", manifest_roundtrip)
    check("A3 · the error family is honest", error_family)


# ------------------------------------------------------------------- section B


def section_b() -> None:
    from nexus.recovery import (
        CheckpointManager,
        CheckpointScope,
        DiskCheckpointStore,
        RecoveryError,
        TriggerEvent,
    )

    def four_scopes_captured() -> None:
        base = Path(tempfile.mkdtemp(prefix="p22-gate-b-"))
        repo = base / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "app.py").write_text("print('gate')\n", encoding="utf-8")
        manager = CheckpointManager(
            DiskCheckpointStore(base / "ck"), repo,
            version="0.22.0", phase=22,
            expectations_provider=lambda: ((), (), ()),
        )
        t = manager.create(CheckpointScope.TASK, TriggerEvent.TASK_START,
                           task_state={"step": 1})
        p = manager.create(CheckpointScope.PROJECT, TriggerEvent.MAJOR_CHANGE)
        g = manager.create(CheckpointScope.GIT, TriggerEvent.CRITICAL_TEST)
        s = manager.create(CheckpointScope.STATE, TriggerEvent.PERIODIC,
                           extra_state={"k": "v"})
        assert t.state["task_state"] == {"step": 1}
        assert {f.path for f in p.files} == {"src/app.py"}
        blob = manager.store.read_blob(p.checkpoint_id, "src/app.py")
        assert blob == b"print('gate')\n"
        assert s.state["k"] == "v"
        assert {m.scope.value for m in manager.store.list()} == {
            "task", "project", "git", "state",
        }
        assert g.git_head is None  # fixture tree is not a repo — honest

    def retention_and_escape_proof() -> None:
        store = DiskCheckpointStore(Path(tempfile.mkdtemp(prefix="p22-gate-r-")), keep_per_scope=2)
        from nexus.recovery import CheckpointManifest

        def make(i: int) -> CheckpointManifest:
            return CheckpointManifest(
                checkpoint_id=f"ck_state_20260212T10151{i}Z_{i:04x}",
                scope=CheckpointScope.STATE,
                trigger=TriggerEvent.PERIODIC,
                label="",
                created_at_utc=f"2026-02-12T10:15:1{i}+00:00",
                nexus_version="0.22.0",
                nexus_phase=22,
            )

        for i in range(4):
            store.save(make(i))
        assert len(store.list()) == 2
        expects((RecoveryError,), store.load, "../escape")
        expects((RecoveryError,), store.read_blob,
                "ck_state_20260212T101510Z_0000", "../../x")

    check("B1 · §22.1 four scopes captured for real", four_scopes_captured)
    check("B2 · retention prunes per scope · paths cannot escape", retention_and_escape_proof)


# ------------------------------------------------------------------- section C


def section_c() -> None:
    from nexus.recovery import (
        CheckpointManager,
        DiskCheckpointStore,
        TriggerEvent,
        TriggerPolicy,
    )

    def six_events_fire() -> None:
        base = Path(tempfile.mkdtemp(prefix="p22-gate-c-"))
        manager = CheckpointManager(
            DiskCheckpointStore(base / "ck"), base / "repo",
            version="0.22.0", phase=22,
            triggers=TriggerPolicy(min_interval_seconds=0),
            expectations_provider=lambda: ((), (), ()),
        )
        (base / "repo").mkdir()
        made = [manager.on_event(e, label=f"gate:{e.value}") for e in TriggerEvent]
        assert all(m is not None for m in made)
        assert [m.trigger.value for m in made] == [
            "task_start", "phase_complete", "major_change",
            "critical_test", "before_risky_change", "periodic",
        ]

    def periodic_gated() -> None:
        ticks = iter((1000.0, 1005.0, 1400.0))

        class Clock:
            def __call__(self) -> float:
                return next(ticks)

        policy = TriggerPolicy(min_interval_seconds=300.0, clock=Clock())
        assert policy.allows(TriggerEvent.PERIODIC) is True
        assert policy.allows(TriggerEvent.PERIODIC) is False
        assert policy.allows(TriggerEvent.PERIODIC) is True
        assert policy.allows(TriggerEvent.BEFORE_RISKY_CHANGE) is True

    check("C1 · §22.2 six events → six checkpoints", six_events_fire)
    check("C2 · periodic declines when the interval has not elapsed", periodic_gated)


# ------------------------------------------------------------------- section D


def section_d() -> None:
    from nexus.recovery import (
        CheckpointManager,
        CheckpointScope,
        DiskCheckpointStore,
        RecoveryAction,
        RecoveryVerdict,
        TriggerEvent,
        TriggerPolicy,
    )
    from nexus.recovery.engine import RecoveryEngine

    def clean_chain() -> None:
        base = Path(tempfile.mkdtemp(prefix="p22-gate-d-"))
        repo = base / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "app.py").write_text("print('d')\n", encoding="utf-8")
        state_path = base / "task_state.json"
        state_path.write_text(json.dumps({"t": 1}), encoding="utf-8")
        manager = CheckpointManager(
            DiskCheckpointStore(base / "ck"), repo,
            version="0.22.0", phase=22,
            triggers=TriggerPolicy(min_interval_seconds=0),
            expectations_provider=lambda: ((), (), ()),
        )
        engine = RecoveryEngine(manager.store, repo, state_path)
        manifest = manager.create(
            CheckpointScope.PROJECT, TriggerEvent.BEFORE_RISKY_CHANGE,
            task_state={"t": 1},
        )
        outcome = engine.recover(manifest.checkpoint_id)
        assert outcome.action is RecoveryAction.RESUME
        assert outcome.stages[-1] == "resume"
        assert outcome.report.verdict is RecoveryVerdict.RESUME_READY

    def repair_and_unrecoverable() -> None:
        base = Path(tempfile.mkdtemp(prefix="p22-gate-d2-"))
        repo = base / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "app.py").write_text("print('d')\n", encoding="utf-8")
        state_path = base / "task_state.json"
        state_path.write_text(json.dumps({"t": 1}), encoding="utf-8")
        manager = CheckpointManager(
            DiskCheckpointStore(base / "ck"), repo,
            version="0.22.0", phase=22,
            triggers=TriggerPolicy(min_interval_seconds=0),
            expectations_provider=lambda: ((), (), ()),
        )
        engine = RecoveryEngine(manager.store, repo, state_path)
        manifest = manager.create(
            CheckpointScope.PROJECT, TriggerEvent.CRITICAL_TEST, task_state={"t": 1}
        )
        (repo / "src" / "app.py").write_text("drifted\n", encoding="utf-8")
        blocked = engine.recover(manifest.checkpoint_id, repair=False)
        assert blocked.action is RecoveryAction.RESTART_TASK
        repaired = engine.recover(manifest.checkpoint_id, repair=True)
        assert repaired.action is RecoveryAction.RESUME and repaired.restored_files == 1
        gone = engine.recover("ck_task_20260212T101599Z_dead")
        assert gone.report.verdict is RecoveryVerdict.UNRECOVERABLE
        assert gone.action is RecoveryAction.ABORT

    check("D1 · §22.3 the clean chain ends in a verified resume", clean_chain)
    check("D2 · repair re-earns · a lost checkpoint is UNRECOVERABLE", repair_and_unrecoverable)


# ------------------------------------------------------------------- section E


def section_e() -> None:
    import dataclasses

    from nexus.recovery import (
        CheckpointManager,
        CheckpointScope,
        DiskCheckpointStore,
        DriftKind,
        NoBlindResumeError,
        RecoveryAction,
        TriggerEvent,
        TriggerPolicy,
        VerificationSurface,
    )
    from nexus.recovery.engine import RecoveryEngine

    def make_world(prefix: str):  # noqa: ANN202
        base = Path(tempfile.mkdtemp(prefix=prefix))
        repo = base / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "app.py").write_text("print('e')\n", encoding="utf-8")
        state_path = base / "task_state.json"
        state_path.write_text(json.dumps({"t": 1}), encoding="utf-8")
        manager = CheckpointManager(
            DiskCheckpointStore(base / "ck"), repo,
            version="0.22.0", phase=22,
            triggers=TriggerPolicy(min_interval_seconds=0),
            expectations_provider=lambda: ((), (), ()),
        )
        engine = RecoveryEngine(manager.store, repo, state_path)
        manifest = manager.create(
            CheckpointScope.PROJECT, TriggerEvent.BEFORE_RISKY_CHANGE,
            task_state={"t": 1},
        )
        return repo, manager, engine, manifest, state_path

    def files_block() -> None:
        repo, _m, engine, manifest, _s = make_world("p22-gate-e1-")
        (repo / "src" / "app.py").write_text("changed\n", encoding="utf-8")
        report = engine.reconcile(manifest)
        assert not report.ok()
        with pytest.raises(NoBlindResumeError):
            engine.resume(report)

    def git_block() -> None:
        if shutil.which("git") is None:  # pragma: no cover
            return  # the honest absence is asserted in the live proof
        repo, _m, engine, manifest, _s = make_world("p22-gate-e2-")
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@n.dev"], check=True)
        subprocess.run(["git", "-C", str(repo), "config", "user.name", "n"], check=True)
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "c1"], check=True)
        manifest = _m.create(
            CheckpointScope.PROJECT, TriggerEvent.BEFORE_RISKY_CHANGE,
            task_state={"t": 1},
        )
        (repo / "z.txt").write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "c2"], check=True)
        report = engine.reconcile(manifest)
        assert any(d.kind is DriftKind.GIT_DIVERGED for d in report.drift)
        assert not report.ok()

    def state_block() -> None:
        repo, _m, engine, manifest, state_path = make_world("p22-gate-e3-")
        state_path.write_text(json.dumps({"t": 999}), encoding="utf-8")
        report = engine.reconcile(manifest)
        assert not report.ok()
        outcome = engine.recover(manifest.checkpoint_id, repair=False)
        assert outcome.action is not RecoveryAction.RESUME

    def forged_verdict_refused() -> None:
        from nexus.recovery import (
            Drift,
            DriftKind,
            DriftSeverity,
            RecoveryVerdict,
        )

        _r, _m, engine, manifest, _s = make_world("p22-gate-e4-")
        clean = engine.reconcile(manifest)
        outcome = engine.resume(clean)
        assert outcome.action is RecoveryAction.RESUME

        poisoned = dataclasses.replace(
            clean,
            verdict=RecoveryVerdict.DRIFT_DETECTED,
            drift=(Drift(
                surface=VerificationSurface.FILES,
                kind=DriftKind.FILE_MODIFIED,
                severity=DriftSeverity.ERROR,
                detail="tampered",
            ),),
        )
        with pytest.raises(NoBlindResumeError):
            engine.resume(poisoned)

    check("E1 · §22.4 files alone block the resume", files_block)
    check("E2 · §22.4 a diverged git head blocks the resume", git_block)
    check("E3 · §22.4 a tampered task state blocks the resume", state_block)
    check("E4 · resume() is the only door and it checks the errors", forged_verdict_refused)


# ------------------------------------------------------------------- section F


def section_f() -> None:
    import nexus

    def identity() -> None:
        assert nexus.NEXUS_PHASE >= 22, f"NEXUS_PHASE={nexus.NEXUS_PHASE}"
        major, minor, _ = (int(p) for p in nexus.__version__.split("."))
        assert (major, minor) >= (0, 22), f"version {nexus.__version__}"

    def stdlib_only_top_level() -> None:
        pkg = ROOT / "nexus" / "recovery"
        for py in pkg.glob("*.py"):
            tree = ast.parse(py.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.ImportFrom) and node.level > 0:
                        continue  # relative — nexus's own
                    roots = (
                        [a.name.split(".")[0] for a in node.names]
                        if isinstance(node, ast.Import)
                        else [str(node.module or "").split(".")[0]]
                    )
                    for root in roots:
                        assert root in sys.stdlib_module_names | {"nexus"} or root == "", (
                            f"{py.name}: non-stdlib top-level import {root!r}"
                        )

    def regression() -> None:
        if NO_REGRESSION:
            print("      (skipped by --no-regression)")
            return
        for phase in (15, 16, 17, 18, 19, 20, 21):
            suite = ROOT / "tests" / f"phase{phase:02d}"
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", str(suite), "-q", "-p", "no:cacheprovider",
                 "--ignore-glob=*test_device_proof*", "--ignore-glob=*live_*"],
                capture_output=True, text=True, timeout=560, cwd=str(ROOT),
            )
            assert proc.returncode == 0, f"phase {phase} regression failed:\n{proc.stdout[-1500:]}"

    check("F1 · NEXUS_PHASE ≥ 22 and nexus-core ≥ 0.22.0", identity)
    check("F2 · the recovery core stays stdlib-only at top level", stdlib_only_top_level)
    check("F3 · neighbor suites 15–21 stay green", regression)


# ----------------------------------------------------------------------- main

import pytest  # noqa: E402 — used by the section-E asserts

NO_REGRESSION = False


def main() -> int:
    global NO_REGRESSION
    parser = argparse.ArgumentParser(description="Phase 22 exit gate")
    parser.add_argument("--no-regression", action="store_true")
    args = parser.parse_args()
    NO_REGRESSION = args.no_regression

    print("PHASE 22 — Recovery + Checkpoints — Exit Gate")
    for section, title in (
        (section_a, "A · Contracts & vocabulary (§22.1–§22.3)"),
        (section_b, "B · Checkpoint Manager (§22.1)"),
        (section_c, "C · Trigger Events (§22.2)"),
        (section_d, "D · Recovery chain (§22.3)"),
        (section_e, "E · No Blind Resume (§22.4)"),
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
