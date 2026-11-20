"""Stall Detection — §23.2: the four loop shapes, named verbatim.

    يبحث عن: same action · same error · same state · no progress

A stuck worker almost always traces one of four loop shapes, so the
detector watches a sliding window of :class:`Observation` records and
fires a :class:`StallFinding` the moment a shape completes:

* ``same action``  — the trailing run of observations shares one
  action signature: the actor is not consuming its own result.
* ``same error``   — the trailing run shares one error signature:
  the fix is not landing.
* ``same state``   — the trailing run shares one state hash: nothing
  is changing anymore.
* ``no progress``  — across the whole progress window neither the
  progress marker nor the state moved: the task stopped advancing.

Empty fields are never judged — nothing is invented from nothing —
and a finding fires **once per evidence** (no alert spam while the
loop keeps looping); :meth:`StallDetector.reset` re-arms after a
recovery, and a changed loop shape re-arms by itself.

Stdlib only.
"""

from __future__ import annotations

from collections import deque

from .contracts import (
    Observation,
    StallFinding,
    StallSignal,
    utc_now_iso,
)
from .heartbeat import HealthError


class StallDetector:
    """§23.2 — one sliding window, four shapes, one-fire-per-evidence."""

    def __init__(
        self,
        *,
        repeat_threshold: int = 3,
        progress_window: int = 8,
        history_max: int = 256,
    ) -> None:
        if repeat_threshold < 2:
            raise HealthError("repeat_threshold must be ≥ 2 — one repeat is not a loop")
        if progress_window < 2:
            raise HealthError("progress_window must be ≥ 2 — a window of one sees nothing")
        self._repeat = int(repeat_threshold)
        self._window = int(progress_window)
        self._history: deque[Observation] = deque(maxlen=max(history_max, progress_window))
        # signal → the evidence key already fired (no spam while it holds)
        self._fired: dict[StallSignal, str] = {}

    # ------------------------------------------------------------ public

    def observe(self, *observations: Observation) -> tuple[StallFinding, ...]:
        """Feed the window, return every finding the new evidence confirms."""
        findings: list[StallFinding] = []
        for obs in observations:
            self._history.append(obs)
            findings.extend(self._evaluate(obs))
        return tuple(findings)

    def reset(self) -> None:
        """Re-arm after a recovery — the old loop is history now."""
        self._history.clear()
        self._fired.clear()

    @property
    def depth(self) -> int:
        return len(self._history)

    # ----------------------------------------------------------- private

    def _evaluate(self, latest: Observation) -> list[StallFinding]:
        candidates: list[tuple[StallSignal, str, int, str]] = []

        run_action = self._trailing_run(lambda o: o.action)
        if run_action[0] >= self._repeat:
            candidates.append(
                (
                    StallSignal.SAME_ACTION,
                    run_action[1],
                    run_action[0],
                    f"action {run_action[1]!r} repeated {run_action[0]}× "
                    "without consuming a result",
                )
            )

        run_error = self._trailing_run(lambda o: o.error)
        if run_error[0] >= self._repeat:
            candidates.append(
                (
                    StallSignal.SAME_ERROR,
                    run_error[1],
                    run_error[0],
                    f"error {run_error[1]!r} repeated {run_error[0]}× — the fix is not landing",
                )
            )

        run_state = self._trailing_run(lambda o: o.state)
        if run_state[0] >= self._repeat:
            candidates.append(
                (
                    StallSignal.SAME_STATE,
                    run_state[1],
                    run_state[0],
                    f"state {run_state[1]!r} frozen across {run_state[0]} observations",
                )
            )

        no_progress = self._no_progress_evidence()
        if no_progress:
            key, span = no_progress
            candidates.append(
                (
                    StallSignal.NO_PROGRESS,
                    key,
                    span,
                    f"no forward movement across the last {span} observations "
                    f"(progress/state pinned at {key!r})",
                )
            )

        fired: list[StallFinding] = []
        for signal, evidence, repeats, detail in candidates:
            if self._fired.get(signal) == evidence:
                continue  # already reported — no spam while the loop holds
            self._fired[signal] = evidence
            fired.append(
                StallFinding(
                    signal=signal,
                    repeats=repeats,
                    detail=detail,
                    at_utc=latest.at_utc or utc_now_iso(),
                )
            )
        return fired

    def _trailing_run(self, key) -> tuple[int, str]:  # type: ignore[no-untyped-def]
        """(length, value) of the trailing run sharing one non-empty key."""
        value: str | None = None
        run = 0
        for obs in reversed(self._history):
            v = key(obs)
            if not v:
                break
            if value is None:
                value = v
                run = 1
            elif v == value:
                run += 1
            else:
                break
        return (run, value) if value else (0, "")

    def _no_progress_evidence(self) -> tuple[str, int] | None:
        if len(self._history) < self._window:
            return None
        tail = list(self._history)[-self._window :]
        keys = [o.progress or o.state for o in tail]
        if not keys or any(not k for k in keys):
            return None  # an unmarked step is not evidence of anything
        if len(set(keys)) != 1:
            return None
        return keys[0], self._window
