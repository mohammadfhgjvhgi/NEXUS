"""NEXUS Learning System (New Plan §13 — PHASE 13).

*«يتذكر» ≠ «يتعلم»* — telling "it remembers" from "it learns".

========================  ======================================  ==========
Component                 Plan source                             Module
========================  ======================================  ==========
Experience kinds (six)    §13.1                                   contracts
Experience Extractor      §13.1                                   extractor
Learning Record           §13.2                                   contracts
SQLite learning index     §13.3 (Store)                           store
Learning Pipeline         §13.3                                   pipeline
Skill Candidate           §13.4                                   contracts
Workflow miner            §13.4                                   skills
Confidence rule           §13.3 stage 4                           contracts
letta-code reference      §13.5 (MODE D)                          docs only
prime-agent reference     §13.6 (MODE D/B)                        docs only
DSPy reference            §13.7 (MODE D, later)                   docs only
========================  ======================================  ==========

The §13.3 flow — ``Experience → Candidate lesson → Evidence check →
Confidence → Store → Future retrieval`` — runs end-to-end on
:class:`~nexus.learning.pipeline.LearningPipeline.absorb`, and the
promoted lessons land in the §12 Memory Engine (source ``"learning"``,
``conflict_key`` the lesson signature) so the §12.7 retrieval pipeline
already knows them for every future task. The §12.8 conflict ladder
stays in force: an old lesson never overrides the operator's *now*.

The external references (letta-code §13.5, prime-agent §13.6, DSPy
§13.7) were cloned + audited in ``vendor-staging/phase-13/`` — MODE
D/B, ideas documented in docs/REPOSITORY-INTEGRATION.md, zero imports
(Plan §61: *NEXUS owns Learning semantics*). DSPy's prompt/workflow
optimization is deliberately deferred (§13.7 says «مرحلة لاحقة» — a
later, methodical phase; see docs/DEFERRED-WORK.md).

نظام التعلّم — من «يتذكر» إلى «يتعلم»: مستخرج وخبرات وسجلات
وأنابيب وعدّاد مهارات، والدروس المعتمدة تدخل محرّك الذاكرة.

Stdlib only.
"""

from .contracts import (
    CONFIDENCE_CEILING,
    CONFIDENCE_FLOOR,
    EXPERIENCE_CONTAINERS,
    EXPERIENCE_KINDS,
    KIND_BASE_CONFIDENCE,
    LEARN_PROMOTE_THRESHOLD,
    LEARNING_RECORD_FIELDS,
    LEARNING_STATUSES,
    LESSON_MEMORY_TYPES,
    MIN_EVIDENCE_ITEMS,
    SKILL_MIN_REPEATS,
    SKILL_STATUSES,
    Experience,
    ExperienceKind,
    InvalidLearningError,
    LearningError,
    LearningRecord,
    SkillCandidate,
    confidence_for,
    evidence_methods_of,
    lesson_signature,
    new_learning_id,
    workflow_signature,
)
from .extractor import ExperienceExtractor, step_sequence_of
from .pipeline import (
    EVENT_RECORD_CREATED,
    EVENT_RECORD_PROMOTED,
    EVENT_RECORD_REFUSED,
    EVENT_SKILL_FOUND,
    LESSON_SCOPE_BY_KIND,
    LearningOutcome,
    LearningPipeline,
    LearningRecall,
    build_learning_pipeline,
)
from .skills import WorkflowMiner
from .store import SCHEMA_VERSION, SQLiteLearningStore

__all__ = [
    "CONFIDENCE_CEILING",
    "CONFIDENCE_FLOOR",
    "EXPERIENCE_KINDS",
    "EXPERIENCE_CONTAINERS",
    "KIND_BASE_CONFIDENCE",
    "LEARNING_RECORD_FIELDS",
    "LEARNING_STATUSES",
    "LEARN_PROMOTE_THRESHOLD",
    "LESSON_MEMORY_TYPES",
    "MIN_EVIDENCE_ITEMS",
    "SKILL_MIN_REPEATS",
    "SKILL_STATUSES",
    "SCHEMA_VERSION",
    "Experience",
    "ExperienceKind",
    "InvalidLearningError",
    "LearningError",
    "LearningRecord",
    "SkillCandidate",
    "confidence_for",
    "evidence_methods_of",
    "lesson_signature",
    "new_learning_id",
    "workflow_signature",
    "ExperienceExtractor",
    "step_sequence_of",
    "WorkflowMiner",
    "SQLiteLearningStore",
    "LearningOutcome",
    "LearningPipeline",
    "LearningRecall",
    "LESSON_SCOPE_BY_KIND",
    "EVENT_RECORD_CREATED",
    "EVENT_RECORD_PROMOTED",
    "EVENT_RECORD_REFUSED",
    "EVENT_SKILL_FOUND",
    "build_learning_pipeline",
]
