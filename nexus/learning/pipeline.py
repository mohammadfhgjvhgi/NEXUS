"""Learning Pipeline (New Plan §13.3) — the phase's spine.

The plan's own flow, verbatim::

    Experience
      ↓
    Candidate lesson
      ↓
    Evidence check
      ↓
    Confidence
      ↓
    Store
      ↓
    Future retrieval

:class:`LearningPipeline` runs that flow for every finished task
(``absorb``) and answers the last arrow on demand (``recall``):

* **Experience**        — the §13.1 extractor turns the TaskResult
                          into the six kinds.
* **Candidate lesson**  — each experience becomes one candidate
                          (lesson / worked / failed / decision /
                          pattern / skill candidate).
* **Evidence check**    — no evidence → refused, counted, kept in the
                          experiences audit (never silently dropped).
* **Confidence**        — :func:`~nexus.learning.contracts.confidence_for`
                          (pure rule: kind prior + evidence + repeats).
* **Store**             — :class:`~nexus.learning.store.SQLiteLearningStore`
                          upserts by ``signature``: the same lesson
                          re-learned *merges* (occurrences +1, confidence
                          rises — repetition is signal).
* **Future retrieval**  — lessons that clear ``LEARN_PROMOTE_THRESHOLD``
                          are written into the §12 Memory Engine
                          (source ``"learning"``, conflict_key the lesson
                          signature) so every future task's §12.7 context
                          already knows them; ``recall()`` additionally
                          surfaces still-pending lessons (honest: they
                          exist, they are not yet confident).

The §12.8 ladder stays in force untouched: an old lesson loses to a
current prompt, task, workspace rule or project decision — learning
never overrides the operator's *now*.

MODE provenance (§13.5–§13.7): letta-code's continual agent state,
prime-agent's persistent goals/heartbeat, DSPy's evaluation-driven
refinement — all studied as reference (MODE D/B); this implementation
is NEXUS-native, imports nothing from them (Plan §61).

مسار التعلّم — خبرة فدرس مرشّح فتحقق الدليل فالثقة فالتخزين
فالاسترجال المستقبلي؛ الدروس المعروضة تدخل محرّك الذاكرة §12
فيعرفها سياق كل مهمة قادمة.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from nexus.memory.contracts import (
    MemoryProvider,
    MemoryQuery,
    MemoryScope,
    MemoryType,
)

from .contracts import (
    EXPERIENCE_KINDS,
    LEARN_PROMOTE_THRESHOLD,
    LESSON_MEMORY_TYPES,
    MIN_EVIDENCE_ITEMS,
    Experience,
    ExperienceKind,
    LearningRecord,
    SkillCandidate,
    confidence_for,
    evidence_methods_of,
    lesson_signature,
    new_learning_id,
)
from .extractor import ExperienceExtractor, step_sequence_of
from .skills import WorkflowMiner
from .store import SQLiteLearningStore

#: Where a learned kind lands in the §12.2 scope vocabulary.
LESSON_SCOPE_BY_KIND: dict[str, str] = {
    ExperienceKind.SUCCESS: MemoryScope.LESSON,
    ExperienceKind.FAILURE: MemoryScope.ERROR,
    ExperienceKind.DECISION: MemoryScope.DECISION,
    ExperienceKind.PATTERN: MemoryScope.KNOWLEDGE,
    ExperienceKind.LESSON: MemoryScope.LESSON,
    ExperienceKind.SKILL_CANDIDATE: MemoryScope.SKILL,
}

#: The memory types a recall searches for learning-sourced records.
_RECALL_TYPES: tuple[str, ...] = (
    MemoryType.LESSON,
    MemoryType.ERROR,
    MemoryType.DECISION,
    MemoryType.KNOWLEDGE,
    MemoryType.OBSERVATION,
    MemoryType.SKILL,
)

#: Events the pipeline publishes on a §2.2 bus (never fatal).
EVENT_RECORD_CREATED = "learning.record.created"
EVENT_RECORD_PROMOTED = "learning.record.promoted"
EVENT_RECORD_REFUSED = "learning.record.refused"
EVENT_SKILL_FOUND = "learning.skill.found"


@dataclass(slots=True)
class LearningOutcome:
    """What one ``absorb()`` learned — the honest ledger."""

    task_id: str
    experiences: int = 0
    lessons_stored: int = 0
    lessons_merged: int = 0
    lessons_promoted: int = 0
    lessons_refused: int = 0
    skill_candidates: int = 0
    skills_promoted: int = 0
    refused: list[dict[str, str]] = field(default_factory=list)
    promoted_memory_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "experiences": self.experiences,
            "lessons_stored": self.lessons_stored,
            "lessons_merged": self.lessons_merged,
            "lessons_promoted": self.lessons_promoted,
            "lessons_refused": self.lessons_refused,
            "skill_candidates": self.skill_candidates,
            "skills_promoted": self.skills_promoted,
            "refused": self.refused,
            "promoted_memory_ids": self.promoted_memory_ids,
        }


@dataclass(slots=True)
class LearningRecall:
    """The answer to ``recall()`` — future retrieval, assembled.

    ``promoted`` — memory records written by learning (source
    ``"learning"``, already inside every §12.7 context).
    ``pending``  — §13.2 records below the promote threshold (they
    exist, they are searchable, they are not yet confident).
    """

    prompt: str
    promoted: list[dict[str, Any]] = field(default_factory=list)
    pending: list[dict[str, Any]] = field(default_factory=list)

    def as_prompt(self) -> str:
        """One context block — the same budget-honesty as §12.7."""
        return self.prompt

    def to_dict(self) -> dict[str, Any]:
        return {
            "prompt": self.prompt,
            "promoted": self.promoted,
            "pending": self.pending,
        }


class LearningPipeline:
    """§13.3 — the six-stage flow, one call per finished task.

    ``store``   — SQLiteLearningStore (path or ``:memory:``).
    ``memory``  — optional MemoryProvider (§12 engine); promotion is
                  skipped honestly when absent, lessons stay pending.
    ``bus``     — optional §2.2 EventBus for LEARNING_* events.
    """

    def __init__(
        self,
        store: SQLiteLearningStore,
        *,
        memory: MemoryProvider | None = None,
        extractor: ExperienceExtractor | None = None,
        miner: WorkflowMiner | None = None,
        bus: object | None = None,
        promote_threshold: float = LEARN_PROMOTE_THRESHOLD,
    ) -> None:
        self._store = store
        self._memory = memory
        self._extractor = extractor or ExperienceExtractor()
        self._miner = miner or WorkflowMiner(store)
        self._bus = bus
        self.promote_threshold = promote_threshold

    # ------------------------------------------------------------ absorb

    def absorb(self, task_result: dict[str, Any]) -> LearningOutcome:
        """Run the full §13.3 flow over one finished task."""
        task_id = str(task_result.get("task_id") or "").strip()
        outcome = LearningOutcome(task_id=task_id)

        # ---- stage 1: Experience --------------------------------------
        experiences = self._extractor.extract(task_result)
        for experience in experiences:
            self._store.add_experience(experience)
        outcome.experiences = len(experiences)

        # ---- §13.4 feed: the sequence joins the miner's corpus --------
        sequence = step_sequence_of(task_result)
        if sequence:
            self._store.record_sequence(
                task_id,
                sequence,
                project=task_result.get("project") or None,
                workspace=task_result.get("workspace") or None,
                task=task_result.get("task") or None,
                session=task_result.get("session") or None,
                agent=task_result.get("agent") or None,
            )
        mined = self._miner.mine()
        for candidate in mined:
            minted = self._extractor.extract_skill_candidate(
                steps=candidate.steps,
                occurrences=candidate.occurrences,
                source_tasks=candidate.source_tasks,
            )
            self._store.add_experience(minted)
            experiences.append(minted)
            outcome.experiences += 1
            outcome.skill_candidates += 1
            self._emit(
                EVENT_SKILL_FOUND,
                {
                    "pattern": candidate.pattern,
                    "steps": list(candidate.steps),
                    "occurrences": candidate.occurrences,
                },
            )

        # ---- stages 2–5: candidate → evidence → confidence → store ----
        for experience in experiences:
            self._absorb_experience(experience, outcome)

        # ---- skill promotion (§13.4 → memory SKILL) --------------------
        for candidate in mined:
            if candidate.memory_id is None and self._memory is not None:
                if candidate.confidence >= self.promote_threshold:
                    self._promote_skill(candidate)
                    outcome.skills_promoted += 1
                    outcome.promoted_memory_ids.append(candidate.memory_id or "")
        return outcome

    # ------------------------------------------------------------ recall

    def recall(
        self,
        prompt: str,
        *,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        agent: str | None = None,
        limit: int = 12,
    ) -> LearningRecall:
        """§13.3's last arrow — what learning knows, for this context.

        Promoted records come from the §12 engine (they also ride the
        normal §12.7 retrieve); pending ones from the learning store.
        """
        promoted: list[dict[str, Any]] = []
        if self._memory is not None:
            query = MemoryQuery(
                text=prompt,
                project=project,
                workspace=workspace,
                task=task,
                session=session,
                agent=agent,
                types=_RECALL_TYPES,
                limit=limit,
                include_semantic=True,
            )
            for hit in self._memory.search(query):
                record = hit.record
                if record.source == "learning":
                    promoted.append(
                        {
                            "memory_id": record.id,
                            "type": record.type,
                            "scope": record.scope,
                            "content": record.content,
                            "confidence": record.confidence,
                            "lexical": round(hit.lexical, 4),
                            "semantic": round(hit.semantic, 4),
                        }
                    )
                    if len(promoted) >= limit:
                        break
        pending = [
            record.to_dict()
            for record in self._store.search_lessons(prompt, limit=limit)
            if record.status == "pending"
        ]
        return self._assemble(prompt, promoted, pending)

    # ------------------------------------------------------------- stats

    def stats(self) -> dict[str, Any]:
        """The honest ledger — counts by kind, status and skills."""
        records = self._store.list_records()
        by_status = {"pending": 0, "promoted": 0, "superseded": 0}
        by_scope: dict[str, int] = {}
        for record in records:
            by_status[record.status] = by_status.get(record.status, 0) + 1
            by_scope[record.scope] = by_scope.get(record.scope, 0) + 1
        kinds = {
            kind: self._store.count_experiences(kind) for kind in EXPERIENCE_KINDS
        }
        return {
            "experiences": self._store.count_experiences(),
            "kinds": kinds,
            "records": len(records),
            "records_by_status": by_status,
            "records_by_scope": by_scope,
            "task_sequences": len(self._store.all_sequences()),
            "skill_candidates": [
                c.to_dict() for c in self._store.list_skills()
            ],
            "promote_threshold": self.promote_threshold,
            "memory_attached": self._memory is not None,
        }

    def close(self) -> None:
        """Release the store (§12 lesson: folders lock)."""
        self._store.close()

    # ------------------------------------------------------------ private

    def _absorb_experience(
        self, experience: Experience, outcome: LearningOutcome
    ) -> None:
        """Stages 2–5 for one experience → one candidate lesson."""
        scope = LESSON_SCOPE_BY_KIND.get(experience.kind, MemoryScope.LESSON)
        signature = lesson_signature(experience.summary, scope)
        existing = self._store.find_by_signature(signature)

        # ---- stage 3: evidence check ----------------------------------
        if len(experience.evidence) < MIN_EVIDENCE_ITEMS and existing is None:
            outcome.lessons_refused += 1
            outcome.refused.append(
                {
                    "lesson": experience.summary,
                    "reason": "no evidence — an opinion, not a lesson",
                    "kind": experience.kind,
                }
            )
            self._emit(
                EVENT_RECORD_REFUSED,
                {"lesson": experience.summary, "kind": experience.kind},
            )
            return

        # ---- stages 4–5: confidence + store (merge by signature) -------
        methods = evidence_methods_of(experience.evidence)
        if existing is None:
            record = LearningRecord(
                id=new_learning_id("les_"),
                experience_id=experience.id,
                lesson=experience.summary,
                source_task=experience.task_id,
                evidence=experience.evidence,
                confidence=confidence_for(
                    experience.kind,
                    evidence_methods=methods,
                    occurrences=1,
                ),
                scope=scope,
                status="pending",
                occurrences=1,
                signature=signature,
                project=experience.project,
                workspace=experience.workspace,
                task=experience.task,
                session=experience.session,
                agent=experience.agent,
            )
            self._store.add_record(record)
            outcome.lessons_stored += 1
            self._emit(EVENT_RECORD_CREATED, record.to_dict())
        else:
            # re-learned: occurrences merge, confidence rises
            existing.occurrences += 1
            merged_methods = tuple(
                sorted({m for m in methods} | {m for m in evidence_methods_of(existing.evidence)})
            )
            existing.evidence = _merge_evidence(
                existing.evidence, experience.evidence
            )
            existing.confidence = confidence_for(
                experience.kind,
                evidence_methods=merged_methods,
                occurrences=existing.occurrences,
            )
            existing.source_task = experience.task_id
            existing.project = existing.project or experience.project
            existing.workspace = existing.workspace or experience.workspace
            existing.task = existing.task or experience.task
            self._store.update_record(existing)
            outcome.lessons_merged += 1
            record = existing

        # ---- stage 5b: promotion into the §12 engine -------------------
        if (
            self._memory is not None
            and record.confidence >= self.promote_threshold
        ):
            if record.memory_id:
                # already promoted — reinforce the §12 confidence
                try:
                    self._memory.update(
                        record.memory_id, confidence=record.confidence
                    )
                except Exception:  # noqa: BLE001 — memory never breaks learning
                    pass
            else:
                memory_record = self._memory.remember(
                    record.lesson,
                    type=LESSON_MEMORY_TYPES.get(
                        experience.kind, MemoryType.LESSON
                    ),
                    scope=record.scope,
                    source="learning",
                    confidence=record.confidence,
                    project=record.project,
                    workspace=record.workspace,
                    task=record.task,
                    session=record.session,
                    agent=record.agent,
                    conflict_key=record.signature,
                    evidence=record.evidence,
                )
                record.memory_id = memory_record.id
                record.status = "promoted"
                self._store.update_record(record)
                outcome.lessons_promoted += 1
                outcome.promoted_memory_ids.append(memory_record.id)
                self._emit(EVENT_RECORD_PROMOTED, record.to_dict())

    def _promote_skill(self, candidate: SkillCandidate) -> None:
        """§13.4 → the §12 engine as a SKILL record (reusable workflow)."""
        if self._memory is None:
            return
        content = (
            f"skill: {' > '.join(candidate.steps)} "
            f"(ran {candidate.occurrences}x across "
            f"{len(candidate.source_tasks)} tasks)"
        )
        memory_record = self._memory.remember(
            content,
            type=MemoryType.SKILL,
            scope=MemoryScope.SKILL,
            source="learning",
            confidence=candidate.confidence,
            conflict_key=candidate.pattern,
            evidence=candidate.evidence,
        )
        candidate.memory_id = memory_record.id
        candidate.status = "promoted"
        self._store.update_skill(candidate)
        self._emit(
            EVENT_RECORD_PROMOTED,
            {
                "skill": candidate.pattern,
                "steps": list(candidate.steps),
                "memory_id": memory_record.id,
            },
        )

    @staticmethod
    def _assemble(
        prompt: str,
        promoted: list[dict[str, Any]],
        pending: list[dict[str, Any]],
    ) -> LearningRecall:
        """Assemble the recall prompt — §12.7's budget honesty, light."""
        lines: list[str] = []
        if promoted:
            lines.append("Lessons learned (proven):")
            for item in promoted:
                lines.append(
                    f"  - [{item.get('scope')}] {item.get('content')} "
                    f"(confidence {item.get('confidence')})"
                )
        if pending:
            lines.append("Pending lessons (not yet confident):")
            for item in pending:
                lines.append(f"  - {item.get('lesson')} (pending)")
        text = "\n".join(lines) if lines else "(no lessons learned yet)"
        return LearningRecall(
            prompt=f"Learning context for: {prompt}\n{text}",
            promoted=promoted,
            pending=pending,
        )

    def _emit(self, name: str, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        try:
            self._bus.publish(name, payload=payload)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 — the bus never breaks learning
            pass


def _merge_evidence(
    base: tuple, incoming: tuple
) -> tuple:
    """Union evidence by (method, uri, snippet) — dedupe, keep order."""
    seen: dict[tuple[str, str, str], Any] = {}
    for item in (*base, *incoming):
        key = (item.method, item.uri, item.snippet)
        seen.setdefault(key, item)
    return tuple(seen.values())


def build_learning_pipeline(
    root: Any,
    *,
    memory: MemoryProvider | None = None,
    bus: object | None = None,
    promote_threshold: float = LEARN_PROMOTE_THRESHOLD,
) -> LearningPipeline:
    """Factory — one root, one learning.db, one §13.3 pipeline.

    ``root`` — a path (str/Path) for the SQLite file, or the literal
    ``":memory:"``. Attach the §12 engine via ``memory=`` (the caller
    owns its construction — same root convention as
    ``build_memory_engine``).
    """
    from pathlib import Path

    if str(root) == ":memory:":
        store = SQLiteLearningStore(":memory:")
    else:
        path = Path(root)
        path.mkdir(parents=True, exist_ok=True)
        store = SQLiteLearningStore(path / "learning.db")
    return LearningPipeline(
        store,
        memory=memory,
        bus=bus,
        promote_threshold=promote_threshold,
    )
