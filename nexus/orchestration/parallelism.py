"""Parallelism gate (PHASE 24 §24.3).

The plan, verbatim::

    Parallelism — يُسمح به عندما:
      Tasks independent · Files independent · Resources available

Three conjunctive gates: parallelism is allowed only when **all three**
pass — any single failure means sequential, and the denial always
carries its reason (a gate that says no must say why).

* ``tasks_independent``  — different tasks, no declared dependency
  between the two requests (``depends_on`` is stated, never guessed);
* ``files_independent``  — the two requests claim disjoint files (a
  shared file is a shared fate — sequential);
* ``resources_available`` — no §6.6 resource is claimed by both, and
  no claimed resource is held by a *third* party
  (:class:`~nexus.agents.ownership.ResourceOwnedError` prevented by
  looking before running, not by crashing mid-flight).

:func:`plan_waves` composes the pairwise gate into a deterministic
wave plan: greedy first-fit — a request joins the earliest wave where
it is pairwise-parallel with every member; otherwise it opens (or
waits for) the next wave.  Waves run in order; within a wave, agents
genuinely run side by side (the orchestrator proves it with real
threads).

Stdlib only.
"""

from __future__ import annotations

from collections.abc import Sequence

from nexus.agents import OwnershipManager

from .contracts import (
    PARALLELISM_GATES,
    DispatchRequest,
    GateReport,
    ParallelismVerdict,
)


class ParallelismGate:
    """The §24.3 three gates, pairwise and honest."""

    def __init__(self, ownership: OwnershipManager | None = None) -> None:
        self._ownership = ownership

    # ------------------------------------------------------------- decide

    def decide(self, a: DispatchRequest, b: DispatchRequest) -> ParallelismVerdict:
        """May ``a`` and ``b`` run side by side?  All three gates or no."""
        reports: list[GateReport] = []
        reports.append(self._tasks_independent(a, b))
        reports.append(self._files_independent(a, b))
        reports.append(self._resources_available(a, b))
        reasons = tuple(r.detail for r in reports if not r.passed)
        decision = "parallel" if not reasons else "sequential"
        return ParallelismVerdict(decision=decision, gates=tuple(reports), reasons=reasons)

    # -------------------------------------------------------------- gates

    @staticmethod
    def _tasks_independent(a: DispatchRequest, b: DispatchRequest) -> GateReport:
        """Gate 1 — different tasks AND no declared dependency."""
        if a.task_id == b.task_id:
            return GateReport(
                gate="tasks_independent",
                passed=False,
                detail=f"both requests belong to task {a.task_id!r}",
            )
        if a.request_id in b.depends_on:
            return GateReport(
                gate="tasks_independent",
                passed=False,
                detail=(
                    f"{b.request_id!r} declares a dependency on"
                    f" {a.request_id!r}"
                ),
            )
        if b.request_id in a.depends_on:
            return GateReport(
                gate="tasks_independent",
                passed=False,
                detail=(
                    f"{a.request_id!r} declares a dependency on"
                    f" {b.request_id!r}"
                ),
            )
        return GateReport(
            gate="tasks_independent",
            passed=True,
            detail=(
                f"tasks {a.task_id!r} ≠ {b.task_id!r} with no declared"
                " dependency"
            ),
        )

    @staticmethod
    def _files_independent(a: DispatchRequest, b: DispatchRequest) -> GateReport:
        """Gate 2 — disjoint file claims."""
        shared = sorted(set(a.files) & set(b.files))
        if shared:
            return GateReport(
                gate="files_independent",
                passed=False,
                detail=f"both requests claim file(s) {shared}",
            )
        return GateReport(
            gate="files_independent",
            passed=True,
            detail=f"file claims disjoint ({len(a.files)} vs {len(b.files)})",
        )

    def _resources_available(
        self, a: DispatchRequest, b: DispatchRequest
    ) -> GateReport:
        """Gate 3 — no shared claim, no third-party holder."""
        shared = sorted(set(a.resources) & set(b.resources))
        if shared:
            return GateReport(
                gate="resources_available",
                passed=False,
                detail=f"both requests claim resource(s) {shared}",
            )
        if self._ownership is not None:
            held_by: dict[str, str | None] = {
                r: self._ownership.owner_of(r) for r in (*a.resources, *b.resources)
            }
            foreign = sorted(
                r for r, holder in held_by.items()
                if holder not in (None, a.request_id, b.request_id)
            )
            if foreign:
                return GateReport(
                    gate="resources_available",
                    passed=False,
                    detail=f"resource(s) {foreign} held by others {held_by}",
                )
        return GateReport(
            gate="resources_available",
            passed=True,
            detail="no shared claims, no third-party holders",
        )

    # --------------------------------------------------------------- waves

    def plan_waves(
        self, requests: Sequence[DispatchRequest]
    ) -> tuple[tuple[DispatchRequest, ...], ...]:
        """Greedy first-fit wave plan (deterministic, order-preserving).

        A request joins the earliest wave where the pairwise gate says
        ``parallel`` against every member; otherwise the next wave.
        The result is a tuple of waves — the orchestrator runs them in
        order, each wave's members side by side.
        """
        waves: list[list[DispatchRequest]] = []
        for request in requests:
            placed = False
            for wave in waves:
                if all(
                    self.decide(request, member).allowed for member in wave
                ):
                    wave.append(request)
                    placed = True
                    break
            if not placed:
                waves.append([request])
        return tuple(tuple(wave) for wave in waves)


def gate_report_summary(verdict: ParallelismVerdict) -> str:
    """One-line human summary of a verdict (reports / harness output)."""
    if verdict.allowed:
        return "parallel — " + "; ".join(
            f"{r.gate}: ok" for r in verdict.gates if r.gate in PARALLELISM_GATES
        )
    return "sequential — " + "; ".join(verdict.reasons)
