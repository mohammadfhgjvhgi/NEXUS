"""The Coding Loop (New Plan §15.6) — eight stages, this exact order.

::

    Understand → Plan → Edit → Build → Test → Debug → Retest → Review

The loop drives the §15.1 operations through the §2.4 task state
machine (ANALYZING for understand, PLANNING for plan, EXECUTING for
edit/build/test/debug/retest, VERIFYING for review) and publishes
only canonical §2.2 events (``task.*``, ``agent.*``, ``tool.*``,
``verification.*``) — never a new event name.

The Debug→Retest cycle is **bounded**: ``max_debug_cycles`` (default
3, constructor-checked ``>= 1``). Each cycle runs the debug operation,
applies the next pending fix recipe, and retests; if the suite still
fails when the budget is spent, the loop exits honestly — review
returns a REJECTED verdict with the reasons, never an infinite spin.

OpenHands contributed the loop framing (agent abstraction + event
loop + sandboxed execution, MODE B/D — zero imports); OpenCode the
session persistence; Cline the trail. All three live in
``vendor-staging/phase-15/`` as study material only.

حلقة البرمجة — ثماني مراحل بهذا الترتيب؛ دورة التصحيح محدودة
ودائمًا هناك حكم نهائي: مقبول أو مرفوض بأسباب.

Stdlib only.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from nexus.core.engine import TaskState
from nexus.events import EventName

from .contracts import (
    CodingOperationKind,
    EditAction,
    OperationRequest,
    OperationResult,
    ReviewVerdict,
    parse_edit_actions,
)
from .specialists import specialists_for_stage

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from nexus.events import EventBus

    from .operations import CodingAgent
    from .session import CodingSession

#: §15.6 stage → §2.4 task state (the documented mapping).
STAGE_TASK_STATES: dict[str, str] = {
    "understand": TaskState.ANALYZING.value,
    "plan": TaskState.PLANNING.value,
    "edit": TaskState.EXECUTING.value,
    "build": TaskState.EXECUTING.value,
    "test": TaskState.EXECUTING.value,
    "debug": TaskState.EXECUTING.value,
    "retest": TaskState.EXECUTING.value,
    "review": TaskState.VERIFYING.value,
}


class CodingLoopError(Exception):
    """Coding-loop misuse (bad bounds, no agent…)."""


@dataclass(slots=True)
class StageTrace:
    """One executed stage — what ran, how long, what it said."""

    stage: str
    state: str
    status: str
    summary: str
    duration_ms: float
    events: tuple[str, ...] = ()
    files_touched: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "state": self.state,
            "status": self.status,
            "summary": self.summary,
            "duration_ms": self.duration_ms,
            "events": list(self.events),
            "files_touched": list(self.files_touched),
        }


@dataclass(slots=True)
class CodingLoopResult:
    """The full §15.6 outcome — traces, verdict, files, bounds."""

    goal: str
    stage_traces: tuple[StageTrace, ...] = ()
    verdict: ReviewVerdict | None = None
    files_touched: tuple[str, ...] = ()
    debug_cycles: int = 0
    max_debug_cycles: int = 3
    events: tuple[str, ...] = field(default_factory=tuple)

    @property
    def approved(self) -> bool:
        return self.verdict.approved if self.verdict is not None else False

    @property
    def stage_order(self) -> tuple[str, ...]:
        return tuple(trace.stage for trace in self.stage_traces)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "approved": self.approved,
            "stage_traces": [trace.to_dict() for trace in self.stage_traces],
            "verdict": self.verdict.to_dict() if self.verdict else None,
            "files_touched": list(self.files_touched),
            "debug_cycles": self.debug_cycles,
            "max_debug_cycles": self.max_debug_cycles,
            "events": list(self.events),
        }


class CodingLoop:
    """Drives the eight §15.6 stages over one :class:`CodingAgent`.

    ``fixes``   — pending fix recipes (``EditAction``): the Debug→Retest
                  cycle consumes them one per cycle. In the full system
                  the model proposes them; here the declared recipe is
                  the proposal (stdlib-only honesty).
    ``edits``   — direct edits the Plan/Edit stages apply upfront
                  (goals that do not wait for a failing test).
    ``session`` — optional trail session (persisted on close when it
                  carries a directory).
    """

    def __init__(
        self,
        agent: CodingAgent,
        workspace_root: str | Path,
        goal: str,
        max_debug_cycles: int = 3,
        *,
        fixes: Sequence[EditAction | dict[str, Any]] = (),
        edits: Sequence[EditAction | dict[str, Any]] = (),
        session: CodingSession | None = None,
        bus: EventBus | None = None,
        task_id: str | None = None,
    ) -> None:
        if max_debug_cycles < 1:
            raise CodingLoopError(
                f"max_debug_cycles must be >= 1 (bounded, never zero/unbounded),"
                f" got {max_debug_cycles}"
            )
        self._agent = agent
        self._root = str(workspace_root)
        self._goal = goal
        self._max_debug_cycles = int(max_debug_cycles)
        self._pending_fixes = list(parse_edit_actions(fixes))
        self._direct_edits = list(parse_edit_actions(edits))
        self._session = session
        self._bus = bus
        self._task_id = task_id
        self._traces: list[StageTrace] = []
        self._events: list[str] = []
        self._files_touched: set[str] = set()
        self._edits_applied = 0
        self._last_review_result: OperationResult | None = None

    # ------------------------------------------------------------ driving

    def run(self) -> CodingLoopResult:
        """The §15.6 pass — the eight stages in order, bounded debugging.

        The recorded skeleton is always the §15.6 eight (understand →
        plan → edit → build → test → debug → retest → review): a green
        first pass records debug + retest as honest no-ops; extra
        Debug→Retest cycles extend the skeleton *after* the first
        review slot, and the returned verdict always reflects the
        latest review — never a stale one, never an infinite spin.
        """
        self._emit(EventName.TASK_STARTED, {"goal": self._goal, "loop": "coding"})
        analyze_payload = self._stage_understand()
        self._stage_plan(analyze_payload)
        self._stage_edit()
        self._stage_build()
        last_test = self._stage_test()
        cycles = 0
        verdict: ReviewVerdict | None = None
        while True:
            if last_test is not None and self._tests_green(last_test):
                if cycles == 0:
                    # green first pass — §15.6 still records all eight
                    # stages: debug + retest as honest no-ops
                    self._stage_debug_noop()
                    self._stage_retest_noop()
                verdict = self._stage_review(last_test, cycles)
                break
            if cycles >= self._max_debug_cycles:
                # budget spent and still red: a review ran after every
                # cycle, so the latest verdict stands — the honest
                # bounded rejection, never an infinite spin
                if verdict is None:
                    verdict = self._stage_review(last_test, cycles, record=False)
                break
            cycles += 1
            debug_payload, applied_files = self._stage_debug(cycles, last_test)
            last_test = self._stage_retest(cycles, applied_files)
            if cycles == 1:
                # the eighth skeleton slot — the review trace
                verdict = self._stage_review(last_test, cycles)
            else:
                # extra cycles extend (debug, retest); the verdict
                # refreshes, the eight-wide skeleton does not
                verdict = self._stage_review(last_test, cycles, record=False)
            if verdict.approved:
                if cycles > 1:
                    # turned green during an extra cycle — the recorded
                    # review trace must tell the latest truth
                    self._refresh_review_trace()
                break
        self._debug_cycles = cycles
        assert verdict is not None  # every path above sets one
        if verdict.approved:
            self._emit(
                EventName.TASK_COMPLETED,
                {"goal": self._goal, "debug_cycles": cycles, "verdict": "approved"},
            )
        else:
            self._emit(
                EventName.TASK_UPDATED,
                {
                    "goal": self._goal,
                    "debug_cycles": cycles,
                    "verdict": "rejected",
                    "note": "bounded debug budget spent — honest failure",
                },
            )
        self._close_session("closed" if verdict.approved else "failed")
        return CodingLoopResult(
            goal=self._goal,
            stage_traces=tuple(self._traces),
            verdict=verdict,
            files_touched=tuple(sorted(self._files_touched)),
            debug_cycles=cycles,
            max_debug_cycles=self._max_debug_cycles,
            events=tuple(self._events),
        )

    # ------------------------------------------------------------ stages

    def _request(
        self,
        kind: CodingOperationKind,
        payload: dict[str, Any] | None = None,
        timeout_s: float = 120.0,
    ) -> OperationRequest:
        return OperationRequest(
            kind=kind,
            goal=self._goal,
            workspace_root=self._root,
            payload=payload or {},
            timeout_s=timeout_s,
        )

    def _run_stage(
        self,
        stage: str,
        request: OperationRequest,
        *,
        tool_events: bool = False,
        extra_files: Sequence[str] = (),
        result: OperationResult | None = None,
        record: bool = True,
    ) -> OperationResult:
        """Execute one stage: specialists on, task state, events, trace.

        ``result`` — a precomputed result (skips the agent call: used
        for honest no-op stages that must still emit events + trace).
        ``record`` — append the StageTrace (the skeleton review slot is
        recorded once; later reviews refresh the verdict only).
        """
        state = STAGE_TASK_STATES[stage]
        events: list[str] = []
        serving = specialists_for_stage(stage)
        if serving:
            specialist = serving[0]
            self._emit(
                EventName.AGENT_STARTED,
                {"stage": stage, "specialist": specialist.agent_id, "role": specialist.role},
            )
            events.append(EventName.AGENT_STARTED.value)
        self._emit(EventName.TASK_UPDATED, {"stage": stage, "state": state})
        events.append(EventName.TASK_UPDATED.value)
        if tool_events:
            self._emit(
                EventName.TOOL_CALLED,
                {"stage": stage, "tool": f"coding.{request.kind.value}"},
            )
            events.append(EventName.TOOL_CALLED.value)
        if result is None:
            result = self._agent.execute(request)  # precomputed no-ops skip this
        if tool_events:
            self._emit(
                EventName.TOOL_COMPLETED,
                {"stage": stage, "ok": result.ok, "summary": result.summary[:200]},
            )
            events.append(EventName.TOOL_COMPLETED.value)
        if serving:
            self._emit(
                EventName.AGENT_COMPLETED,
                {"stage": stage, "specialist": serving[0].agent_id, "ok": result.ok},
            )
            events.append(EventName.AGENT_COMPLETED.value)
        self._files_touched.update(extra_files)
        if record:
            self._traces.append(
                StageTrace(
                    stage=stage,
                    state=state,
                    status=result.status.value,
                    summary=result.summary,
                    duration_ms=result.duration_ms,
                    events=tuple(events),
                    files_touched=tuple(extra_files),
                )
            )
        return result

    def _stage_understand(self) -> dict[str, Any]:
        result = self._run_stage("understand", self._request(CodingOperationKind.ANALYZE))
        return dict(result.payload)

    def _stage_plan(self, analyze_payload: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {"analyze": analyze_payload}
        if self._direct_edits:
            payload["fixes"] = [edit.to_dict() for edit in self._direct_edits]
        else:
            payload["fixes"] = []  # recipes stay pending for the debug cycle
        result = self._run_stage("plan", self._request(CodingOperationKind.PLAN, payload))
        return dict(result.payload)

    def _stage_edit(self) -> None:
        if self._direct_edits:
            request = self._request(
                CodingOperationKind.EDIT,
                {"actions": [edit.to_dict() for edit in self._direct_edits]},
            )
            result = self._run_stage(
                "edit",
                request,
                extra_files=[edit.path for edit in self._direct_edits],
            )
            self._edits_applied += int(result.payload.get("applied", 0))
            return
        # No upfront edits: the fix recipes are held for the Debug→Retest
        # cycle — the honest deterministic order of this phase. The stage
        # still runs (events, state, trace) with an honest no-op result.
        no_op = OperationResult.ok_result(
            CodingOperationKind.EDIT,
            0.0,
            "no direct edits planned — fix recipes held for the Debug→Retest cycle",
        )
        self._run_stage(
            "edit", self._request(CodingOperationKind.EDIT, {"actions": []}), result=no_op
        )

    def _stage_build(self) -> None:
        request = self._request(
            CodingOperationKind.RUN,
            {"command": [sys.executable, "-m", "compileall", "-q", self._root]},
            timeout_s=120.0,
        )
        self._run_stage("build", request, tool_events=True)

    def _stage_test(self) -> dict[str, Any]:
        request = self._request(CodingOperationKind.TEST, timeout_s=180.0)
        result = self._run_stage("test", request, tool_events=True)
        return dict(result.payload)

    def _stage_debug(
        self, cycle: int, last_test: dict[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        payload: dict[str, Any] = {
            "test_outcome": last_test,
            "failing_tests": list(last_test.get("failing_tests") or ()),
            "stderr": str(last_test.get("stderr_tail") or ""),
            "fixes": [fix.to_dict() for fix in self._pending_fixes[:1]],
        }
        request = self._request(CodingOperationKind.DEBUG, payload)
        result = self._run_stage("debug", request, tool_events=True)
        applied_files: list[str] = []
        if self._pending_fixes:
            fix = self._pending_fixes.pop(0)
            edit_request = self._request(
                CodingOperationKind.EDIT, {"actions": [fix.to_dict()]}
            )
            edit_result = self._agent.execute(edit_request)
            self._edits_applied += int(edit_result.payload.get("applied", 0))
            if edit_result.payload.get("applied"):
                applied_files.append(fix.path)
                self._files_touched.add(fix.path)
            if self._traces:
                self._traces[-1] = StageTrace(
                    stage=self._traces[-1].stage,
                    state=self._traces[-1].state,
                    status=self._traces[-1].status,
                    summary=(
                        f"{self._traces[-1].summary}; fix applied to {fix.path}"
                        if edit_result.payload.get("applied")
                        else f"{self._traces[-1].summary}; fix FAILED: {edit_result.error}"
                    ),
                    duration_ms=self._traces[-1].duration_ms,
                    events=self._traces[-1].events,
                    files_touched=tuple(applied_files),
                )
        return dict(result.payload), applied_files

    def _stage_retest(
        self, cycle: int, applied_files: Sequence[str]
    ) -> dict[str, Any]:
        request = self._request(CodingOperationKind.TEST, timeout_s=180.0)
        result = self._run_stage(
            "retest", request, tool_events=True, extra_files=applied_files
        )
        return dict(result.payload)

    def _stage_debug_noop(self) -> None:
        """Green first pass — the debug stage still runs (events, state,
        trace) with an honest no-op result: nothing to debug."""
        no_op = OperationResult.ok_result(
            CodingOperationKind.DEBUG,
            0.0,
            "green first pass — nothing to debug (honest no-op)",
        )
        self._run_stage(
            "debug", self._request(CodingOperationKind.DEBUG, {}), result=no_op
        )

    def _stage_retest_noop(self) -> None:
        """Green first pass — the retest stage still runs with an honest
        no-op result: no retest needed."""
        no_op = OperationResult.ok_result(
            CodingOperationKind.TEST,
            0.0,
            "green first pass — no retest needed (honest no-op)",
        )
        self._run_stage(
            "retest", self._request(CodingOperationKind.TEST), result=no_op
        )

    def _refresh_review_trace(self) -> None:
        """Rewrite the recorded review trace with the latest outcome.

        Extra Debug→Retest cycles run after the skeleton review slot;
        when a later cycle turns the project green, the recorded trace
        must tell the latest truth — the skeleton stays eight-wide.
        """
        latest = self._last_review_result
        if latest is None:
            return
        for index, trace in enumerate(self._traces):
            if trace.stage == "review":
                self._traces[index] = StageTrace(
                    stage=trace.stage,
                    state=trace.state,
                    status=latest.status.value,
                    summary=latest.summary,
                    duration_ms=latest.duration_ms,
                    events=trace.events,
                    files_touched=trace.files_touched,
                )
                return

    def _stage_review(
        self,
        last_test: dict[str, Any] | None,
        cycles: int,
        *,
        record: bool = True,
    ) -> ReviewVerdict:
        # Review re-runs the tests itself (independent verification — the
        # §15.1 review contract); the loop's last outcome is only the
        # decision input for reaching this stage.
        payload: dict[str, Any] = {
            "edits_applied": self._edits_applied,
            "debug_cycles": cycles,
            "max_debug_cycles": self._max_debug_cycles,
            "last_known_failures": list((last_test or {}).get("failing_tests") or ()),
        }
        request = self._request(CodingOperationKind.REVIEW, payload)
        self._emit(EventName.VERIFICATION_STARTED, {"goal": self._goal, "stage": "review"})
        result = self._run_stage("review", request, record=record)
        self._last_review_result = result
        verdict_data = dict(result.payload.get("verdict") or {})
        if not verdict_data:
            verdict_data = {
                "approved": False,
                "reasons": ["review produced no verdict — honest rejection"],
            }
        verdict = ReviewVerdict.from_dict(verdict_data)
        self._emit(
            EventName.VERIFICATION_PASSED if verdict.approved else EventName.VERIFICATION_FAILED,
            {"goal": self._goal, "debug_cycles": cycles},
        )
        return verdict

    # ------------------------------------------------------------ helpers

    def _tests_green(self, test_payload: dict[str, Any]) -> bool:
        return int(test_payload.get("exit_code", -1)) == 0 and not (
            test_payload.get("failing_tests") or ()
        )

    def _emit(self, name: EventName, payload: dict[str, Any]) -> None:
        bus = self._bus or getattr(self._agent, "bus", None)
        self._events.append(name.value)
        if bus is not None:
            bus.publish(
                name,
                payload=payload,
                source="nexus.coding.loop",
                task_id=self._task_id,
            )

    def _close_session(self, status: str) -> None:
        session = self._session or getattr(self._agent, "session", None)
        if session is not None:
            session.close(status)
