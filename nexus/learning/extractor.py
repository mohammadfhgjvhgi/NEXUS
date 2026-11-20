"""Experience Extractor (New Plan §13.1).

Turns one finished task into the six §13.1 experience kinds::

    success · failure · decision · pattern · lesson · skill_candidate

Input — a ``TaskResult`` dict, the honest shape the §2.4 engine already
produces when a task ends:

    task_id     str                     the task that lived it
    outcome     "success"|"failure"|"partial"
    summary     str                     what happened, one sentence
    steps       list[dict]              name · status · error? · decision?
    lesson      str?                    an explicit lesson (model/operator)
    evidence    list[MemoryEvidence]?   proof captured along the way
    + the §12.2 containers (project…agent)

Output — ``list[Experience]``, audit-grade: every item carries the task
id, an honest summary and whatever evidence the result held.

* success   — outcome == success → what worked, and *why* (summary).
* failure   — outcome != success → what failed; each failing step adds
              its own failure experience (the error text is evidence).
* decision  — every step flagged ``decision=True`` → the choice made.
* pattern   — a step sequence repeated *inside* one task (loops,
              retry chains) → the repetition itself is the signal.
* lesson    — the explicit ``lesson`` field, or distilled from a
              failure summary («avoid …» / «fix … first»).
* skill_candidate — minted by :meth:`extract_skill_candidate` when the
              §13.4 miner sees a workflow repeat across tasks (Task A,
              Task B, Task C → pattern → candidate). The kind belongs
              to this extractor's vocabulary; the pipeline feeds it.

مستخرج الخبرة — يحوّل نهاية مهمة إلى الأنواع الستة: نجاح وفشل
وقرار ونمط ودرس ومرشّح مهارة، كل واحد مع دليله ومهمته.

Stdlib only.
"""

from __future__ import annotations

from typing import Any

from nexus.memory.contracts import MemoryEvidence

from .contracts import (
    EXPERIENCE_CONTAINERS,
    Experience,
    ExperienceKind,
    new_learning_id,
)

#: Step statuses that mark a step as failed (the rest are fine).
_FAILED_STEP_STATUSES = frozenset({"error", "failed", "failure", "timeout", "crash"})

#: A within-task pattern needs this many repeats of a ≥2-step window
#: before it stops being coincidence.
_INTRA_PATTERN_MIN_REPEATS = 2


def _step_name(step: dict[str, Any]) -> str:
    name = str(step.get("name") or step.get("action") or "").strip()
    return name or "unnamed_step"


def _containers_of(result: dict[str, Any]) -> dict[str, str | None]:
    return {key: result.get(key) or None for key in EXPERIENCE_CONTAINERS}


class ExperienceExtractor:
    """§13.1 — one pure transform: TaskResult → [Experience]."""

    def extract(self, task_result: dict[str, Any]) -> list[Experience]:
        """Extract every §13.1 kind one finished task offers."""
        task_id = str(task_result.get("task_id") or "").strip()
        if not task_id:
            raise ValueError("task_result needs a task_id")
        summary = str(task_result.get("summary") or "").strip()
        if not summary:
            summary = "no summary provided"

        steps = [s for s in task_result.get("steps") or [] if isinstance(s, dict)]
        evidence = tuple(
            e for e in task_result.get("evidence") or [] if isinstance(e, MemoryEvidence)
        )
        containers = _containers_of(task_result)
        outcome = str(task_result.get("outcome") or "").strip().casefold()
        explicit_lesson = str(task_result.get("lesson") or "").strip()

        out: list[Experience] = []

        # ---- success ------------------------------------------------
        if outcome == "success":
            out.append(self._experience(
                kind=ExperienceKind.SUCCESS,
                task_id=task_id,
                summary=f"worked: {summary}",
                evidence=evidence,
                containers=containers,
                payload={"outcome": outcome, "step_count": len(steps)},
            ))

        # ---- failure (overall + per failing step) --------------------
        if outcome in ("failure", "failed", "partial"):
            why = "failed" if outcome != "partial" else "partially failed"
            out.append(self._experience(
                kind=ExperienceKind.FAILURE,
                task_id=task_id,
                summary=f"{why}: {summary}",
                evidence=evidence,
                containers=containers,
                payload={"outcome": outcome},
            ))
            for step in steps:
                status = str(step.get("status") or "").strip().casefold()
                if status in _FAILED_STEP_STATUSES:
                    out.append(self._experience(
                        kind=ExperienceKind.FAILURE,
                        task_id=task_id,
                        summary=(
                            f"step '{_step_name(step)}' failed: "
                            f"{step.get('error') or status}"
                        ),
                        evidence=tuple(evidence) + self._step_evidence(step, task_id),
                        containers=containers,
                        payload={"step": _step_name(step), "status": status},
                    ))

        # ---- decision ------------------------------------------------
        for step in steps:
            if step.get("decision"):
                out.append(self._experience(
                    kind=ExperienceKind.DECISION,
                    task_id=task_id,
                    summary=(
                        f"decision at '{_step_name(step)}': "
                        f"{step.get('choice') or step.get('detail') or 'made'}"
                    ),
                    evidence=tuple(evidence) + self._step_evidence(step, task_id),
                    containers=containers,
                    payload={"step": _step_name(step)},
                ))

        # ---- pattern (repetition inside one task) ---------------------
        for window, count in _intra_task_patterns(steps):
            out.append(self._experience(
                kind=ExperienceKind.PATTERN,
                task_id=task_id,
                summary=(
                    f"pattern within task: {' > '.join(window)} "
                    f"(x{count} in one task)"
                ),
                evidence=tuple(evidence) + self._step_evidence(steps[0], task_id),
                containers=containers,
                payload={"window": list(window), "count": count},
            ))

        # ---- lesson (explicit, or distilled from failure) --------------
        if explicit_lesson:
            out.append(self._experience(
                kind=ExperienceKind.LESSON,
                task_id=task_id,
                summary=explicit_lesson,
                evidence=evidence,
                containers=containers,
                payload={"origin": "explicit"},
            ))
        elif (
            outcome in ("failure", "failed", "partial")
            and any(word in summary.casefold() for word in ("fix", "avoid", "wrong", "خطأ"))
        ):
            out.append(self._experience(
                kind=ExperienceKind.LESSON,
                task_id=task_id,
                summary=f"lesson from failure: {summary}",
                evidence=evidence,
                containers=containers,
                payload={"origin": "distilled"},
            ))

        return out

    def extract_skill_candidate(
        self,
        *,
        steps: tuple[str, ...],
        occurrences: int,
        source_tasks: tuple[str, ...],
    ) -> Experience:
        """Mint the §13.4 kind — the pipeline calls this when the
        WorkflowMiner sees a workflow repeat (Task A, Task B, Task C)."""
        return self._experience(
            kind=ExperienceKind.SKILL_CANDIDATE,
            task_id=source_tasks[-1] if source_tasks else "unknown",
            summary=(
                f"repeated workflow ({occurrences}x): {' > '.join(steps)} "
                f"— skill candidate"
            ),
            evidence=tuple(
                MemoryEvidence(
                    method="tool_run",
                    uri=f"task:{tid}",
                    snippet=" > ".join(steps),
                )
                for tid in source_tasks
            ),
            containers={key: None for key in EXPERIENCE_CONTAINERS},
            payload={
                "steps": list(steps),
                "occurrences": occurrences,
                "source_tasks": list(source_tasks),
            },
        )

    # ------------------------------------------------------------ private

    def _experience(
        self,
        *,
        kind: str,
        task_id: str,
        summary: str,
        evidence: tuple[MemoryEvidence, ...],
        containers: dict[str, str | None],
        payload: dict[str, Any],
    ) -> Experience:
        return Experience(
            id=new_learning_id("exp_"),
            kind=kind,
            task_id=task_id,
            summary=summary,
            evidence=evidence,
            project=containers.get("project"),
            workspace=containers.get("workspace"),
            task=containers.get("task"),
            session=containers.get("session"),
            agent=containers.get("agent"),
            payload=payload,
        )

    @staticmethod
    def _step_evidence(step: dict[str, Any], task_id: str) -> tuple[MemoryEvidence, ...]:
        """One step → one evidence row (the step's own error/status)."""
        detail = str(step.get("error") or step.get("status") or step.get("choice") or "")
        return (
            MemoryEvidence(
                method="tool_run",
                uri=f"task:{task_id}#step:{_step_name(step)}",
                snippet=detail[:200],
            ),
        )


def _intra_task_patterns(
    steps: list[dict[str, Any]],
) -> list[tuple[tuple[str, ...], int]]:
    """Windows (length ≥ 2) that repeat inside a single task.

    A window counts once per task — within-task repetition is the
    signal, cross-task repetition is §13.4's job.
    """
    names = [_step_name(s) for s in steps]
    if len(names) < 4:
        # a 2-window needs 4 steps to repeat once; nothing to see yet
        return []
    seen: dict[tuple[str, ...], int] = {}
    for size in range(2, min(len(names), 6) + 1):
        for start in range(0, len(names) - size + 1):
            window = tuple(names[start : start + size])
            seen[window] = seen.get(window, 0) + 1
    return [
        (window, count)
        for window, count in seen.items()
        if count >= _INTRA_PATTERN_MIN_REPEATS
    ]


def step_sequence_of(task_result: dict[str, Any]) -> tuple[str, ...]:
    """The normalized step-name sequence — the miner's raw material."""
    steps = [s for s in task_result.get("steps") or [] if isinstance(s, dict)]
    return tuple(_step_name(s) for s in steps)
