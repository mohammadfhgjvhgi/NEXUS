"""SQLite memory index (New Plan §12.4 — Final Build Plan §13.3).

The structured half of the Memory System: one SQLite database holds

* ``memory_records``       — the §12.3 metadata (verbatim eleven) plus
                              the house seams, with soft-delete
                              tombstones for §12.9;
* ``memory_evidence``      — §12.1 provenance rows;
* ``memory_relationships`` — §13.1 ``link`` graph (record ↔ record);
* ``memory_audit``         — the §12.9 audit trail (forget keeps
                              metadata, drops content);
* ``memory_vectors``       — the local vector rows (float64 blobs) so
                              the semantic layer survives restarts in
                              the *same* single file (exit gate:
                              «Restart persistence ✅»).

Discipline: WAL mode, single connection, explicit transactions, ids
validated by the contracts layer before any SQL — the parameterized
statements below never interpolate user content. The database path is
operator-controlled (``<root>/memory/memory.db`` by default); ``:memory:``
is supported for tests.

فهرس SQLite — البيانات المهيكلة للذاكرة: السجلات والأدلة
والعلاقات وسجل التدقيق والمتجهات، كلها في ملف واحد ينجو من
إعادة التشغيل.

Stdlib only.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .contracts import (
    InvalidMemoryError,
    MemoryEvidence,
    MemoryNotFoundError,
    MemoryRecord,
    utc_now_iso,
)

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memory_records (
    id            TEXT PRIMARY KEY,
    type          TEXT NOT NULL,
    scope         TEXT NOT NULL,
    content       TEXT NOT NULL,
    source        TEXT NOT NULL,
    confidence    REAL NOT NULL DEFAULT 1.0,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    expires_at    TEXT,
    project       TEXT,
    workspace     TEXT,
    task          TEXT,
    session       TEXT,
    agent         TEXT,
    conflict_key  TEXT,
    active        INTEGER NOT NULL DEFAULT 1,
    forgotten_at  TEXT,
    forget_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_records_scope   ON memory_records (scope);
CREATE INDEX IF NOT EXISTS idx_records_task    ON memory_records (task);
CREATE INDEX IF NOT EXISTS idx_records_active  ON memory_records (active);
CREATE INDEX IF NOT EXISTS idx_records_conflict ON memory_records (conflict_key);

CREATE TABLE IF NOT EXISTS memory_evidence (
    record_id   TEXT NOT NULL,
    seq         INTEGER NOT NULL,
    method      TEXT NOT NULL,
    uri         TEXT NOT NULL DEFAULT '',
    snippet     TEXT NOT NULL DEFAULT '',
    captured_at TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (record_id, seq)
);

CREATE TABLE IF NOT EXISTS memory_relationships (
    record_id  TEXT NOT NULL,
    related_id TEXT NOT NULL,
    relation   TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (record_id, related_id, relation)
);
CREATE INDEX IF NOT EXISTS idx_rel_related ON memory_relationships (related_id);

CREATE TABLE IF NOT EXISTS memory_audit (
    audit_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    action       TEXT NOT NULL,
    record_id    TEXT,
    type         TEXT,
    scope        TEXT,
    source       TEXT,
    reason       TEXT NOT NULL DEFAULT '',
    requested_by TEXT NOT NULL DEFAULT 'operator',
    performed_at TEXT NOT NULL,
    detail       TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS memory_vectors (
    record_id     TEXT PRIMARY KEY,
    dim           INTEGER NOT NULL,
    vector        BLOB NOT NULL,
    payload       TEXT NOT NULL DEFAULT '{}'
);
"""


def _row_to_record(row: sqlite3.Row, evidence: Sequence[sqlite3.Row]) -> MemoryRecord:
    return MemoryRecord(
        id=row["id"],
        type=row["type"],
        scope=row["scope"],
        content=row["content"],
        source=row["source"],
        confidence=row["confidence"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        expires_at=row["expires_at"],
        project=row["project"],
        workspace=row["workspace"],
        task=row["task"],
        session=row["session"],
        agent=row["agent"],
        conflict_key=row["conflict_key"],
        evidence=tuple(
            MemoryEvidence(
                method=ev["method"],
                uri=ev["uri"],
                snippet=ev["snippet"],
                captured_at=ev["captured_at"],
            )
            for ev in evidence
        ),
        active=bool(row["active"]),
        forgotten_at=row["forgotten_at"],
        forget_reason=row["forget_reason"],
    )


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One §12.9 audit row (forget/expire/supersede history)."""

    audit_id: int
    action: str
    record_id: str | None
    type: str | None
    scope: str | None
    source: str | None
    reason: str
    requested_by: str
    performed_at: str
    detail: dict[str, Any]

    def redacted(self) -> dict[str, Any]:
        """Audit view — metadata only, content never leaves the audit."""
        return {
            "audit_id": self.audit_id,
            "action": self.action,
            "record_id": self.record_id,
            "type": self.type,
            "scope": self.scope,
            "reason": self.reason,
            "requested_by": self.requested_by,
            "performed_at": self.performed_at,
        }


class SQLiteMemoryStore:
    """The §12.4 index — metadata, relationships, audit and local vectors.

    All writes are transactional; the file is opened in WAL mode so a
    crash mid-write can never corrupt the index. Read paths are pure
    SELECTs; visibility (§12.2 ladder) is applied by the caller — the
    store only answers what is *stored*, the engine decides what is
    *visible* (separation of duties, tested both ways).
    """

    def __init__(self, path: str | Path = ":memory:") -> None:
        self.path = str(path)
        if self.path == ":memory:":
            self._conn = sqlite3.connect(":memory:", isolation_level=None)
        else:
            real = Path(self.path)
            real.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(real), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS memory_meta (key TEXT PRIMARY KEY, value TEXT)"
        )
        self._conn.execute(
            "INSERT OR IGNORE INTO memory_meta (key, value) VALUES ('schema', ?)",
            (str(SCHEMA_VERSION),),
        )

    # ------------------------------------------------------------ records

    def add_record(self, record: MemoryRecord) -> None:
        """Insert one record (with its evidence rows) atomically."""
        with self._transaction():
            self._conn.execute(
                """
                INSERT INTO memory_records (
                    id, type, scope, content, source, confidence,
                    created_at, updated_at, expires_at,
                    project, workspace, task, session, agent,
                    conflict_key, active, forgotten_at, forget_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.type,
                    record.scope,
                    record.content,
                    record.source,
                    record.confidence,
                    record.created_at,
                    record.updated_at,
                    record.expires_at,
                    record.project,
                    record.workspace,
                    record.task,
                    record.session,
                    record.agent,
                    record.conflict_key,
                    int(record.active),
                    record.forgotten_at,
                    record.forget_reason,
                ),
            )
            for seq, ev in enumerate(record.evidence):
                self._conn.execute(
                    """
                    INSERT INTO memory_evidence
                        (record_id, seq, method, uri, snippet, captured_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (record.id, seq, ev.method, ev.uri, ev.snippet, ev.captured_at),
                )

    def get_record(self, record_id: str) -> MemoryRecord:
        row = self._conn.execute(
            "SELECT * FROM memory_records WHERE id = ?", (record_id,)
        ).fetchone()
        if row is None:
            raise MemoryNotFoundError(f"no memory record {record_id!r}")
        evidence = self._conn.execute(
            "SELECT * FROM memory_evidence WHERE record_id = ? ORDER BY seq",
            (record_id,),
        ).fetchall()
        return _row_to_record(row, evidence)

    def update_record(
        self,
        record_id: str,
        *,
        content: str | None = None,
        confidence: float | None = None,
        expires_at: str | None = None,
    ) -> MemoryRecord:
        """Partial update — bumps updated_at, keeps everything else."""
        current = self.get_record(record_id)
        if not current.active:
            raise InvalidMemoryError(f"record {record_id} is forgotten — cannot update")
        new_content = content if content is not None else current.content
        new_confidence = confidence if confidence is not None else current.confidence
        new_expires = expires_at if expires_at is not None else current.expires_at
        if not new_content.strip():
            raise InvalidMemoryError("updated content must not be empty")
        if not 0.0 <= new_confidence <= 1.0:
            raise InvalidMemoryError(
                f"confidence must be within [0.0, 1.0], got {new_confidence}"
            )
        with self._transaction():
            self._conn.execute(
                """
                UPDATE memory_records
                SET content = ?, confidence = ?, expires_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    new_content,
                    new_confidence,
                    new_expires,
                    utc_now_iso(),
                    record_id,
                ),
            )
        return self.get_record(record_id)

    def iter_records(
        self, *, active_only: bool = True, scope: str | None = None
    ) -> Iterator[MemoryRecord]:
        """Scan records (order: created_at, id — deterministic)."""
        sql = "SELECT * FROM memory_records"
        clauses: list[str] = []
        params: list[Any] = []
        if active_only:
            clauses.append("active = 1")
        if scope is not None:
            clauses.append("scope = ?")
            params.append(scope)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at, id"
        for row in self._conn.execute(sql, params):
            evidence = self._conn.execute(
                "SELECT * FROM memory_evidence WHERE record_id = ? ORDER BY seq",
                (row["id"],),
            ).fetchall()
            yield _row_to_record(row, evidence)

    def lexical_search(
        self, needles: Sequence[str], *, limit: int = 64
    ) -> list[MemoryRecord]:
        """Lexical stage (§12.7) — substring scan over active records.

        Returns records whose content contains any needle, ranked by
        hit count then recency. Deterministic; never sees SQL.
        """
        if not needles:
            return []
        scored: list[tuple[int, str, MemoryRecord]] = []
        for record in self.iter_records(active_only=True):
            hay = record.content.lower()
            hits = sum(1 for n in needles if n and n in hay)
            if hits:
                scored.append((-hits, record.updated_at, record))
        scored.sort(key=lambda item: (item[0], item[1]))
        return [record for _, _, record in scored[:limit]]

    def count_records(self, *, active_only: bool = True) -> int:
        sql = "SELECT COUNT(*) AS n FROM memory_records"
        if active_only:
            sql += " WHERE active = 1"
        row = self._conn.execute(sql).fetchone()
        return int(row["n"])

    # ---------------------------------------------------- §12.9 tombstones

    def tombstone(
        self,
        record_ids: Iterable[str],
        *,
        action: str,
        reason: str,
        requested_by: str,
    ) -> int:
        """Soft-delete records + write audit rows; returns the count.

        Audit keeps the metadata (id/type/scope/source/reason/who/when);
        the *content* is dropped from the audit by design — §12.9
        «مع الحفاظ على audit metadata حيث يلزم».
        """
        ids = list(record_ids)
        if not ids:
            return 0
        now = utc_now_iso()
        with self._transaction():
            for record_id in ids:
                row = self._conn.execute(
                    "SELECT type, scope, source FROM memory_records WHERE id = ?",
                    (record_id,),
                ).fetchone()
                if row is None:
                    continue
                self._conn.execute(
                    """
                    UPDATE memory_records
                    SET active = 0, forgotten_at = ?, forget_reason = ?
                    WHERE id = ?
                    """,
                    (now, reason, record_id),
                )
                self._conn.execute(
                    """
                    INSERT INTO memory_audit (
                        action, record_id, type, scope, source,
                        reason, requested_by, performed_at, detail
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        action,
                        record_id,
                        row["type"],
                        row["scope"],
                        row["source"],
                        reason,
                        requested_by,
                        now,
                        json.dumps({"content_dropped": True}),
                    ),
                )
                self._conn.execute(
                    "DELETE FROM memory_vectors WHERE record_id = ?",
                    (record_id,),
                )
        return len(ids)

    def sweep_expired(self, now: str | None = None) -> list[str]:
        """Expire records whose expires_at passed — returns their ids."""
        moment = now or utc_now_iso()
        rows = self._conn.execute(
            """
            SELECT id FROM memory_records
            WHERE active = 1 AND expires_at IS NOT NULL AND expires_at < ?
            """,
            (moment,),
        ).fetchall()
        expired = [row["id"] for row in rows]
        if expired:
            self.tombstone(
                expired,
                action="expire",
                reason="expires_at passed",
                requested_by="system",
            )
        return expired

    def audit_log(self, *, limit: int = 100) -> list[AuditEntry]:
        rows = self._conn.execute(
            "SELECT * FROM memory_audit ORDER BY audit_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        entries = []
        for row in rows:
            try:
                detail = json.loads(row["detail"])
            except (json.JSONDecodeError, TypeError):
                detail = {}
            entries.append(
                AuditEntry(
                    audit_id=row["audit_id"],
                    action=row["action"],
                    record_id=row["record_id"],
                    type=row["type"],
                    scope=row["scope"],
                    source=row["source"],
                    reason=row["reason"],
                    requested_by=row["requested_by"],
                    performed_at=row["performed_at"],
                    detail=detail,
                )
            )
        return entries

    # ------------------------------------------------------ relationships

    def add_relationship(
        self, record_id: str, related_id: str, relation: str
    ) -> None:
        with self._transaction():
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memory_relationships (
                    record_id, related_id, relation, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (record_id, related_id, relation, utc_now_iso()),
            )

    def links_of(self, record_id: str) -> list[dict[str, str]]:
        rows = self._conn.execute(
            """
            SELECT record_id, related_id, relation, created_at
            FROM memory_relationships
            WHERE record_id = ? OR related_id = ?
            ORDER BY created_at
            """,
            (record_id, record_id),
        ).fetchall()
        return [dict(row) for row in rows]

    def count_relationships(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM memory_relationships"
        ).fetchone()
        return int(row["n"])

    # ------------------------------------------- local vector persistence

    def upsert_vector(
        self, record_id: str, vector: Sequence[float], payload: dict[str, Any]
    ) -> None:
        import array

        arr = array.array("d", vector)
        with self._transaction():
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memory_vectors
                    (record_id, dim, vector, payload)
                VALUES (?, ?, ?, ?)
                """,
                (record_id, len(vector), arr.tobytes(), json.dumps(payload)),
            )

    def get_vector(self, record_id: str) -> tuple[list[float], dict[str, Any]]:
        import array

        row = self._conn.execute(
            "SELECT dim, vector, payload FROM memory_vectors WHERE record_id = ?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise MemoryNotFoundError(f"no vector for {record_id!r}")
        arr = array.array("d")
        arr.frombytes(row["vector"])
        values = list(arr)
        if len(values) != row["dim"]:
            raise MemoryError(
                f"vector dim mismatch for {record_id}: {len(values)} != {row['dim']}"
            )
        return values, json.loads(row["payload"])

    def iter_vectors(self) -> Iterator[tuple[str, list[float], dict[str, Any]]]:
        import array

        rows = self._conn.execute(
            "SELECT record_id, dim, vector, payload FROM memory_vectors "
            "ORDER BY record_id"
        ).fetchall()
        for row in rows:
            arr = array.array("d")
            arr.frombytes(row["vector"])
            values = list(arr)
            if len(values) != row["dim"]:
                raise MemoryError(
                    f"vector dim mismatch for {row['record_id']}: "
                    f"{len(values)} != {row['dim']}"
                )
            yield row["record_id"], values, json.loads(row["payload"])

    def delete_vector(self, record_id: str) -> None:
        with self._transaction():
            self._conn.execute(
                "DELETE FROM memory_vectors WHERE record_id = ?", (record_id,)
            )

    def count_vectors(self) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM memory_vectors"
        ).fetchone()
        return int(row["n"])

    # ------------------------------------------------------------ plumbing

    def close(self) -> None:
        self._conn.close()

    class _Transaction:
        def __init__(self, conn: sqlite3.Connection) -> None:
            self._conn = conn

        def __enter__(self) -> sqlite3.Connection:
            self._conn.execute("BEGIN IMMEDIATE")
            return self._conn

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            if exc_type is None:
                self._conn.execute("COMMIT")
            else:
                self._conn.execute("ROLLBACK")

    def _transaction(self) -> SQLiteMemoryStore._Transaction:
        return SQLiteMemoryStore._Transaction(self._conn)
