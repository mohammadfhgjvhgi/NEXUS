"""Background workers + deadline (PHASE 25 §25.2 + §25.4 + §25.5 + §25.7).

§25.2 — the work runs **in the background**: :meth:`HorizonRunner.start`
opens a run, spawns one real :class:`threading.Thread` and returns a
:class:`HorizonHandle` immediately.  The caller keeps living its own
life while the goal works — and may read the durable state, the
journal, or simply wait.

§25.4 — the runner beats the injected §23
:class:`~nexus.health.HeartbeatMonitor` (``agent`` per step, ``task``
at the milestones).  Nobody here derives health from exceptions — the
monitor's clock does that, exactly as §23 wrote it.

§25.5 — every ``checkpoint_every`` steps the runner captures a real
§22 :class:`~nexus.recovery.CheckpointManager` checkpoint (``PERIODIC``
trigger) and persists the returned id with the goal — the resume path
will verify it (§25.6/§22.4).

§25.7 — the deadline law, honestly:

* the four verbatim kinds are the only vocabulary (``30_minutes``,
  ``2_hours``, ``8_hours``, ``until_completion``);
* a bounded deadline is a **wall** deadline (epoch seconds) so it
  survives a reboot, and it is enforced at step granularity — a
  cooperative runner cannot preempt a step mid-flight (documented);
* hitting the wall stops the run with ``deadline_hit`` — never a fake
  completion, never an exception smuggled as success;
* ``until_completion`` has ``deadline_at is None``: it works until the
  step itself says «done».

The generation lease: every ``begin_run`` bumps the goal's persisted
``generation``; each step re-reads the record from disk and a runner
whose generation moved on retires itself without writing — a resumed
goal is never fought over by the corpse of its previous worker.

Stdlib only.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from nexus.recovery import TriggerEvent

from .contracts import (
    DEADLINE_SECONDS,
    HorizonError,
    StepFn,
    StepOutcome,
)
from .goals import GoalStore

logger = logging.getLogger("nexus.horizon")

#: Default §22 checkpoint cadence (steps between PERIODIC captures).
DEFAULT_CHECKPOINT_EVERY = 5


def deadline_window(
    deadline: str, *, wall_clock: Callable[[], float] = time.time
) -> float | None:
    """The §25.7 window opening now: epoch deadline for bounded kinds,
    ``None`` for ``until_completion`` (a missing deadline, honestly)."""
    seconds = DEADLINE_SECONDS[deadline]
    return None if seconds is None else wall_clock() + seconds


class HorizonRunner:
    """§25.2 — take the goal and work until it's done, in the background."""

    def __init__(
        self,
        store: GoalStore,
        *,
        heartbeat: Any | None = None,
        checkpoints: Any | None = None,
        checkpoint_every: int = DEFAULT_CHECKPOINT_EVERY,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        if checkpoint_every < 1:
            raise ValueError("checkpoint_every must be >= 1")
        self._store = store
        self._heartbeat = heartbeat
        self._checkpoints = checkpoints
        self._checkpoint_every = int(checkpoint_every)
        self._wall = wall_clock

    # ------------------------------------------------------------- reads

    @property
    def store(self) -> GoalStore:
        return self._store

    # -------------------------------------------------------------- 25.2

    def start(self, goal_id: str, step_fn: StepFn) -> HorizonHandle:
        """Start a **new** goal (state ``pending``) in the background.

        The deadline window opens now (§25.7): a bounded kind sets
        ``deadline_at = wall() + window``; ``until_completion`` stays
        ``None``.
        """
        record = self._store.get(goal_id)
        if record.state != "pending":
            raise HorizonError(
                f"goal {goal_id} is {record.state!r} — start() is for"
                " pending goals; use nexus.horizon.resume for the rest"
            )
        return self._launch(goal_id, step_fn, record.deadline)

    def relaunch(self, goal_id: str, step_fn: StepFn) -> HorizonHandle:
        """Re-open a run for a goal the resume preflight already vetted
        (nexus.horizon.resume is the only intended caller): a fresh
        generation, a fresh bounded window, no state policy here."""
        return self._launch(goal_id, step_fn, self._store.get(goal_id).deadline)

    # ------------------------------------------------------------ launch

    def _launch(
        self, goal_id: str, step_fn: StepFn, deadline_kind: str
    ) -> HorizonHandle:
        window = deadline_window(deadline_kind, wall_clock=self._wall)
        record = self._store.begin_run(goal_id, deadline_at=window)
        generation = record.generation
        thread = threading.Thread(
            target=self._loop,
            args=(goal_id, step_fn, generation),
            name=f"nexus-horizon-{goal_id}",
            daemon=True,
        )
        handle = HorizonHandle(self._store, goal_id, thread)
        thread.start()
        logger.debug("horizon worker started (goal %s · gen %d)", goal_id, generation)
        return handle

    # ---------------------------------------------------------- the loop

    def _loop(self, goal_id: str, step_fn: StepFn, generation: int) -> None:
        """The worker loop — every decision from disk, every beat real."""
        store = self._store
        while True:
            record = store.get(goal_id)
            if record.generation != generation:
                logger.debug(
                    "worker superseded (goal %s · gen %d < %d)",
                    goal_id, generation, record.generation,
                )
                return  # a newer runner owns the goal — retire silently
            if record.state != "running":
                return  # paused elsewhere / already resolved — obey the disk

            # §25.7 — the wall, checked before every step starts.
            if record.deadline_at is not None and self._wall() > record.deadline_at:
                store.transition(goal_id, "deadline_hit")
                if self._heartbeat is not None:
                    self._heartbeat.beat(
                        "task",
                        detail=f"deadline_hit {goal_id} after {record.progress_seq} steps",
                    )
                logger.debug("goal %s hit its deadline — honest stop", goal_id)
                return

            # the step — the user's work unit
            try:
                outcome = step_fn(record.progress_seq, record)
            except Exception as exc:  # noqa: BLE001 — the failure is the state
                if store.get(goal_id).generation != generation:
                    return  # superseded mid-step — its failure is not the goal's
                store.transition(goal_id, "failed")
                store.append_progress(goal_id, f"FAILED: {type(exc).__name__}: {exc}")
                logger.debug("goal %s step failed: %s", goal_id, exc)
                return
            if store.get(goal_id).generation != generation:
                return  # superseded mid-step — write nothing, retire now
            if not isinstance(outcome, StepOutcome):
                store.transition(goal_id, "failed")
                store.append_progress(
                    goal_id,
                    f"FAILED: step returned {type(outcome).__name__}, not StepOutcome",
                )
                return

            note = store.append_progress(
                goal_id, outcome.note or f"step {record.progress_seq + 1}"
            )

            # §25.4 — the heartbeat rides every step
            if self._heartbeat is not None:
                self._heartbeat.beat(
                    "agent", detail=f"horizon {goal_id} step {note.seq}"
                )

            # §25.5 — the §22 checkpoint cadence
            if self._checkpoints is not None and note.seq % self._checkpoint_every == 0:
                manifest = self._checkpoints.on_event(
                    TriggerEvent.PERIODIC, label=f"horizon {goal_id} step {note.seq}"
                )
                if manifest is not None:
                    store.set_checkpoint(goal_id, str(manifest.checkpoint_id))

            if outcome.done:
                store.transition(goal_id, "completed")
                if self._heartbeat is not None:
                    self._heartbeat.beat(
                        "task", detail=f"completed {goal_id} at step {note.seq}"
                    )
                logger.debug("goal %s completed at step %d", goal_id, note.seq)
                return


class HorizonHandle:
    """The background worker's handle — observe without interrupting."""

    def __init__(
        self, store: GoalStore, goal_id: str, thread: threading.Thread
    ) -> None:
        self._store = store
        self.goal_id = goal_id
        self._thread = thread

    def state(self) -> str:
        """The durable state — from disk, this instant."""
        return self._store.get(self.goal_id).state

    def record(self):
        """The full durable record."""
        return self._store.get(self.goal_id)

    def progress(self):
        """The journal so far."""
        return self._store.progress(self.goal_id)

    def is_alive(self) -> bool:
        return self._thread.is_alive()

    def pause(self) -> str:
        """running → paused (the ladder's polite exit)."""
        return self._store.transition(self.goal_id, "paused").state

    def wait(self, timeout: float | None = None) -> str:
        """Join the worker; return the final durable state."""
        self._thread.join(timeout=timeout)
        return self.state()

    def __repr__(self) -> str:  # pragma: no cover — debug convenience
        return f"<HorizonHandle {self.goal_id} alive={self.is_alive()}>"
