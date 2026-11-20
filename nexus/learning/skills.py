"""Workflow miner — the Skill Candidate engine (New Plan §13.4).

The plan's own picture::

    Task A
    Task B
    Task C
      ↓
    Pattern
      ↓
    Skill candidate

The miner watches every task's step sequence (stored by the pipeline)
and folds repeats into :class:`~nexus.learning.contracts.SkillCandidate`
records — same workflow run by SKILL_MIN_REPEATS (§13.4's three)
distinct tasks. Full-sequence matches count; so do shared sub-windows
(length ≥ 2) — a skill is often one segment of a longer task.

MODE provenance (§13.5/§13.6): the *idea* — persistent skills mined
from repeated workflows — was studied in letta-code (skills +
continual agent state) and prime-agent (skills + persistent goals),
both MODE D reference; the implementation here is NEXUS-native and
imports nothing from either (Plan §61).

مُعدِّن المهارات — إذا تكرر سير عمل عبر ثلاث مهام يصبح نمطًا،
والنمط مرشّح مهارة، بأدلة من كل مهمة عاشته.

Stdlib only.
"""

from __future__ import annotations

from nexus.memory.contracts import MemoryEvidence

from .contracts import (
    CONFIDENCE_CEILING,
    CONFIDENCE_FLOOR,
    ExperienceKind,
    SkillCandidate,
    new_learning_id,
    workflow_signature,
)
from .store import SQLiteLearningStore

#: §13.4 verbatim — Task A, Task B, Task C (three distinct tasks).
SKILL_MIN_REPEATS = 3

#: Longest window the miner considers (bounded work, honest bound —
#: longer workflows fold into their repeated sub-windows anyway).
_MAX_WINDOW = 6


class WorkflowMiner:
    """§13.4 — sequence → pattern → skill candidate.

    ``store`` — the SQLiteLearningStore holding ``task_sequences``.
    """

    def __init__(self, store: SQLiteLearningStore) -> None:
        self._store = store

    def mine(
        self,
        *,
        min_repeats: int = SKILL_MIN_REPEATS,
    ) -> list[SkillCandidate]:
        """Fold repeated workflows into candidates (idempotent).

        Returns every candidate that exists or was updated by this
        pass — the pipeline turns the *new/changed* ones into §13.1
        ``skill_candidate`` experiences.
        """
        sequences = self._store.all_sequences()
        if len(sequences) < min_repeats:
            return []

        # signature → the distinct tasks that ran it (per task once)
        seen: dict[str, dict[str, tuple[str, ...]]] = {}
        for entry in sequences:
            task_id = entry["task_id"]
            steps = entry["sequence"]
            # the whole workflow…
            self._register(seen, steps, task_id)
            # …and every sub-window of length 2.._MAX_WINDOW
            for size in range(2, min(len(steps), _MAX_WINDOW) + 1):
                for start in range(0, len(steps) - size + 1):
                    self._register(
                        seen, steps[start : start + size], task_id
                    )

        # maximal windows only — a sub-window of a kept workflow adds
        # nothing (§13.4's pattern is the WHOLE repeated workflow, not
        # its fragments), and only a window that *itself* qualifies
        # may shadow: a 2× long workflow must not hide the 5× prefix
        # that actually repeats.
        entries = sorted(
            (
                (signature, tasks, next(iter(tasks.values())))
                for signature, tasks in seen.items()
            ),
            key=lambda item: len(item[2]),
            reverse=True,
        )
        kept: list[tuple[str, dict[str, tuple[str, ...]], tuple[str, ...]]] = []
        for signature, tasks, steps in entries:
            if len(tasks) < min_repeats:
                continue  # noise — and it never shadows a real pattern
            if any(
                _is_subwindow(steps, kept_steps) for _, _, kept_steps in kept
            ):
                continue
            kept.append((signature, tasks, steps))

        candidates: list[SkillCandidate] = []
        for signature, tasks, _steps in kept:
            changed = self._upsert_candidate(signature, tasks)
            if changed is not None:
                candidates.append(changed)
        return candidates

    # ------------------------------------------------------------ private

    @staticmethod
    def _register(
        seen: dict[str, dict[str, tuple[str, ...]]],
        steps: tuple[str, ...],
        task_id: str,
    ) -> None:
        """One window, one task — a window run twice inside one task
        still counts once (cross-task repeat is the §13.4 signal)."""
        if len(steps) < 2:
            return
        signature = workflow_signature(steps)
        seen.setdefault(signature, {})[task_id] = steps

    def _upsert_candidate(
        self,
        signature: str,
        tasks: dict[str, tuple[str, ...]],
    ) -> SkillCandidate | None:
        """Create or merge the candidate; None when nothing changed."""
        source_tasks = tuple(sorted(tasks))
        occurrences = len(source_tasks)
        steps = next(iter(tasks.values()))
        evidence = tuple(
            MemoryEvidence(
                method="tool_run",
                uri=f"task:{tid}",
                snippet=" > ".join(steps)[:200],
            )
            for tid in source_tasks
        )
        confidence = self._confidence(occurrences, len(source_tasks))

        existing = self._store.find_skill(signature)
        if existing is None:
            candidate = SkillCandidate(
                id=new_learning_id("skc_"),
                pattern=signature,
                steps=steps,
                occurrences=occurrences,
                evidence=evidence,
                confidence=confidence,
                status="candidate",
                source_tasks=source_tasks,
            )
            return self._store.add_skill(candidate)
        if (
            existing.occurrences == occurrences
            and existing.status == "candidate"
            and set(existing.source_tasks) == set(source_tasks)
        ):
            return None  # already known, nothing new learned
        existing.occurrences = max(existing.occurrences, occurrences)
        existing.source_tasks = tuple(
            sorted(set(existing.source_tasks) | set(source_tasks))
        )
        existing.evidence = evidence
        existing.confidence = max(existing.confidence, confidence)
        if existing.status == "rejected":
            existing.status = "candidate"  # new evidence re-opens it
        return self._store.update_skill(existing)

    @staticmethod
    def _confidence(occurrences: int, distinct_methods: int) -> float:
        """Skill confidence — repetition is the whole story here."""
        base = 0.45
        repeat_bonus = min(0.12 * (occurrences - SKILL_MIN_REPEATS + 1), 0.36)
        evidence_bonus = min(0.05 * distinct_methods, 0.10)
        value = base + repeat_bonus + evidence_bonus
        return round(min(max(value, CONFIDENCE_FLOOR), CONFIDENCE_CEILING), 4)


#: The §13.1 kind this miner mints (extractor's sixth vocabulary entry).
MINED_KIND = ExperienceKind.SKILL_CANDIDATE


def _is_subwindow(small: tuple[str, ...], big: tuple[str, ...]) -> bool:
    """True when ``small`` is a contiguous fragment of ``big``."""
    if len(small) >= len(big):
        return False
    return any(
        big[i : i + len(small)] == small for i in range(len(big) - len(small) + 1)
    )
