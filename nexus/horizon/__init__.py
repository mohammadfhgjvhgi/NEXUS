"""NEXUS Long-Horizon System (PHASE 25 — Long-Horizon Execution).

*«خذ المهمة واشتغل لحد ما تخلص.»*
(Take the task and work until it's done.)

The seven sections::

    25.1  Goal persistence    — every goal on disk, atomically, and a
                                reboot finds it (§25.1)
    25.2  Background workers  — one real thread per run; the handle
                                returns immediately (§25.2)
    25.3  Long-running state  — the durable ladder pending → running →
                                paused/completed/failed/deadline_hit,
                                written between steps (§25.3)
    25.4  Heartbeat           — the §23 monitor beaten per step;
                                silence derived from the clock (§25.4)
    25.5  Checkpoints         — real §22 PERIODIC captures on a
                                cadence, ids persisted with the goal
                                (§25.5)
    25.6  Resume              — the §22.4 law again: the disk decides —
                                a corrupt state, a terminal goal, a
                                missing checkpoint all refuse the
                                resume (§25.6)
    25.7  Deadline            — 30 minutes · 2 hours · 8 hours ·
                                Until completion; a bounded deadline
                                stops with deadline_hit, never a fake
                                completion (§25.7)

The structural laws:

* **durable before memory** — every decision the worker makes re-reads
  ``goal.json`` from disk; the state is true between steps, not only
  at the ends;
* **the generation lease** — every run bumps the persisted generation;
  a superseded worker retires itself at its next step, so a resumed
  goal is never fought over by the corpse of its previous worker;
* **a deadline bounds ONE RUN** — resuming a deadline-hit goal opens a
  fresh window of the same kind; «اشتغل لحد ما تخلص» is the goal's
  law, the wall is the run's law;
* **completion is claimed by the work itself** — only the step's
  ``done=True`` completes a goal; deadlines and failures stop honestly.

Stdlib only.
"""

from __future__ import annotations

from .contracts import (
    DEADLINE_SECONDS,
    DEADLINES,
    GOAL_STATES,
    HORIZON_SCHEMA_VERSION,
    RESUMABLE_STATES,
    TRANSITIONS,
    BlindResumeError,
    GoalRecord,
    HorizonError,
    IllegalTransitionError,
    ProgressNote,
    StepFn,
    StepOutcome,
    UnknownDeadlineError,
    UnknownGoalError,
    deadline_seconds,
    new_goal_id,
)
from .goals import GoalStore, load_store
from .resume import ResumeInspector, ResumeVerdict, resume
from .runner import (
    DEFAULT_CHECKPOINT_EVERY,
    HorizonHandle,
    HorizonRunner,
    deadline_window,
)

__all__ = [
    "DEFAULT_CHECKPOINT_EVERY",
    "DEADLINES",
    "DEADLINE_SECONDS",
    "GOAL_STATES",
    "HORIZON_SCHEMA_VERSION",
    "RESUMABLE_STATES",
    "TRANSITIONS",
    "BlindResumeError",
    "GoalRecord",
    "GoalStore",
    "HorizonError",
    "HorizonHandle",
    "HorizonRunner",
    "IllegalTransitionError",
    "ProgressNote",
    "ResumeInspector",
    "ResumeVerdict",
    "StepFn",
    "StepOutcome",
    "UnknownDeadlineError",
    "UnknownGoalError",
    "deadline_seconds",
    "deadline_window",
    "load_store",
    "new_goal_id",
    "resume",
]
