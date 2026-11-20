"""Resume (PHASE 25 §25.6) — continue the long run, never blindly.

The §22.4 law rides again: **no blind resume.**  The successor process
knows nothing the disk does not — so before a single step runs, the
:class:`ResumeInspector` re-reads the persisted evidence and refuses
the resume unless every check holds:

1. **the state is readable** — ``goal.json`` exists and parses (a
   corrupt file is a refusal, not a fresh start);
2. **the goal exists** — an unknown id is a refusal, not a new goal;
3. **the ladder allows it** — the persisted state must be one of the
   resumable states; a ``completed`` goal is terminal (resuming one is
   refused — finished means finished);
4. **the deadline vocabulary is intact** — the persisted deadline must
   be one of the §25.7 four (a corrupt value is a refusal);
5. **the checkpoint is really there** — when a §22 manager is wired and
   the record names a ``last_checkpoint_id``, that checkpoint must
   still be listed in the store; a recorded-but-missing checkpoint is
   exactly the drift §22.4 refuses.

Every refusal is collected — :class:`BlindResumeError` carries the full
list, so the operator sees all the reasons, not the first.

Resuming opens a fresh run: a new generation (the durable lease that
retires any superseded worker), a fresh §25.7 window for bounded
deadlines (a deadline bounds ONE RUN — documented decision), and the
step function resumes from the persisted ``progress_seq``.

Stdlib only.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from .contracts import (
    DEADLINES,
    RESUMABLE_STATES,
    BlindResumeError,
    GoalRecord,
    StepFn,
)
from .goals import GoalStore
from .runner import HorizonHandle, HorizonRunner

logger = logging.getLogger("nexus.horizon")


class ResumeVerdict:
    """The inspector's verdict — ok, or the full refusal list."""

    def __init__(
        self, ok: bool, refusals: list[str], record: GoalRecord | None
    ) -> None:
        self.ok = ok
        self.refusals = tuple(refusals)
        self.record = record


class ResumeInspector:
    """The §25.6 preflight — the evidence on disk decides."""

    def __init__(self, store: GoalStore, *, checkpoints: Any | None = None) -> None:
        self._store = store
        self._checkpoints = checkpoints

    def inspect(self, goal_id: str) -> ResumeVerdict:
        refusals: list[str] = []
        record: GoalRecord | None = None

        # 1+2 — exists? raw-readable?
        path = self._store.goal_path(goal_id)
        if not path.exists():
            refusals.append(f"no goal persisted under {goal_id!r}")
            return ResumeVerdict(False, refusals, None)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            refusals.append(f"goal state unreadable on disk: {exc}")
            return ResumeVerdict(False, refusals, None)

        # 4 — the §25.7 vocabulary intact? (read from the raw file — a
        # corrupt deadline must be *named*, not hidden by a parse error)
        if raw.get("deadline") not in DEADLINES:
            refusals.append(
                f"persisted deadline {raw.get('deadline')!r} is not one of"
                f" {DEADLINES}"
            )

        # structural parse — a malformed record is named, and the rest
        # of the evidence is still inspected
        try:
            record = GoalRecord.from_dict(raw)
        except Exception as exc:  # noqa: BLE001 — malformed is a refusal
            refusals.append(f"goal record malformed: {exc}")

        # 3 — the ladder allows it?
        if record is not None and record.state not in RESUMABLE_STATES:
            refusals.append(
                f"state {record.state!r} is not resumable"
                f" (resumable: {sorted(RESUMABLE_STATES)})"
            )

        # 5 — the §22 checkpoint really there? (§22.4 drift law; use the
        # raw field so a malformed record cannot hide a drifted id)
        checkpoint_id = raw.get("last_checkpoint_id")
        if self._checkpoints is not None and checkpoint_id is not None:
            try:
                listed = {str(m.checkpoint_id) for m in self._checkpoints.store.list()}
            except Exception as exc:  # noqa: BLE001 — store failure is drift
                refusals.append(f"checkpoint store unreadable: {exc}")
            else:
                if str(checkpoint_id) not in listed:
                    refusals.append(
                        f"recorded checkpoint {checkpoint_id!r}"
                        " is not in the §22 store — the run drifted"
                    )

        ok = not refusals
        if ok:
            logger.debug(
                "resume preflight ok (goal %s · seq %d)",
                goal_id, record.progress_seq if record else -1,
            )
        else:
            logger.debug("resume preflight refused: %s", refusals)
        return ResumeVerdict(ok, refusals, record)


def resume(
    runner: HorizonRunner,
    goal_id: str,
    step_fn: StepFn,
    *,
    checkpoints: Any | None = None,
) -> HorizonHandle:
    """§25.6 — resume a persisted goal after evidence, never blind.

    Raises :class:`BlindResumeError` with every refusal reason when the
    preflight fails; otherwise opens a fresh run (new generation, fresh
    bounded window) and returns the background handle.
    """
    store: GoalStore = runner.store
    verdict = ResumeInspector(store, checkpoints=checkpoints).inspect(goal_id)
    if not verdict.ok or verdict.record is None:
        raise BlindResumeError(verdict.refusals)
    record = verdict.record
    if record.state == "running":
        # the previous process died mid-run — say so on the record
        store.append_progress(
            goal_id,
            f"RESUMED after interrupted run (superseded generation"
            f" {record.generation}, seq {record.progress_seq})",
        )
    return runner.relaunch(goal_id, step_fn)
