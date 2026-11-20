"""SQLite learning index (New Plan §13.2 / §13.3 stage 5 — Store).

Four tables, one file, restart-proof:

* ``experiences``      — the raw §13.1 audit trail (nothing learned is
                          ever lost, even when refused).
* ``learning_records`` — the §13.2 records, deduped by ``signature``
                          (occurrences merge — repetition is signal).
* ``task_sequences``   — every observed task's step sequence (the
                          §13.4 miner's raw material).
* ``skill_candidates`` — the §13.4 candidates with their evidence.

The store is NEXUS-native (Plan §61: *NEXUS owns Learning semantics*),
the SQLite shape mirrors the §12.4 house style (one file, WAL, JSON
columns for evidence, ISO timestamps, deterministic ids for tests),
and promotion into the Memory Engine is a *link* (``memory_id``), not
a copy of the engine's semantics.

فهرس SQLite للتعلّم — الخبرات والسجلات وتسلسلات المهام ومرشحو
المهارة، ملف واحد ينجو من إعادة التشغيل.

Stdlib only.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from nexus.memory.contracts import MemoryEvidence

from .contracts import (
    LEARNING_STATUSES,
    SKILL_STATUSES,
    Experience,
    LearningRecord,
    SkillCandidate,
    lesson_signature,
    utc_now_iso,
)

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS experiences (
    id          TEXT PRIMARY KEY,
    kind        TEXT NOT NULL,
    task_id     TEXT NOT NULL,
    summary     TEXT NOT NULL,
    evidence    TEXT NOT NULL DEFAULT '[]',
    project     TEXT,
    workspace   TEXT,
    task        TEXT,
    session     TEXT,
    agent       TEXT,
    occurred_at TEXT NOT NULL,
    payload     TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_experiences_task ON experiences(task_id);
CREATE INDEX IF NOT EXISTS idx_experiences_kind ON experiences(kind);

CREATE TABLE IF NOT EXISTS learning_records (
    id             TEXT PRIMARY KEY,
    experience_id  TEXT NOT NULL,
    lesson         TEXT NOT NULL,
    source_task    TEXT NOT NULL,
    evidence       TEXT NOT NULL DEFAULT '[]',
    confidence     REAL NOT NULL,
    scope          TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'pending',
    occurrences    INTEGER NOT NULL DEFAULT 1,
    signature      TEXT NOT NULL UNIQUE,
    memory_id      TEXT,
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    project        TEXT,
    workspace      TEXT,
    task           TEXT,
    session        TEXT,
    agent          TEXT
);
CREATE INDEX IF NOT EXISTS idx_learning_status ON learning_records(status);

CREATE TABLE IF NOT EXISTS task_sequences (
    task_id      TEXT PRIMARY KEY,
    sequence     TEXT NOT NULL,
    project      TEXT,
    workspace    TEXT,
    task         TEXT,
    session      TEXT,
    agent        TEXT,
    observed_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS skill_candidates (
    id            TEXT PRIMARY KEY,
    pattern       TEXT NOT NULL UNIQUE,
    steps         TEXT NOT NULL,
    occurrences   INTEGER NOT NULL,
    evidence      TEXT NOT NULL DEFAULT '[]',
    confidence    REAL NOT NULL,
    status        TEXT NOT NULL DEFAULT 'candidate',
    source_tasks  TEXT NOT NULL DEFAULT '[]',
    memory_id     TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
"""


def _rows_to_evidence(blob: str) -> tuple[MemoryEvidence, ...]:
    return tuple(
        MemoryEvidence(
            method=row.get("method", "tool_run"),
            uri=row.get("uri", ""),
            snippet=row.get("snippet", ""),
            captured_at=row.get("captured_at", ""),
        )
        for row in json.loads(blob or "[]")
    )


def _evidence_to_rows(items: tuple[MemoryEvidence, ...]) -> str:
    return json.dumps(
        [
            {
                "method": e.method,
                "uri": e.uri,
                "snippet": e.snippet,
                "captured_at": e.captured_at,
            }
            for e in items
        ],
        ensure_ascii=False,
    )


class SQLiteLearningStore:
    """The §13.2/§13.3 persistence — stdlib sqlite3, one file, WAL."""

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path == ":memory:":
            self._conn = sqlite3.connect(":memory:")
        else:
            root = Path(self.path)
            if root.parent and str(root.parent):
                root.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------- experiences

    def add_experience(self, experience: Experience) -> None:
        """Append one raw experience to the audit trail."""
        self._conn.execute(
            """
            INSERT OR REPLACE INTO experiences
            (id, kind, task_id, summary, evidence, project, workspace,
             task, session, agent, occurred_at, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experience.id,
                experience.kind,
                experience.task_id,
                experience.summary,
                _evidence_to_rows(experience.evidence),
                experience.project,
                experience.workspace,
                experience.task,
                experience.session,
                experience.agent,
                experience.occurred_at,
                json.dumps(experience.payload or {}, ensure_ascii=False),
            ),
        )
        self._conn.commit()

    def get_experience(self, experience_id: str) -> Experience | None:
        row = self._conn.execute(
            "SELECT * FROM experiences WHERE id = ?", (experience_id,)
        ).fetchone()
        if row is None:
            return None
        return Experience(
            id=row["id"],
            kind=row["kind"],
            task_id=row["task_id"],
            summary=row["summary"],
            evidence=_rows_to_evidence(row["evidence"]),
            project=row["project"],
            workspace=row["workspace"],
            task=row["task"],
            session=row["session"],
            agent=row["agent"],
            occurred_at=row["occurred_at"],
            payload=json.loads(row["payload"] or "{}"),
        )

    def count_experiences(self, kind: str | None = None) -> int:
        if kind:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM experiences WHERE kind = ?", (kind,)
            ).fetchone()
        else:
            row = self._conn.execute("SELECT COUNT(*) AS n FROM experiences").fetchone()
        return int(row["n"])

    # -------------------------------------------------- learning records

    def find_by_signature(self, signature: str) -> LearningRecord | None:
        row = self._conn.execute(
            "SELECT * FROM learning_records WHERE signature = ?", (signature,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def add_record(self, record: LearningRecord) -> LearningRecord:
        """Insert a fresh §13.2 record (signature must be new)."""
        self._conn.execute(
            """
            INSERT INTO learning_records
            (id, experience_id, lesson, source_task, evidence, confidence,
             scope, status, occurrences, signature, memory_id,
             created_at, updated_at, project, workspace, task, session, agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            self._record_row_values(record),
        )
        self._conn.commit()
        return record

    def update_record(self, record: LearningRecord) -> LearningRecord:
        """Persist a merged/recomputed record (same id)."""
        record.updated_at = utc_now_iso()
        self._conn.execute(
            """
            UPDATE learning_records SET
                lesson = ?, source_task = ?, evidence = ?, confidence = ?,
                scope = ?, status = ?, occurrences = ?, memory_id = ?,
                updated_at = ?, project = ?, workspace = ?, task = ?,
                session = ?, agent = ?
            WHERE id = ?
            """,
            (
                record.lesson,
                record.source_task,
                _evidence_to_rows(record.evidence),
                record.confidence,
                record.scope,
                record.status,
                record.occurrences,
                record.memory_id,
                record.updated_at,
                record.project,
                record.workspace,
                record.task,
                record.session,
                record.agent,
                record.id,
            ),
        )
        self._conn.commit()
        return record

    def get_record(self, record_id: str) -> LearningRecord | None:
        row = self._conn.execute(
            "SELECT * FROM learning_records WHERE id = ?", (record_id,)
        ).fetchone()
        return self._row_to_record(row) if row else None

    def list_records(
        self,
        *,
        status: str | None = None,
        scope: str | None = None,
        promoted_only: bool = False,
    ) -> list[LearningRecord]:
        """Records in id order — filters compose."""
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        if promoted_only:
            clauses.append("memory_id IS NOT NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM learning_records {where} ORDER BY created_at, id",
            params,
        ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def search_lessons(self, text: str, *, limit: int = 10) -> list[LearningRecord]:
        """Lexical lesson search — the pending-layer recall (§13.3's
        «Future retrieval» for lessons not yet promoted)."""
        needle = text.strip().casefold()
        if not needle:
            return []
        rows = self._conn.execute(
            "SELECT * FROM learning_records ORDER BY updated_at DESC"
        ).fetchall()
        hits = []
        for row in rows:
            lesson = str(row["lesson"]).casefold()
            if needle in lesson or any(
                word and word in lesson for word in needle.split()
            ):
                hits.append(self._row_to_record(row))
            if len(hits) >= limit:
                break
        return hits

    # --------------------------------------------------- task sequences

    def record_sequence(
        self,
        task_id: str,
        sequence: tuple[str, ...],
        *,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        agent: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT OR REPLACE INTO task_sequences
            (task_id, sequence, project, workspace, task, session, agent, observed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                json.dumps(list(sequence)),
                project,
                workspace,
                task,
                session,
                agent,
                utc_now_iso(),
            ),
        )
        self._conn.commit()

    def all_sequences(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT * FROM task_sequences ORDER BY observed_at, task_id"
        ).fetchall()
        return [
            {
                "task_id": r["task_id"],
                "sequence": tuple(json.loads(r["sequence"])),
                "project": r["project"],
                "workspace": r["workspace"],
                "task": r["task"],
                "session": r["session"],
                "agent": r["agent"],
            }
            for r in rows
        ]

    # -------------------------------------------------- skill candidates

    def find_skill(self, pattern: str) -> SkillCandidate | None:
        row = self._conn.execute(
            "SELECT * FROM skill_candidates WHERE pattern = ?", (pattern,)
        ).fetchone()
        return self._row_to_skill(row) if row else None

    def add_skill(self, candidate: SkillCandidate) -> SkillCandidate:
        self._conn.execute(
            """
            INSERT INTO skill_candidates
            (id, pattern, steps, occurrences, evidence, confidence, status,
             source_tasks, memory_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                candidate.id,
                candidate.pattern,
                json.dumps(list(candidate.steps)),
                candidate.occurrences,
                _evidence_to_rows(candidate.evidence),
                candidate.confidence,
                candidate.status,
                json.dumps(list(candidate.source_tasks)),
                candidate.memory_id,
                candidate.created_at,
                candidate.updated_at,
            ),
        )
        self._conn.commit()
        return candidate

    def update_skill(self, candidate: SkillCandidate) -> SkillCandidate:
        candidate.updated_at = utc_now_iso()
        self._conn.execute(
            """
            UPDATE skill_candidates SET
                occurrences = ?, evidence = ?, confidence = ?, status = ?,
                source_tasks = ?, memory_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                candidate.occurrences,
                _evidence_to_rows(candidate.evidence),
                candidate.confidence,
                candidate.status,
                json.dumps(list(candidate.source_tasks)),
                candidate.memory_id,
                candidate.updated_at,
                candidate.id,
            ),
        )
        self._conn.commit()
        return candidate

    def list_skills(self, *, status: str | None = None) -> list[SkillCandidate]:
        if status:
            rows = self._conn.execute(
                "SELECT * FROM skill_candidates WHERE status = ? ORDER BY created_at",
                (status,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM skill_candidates ORDER BY created_at"
            ).fetchall()
        return [self._row_to_skill(r) for r in rows]

    # ----------------------------------------------------------- plumbing

    def _record_row_values(self, record: LearningRecord) -> tuple[Any, ...]:
        return (
            record.id,
            record.experience_id,
            record.lesson,
            record.source_task,
            _evidence_to_rows(record.evidence),
            record.confidence,
            record.scope,
            record.status,
            record.occurrences,
            record.signature or lesson_signature(record.lesson, record.scope),
            record.memory_id,
            record.created_at,
            record.updated_at,
            record.project,
            record.workspace,
            record.task,
            record.session,
            record.agent,
        )

    def _row_to_record(self, row: sqlite3.Row) -> LearningRecord:
        return LearningRecord(
            id=row["id"],
            experience_id=row["experience_id"],
            lesson=row["lesson"],
            source_task=row["source_task"],
            evidence=_rows_to_evidence(row["evidence"]),
            confidence=float(row["confidence"]),
            scope=row["scope"],
            status=row["status"],
            occurrences=int(row["occurrences"]),
            signature=row["signature"],
            memory_id=row["memory_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            project=row["project"],
            workspace=row["workspace"],
            task=row["task"],
            session=row["session"],
            agent=row["agent"],
        )

    def _row_to_skill(self, row: sqlite3.Row) -> SkillCandidate:
        return SkillCandidate(
            id=row["id"],
            pattern=row["pattern"],
            steps=tuple(json.loads(row["steps"])),
            occurrences=int(row["occurrences"]),
            evidence=_rows_to_evidence(row["evidence"]),
            confidence=float(row["confidence"]),
            status=row["status"],
            source_tasks=tuple(json.loads(row["source_tasks"])),
            memory_id=row["memory_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def backend(self) -> dict[str, Any]:
        """Introspection — the honest report of what persists where."""
        return {
            "backend": "sqlite",
            "path": self.path,
            "schema_version": SCHEMA_VERSION,
            "valid_statuses": LEARNING_STATUSES,
            "valid_skill_statuses": SKILL_STATUSES,
            "counts": {
                "experiences": self.count_experiences(),
                "learning_records": len(self.list_records()),
                "task_sequences": len(self.all_sequences()),
                "skill_candidates": len(self.list_skills()),
            },
        }

    def close(self) -> None:
        """Release the file handle (the §12 lesson: folders lock)."""
        self._conn.close()

    def __enter__(self) -> SQLiteLearningStore:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
