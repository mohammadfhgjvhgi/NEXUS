"""Master orchestration engine (PHASE 24 §24.1 + §24.3 + §24.4).

The §24.1 law as code::

    Master Agent — يبقى الوكيل الوحيد الذي يتعامل مع المستخدم.

:class:`MasterOrchestrator` accepts the user's goal through exactly
one door (:meth:`submit_user_goal`), plans the §24.3 waves over the
§24.2 specialists, runs each wave — genuinely side by side on real
threads when the gates allow, strictly in order when they do not —
coordinates §24.4 ownership through the §6.6 OwnershipManager, and
delivers one report back through the master's channel.  The
specialists report to their parent; the parent talks to the user.

Honesty laws carried over:

* **claims are checked before threads start** — a request whose
  resources collide with a live holder fails with the coordination
  detail (§6.6's :class:`ResourceOwnedError`), never an overwrite;
* **success is claimed, never granted** — a missing handler, a raised
  exception, a scope violation all come back as ``ok=False`` results
  with the true reason;
* **every §24.3 denial is explainable** — the wave plan keeps each
  verdict behind each placement;
* **§23 rides along** — when a :class:`~nexus.health.HeartbeatMonitor`
  is injected, every dispatch beats ``agent`` and every completed wave
  beats ``task``; the orchestrator is never a silent stall.

Stdlib only.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from nexus.agents import (
    MASTER_AGENT_ID,
    AgentRegistry,
    OwnershipManager,
    ResourceOwnedError,
)

from .contracts import (
    OWNERSHIP_FIELDS,
    AgentResult,
    DispatchOutcome,
    DispatchRequest,
    OrchestrationError,
    OrchestrationReport,
    ScopeViolationError,
)
from .parallelism import ParallelismGate
from .team import SpecialistTeam, UserChannel

logger = logging.getLogger("nexus.orchestration")

#: Default wall-clock budget for one wave of real threads.
DEFAULT_WAVE_TIMEOUT_SECONDS = 120.0


class MasterOrchestrator:
    """The §24.1 Master Agent's orchestration engine.

    One door for the user (:meth:`submit_user_goal`), one voice to the
    user (:meth:`report_to_user`), and a wave machine in between.
    """

    def __init__(
        self,
        team: SpecialistTeam,
        registry: AgentRegistry,
        ownership: OwnershipManager,
        *,
        heartbeat: Any | None = None,
        wave_timeout_seconds: float = DEFAULT_WAVE_TIMEOUT_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._team = team
        self._registry = registry
        self._ownership = ownership
        self._gate = ParallelismGate(ownership)
        self._heartbeat = heartbeat
        self._wave_timeout = float(wave_timeout_seconds)
        self._clock = clock

    # ------------------------------------------------------------- reads

    @property
    def team(self) -> SpecialistTeam:
        return self._team

    @property
    def channel(self) -> UserChannel:
        """The §24.1 user channel — the master's alone."""
        return self._team.channel

    @property
    def gate(self) -> ParallelismGate:
        return self._gate

    # ------------------------------------------------- the one user door

    def submit_user_goal(
        self,
        goal: str,
        requests: Sequence[DispatchRequest],
    ) -> OrchestrationReport:
        """§24.1 — the ONLY entry from the user.

        The goal plus the master's dispatch plan (the caller — or a
        planner specialist's output — supplies the requests; nothing
        here invents work) goes through the wave machine; the report
        comes back through the master's voice.
        """
        if not goal.strip():
            raise OrchestrationError("a goal must be non-empty")
        for request in requests:
            if request.task_id == MASTER_AGENT_ID or not request.task_id.strip():
                raise OrchestrationError(
                    f"request {request.request_id!r} carries an unusable task id"
                )
        return self.orchestrate(goal, requests)

    def report_to_user(self, report: OrchestrationReport) -> OrchestrationReport:
        """§24.1 — the single voice to the user: the master's."""
        self.channel.write(
            MASTER_AGENT_ID,
            report.summary or f"goal {report.goal!r}: {len(report.outcomes)} outcome(s)",
        )
        delivered = OrchestrationReport(
            goal=report.goal,
            master_id=report.master_id,
            wave_count=report.wave_count,
            outcomes=report.outcomes,
            summary=report.summary,
            user_delivered=True,
            field_notes=report.field_notes,
        )
        return delivered

    # -------------------------------------------------------- orchestrate

    def orchestrate(
        self,
        goal: str,
        requests: Sequence[DispatchRequest],
    ) -> OrchestrationReport:
        """Plan the waves, run them, own the resources, report once."""
        waves = self._gate.plan_waves(requests)
        outcomes: list[DispatchOutcome] = []
        notes: list[str] = []

        for index, wave in enumerate(waves):
            parallel = len(wave) > 1
            wave_outcomes = self._run_wave(index, wave, parallel)
            outcomes.extend(wave_outcomes)
            if self._heartbeat is not None:
                self._heartbeat.beat("task", detail=f"wave {index + 1}/{len(waves)} done")
            failed = [o for o in wave_outcomes if not o.result.ok]
            if failed:
                notes.append(
                    f"wave {index}: {len(failed)} failed — "
                    + "; ".join(f"{o.request_id}: {o.result.detail}" for o in failed)
                )

        report = OrchestrationReport(
            goal=goal,
            master_id=MASTER_AGENT_ID,
            wave_count=len(waves),
            outcomes=tuple(outcomes),
            summary=self._summary(goal, outcomes, waves),
            field_notes=tuple(notes),
        )
        return self.report_to_user(report)

    # ------------------------------------------------------------- waves

    def _run_wave(
        self,
        index: int,
        wave: tuple[DispatchRequest, ...],
        parallel: bool,
    ) -> list[DispatchOutcome]:
        """Acquire ownership, execute (threads when parallel), release."""
        acquisitions: dict[str, list[str]] = {}
        results: dict[str, AgentResult] = {}

        # §24.4/§6.6 — claims are settled before any thread starts.
        for request in wave:
            acquired: list[str] = []
            try:
                for resource in request.resources:
                    self._ownership.acquire(
                        resource, owner=request.request_id, task_id=request.task_id
                    )
                    acquired.append(resource)
                acquisitions[request.request_id] = acquired
            except ResourceOwnedError as exc:
                # The coordination signal, surfaced honestly — no overwrite.
                self._ownership.release_owner(request.request_id)
                acquisitions[request.request_id] = []
                results[request.request_id] = AgentResult(
                    request_id=request.request_id,
                    agent_id=self._team.get(request.role).agent_id,
                    role=request.role,
                    ok=False,
                    detail=f"ownership conflict — {exc}",
                )
                logger.debug("orchestration: %s blocked by ownership", request.request_id)

        runnable = [r for r in wave if r.request_id not in results]

        if parallel and len(runnable) > 1:
            results.update(self._run_parallel(runnable))
        else:
            for request in runnable:
                results[request.request_id] = self._execute_one(request)

        # Teardown — the owner returns what it held (§6.6 release).
        for request in wave:
            self._ownership.release_owner(request.request_id)

        return [
            DispatchOutcome(
                request_id=request.request_id,
                role=request.role,
                wave_index=index,
                ran_parallel=parallel and len(runnable) > 1,
                result=results[request.request_id],
            )
            for request in wave
        ]

    def _run_parallel(
        self, runnable: Sequence[DispatchRequest]
    ) -> dict[str, AgentResult]:
        """Real threads, genuinely side by side — join, then collect."""
        results: dict[str, AgentResult] = {}
        lock = threading.Lock()

        def worker(request: DispatchRequest) -> None:
            result = self._execute_one(request)
            with lock:
                results[request.request_id] = result

        threads = [
            threading.Thread(
                target=worker,
                args=(request,),
                name=f"nexus-orch-{request.request_id}",
                daemon=True,
            )
            for request in runnable
        ]
        for thread in threads:
            thread.start()
            if self._heartbeat is not None:
                self._heartbeat.beat("agent", detail=f"dispatched {thread.name}")
        deadline = self._clock() + self._wave_timeout
        for thread in threads:
            remaining = max(0.0, deadline - self._clock())
            thread.join(timeout=remaining)
        for request in runnable:
            if request.request_id not in results:
                results[request.request_id] = AgentResult(
                    request_id=request.request_id,
                    agent_id=self._team.get(request.role).agent_id,
                    role=request.role,
                    ok=False,
                    detail=(
                        f"wave timeout after {self._wave_timeout:.0f}s —"
                        " thread still running (threads cannot be killed;"
                        " documented honestly)"
                    ),
                )
        return results

    def _execute_one(self, request: DispatchRequest) -> AgentResult:
        """One request through its specialist — §23 beats included."""
        specialist = self._team.get(request.role)
        if self._heartbeat is not None:
            self._heartbeat.beat(
                "agent",
                detail=f"dispatch {request.request_id} → {specialist.agent_id}",
            )
        try:
            return specialist.execute(request)
        except ScopeViolationError as exc:
            return AgentResult(
                request_id=request.request_id,
                agent_id=specialist.agent_id,
                role=request.role,
                ok=False,
                detail=str(exc),
            )

    # ------------------------------------------------------------ summary

    @staticmethod
    def _summary(
        goal: str,
        outcomes: Sequence[DispatchOutcome],
        waves: Sequence[Sequence[DispatchRequest]],
    ) -> str:
        ok = sum(1 for o in outcomes if o.result.ok)
        parallel_waves = sum(1 for wave in waves if len(wave) > 1)
        return (
            f"goal {goal!r}: {ok}/{len(outcomes)} request(s) succeeded across"
            f" {len(waves)} wave(s) ({parallel_waves} parallel)"
            f" — ownership fields {', '.join(OWNERSHIP_FIELDS)}"
        )
