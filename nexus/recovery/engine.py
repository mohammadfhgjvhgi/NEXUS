"""Recovery Engine — the §22.3 chain under the §22.4 law.

    Crash → Checkpoint → Actual environment → Reconciliation → Resume

The §22.4 rule, verbatim:

    No Blind Resume — لا يعتمد على الذاكرة. يفحص:
    Files · Git · Processes · Windows · Browser · Task state

Structural reading of the rule: :meth:`RecoveryEngine.reconcile`
re-probes the *actual* machine through
:class:`nexus.recovery.probes.CompositeProbe` and diffs it against
the on-disk :class:`CheckpointManifest`.  :meth:`RecoveryEngine.resume`
is the only way to obtain a ``resume`` outcome and it *raises*
:class:`NoBlindResumeError` unless the report passed all six surfaces.
Repair (when asked) re-applies the checkpoint's captured blobs, then
re-reconciles — a resume that follows repair is still a *verified*
resume, never a blind one.

Stdlib only.
"""

from __future__ import annotations

import posixpath
from pathlib import Path

from .contracts import (
    CheckpointManifest,
    CheckpointNotFoundError,
    CorruptCheckpointError,
    Drift,
    DriftKind,
    DriftSeverity,
    EnvironmentFacts,
    NoBlindResumeError,
    ReconciliationReport,
    RecoveryAction,
    RecoveryOutcome,
    RecoveryVerdict,
    VerificationSurface,
)
from .probes import CompositeProbe, inventory_files, sha256_bytes
from .store import DiskCheckpointStore


class RecoveryEngine:
    """The §22.3 walk, bounded by the §22.4 six-surface check."""

    def __init__(
        self,
        store: DiskCheckpointStore,
        repo_root: Path,
        task_state_path: Path,
        probe: CompositeProbe | None = None,
    ) -> None:
        self._store = store
        self._root = Path(repo_root)
        self._probe = probe or CompositeProbe(self._root, Path(task_state_path))
        self.probe_calls = 0

    # ------------------------------------------------------------ public

    def reconcile(self, manifest: CheckpointManifest) -> ReconciliationReport:
        """Live probe → six-surface diff → verdict.  Never memory."""
        self.probe_calls += 1
        facts = self._probe.probe()
        return self.reconcile_with_facts(manifest, facts)

    def reconcile_with_facts(
        self, manifest: CheckpointManifest, facts: EnvironmentFacts
    ) -> ReconciliationReport:
        """The pure six-surface diff — public so the §22.4 law is
        testable against any honest facts snapshot."""
        drift: list[Drift] = []

        drift.extend(self._check_files(manifest, facts))
        drift.extend(self._check_git(manifest, facts))
        drift.extend(self._check_processes(manifest, facts))
        drift.extend(self._check_windows(manifest, facts))
        drift.extend(self._check_browser(manifest, facts))
        drift.extend(self._check_task_state(manifest, facts))

        errors = [d for d in drift if d.severity is DriftSeverity.ERROR]
        verdict = RecoveryVerdict.DRIFT_DETECTED if errors else RecoveryVerdict.RESUME_READY
        bad = {d.surface for d in errors}
        matched = tuple(s for s in VerificationSurface if s not in bad)
        return ReconciliationReport(
            checkpoint_id=manifest.checkpoint_id,
            verdict=verdict,
            matched=matched,
            drift=tuple(drift),
        )

    def resume(self, report: ReconciliationReport) -> RecoveryOutcome:
        """The only door to ``resume`` — and it is a verified door.

        Raises :class:`NoBlindResumeError` when the report carries any
        error-severity drift — checked twice: the verdict AND the
        error list (a forged RESUME_READY header with drift attached
        is still refused).  There is no blind resume in this system,
        by construction.
        """
        if not report.ok() or report.errors():
            names = ", ".join(
                sorted({d.surface.value for d in report.errors()})
                or (report.verdict.value,)
            )
            raise NoBlindResumeError(
                f"§22.4 no blind resume — surfaces failed: {names}"
            )
        return RecoveryOutcome(
            checkpoint_id=report.checkpoint_id,
            report=report,
            action=RecoveryAction.RESUME,
            detail="all six §22.4 surfaces verified against a live probe",
        )

    def recover(
        self,
        checkpoint_id: str,
        *,
        repair: bool = True,
    ) -> RecoveryOutcome:
        """The full §22.3 chain from a checkpoint id.

        1. ``checkpoint`` — load the on-disk manifest (missing/corrupt
           → UNRECOVERABLE + abort).
        2. ``actual_environment`` — one live probe of the six surfaces.
        3. ``reconciliation`` — the six-surface diff.
        4. ``resume`` — only when the report is clean, or when repair
           re-applied the captured blobs and the *re*-reconciliation
           came back clean.
        """
        try:
            manifest = self._store.load(checkpoint_id)
        except (CheckpointNotFoundError, CorruptCheckpointError) as exc:
            report = ReconciliationReport(
                checkpoint_id=checkpoint_id,
                verdict=RecoveryVerdict.UNRECOVERABLE,
                drift=(
                    Drift(
                        surface=VerificationSurface.FILES,
                        kind=DriftKind.FILE_MISSING,
                        severity=DriftSeverity.ERROR,
                        detail=f"checkpoint unusable: {exc}",
                    ),
                ),
            )
            return RecoveryOutcome(
                checkpoint_id=checkpoint_id,
                report=report,
                action=RecoveryAction.ABORT,
                detail=f"§22.3 stopped at 'checkpoint': {type(exc).__name__}",
            )

        report = self.reconcile(manifest)
        if report.ok():
            return self.resume(report)

        restored = 0
        if repair:
            restored = self._restore(manifest)
            if restored:
                report = self.reconcile(manifest)
                if report.ok():
                    outcome = self.resume(report)
                    return RecoveryOutcome(
                        checkpoint_id=manifest.checkpoint_id,
                        report=outcome.report,
                        action=RecoveryAction.RESUME,
                        detail=f"resumed after repair — {restored} file(s) re-applied",
                        restored_files=restored,
                    )
                return RecoveryOutcome(
                    checkpoint_id=manifest.checkpoint_id,
                    report=report,
                    action=RecoveryAction.ABORT,
                    detail="§22.4 still failing after repair — no blind resume",
                    restored_files=restored,
                )
        names = ", ".join(sorted({d.surface.value for d in report.errors()}))
        return RecoveryOutcome(
            checkpoint_id=manifest.checkpoint_id,
            report=report,
            action=RecoveryAction.RESTART_TASK,
            detail=f"§22.4 drift on: {names} — restart from the checkpoint, never blind-resume",
        )

    # ----------------------------------------------------------- private

    def _restore(self, manifest: CheckpointManifest) -> int:
        """Re-apply captured blobs — digest-checked before writing."""
        count = 0
        for entry in manifest.files:
            try:
                data = self._store.read_blob(manifest.checkpoint_id, entry.path)
            except Exception:  # noqa: BLE001 — nothing to restore for it
                continue
            if sha256_bytes(data) != entry.sha256:
                continue  # a corrupt blob is never written
            target = self._root / posixpath.normpath(entry.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            count += 1
        return count

    def _check_files(
        self, manifest: CheckpointManifest, facts: EnvironmentFacts
    ) -> list[Drift]:
        drift: list[Drift] = []
        if not manifest.files:
            return drift
        for entry in manifest.files:
            live = facts.files.get(entry.path)
            if live is None:
                drift.append(
                    Drift(
                        VerificationSurface.FILES,
                        DriftKind.FILE_MISSING,
                        DriftSeverity.ERROR,
                        f"captured file absent: {entry.path}",
                    )
                )
            elif live != entry.sha256:
                drift.append(
                    Drift(
                        VerificationSurface.FILES,
                        DriftKind.FILE_MODIFIED,
                        DriftSeverity.ERROR,
                        f"content changed since capture: {entry.path}",
                    )
                )
        captured = {e.path for e in manifest.files}
        extra = sorted(set(facts.files) - captured)
        # extra files annotate but do not block — work may legitimately
        # have continued after the capture; the §22.4 check is that the
        # captured world still exists, not that the world froze.
        if extra[:5]:
            drift.append(
                Drift(
                    VerificationSurface.FILES,
                    DriftKind.FILE_EXTRA,
                    DriftSeverity.WARNING,
                    f"{len(extra)} new file(s), e.g. {extra[:3]}",
                )
            )
        return drift

    def _check_git(
        self, manifest: CheckpointManifest, facts: EnvironmentFacts
    ) -> list[Drift]:
        drift: list[Drift] = []
        if manifest.git_head:
            if facts.git_head != manifest.git_head:
                detail = (
                    "head moved since capture "
                    f"({manifest.git_head[:12]} → {str(facts.git_head)[:12]})"
                    if facts.git_head
                    else "checkpoint from a repository; the environment is not one now"
                )
                drift.append(
                    Drift(
                        VerificationSurface.GIT,
                        DriftKind.GIT_DIVERGED,
                        DriftSeverity.ERROR,
                        detail,
                    )
                )
            elif facts.git_dirty:
                drift.append(
                    Drift(
                        VerificationSurface.GIT,
                        DriftKind.GIT_DIRTY,
                        DriftSeverity.WARNING,
                        "worktree carries uncommitted changes",
                    )
                )
        return drift

    @staticmethod
    def _subset_drift(
        surface: VerificationSurface,
        kind_missing: DriftKind,
        expected: tuple[str, ...] | list[str],
        actual: tuple[str, ...],
        noun: str,
    ) -> list[Drift]:
        missing = sorted(set(expected) - set(actual))
        if not missing:
            return []
        return [
            Drift(
                surface,
                kind_missing,
                DriftSeverity.ERROR,
                f"{noun} gone since capture: {', '.join(missing[:5])}",
            )
        ]

    def _check_processes(
        self, manifest: CheckpointManifest, facts: EnvironmentFacts
    ) -> list[Drift]:
        expected = (manifest.state.get("environment") or {}).get("processes") or []
        return self._subset_drift(
            VerificationSurface.PROCESSES,
            DriftKind.PROCESS_DEAD,
            tuple(expected),
            facts.processes,
            "process",
        )

    def _check_windows(
        self, manifest: CheckpointManifest, facts: EnvironmentFacts
    ) -> list[Drift]:
        expected = (manifest.state.get("environment") or {}).get("windows") or []
        if not expected:
            return []  # nothing was expected — nothing can close
        return self._subset_drift(
            VerificationSurface.WINDOWS,
            DriftKind.WINDOW_CLOSED,
            tuple(expected),
            facts.windows,
            "window",
        )

    def _check_browser(
        self, manifest: CheckpointManifest, facts: EnvironmentFacts
    ) -> list[Drift]:
        expected = (manifest.state.get("environment") or {}).get("browser") or []
        if not expected:
            return []  # no browser was expected — none can vanish
        return self._subset_drift(
            VerificationSurface.BROWSER,
            DriftKind.BROWSER_CHANGED,
            tuple(expected),
            facts.browser,
            "browser",
        )

    @staticmethod
    def _check_task_state(
        manifest: CheckpointManifest, facts: EnvironmentFacts
    ) -> list[Drift]:
        captured = manifest.state.get("task_state") or {}
        if captured == {} and facts.task_state == {}:
            return []
        if captured == dict(facts.task_state):
            return []
        return [
            Drift(
                VerificationSurface.TASK_STATE,
                DriftKind.TASK_STATE_MISMATCH,
                DriftSeverity.ERROR,
                "persisted task state differs from the checkpoint's",
            )
        ]


def verify_tree(root: Path, expected: dict[str, str]) -> tuple[bool, dict[str, str]]:
    """Standalone files-surface check — the §22.4 law as a function.

    Returns (all_ok, drift_map) where drift_map holds ``path →
    missing|modified`` for every capture the live tree fails to
    reproduce.  Used by the exit gate and the device proof.
    """
    live = inventory_files(root)
    drift: dict[str, str] = {}
    for rel, digest in expected.items():
        now = live.get(rel)
        if now is None:
            drift[rel] = "missing"
        elif now != digest:
            drift[rel] = "modified"
    return (not drift, drift)
