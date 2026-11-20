"""Code-intelligence store (New Plan §14.1 / §14.2 / §14.4–§14.6).

One SQLite file — ``codeintel.db`` — holds the whole §14 state:

* ``files``          — the §14.1 File Index (path · language · size ·
                       mtime · sha · lines · is_test).
* ``symbols``        — the §14.2 Symbol Index (definitions).
* ``references``     — symbol uses, later resolved to project files.
* ``dep_edges``      — §14.4 Dependency Graph edges.
* ``api_endpoints``  — §14.5 API Graph.
* ``test_links``     — §14.6 Test Graph.
* ``index_meta``     — root · schema version · last scan · engine.

WAL journal, explicit transactions, upsert semantics, atomic
``replace_file_*`` (delete + insert in one transaction) — the house
SQLite pattern since PHASE 2. The store is restart-persistent by
construction: a new engine over the same file sees the same index.

مخزن ذكاء الكود — فهرس واحد SQLite لكل شيء: الملفات والرموز
والمراجع وحواف التبعية ونقاط الـAPI وروابط الاختبار.

Stdlib only.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from .contracts import (
    ApiEndpoint,
    DependencyEdge,
    FileEntry,
    IndexStats,
    Symbol,
    SymbolReference,
    TestLink,
    normalize_path,
    utc_now_iso,
)

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS files (
    path        TEXT PRIMARY KEY,
    language    TEXT NOT NULL DEFAULT '',
    size        INTEGER NOT NULL DEFAULT 0,
    mtime       REAL NOT NULL DEFAULT 0.0,
    sha         TEXT NOT NULL DEFAULT '',
    lines       INTEGER NOT NULL DEFAULT 0,
    is_test     INTEGER NOT NULL DEFAULT 0,
    is_parsed   INTEGER NOT NULL DEFAULT 0,
    engine      TEXT NOT NULL DEFAULT '',
    indexed_at  TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_files_language ON files (language);

CREATE TABLE IF NOT EXISTS symbols (
    symbol_id  TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    qualified  TEXT NOT NULL,
    kind       TEXT NOT NULL,
    file       TEXT NOT NULL,
    line       INTEGER NOT NULL,
    end_line   INTEGER NOT NULL DEFAULT 0,
    signature  TEXT NOT NULL DEFAULT '',
    container  TEXT NOT NULL DEFAULT '',
    language   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_symbols_name  ON symbols (name);
CREATE INDEX IF NOT EXISTS idx_symbols_file  ON symbols (file);
CREATE INDEX IF NOT EXISTS idx_symbols_kind  ON symbols (kind);
CREATE INDEX IF NOT EXISTS idx_symbols_qual  ON symbols (qualified);

CREATE TABLE IF NOT EXISTS symbol_references (
    rowid_ref     INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    file          TEXT NOT NULL,
    line          INTEGER NOT NULL DEFAULT 0,
    resolved_file TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_refs_name ON symbol_references (name);
CREATE INDEX IF NOT EXISTS idx_refs_file ON symbol_references (file);
CREATE INDEX IF NOT EXISTS idx_refs_resolved ON symbol_references (resolved_file);

CREATE TABLE IF NOT EXISTS dep_edges (
    source      TEXT NOT NULL,
    target      TEXT NOT NULL,
    kind        TEXT NOT NULL,
    import_spec TEXT NOT NULL,
    PRIMARY KEY (source, target, import_spec)
);
CREATE INDEX IF NOT EXISTS idx_edges_source ON dep_edges (source);
CREATE INDEX IF NOT EXISTS idx_edges_target ON dep_edges (target);

CREATE TABLE IF NOT EXISTS api_endpoints (
    method    TEXT NOT NULL DEFAULT '',
    path      TEXT NOT NULL,
    file      TEXT NOT NULL,
    handler   TEXT NOT NULL DEFAULT '',
    line      INTEGER NOT NULL DEFAULT 0,
    framework TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (file, line, method, path)
);

CREATE TABLE IF NOT EXISTS test_links (
    test_file TEXT NOT NULL,
    target    TEXT NOT NULL,
    via       TEXT NOT NULL DEFAULT 'import',
    tests     INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (test_file, target)
);

CREATE TABLE IF NOT EXISTS index_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


class SQLiteCodeIntelStore:
    """The §14 persistence — one file, seven tables, restart-safe."""

    def __init__(self, db_path: str | Path) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(self._path))
        self._db.row_factory = sqlite3.Row
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.execute("PRAGMA synchronous=NORMAL")
        self._db.executescript(_SCHEMA)
        self._db.commit()
        self.set_meta("schema_version", str(SCHEMA_VERSION))

    # ------------------------------------------------------------ meta

    def set_meta(self, key: str, value: str) -> None:
        self._db.execute(
            "INSERT INTO index_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._db.commit()

    def get_meta(self, key: str) -> str:
        row = self._db.execute(
            "SELECT value FROM index_meta WHERE key = ?", (key,)
        ).fetchone()
        return str(row["value"]) if row is not None else ""

    # ------------------------------------------------- §14.1 file index

    def upsert_file(
        self,
        entry: FileEntry,
        *,
        is_test: bool = False,
        is_parsed: bool = False,
        engine: str = "",
    ) -> None:
        entry.validate()
        self._db.execute(
            """
            INSERT INTO files (path, language, size, mtime, sha, lines, is_test,
                               is_parsed, engine, indexed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path) DO UPDATE SET
                language = excluded.language,
                size = excluded.size,
                mtime = excluded.mtime,
                sha = excluded.sha,
                lines = excluded.lines,
                is_test = excluded.is_test,
                is_parsed = excluded.is_parsed,
                engine = excluded.engine,
                indexed_at = excluded.indexed_at
            """,
            (
                entry.path,
                entry.language,
                entry.size,
                entry.mtime,
                entry.sha,
                entry.lines,
                int(is_test),
                int(is_parsed),
                engine,
                entry.indexed_at or utc_now_iso(),
            ),
        )
        self._db.commit()

    def upsert_files(self, rows: Sequence[tuple[FileEntry, bool, bool, str]]) -> None:
        """Batched upsert — one transaction (§14.11 batching)."""
        payload = [
            (
                entry.path,
                entry.language,
                entry.size,
                entry.mtime,
                entry.sha,
                entry.lines,
                int(is_test),
                int(is_parsed),
                engine,
                entry.indexed_at or utc_now_iso(),
            )
            for entry, is_test, is_parsed, engine in rows
        ]
        with self._db:
            self._db.executemany(
                """
                INSERT INTO files (path, language, size, mtime, sha, lines, is_test,
                                   is_parsed, engine, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(path) DO UPDATE SET
                    language = excluded.language,
                    size = excluded.size,
                    mtime = excluded.mtime,
                    sha = excluded.sha,
                    lines = excluded.lines,
                    is_test = excluded.is_test,
                    is_parsed = excluded.is_parsed,
                    engine = excluded.engine,
                    indexed_at = excluded.indexed_at
                """,
                payload,
            )

    def get_file(self, path: str) -> FileEntry | None:
        row = self._db.execute(
            "SELECT * FROM files WHERE path = ?", (normalize_path(path),)
        ).fetchone()
        if row is None:
            return None
        return FileEntry(
            path=row["path"],
            language=row["language"],
            size=row["size"],
            mtime=row["mtime"],
            sha=row["sha"],
            lines=row["lines"],
            indexed_at=row["indexed_at"],
        )

    def file_flags(self, path: str) -> tuple[bool, bool, str]:
        """``(is_test, is_parsed, engine)`` for one indexed file."""
        row = self._db.execute(
            "SELECT is_test, is_parsed, engine FROM files WHERE path = ?",
            (normalize_path(path),),
        ).fetchone()
        if row is None:
            return (False, False, "")
        return (bool(row["is_test"]), bool(row["is_parsed"]), str(row["engine"]))

    def all_files(self) -> list[FileEntry]:
        rows = self._db.execute(
            "SELECT path, language, size, mtime, sha, lines, indexed_at FROM files"
        ).fetchall()
        return [
            FileEntry(
                path=row["path"],
                language=row["language"],
                size=row["size"],
                mtime=row["mtime"],
                sha=row["sha"],
                lines=row["lines"],
                indexed_at=row["indexed_at"],
            )
            for row in rows
        ]

    def delete_file(self, path: str) -> None:
        norm = normalize_path(path)
        with self._db:
            self._db.execute("DELETE FROM files WHERE path = ?", (norm,))
            self._db.execute("DELETE FROM symbols WHERE file = ?", (norm,))
            self._db.execute("DELETE FROM symbol_references WHERE file = ?", (norm,))
            self._db.execute(
                "DELETE FROM dep_edges WHERE source = ? OR target = ?", (norm, norm)
            )
            self._db.execute("DELETE FROM api_endpoints WHERE file = ?", (norm,))
            self._db.execute(
                "DELETE FROM test_links WHERE test_file = ? OR target = ?", (norm, norm)
            )

    def known_paths(self) -> set[str]:
        rows = self._db.execute("SELECT path FROM files").fetchall()
        return {str(row["path"]) for row in rows}

    def parsed_paths(self) -> set[str]:
        rows = self._db.execute(
            "SELECT path FROM files WHERE is_parsed = 1"
        ).fetchall()
        return {str(row["path"]) for row in rows}

    def test_paths(self) -> set[str]:
        rows = self._db.execute("SELECT path FROM files WHERE is_test = 1").fetchall()
        return {str(row["path"]) for row in rows}

    # ---------------------------------------------- §14.2 symbol index

    def replace_file_symbols(self, path: str, symbols: Iterable[Symbol]) -> None:
        """Atomic delete + insert — the §14.12 symbol update."""
        norm = normalize_path(path)
        payload = [
            (
                sym.symbol_id,
                sym.name,
                sym.qualified,
                sym.kind,
                norm,
                sym.line,
                sym.end_line,
                sym.signature,
                sym.container,
                sym.language,
            )
            for sym in symbols
        ]
        with self._db:
            self._db.execute("DELETE FROM symbols WHERE file = ?", (norm,))
            self._db.executemany(
                """
                INSERT INTO symbols (symbol_id, name, qualified, kind, file, line,
                                     end_line, signature, container, language)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )

    def search_symbols(
        self,
        query: str = "",
        kind: str = "",
        file: str = "",
        limit: int = 50,
    ) -> list[Symbol]:
        """Substring name search with optional kind/file filters."""
        clauses: list[str] = []
        params: list[Any] = []
        if query:
            clauses.append("name LIKE ?")
            params.append(f"%{query}%")
        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if file:
            clauses.append("file = ?")
            params.append(normalize_path(file))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(max(1, limit))
        rows = self._db.execute(
            "SELECT * FROM symbols" + where + " ORDER BY file, line LIMIT ?",
            params,
        ).fetchall()
        return [self._row_to_symbol(row) for row in rows]

    def file_symbols(self, path: str) -> list[Symbol]:
        rows = self._db.execute(
            "SELECT * FROM symbols WHERE file = ? ORDER BY line",
            (normalize_path(path),),
        ).fetchall()
        return [self._row_to_symbol(row) for row in rows]

    def symbols_by_name(self, name: str) -> list[Symbol]:
        rows = self._db.execute(
            "SELECT * FROM symbols WHERE name = ? ORDER BY file, line", (name,)
        ).fetchall()
        return [self._row_to_symbol(row) for row in rows]

    @staticmethod
    def _row_to_symbol(row: sqlite3.Row) -> Symbol:
        return Symbol(
            symbol_id=str(row["symbol_id"]),
            name=str(row["name"]),
            qualified=str(row["qualified"]),
            kind=str(row["kind"]),
            file=str(row["file"]),
            line=int(row["line"]),
            end_line=int(row["end_line"]),
            signature=str(row["signature"]),
            container=str(row["container"]),
            language=str(row["language"]),
        )

    # ----------------------------------------------------- references

    def replace_file_references(
        self, path: str, references: Iterable[SymbolReference]
    ) -> None:
        norm = normalize_path(path)
        payload = [
            (ref.name, norm, ref.line, ref.resolved_file) for ref in references
        ]
        with self._db:
            self._db.execute("DELETE FROM symbol_references WHERE file = ?", (norm,))
            self._db.executemany(
                "INSERT INTO symbol_references (name, file, line, resolved_file) "
                "VALUES (?, ?, ?, ?)",
                payload,
            )

    def definition_map(self) -> dict[str, set[str]]:
        """name → set of files defining it (the resolution table)."""
        rows = self._db.execute(
            "SELECT name, file FROM symbols"
        ).fetchall()
        table: dict[str, set[str]] = {}
        for row in rows:
            table.setdefault(str(row["name"]), set()).add(str(row["file"]))
        return table

    def unresolved_references(self) -> list[SymbolReference]:
        rows = self._db.execute(
            "SELECT name, file, line, resolved_file FROM symbol_references "
            "WHERE resolved_file = ''"
        ).fetchall()
        return [
            SymbolReference(
                name=str(row["name"]),
                file=str(row["file"]),
                line=int(row["line"]),
                resolved_file=str(row["resolved_file"]),
            )
            for row in rows
        ]

    def set_reference_resolutions(
        self, resolutions: Iterable[tuple[str, str, int, str]]
    ) -> None:
        """``(name, file, line, resolved_file)`` rows — resolve in place."""
        with self._db:
            self._db.executemany(
                "UPDATE symbol_references SET resolved_file = ? WHERE name = ? AND file = ? "
                "AND line = ?",
                [
                    (resolved, name, file, line)
                    for name, file, line, resolved in resolutions
                ],
            )

    def reference_counts(self) -> dict[str, int]:
        """name → how many times it is used (map ranking weight)."""
        rows = self._db.execute(
            "SELECT name, COUNT(*) AS n FROM symbol_references GROUP BY name"
        ).fetchall()
        return {str(row["name"]): int(row["n"]) for row in rows}

    def reference_edges(self) -> list[tuple[str, str, int]]:
        """``(from_file, to_file, weight)`` — the §14.8 graph raw data."""
        rows = self._db.execute(
            "SELECT file, resolved_file, COUNT(*) AS n FROM symbol_references "
            "WHERE resolved_file != '' AND resolved_file != file "
            "GROUP BY file, resolved_file"
        ).fetchall()
        return [
            (str(row["file"]), str(row["resolved_file"]), int(row["n"]))
            for row in rows
        ]

    # ------------------------------------------------- §14.4 dep edges

    def replace_file_edges(self, path: str, edges: Iterable[DependencyEdge]) -> None:
        norm = normalize_path(path)
        payload = [
            (norm, edge.target, edge.kind, edge.import_spec)
            for edge in edges
        ]
        with self._db:
            self._db.execute("DELETE FROM dep_edges WHERE source = ?", (norm,))
            self._db.executemany(
                "INSERT OR REPLACE INTO dep_edges (source, target, kind, import_spec) "
                "VALUES (?, ?, ?, ?)",
                payload,
            )

    def all_edges(self) -> list[DependencyEdge]:
        rows = self._db.execute(
            "SELECT source, target, kind, import_spec FROM dep_edges"
        ).fetchall()
        return [
            DependencyEdge(
                source=str(row["source"]),
                target=str(row["target"]),
                kind=str(row["kind"]),
                import_spec=str(row["import_spec"]),
            )
            for row in rows
        ]

    def edges_from(self, path: str) -> list[DependencyEdge]:
        rows = self._db.execute(
            "SELECT source, target, kind, import_spec FROM dep_edges WHERE source = ?",
            (normalize_path(path),),
        ).fetchall()
        return [
            DependencyEdge(
                source=str(row["source"]),
                target=str(row["target"]),
                kind=str(row["kind"]),
                import_spec=str(row["import_spec"]),
            )
            for row in rows
        ]

    def edges_to(self, path: str) -> list[DependencyEdge]:
        rows = self._db.execute(
            "SELECT source, target, kind, import_spec FROM dep_edges WHERE target = ?",
            (normalize_path(path),),
        ).fetchall()
        return [
            DependencyEdge(
                source=str(row["source"]),
                target=str(row["target"]),
                kind=str(row["kind"]),
                import_spec=str(row["import_spec"]),
            )
            for row in rows
        ]

    def adjacency(self) -> dict[str, list[str]]:
        """source → targets (the §14.4 graph as one dict)."""
        rows = self._db.execute(
            "SELECT source, target FROM dep_edges"
        ).fetchall()
        graph: dict[str, list[str]] = {}
        for row in rows:
            graph.setdefault(str(row["source"]), []).append(str(row["target"]))
        return graph

    # ------------------------------------------------- §14.5 api graph

    def replace_file_endpoints(
        self, path: str, endpoints: Iterable[ApiEndpoint]
    ) -> None:
        norm = normalize_path(path)
        payload = [
            (
                endpoint.method,
                endpoint.path,
                norm,
                endpoint.handler,
                endpoint.line,
                endpoint.framework,
            )
            for endpoint in endpoints
        ]
        with self._db:
            self._db.execute("DELETE FROM api_endpoints WHERE file = ?", (norm,))
            self._db.executemany(
                "INSERT OR REPLACE INTO api_endpoints (method, path, file, handler, "
                "line, framework) VALUES (?, ?, ?, ?, ?, ?)",
                payload,
            )

    def all_endpoints(self) -> list[ApiEndpoint]:
        rows = self._db.execute(
            "SELECT method, path, file, handler, line, framework FROM api_endpoints "
            "ORDER BY path, method"
        ).fetchall()
        return [
            ApiEndpoint(
                method=str(row["method"]),
                path=str(row["path"]),
                file=str(row["file"]),
                handler=str(row["handler"]),
                line=int(row["line"]),
                framework=str(row["framework"]),
            )
            for row in rows
        ]

    # ------------------------------------------------- §14.6 test graph

    def replace_file_test_links(
        self, test_file: str, links: Iterable[TestLink]
    ) -> None:
        norm = normalize_path(test_file)
        payload = [
            (norm, link.target, link.via, link.tests) for link in links
        ]
        with self._db:
            self._db.execute("DELETE FROM test_links WHERE test_file = ?", (norm,))
            self._db.executemany(
                "INSERT OR REPLACE INTO test_links (test_file, target, via, tests) "
                "VALUES (?, ?, ?, ?)",
                payload,
            )

    def all_test_links(self) -> list[TestLink]:
        rows = self._db.execute(
            "SELECT test_file, target, via, tests FROM test_links"
        ).fetchall()
        return [
            TestLink(
                test_file=str(row["test_file"]),
                target=str(row["target"]),
                via=str(row["via"]),
                tests=int(row["tests"]),
            )
            for row in rows
        ]

    def tests_for(self, path: str) -> list[TestLink]:
        rows = self._db.execute(
            "SELECT test_file, target, via, tests FROM test_links WHERE target = ?",
            (normalize_path(path),),
        ).fetchall()
        return [
            TestLink(
                test_file=str(row["test_file"]),
                target=str(row["target"]),
                via=str(row["via"]),
                tests=int(row["tests"]),
            )
            for row in rows
        ]

    # ----------------------------------------------------------- stats

    def counts(self) -> dict[str, int]:
        def one(table: str) -> int:
            row = self._db.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()  # noqa: S608
            return int(row["n"])

        return {
            "files_indexed": one("files"),
            "files_parsed": self._db.execute(
                "SELECT COUNT(*) AS n FROM files WHERE is_parsed = 1"
            ).fetchone()["n"],
            "symbols": one("symbols"),
            "references": one("symbol_references"),
            "dependency_edges": one("dep_edges"),
            "api_endpoints": one("api_endpoints"),
            "test_links": one("test_links"),
        }

    def stats(self) -> IndexStats:
        raw = self.counts()
        stats = IndexStats(
            files_indexed=raw["files_indexed"],
            files_parsed=raw["files_parsed"],
            files_skipped=raw["files_indexed"] - raw["files_parsed"],
            symbols=raw["symbols"],
            references=raw["references"],
            dependency_edges=raw["dependency_edges"],
            api_endpoints=raw["api_endpoints"],
            test_links=raw["test_links"],
            last_scan_at=self.get_meta("last_scan_at"),
            last_engine=self.get_meta("last_engine"),
        )
        return stats

    # ----------------------------------------------------------- close

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> SQLiteCodeIntelStore:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
