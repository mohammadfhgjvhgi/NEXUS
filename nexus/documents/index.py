"""The §18.2 *index* stage — documents become searchable, with provenance.

A real SQLite index (the §12.4 house pattern): one row per document,
one row per extracted text block, and an inverted ``postings`` table
(term → document · locator) so a search answers *where* the word
lives — ``page 3``, ``slide 2``, ``paragraph 7`` — not just whether.

The Windows law learned on the real box in phase 17 is built in: the
SQLite handle is a scarce resource, so ``close()`` is explicit and
the engine closes what it owns — an open handle keeps the file locked
(WinError 32) and breaks temp cleanup.

مرحلة الفهرسة — مستندات قابلة للبحث مع مصدر كل كلمة، فوق SQLite.

Stdlib only.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

from .contracts import ParsedDocument

_STOPWORDS = frozenset(
    """a an and are as at be by for from has have in is it its of on or that the
    this to was with عن في من على الى إلى ما هل هذا هذه التي الذي""".split()
)

_WORD_RE = re.compile(r"[\w]+", re.UNICODE)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    uri TEXT NOT NULL UNIQUE,
    kind TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    sha256 TEXT NOT NULL DEFAULT '',
    words INTEGER NOT NULL DEFAULT 0,
    parser TEXT NOT NULL DEFAULT '',
    ingested_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS blocks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    locator TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'body',
    text TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS postings (
    term TEXT NOT NULL,
    doc_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    block_id INTEGER NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    locator TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_postings_term ON postings(term);
CREATE INDEX IF NOT EXISTS idx_postings_doc ON postings(doc_id);
"""


def tokenize(text: str) -> list[str]:
    """Index tokens — lowercase words minus stopwords; numbers keep value."""
    return [
        w
        for w in (m.group(0) for m in _WORD_RE.finditer(text.lower()))
        if w not in _STOPWORDS and w.strip("_")
    ]


class DocumentIndex:
    """The §18.2 index — add parsed documents, search them back."""

    def __init__(self, path: str | Path | None = None) -> None:
        if path is None:
            self._conn = sqlite3.connect(":memory:", isolation_level=None)
        else:
            target = Path(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(target), isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.executescript(_SCHEMA)

    # ---------------------------------------------------------------- add

    def add(self, parsed: ParsedDocument) -> int:
        """Index one parsed document — re-ingest replaces (by uri)."""
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            row = self._conn.execute(
                "SELECT id FROM documents WHERE uri = ?", (parsed.uri,)
            ).fetchone()
            if row is not None:
                self._conn.execute(
                    "DELETE FROM documents WHERE id = ?", (row["id"],)
                )
            cursor = self._conn.execute(
                "INSERT INTO documents (uri, kind, title, sha256, words, parser, ingested_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    parsed.uri,
                    parsed.kind,
                    parsed.title,
                    parsed.sha256,
                    parsed.words(),
                    parsed.parser,
                    parsed.metadata.get("ingested_at", ""),
                ),
            )
            doc_id = int(cursor.lastrowid or 0)
            for block in parsed.blocks:
                bcur = self._conn.execute(
                    "INSERT INTO blocks (doc_id, locator, role, text) VALUES (?, ?, ?, ?)",
                    (doc_id, block.locator, block.role, block.text),
                )
                block_id = int(bcur.lastrowid or 0)
                for term in set(tokenize(block.text)):
                    self._conn.execute(
                        "INSERT INTO postings (term, doc_id, block_id, locator)"
                        " VALUES (?, ?, ?, ?)",
                        (term, doc_id, block_id, block.locator),
                    )
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return doc_id

    # ------------------------------------------------------------- search

    def search(self, query: str, *, limit: int = 10) -> list[dict[str, Any]]:
        """Search the index — ranked hits with document and locator."""
        terms = [t for t in tokenize(query) if t]
        if not terms:
            return []
        placeholders = ",".join("?" for _ in terms)
        rows = self._conn.execute(
            "SELECT p.doc_id, p.block_id, p.locator, d.uri, d.kind, d.title,"
            " SUM(1) AS hits, b.text AS block_text"
            f" FROM postings p JOIN documents d ON d.id = p.doc_id"
            f" JOIN blocks b ON b.id = p.block_id"
            f" WHERE p.term IN ({placeholders})"
            " GROUP BY p.block_id"
            " ORDER BY hits DESC, d.ingested_at DESC, p.locator"
            " LIMIT ?",
            (*terms, limit),
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            out.append(
                {
                    "doc_id": row["doc_id"],
                    "uri": row["uri"],
                    "kind": row["kind"],
                    "title": row["title"],
                    "locator": row["locator"],
                    "hits": row["hits"],
                    "snippet": (row["block_text"] or "")[:240],
                }
            )
        return out

    # -------------------------------------------------------------- stats

    def stats(self) -> dict[str, int]:
        documents = self._conn.execute("SELECT COUNT(*) c FROM documents").fetchone()
        blocks = self._conn.execute("SELECT COUNT(*) c FROM blocks").fetchone()
        postings = self._conn.execute("SELECT COUNT(*) c FROM postings").fetchone()
        return {
            "documents": int(documents["c"]),
            "blocks": int(blocks["c"]),
            "postings": int(postings["c"]),
        }

    # ------------------------------------------------------------- Window

    def close(self) -> None:
        """Release the SQLite handle — the WinError-32 law, kept."""
        self._conn.close()

    def __enter__(self) -> DocumentIndex:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
