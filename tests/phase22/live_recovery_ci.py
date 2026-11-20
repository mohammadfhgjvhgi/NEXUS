#!/usr/bin/env python3
"""PHASE 22 live recovery proof — real checkpoints on a real tree, real
probes, real drift, and a resume that is only ever *verified*.

Ten rungs, each printed as [PASS]/[FAIL] with its observation (the §20
evidence law applied to §22):

  1. §22 vocabulary verbatim — four scopes · six triggers · six
     surfaces · the five-stage chain.
  2. §22.1 — a real PROJECT checkpoint over a real tree: manifest,
     file digests, blobs on disk.
  3. §22.1 — the four scopes captured (Task · Project · Git · State)
     and listed back from disk, latest() right.
  4. §22.2 — six trigger events → six checkpoints; periodic gated by
     the interval policy (suppressed when too soon).
  5. §22.3 — the chain walked clean: crash → checkpoint → actual
     environment → reconciliation → resume (all six surfaces).
  6. §22.4 FILES — a real edit on disk blocks the resume; repair
     re-applies the blobs and the re-reconciled resume passes.
  7. §22.4 GIT — a newer commit diverges the head; the wall holds
     (never resume), honest note when the host has no git.
  8. §22.4 PROCESSES — a REAL companion process is started, captured
     from the real process table, killed → process_dead blocks the
     resume; WINDOWS/BROWSER proven on the same engine law.
  9. §22.4 TASK STATE — a tampered task-state document blocks the
     resume; restored state re-earns it; resume() refuses drift.
 10. Identity — NEXUS_PHASE ≥ 22 and nexus-core ≥ 0.22.0.

Run (CI/sandbox):  python tests/phase22/live_recovery_ci.py
Run (device, via pytest): tests/phase22/test_device_proof.py
"""

from __future__ import annotations

import dataclasses
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from nexus.recovery import (  # noqa: E402
    CHECKPOINT_SCOPES,
    RECOVERY_CHAIN,
    TRIGGER_EVENTS,
    VERIFICATION_SURFACES,
    CheckpointManager,
    CheckpointScope,
    DiskCheckpointStore,
    DriftKind,
    GitProbe,
    NoBlindResumeError,
    ProcessProbe,
    RecoveryAction,
    TriggerEvent,
    TriggerPolicy,
    VerificationSurface,
)
from nexus.recovery.engine import RecoveryEngine  # noqa: E402

RESULTS: list[tuple[str, str, str]] = []


def rung(label: str, fn) -> None:  # type: ignore[no-untyped-def]
    try:
        note = fn()
        RESULTS.append(("PASS", label, note or ""))
        print(f"[PASS] {label}" + (f" — {note}" if note else ""))
    except Exception as exc:  # noqa: BLE001
        RESULTS.append(("FAIL", label, f"{type(exc).__name__}: {exc}"))
        print(f"[FAIL] {label} — {type(exc).__name__}: {exc}")


# ------------------------------------------------------------------ helpers


class _HarnessProbe:
    """The real probes over the *repo* tree — a rung may override one
    surface to stage an engine-level scenario; otherwise everything
    measured is the actual machine."""

    def __init__(self, repo: Path, state_path: Path) -> None:
        self._repo = repo
        self._state_path = state_path
        self.override: dict = {}

    def probe(self):  # noqa: ANN202
        from nexus.recovery import CompositeProbe

        facts = CompositeProbe(self._repo, self._state_path).probe()
        if self.override:
            return dataclasses.replace(facts, **self.override)
        return facts


def _world(tag: str, live_expectations: bool = False, min_interval: float = 0.0):
    """A temp world: repo tree + checkpoint store + engine.

    ``live_expectations`` — the manager captures the REAL process
    table / windows instead of an empty baseline (used by the
    process-death rung).  ``min_interval`` — the periodic trigger's
    gate width (a positive value gates back-to-back periodics).
    """
    base = Path(tempfile.mkdtemp(prefix=f"p22-{tag}-"))
    repo = base / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "app.py").write_text("print('nexus-22')\n", encoding="utf-8")
    (repo / "README.md").write_text("recovery fixture\n", encoding="utf-8")
    state_path = base / "task_state.json"
    state_path.write_text(
        json.dumps({"task": "T-22", "state": "RUNNING"}), encoding="utf-8"
    )
    if live_expectations:
        def expectations():  # noqa: ANN202
            from nexus.recovery import WindowProbe, browser_markers

            procs = ProcessProbe().probe()
            wins = WindowProbe().probe()
            return procs, wins, browser_markers(procs)
    else:
        def expectations():  # noqa: ANN202
            return (), (), ()

    store = DiskCheckpointStore(base / "checkpoints")
    manager = CheckpointManager(
        store, repo, version="0.22.0", phase=22,
        triggers=TriggerPolicy(min_interval_seconds=min_interval),
        expectations_provider=expectations,
    )
    engine = RecoveryEngine(
        store, repo, state_path, probe=_HarnessProbe(repo, state_path)
    )
    return base, repo, manager, engine, state_path


def _sentinel() -> tuple[list[str], str]:
    """A long-lived, real, harmless process for the process-death rung."""
    if sys.platform == "win32":  # pragma: no cover — device dialect
        return ["ping", "-n", "60", "127.0.0.1"], "ping.exe"
    return ["sleep", "60"], "sleep"


# ------------------------------------------------------------------- rungs


def rung_1_vocabulary() -> str:
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
    return "scopes 4 · triggers 6 · surfaces 6 · chain 5 — verbatim"


def rung_2_project_checkpoint() -> str:
    import hashlib

    base, repo, manager, engine, _ = _world("cap")
    manifest = manager.create(
        CheckpointScope.PROJECT, TriggerEvent.MAJOR_CHANGE, label="live capture"
    )
    assert {f.path for f in manifest.files} == {"README.md", "src/app.py"}
    blob = manager.store.read_blob(manifest.checkpoint_id, "src/app.py")
    entry = next(f for f in manifest.files if f.path == "src/app.py")
    assert hashlib.sha256(blob).hexdigest() == entry.sha256
    on_disk = manager.store.root / manifest.checkpoint_id / "manifest.json"
    assert on_disk.is_file()
    assert manifest.created_at_utc in on_disk.read_text(encoding="utf-8")
    return f"{manifest.checkpoint_id} · 2 files digested · manifest on disk"


def rung_3_four_scopes() -> str:
    base, repo, manager, engine, state_path = _world("scopes")
    t = manager.create(CheckpointScope.TASK, TriggerEvent.TASK_START,
                       task_state={"task": "T-22", "state": "RUNNING"})
    manager.create(CheckpointScope.PROJECT, TriggerEvent.MAJOR_CHANGE)
    manager.create(CheckpointScope.GIT, TriggerEvent.CRITICAL_TEST)
    s = manager.create(CheckpointScope.STATE, TriggerEvent.PERIODIC,
                       extra_state={"engine": {"cursor": 7}})
    scopes_seen = {m.scope.value for m in manager.store.list()}
    assert scopes_seen == set(CHECKPOINT_SCOPES), scopes_seen
    assert manager.store.latest("task").checkpoint_id == t.checkpoint_id
    assert s.state["engine"] == {"cursor": 7}
    assert t.state["task_state"] == {"task": "T-22", "state": "RUNNING"}
    return "task · project · git · state — all listed from disk"


def rung_4_six_triggers() -> str:
    base, repo, manager, engine, state_path = _world("trig", min_interval=300.0)
    made = []
    for event in TriggerEvent:
        made.append(manager.on_event(event, label=f"evt:{event.value}"))
    assert all(m is not None for m in made)
    assert [m.trigger.value for m in made] == list(TRIGGER_EVENTS)
    assert manager.on_event(TriggerEvent.PERIODIC) is None  # too soon
    return "6 events → 6 checkpoints · periodic gated honestly"


def rung_5_clean_chain() -> str:
    base, repo, manager, engine, state_path = _world("chain")
    manifest = manager.create(
        CheckpointScope.PROJECT, TriggerEvent.BEFORE_RISKY_CHANGE,
        task_state={"task": "T-22", "state": "RUNNING"},
    )
    outcome = engine.recover(manifest.checkpoint_id)
    assert outcome.action is RecoveryAction.RESUME, outcome.as_dict()
    assert outcome.stages == RECOVERY_CHAIN
    assert set(outcome.report.matched) == set(VerificationSurface)
    return " → ".join(outcome.stages)


def rung_6_files_drift_and_repair() -> str:
    base, repo, manager, engine, state_path = _world("files")
    manifest = manager.create(
        CheckpointScope.PROJECT, TriggerEvent.BEFORE_RISKY_CHANGE,
        task_state={"task": "T-22", "state": "RUNNING"},
    )
    (repo / "src" / "app.py").write_text("print('edited after capture')\n", encoding="utf-8")
    blocked = engine.recover(manifest.checkpoint_id, repair=False)
    assert blocked.action is not RecoveryAction.RESUME
    assert any(d.kind is DriftKind.FILE_MODIFIED for d in blocked.report.drift)
    repaired = engine.recover(manifest.checkpoint_id, repair=True)
    assert repaired.action is RecoveryAction.RESUME and repaired.restored_files >= 1
    assert "nexus-22" in (repo / "src" / "app.py").read_text(encoding="utf-8")
    return f"edit blocked the resume · repair re-applied {repaired.restored_files} file(s)"


def rung_7_git_drift() -> str:
    base, repo, manager, engine, state_path = _world("git")
    if shutil.which("git") is None:
        head, _b, _d, _notes = GitProbe(repo).probe()
        assert head is None  # honest: no git → no invented head
        return "git absent on this host — the honest not-a-repo note is the proof"

    def _git(*args: str) -> None:
        subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

    _git("init", "-q")
    _git("config", "user.email", "nexus@local")
    _git("config", "user.name", "nexus")
    _git("add", ".")
    _git("commit", "-q", "-m", "captured")
    manifest = manager.create(
        CheckpointScope.PROJECT, TriggerEvent.BEFORE_RISKY_CHANGE,
        task_state={"task": "T-22", "state": "RUNNING"},
    )
    assert manifest.git_head, "capture inside a repo must see the head"
    (repo / "later.txt").write_text("diverging commit\n", encoding="utf-8")
    _git("add", ".")
    _git("commit", "-q", "-m", "diverged")
    blocked = engine.recover(manifest.checkpoint_id, repair=True)
    assert blocked.action is not RecoveryAction.RESUME
    assert any(d.kind is DriftKind.GIT_DIVERGED for d in blocked.report.drift)
    return f"head {manifest.git_head[:12]}… diverged — the wall held"


def rung_8_process_death_is_real() -> str:
    argv, sentinel = _sentinel()
    companion = subprocess.Popen(
        argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    manifest = None
    try:
        base, repo, manager, engine, state_path = _world(
            "procs", live_expectations=True
        )
        deadline = time.time() + 10
        while time.time() < deadline:
            manifest = manager.create(
                CheckpointScope.TASK, TriggerEvent.TASK_START,
                task_state={"task": "T-22", "state": "RUNNING"},
            )
            captured = manifest.state["environment"]["processes"]
            if sentinel in captured:
                break
            manifest = None
            time.sleep(0.4)
        assert manifest is not None, f"{sentinel!r} never appeared in the real process table"
        # keep only the process expectation in play — windows churn on
        # real desktops and this rung's subject is the process surface
        env = dict(manifest.state["environment"])
        env["windows"] = []
        env["browser"] = []
        manifest = dataclasses.replace(
            manifest, state={**manifest.state, "environment": env}
        )
        manager.store.save(manifest)

        alive = engine.recover(manifest.checkpoint_id, repair=False)
        assert alive.action is RecoveryAction.RESUME, alive.as_dict()
    finally:
        companion.kill()
        companion.wait(timeout=15)
    time.sleep(0.2)
    blocked = engine.recover(manifest.checkpoint_id, repair=False)
    assert blocked.action is not RecoveryAction.RESUME
    assert any(d.kind is DriftKind.PROCESS_DEAD for d in blocked.report.drift)
    return f"real {sentinel} captured alive → killed → process_dead blocks"


def rung_9_task_state_tamper() -> str:
    base, repo, manager, engine, state_path = _world("state")
    manifest = manager.create(
        CheckpointScope.TASK, TriggerEvent.TASK_START,
        task_state={"task": "T-22", "state": "RUNNING"},
    )
    state_path.write_text(
        json.dumps({"task": "T-22", "state": "CRASHED"}), encoding="utf-8"
    )
    blocked = engine.recover(manifest.checkpoint_id, repair=False)
    assert blocked.action is not RecoveryAction.RESUME
    assert any(d.kind is DriftKind.TASK_STATE_MISMATCH for d in blocked.report.drift)
    state_path.write_text(
        json.dumps({"task": "T-22", "state": "RUNNING"}), encoding="utf-8"
    )
    ok = engine.recover(manifest.checkpoint_id, repair=False)
    assert ok.action is RecoveryAction.RESUME
    state_path.write_text("{}", encoding="utf-8")
    drifted = engine.reconcile(manifest)
    try:
        engine.resume(drifted)
    except NoBlindResumeError:
        return "tamper blocked · restore re-earned · resume() refuses drift"
    raise AssertionError("resume() accepted a drifting report")


def rung_10_identity() -> str:
    import nexus

    assert nexus.NEXUS_PHASE >= 22, f"NEXUS_PHASE={nexus.NEXUS_PHASE}"
    major, minor, _ = (int(p) for p in nexus.__version__.split("."))
    assert (major, minor) >= (0, 22), f"version {nexus.__version__}"
    return f"nexus {nexus.__version__} · NEXUS_PHASE={nexus.NEXUS_PHASE}"


# --------------------------------------------------------------------- main


def main() -> int:
    print("PHASE 22 — Recovery + Checkpoints — live proof")
    rung("1 · §22 vocabulary verbatim", rung_1_vocabulary)
    rung("2 · §22.1 real PROJECT checkpoint (digests + blobs)",
         rung_2_project_checkpoint)
    rung("3 · §22.1 four scopes captured and listed from disk", rung_3_four_scopes)
    rung("4 · §22.2 six triggers, periodic gated", rung_4_six_triggers)
    rung("5 · §22.3 the clean chain ends in a verified resume", rung_5_clean_chain)
    rung("6 · §22.4 files: edit blocks, repair re-earns the resume", rung_6_files_drift_and_repair)
    rung("7 · §22.4 git: a diverged head holds the wall", rung_7_git_drift)
    rung("8 · §22.4 a real process death blocks the resume", rung_8_process_death_is_real)
    rung("9 · §22.4 task state: tamper blocked, restore re-earns", rung_9_task_state_tamper)
    rung("10 · identity ≥ 0.22.0 / phase ≥ 22", rung_10_identity)

    passed = sum(1 for status, _, _ in RESULTS if status == "PASS")
    print(f"\nPROOF: {passed}/{len(RESULTS)} rungs passed")
    for status, label, note in RESULTS:
        if status == "FAIL":
            print(f"  ✗ {label}: {note}")
    return 0 if passed == len(RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
