"""Task record serialization (Final Build Plan §2.5).

Round-trips a :class:`~nexus.core.session.models.Task` to/from a JSON-safe
mapping. The record carries an envelope (schema name + version) for
forward compatibility, then the task with **exactly the eleven §2.5
fields** (goal, prompt, scope, workspace, plan, agents, state,
checkpoints, errors, verification, result) plus bookkeeping (ids,
timestamps, sessions, state history).

All datetimes are ISO-8601 UTC strings on disk; naive values are
interpreted as UTC on load (defensive only — the core always writes
aware UTC datetimes).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ..engine.states import TaskState, TransitionRecord
from ..session.models import (
    CheckpointRef,
    PlanStep,
    Session,
    StepStatus,
    Task,
    TaskError,
    TaskPlan,
    TaskResult,
    VerificationCheck,
    VerificationRecord,
    VerificationStatus,
    utc_now,
)

TASK_RECORD_SCHEMA = "nexus.task"
TASK_RECORD_VERSION = 1


class PersistenceError(Exception):
    """Corrupt, incompatible or unsafe persistence payload."""


def _iso(value: datetime) -> str:
    return value.isoformat()


def _parse_dt(value: str | datetime | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError as exc:
            raise PersistenceError(f"invalid datetime value {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _parse_dt_required(
    value: str | datetime | None, context: str, field: str
) -> datetime:
    """Parse a required datetime (never None) with a precise error."""
    parsed = _parse_dt(value)
    if parsed is None:
        raise PersistenceError(f"{context}: missing datetime for {field!r}")
    return parsed


def task_to_record(task: Task) -> dict[str, Any]:
    """Serialize a task into its persisted envelope."""
    task_data: dict[str, Any] = {
        "id": task.id,
        "conversation_id": task.conversation_id,
        # --- the eleven §2.5 fields ---
        "goal": task.goal,
        "prompt": task.prompt,
        "scope": dict(task.scope),
        "workspace": task.workspace,
        "plan": {
            "steps": [
                {
                    "id": step.id,
                    "description": step.description,
                    "status": step.status.value,
                    "agent": step.agent,
                }
                for step in task.plan.steps
            ],
            "created_at": _iso(task.plan.created_at),
            "notes": task.plan.notes,
        },
        "agents": list(task.agents),
        "state": task.state.value,
        "checkpoints": [
            {
                "id": ckpt.id,
                "created_at": _iso(ckpt.created_at),
                "reason": ckpt.reason,
                "path": ckpt.path,
                "session_id": ckpt.session_id,
            }
            for ckpt in task.checkpoints
        ],
        "errors": [
            {
                "code": error.code,
                "message": error.message,
                "at": _iso(error.at),
                "fatal": error.fatal,
                "source": error.source,
            }
            for error in task.errors
        ],
        "verification": {
            "status": task.verification.status.value,
            "checks": [
                {
                    "name": check.name,
                    "passed": check.passed,
                    "detail": check.detail,
                    "at": _iso(check.at),
                }
                for check in task.verification.checks
            ],
            "started_at": (
                _iso(task.verification.started_at)
                if task.verification.started_at is not None
                else None
            ),
            "completed_at": (
                _iso(task.verification.completed_at)
                if task.verification.completed_at is not None
                else None
            ),
        },
        "result": (
            {
                "summary": task.result.summary,
                "artifacts": list(task.result.artifacts),
                "completed_at": (
                    _iso(task.result.completed_at)
                    if task.result.completed_at is not None
                    else None
                ),
                "success": task.result.success,
            }
            if task.result is not None
            else None
        ),
        # --- bookkeeping ---
        "created_at": _iso(task.created_at),
        "updated_at": _iso(task.updated_at),
        "state_before_pause": (
            task.state_before_pause.value
            if task.state_before_pause is not None
            else None
        ),
        "sessions": [
            {
                "id": session.id,
                "task_id": session.task_id,
                "index": session.index,
                "started_at": _iso(session.started_at),
                "ended_at": (
                    _iso(session.ended_at) if session.ended_at is not None else None
                ),
                "context": dict(session.context),
                "notes": session.notes,
            }
            for session in task.sessions
        ],
        "state_history": [
            {
                "from_state": record.from_state.value,
                "to_state": record.to_state.value,
                "at": _iso(record.at),
                "reason": record.reason,
                "session_id": record.session_id,
            }
            for record in task.state_history
        ],
    }
    return {
        "schema": TASK_RECORD_SCHEMA,
        "schema_version": TASK_RECORD_VERSION,
        "saved_at": datetime.now(UTC).isoformat(),
        "task": task_data,
    }


def _require(data: Mapping[str, Any], key: str, context: str) -> Any:
    if key not in data:
        raise PersistenceError(f"{context}: missing field {key!r}")
    return data[key]


def task_from_record(data: Mapping[str, Any]) -> Task:
    """Rebuild a task from its persisted envelope."""
    if data.get("schema") != TASK_RECORD_SCHEMA:
        raise PersistenceError(
            f"not a {TASK_RECORD_SCHEMA} record (got {data.get('schema')!r})"
        )
    version = data.get("schema_version")
    if version != TASK_RECORD_VERSION:
        raise PersistenceError(
            f"unsupported record version {version!r} "
            f"(expected {TASK_RECORD_VERSION})"
        )
    task_data = data.get("task")
    if not isinstance(task_data, Mapping):
        raise PersistenceError("record has no 'task' mapping")
    ctx = f"task record {_require(task_data, 'id', 'record')}"

    plan_data = _require(task_data, "plan", ctx)
    plan = TaskPlan(
        steps=[
            PlanStep(
                id=_require(step, "id", ctx),
                description=_require(step, "description", ctx),
                status=StepStatus(step.get("status", StepStatus.PENDING.value)),
                agent=step.get("agent"),
            )
            for step in plan_data.get("steps", [])
        ],
        created_at=_parse_dt_required(
            _require(plan_data, "created_at", ctx), ctx, "plan.created_at"
        ),
        notes=plan_data.get("notes"),
    )

    verification_data = _require(task_data, "verification", ctx)
    verification = VerificationRecord(
        status=VerificationStatus(
            verification_data.get("status", VerificationStatus.PENDING.value)
        ),
        checks=[
            VerificationCheck(
                name=_require(check, "name", ctx),
                passed=bool(_require(check, "passed", ctx)),
                detail=check.get("detail"),
                at=_parse_dt(check.get("at")) or utc_now(),
            )
            for check in verification_data.get("checks", [])
        ],
        started_at=_parse_dt(verification_data.get("started_at")),
        completed_at=_parse_dt(verification_data.get("completed_at")),
    )

    result_data = task_data.get("result")
    result = (
        TaskResult(
            summary=_require(result_data, "summary", ctx),
            artifacts=list(result_data.get("artifacts", [])),
            completed_at=_parse_dt(result_data.get("completed_at")),
            success=bool(result_data.get("success", True)),
        )
        if isinstance(result_data, Mapping)
        else None
    )

    sessions = [
        Session(
            id=_require(session, "id", ctx),
            task_id=_require(session, "task_id", ctx),
            index=int(_require(session, "index", ctx)),
            started_at=_parse_dt_required(
                _require(session, "started_at", ctx), ctx, "session.started_at"
            ),
            ended_at=_parse_dt(session.get("ended_at")),
            context=dict(session.get("context", {})),
            notes=session.get("notes"),
        )
        for session in task_data.get("sessions", [])
    ]

    state_history = [
        TransitionRecord(
            from_state=TaskState(_require(record, "from_state", ctx)),
            to_state=TaskState(_require(record, "to_state", ctx)),
            at=_parse_dt_required(_require(record, "at", ctx), ctx, "state_history.at"),
            reason=record.get("reason"),
            session_id=record.get("session_id"),
        )
        for record in task_data.get("state_history", [])
    ]

    state_before_pause = task_data.get("state_before_pause")

    return Task(
        id=_require(task_data, "id", ctx),
        conversation_id=_require(task_data, "conversation_id", ctx),
        goal=_require(task_data, "goal", ctx),
        prompt=_require(task_data, "prompt", ctx),
        scope=dict(task_data.get("scope", {})),
        workspace=str(task_data.get("workspace", "main")),
        plan=plan,
        agents=list(task_data.get("agents", [])),
        state=TaskState(_require(task_data, "state", ctx)),
        checkpoints=[
            CheckpointRef(
                id=_require(ckpt, "id", ctx),
                created_at=_parse_dt_required(
                    _require(ckpt, "created_at", ctx), ctx, "checkpoint.created_at"
                ),
                reason=_require(ckpt, "reason", ctx),
                path=ckpt.get("path"),
                session_id=ckpt.get("session_id"),
            )
            for ckpt in task_data.get("checkpoints", [])
        ],
        errors=[
            TaskError(
                code=_require(error, "code", ctx),
                message=_require(error, "message", ctx),
                at=_parse_dt_required(_require(error, "at", ctx), ctx, "error.at"),
                fatal=bool(error.get("fatal", False)),
                source=error.get("source"),
            )
            for error in task_data.get("errors", [])
        ],
        verification=verification,
        result=result,
        created_at=_parse_dt_required(_require(task_data, "created_at", ctx), ctx, "created_at"),
        updated_at=_parse_dt_required(_require(task_data, "updated_at", ctx), ctx, "updated_at"),
        sessions=sessions,
        state_history=state_history,
        state_before_pause=(
            TaskState(state_before_pause) if state_before_pause else None
        ),
    )
