"""The Code-Intelligence Engine (New Plan §14.11 / §14.12).

**§14.11 Large Project Engine** — the 100k/200k/300k/400k+ rungs:

* full-tree **file scan** (ignore rules, binary skips, language map);
* **budgeted parsing** — the file index covers everything, symbol
  and graph parsing honors an explicit ``parse_budget`` and says so
  in :meth:`IndexStats` (``files_skipped`` is the honest number);
* **incremental indexing** — a second scan reparses nothing (size +
  mtime fast path; content hash only on change), deletions are
  pruned;
* **batched persistence** — WAL transactions per ~500 files.

**§14.12 Live Index Update** — the verbatim flow::

    file changed
    ↓
    parse affected region          (tree.edit + reparse with the old
    ↓                               tree when tree-sitter holds it)
    update symbols                 (atomic per-file replace)
    ↓
    update graph                   (edges + test links + reference
                                    resolution for this file only)

Everything the agent consumes hangs off this one façade: symbol
search, the §14.8 repository map, the §14.7 architecture map, impact
sets, test coverage gaps, the §14.5 route table.

محرّك ذكاء الكود — مسح المشاريع الضخمة بميزانية صادقة، وتحديث
حيّ للفهرس عند كل تغيير: تحليل المنطقة المتأثرة ثم تحديث الرموز
ثم تحديث المخطط.

Stdlib only (tree-sitter is the optional MODE A engine behind the
registry).
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nexus.events import EventBus

from .contracts import (
    IGNORED_DIRS,
    SKIP_SUFFIXES,
    ApiEndpoint,
    FileEntry,
    IndexNotReadyError,
    IndexStats,
    InvalidIndexError,
    LayerEntry,
    ParsedFile,
    Symbol,
    SymbolReference,
    TestLink,
    UpdateReport,
    detect_language,
    is_parseable,
    normalize_path,
    utc_now_iso,
)
from .graphs import (
    ApiGraph,
    DependencyGraph,
    ImportResolver,
    TestGraph,
    build_dependency_edges,
    build_test_links,
    resolve_references,
)
from .parsers import ParserRegistry, build_registry, line_edit
from .repomap import ArchitectureMap, RepoMapResult, RepositoryMap
from .store import SQLiteCodeIntelStore

#: Batching for §14.11 — rows per upsert transaction.
FILE_BATCH = 500

#: Live source cache bound (§14.12 diffs old vs new).
MAX_CACHED_SOURCES = 64

#: Default §14.11 parse budget when the caller says nothing.
DEFAULT_PARSE_BUDGET = 20_000


class CodeIntelEngine:
    """The §14 façade — scan, update live, query, prove."""

    def __init__(
        self,
        root: str | Path,
        db_path: str | Path | None = None,
        prefer: str = "auto",
        bus: EventBus | None = None,
    ) -> None:
        self._root = Path(root).resolve()
        if not self._root.is_dir():
            raise InvalidIndexError(f"root is not a directory: {self._root}")
        self._db_path = (
            Path(db_path)
            if db_path is not None
            else self._root / ".nexus" / "codeintel.db"
        )
        self._store = SQLiteCodeIntelStore(self._db_path)
        self._registry: ParserRegistry = build_registry(prefer)
        self._bus = bus
        self._sources: dict[str, str] = {}

    # ------------------------------------------------------------ props

    @property
    def root(self) -> Path:
        return self._root

    @property
    def db_path(self) -> Path:
        return self._db_path

    @property
    def registry(self) -> ParserRegistry:
        return self._registry

    def engine_status(self) -> dict[str, Any]:
        """Parser availability — the honest MODE A report."""
        return self._registry.engine_status()

    def close(self) -> None:
        self._store.close()

    def __enter__(self) -> CodeIntelEngine:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # --------------------------------------------------- §14.11 scan

    def scan(
        self,
        parse_budget: int | None = DEFAULT_PARSE_BUDGET,
        progress: Callable[[int, int], None] | None = None,
    ) -> IndexStats:
        """Full-tree scan — incremental on the second call.

        ``parse_budget`` — how many *changed* parseable files may be
        parsed this run (None = unlimited). The file index still
        covers every file; :attr:`IndexStats.files_skipped` is the
        honest count of indexed-but-unparsed files.
        ``progress`` — optional ``(done, total)`` callback per batch.
        """
        self._publish("index.scan_started", {"root": str(self._root)})
        started = time.monotonic()

        known = self._store.known_paths()
        discovered = self._walk()
        discovered_set = {entry.path for entry in discovered}

        budget = parse_budget
        parsed_files: dict[str, ParsedFile] = {}
        rows: list[tuple[FileEntry, bool, bool, str]] = []
        changed_count = 0
        reparsed = 0
        used_engine = ""

        for entry in discovered:
            language = entry.language
            parseable = is_parseable(language)
            old = self._store.get_file(entry.path)
            unchanged = (
                old is not None
                and old.sha != ""
                and old.content_fingerprint() == entry.content_fingerprint()
            )
            is_test_old, was_parsed_old, old_engine = self._store.file_flags(entry.path)
            should_parse = parseable and not unchanged
            if should_parse:
                changed_count += 1
                if budget is not None and reparsed >= budget:
                    # budget honest: indexed, not parsed this run
                    rows.append((entry, is_test_old, False, ""))
                    continue
            elif parseable and old is not None and was_parsed_old:
                # unchanged parseable file — keep its parse state (sha,
                # lines) so later scans never reparse it (§14.11)
                entry.sha = old.sha
                entry.lines = old.lines
                rows.append((entry, is_test_old, True, old_engine))
                continue
            else:
                rows.append((entry, False, False, ""))
                continue
            source = self._read_source(entry.path)
            if source is None:
                rows.append((entry, is_test_old, was_parsed_old, old_engine))
                continue
            parsed = self._registry.parse(entry.path, source)
            entry.sha = parsed.sha
            entry.lines = source.count("\n") + 1
            self._persist_parse(entry.path, parsed)
            self._cache_source(entry.path, source)
            parsed_files[entry.path] = parsed
            reparsed += 1
            used_engine = parsed.engine
            rows.append((entry, parsed.is_test, True, parsed.engine))

        # deletions — files that vanished since the last scan
        for path in sorted(known - discovered_set):
            self._store.delete_file(path)

        # batched file-index persistence
        for start in range(0, len(rows), FILE_BATCH):
            chunk = rows[start : start + FILE_BATCH]
            self._store.upsert_files(chunk)
            if progress is not None:
                progress(min(start + FILE_BATCH, len(rows)), len(rows))

        # graph phases — §14.4 edges + §14.6 links + reference resolution
        if parsed_files:
            resolver = ImportResolver(discovered_set | self._store.parsed_paths())
            for path, parsed in parsed_files.items():
                edges = build_dependency_edges(
                    [(path, parsed.imports, parsed.language)], resolver
                ).get(path, [])
                self._store.replace_file_edges(path, edges)
            for test_file, links in build_test_links(
                self._store, parsed_files
            ).items():
                self._store.replace_file_test_links(test_file, links)
        resolve_references(self._store)

        stats = self._store.stats()
        stats.reparsed_on_update = reparsed
        if used_engine:
            stats.last_engine = used_engine
        stats.last_scan_at = utc_now_iso()
        self._store.set_meta("root", str(self._root))
        self._store.set_meta("last_scan_at", stats.last_scan_at)
        self._store.set_meta("last_engine", stats.last_engine or used_engine)
        stats.files_skipped = stats.files_indexed - stats.files_parsed
        payload = dict(stats.to_dict())
        payload["scan_seconds"] = round(time.monotonic() - started, 3)
        payload["changed_files"] = changed_count
        self._publish("index.updated", payload)
        return stats

    # -------------------------------------------------- §14.12 live

    def live_update(self, path: str, new_source: str) -> UpdateReport:
        """The §14.12 flow, verbatim — one changed file.

        ``path`` — repository-relative path.
        ``new_source`` — the file's content *after* the change (the
        engine still holds the old source/tree for the diff).

        Returns the honest :class:`UpdateReport` (method, changed
        region, symbol deltas, rebuilt edges).
        """
        norm = self._relative(path)
        language = detect_language(norm)
        if not is_parseable(language):
            raise InvalidIndexError(f"no parser for {norm!r} ({language!r})")
        if not self._store.get_file(norm):
            raise IndexNotReadyError(
                f"{norm!r} is not indexed — run scan() before live updates"
            )
        old_source = self._sources.get(norm, "")
        _is_test, _was_parsed, old_engine = self._store.file_flags(norm)
        parser = self._registry.parser_for(language)
        tree_sitter = self._registry.tree_sitter

        parsed: ParsedFile
        method: str
        if (
            tree_sitter is not None
            and parser is tree_sitter
            and tree_sitter.cached_tree_for(norm) is not None
        ):
            parsed, region = tree_sitter.live_reparse(
                norm, old_source or new_source, new_source
            )
            method = "treesitter-incremental"
        else:
            parsed = parser.parse(norm, new_source)
            if old_source:
                region = line_edit(old_source, new_source)
            else:
                region = (1, new_source.count("\n") + 1)
            method = f"{parsed.engine}-file"

        symbols_before = len(self._store.file_symbols(norm))
        self._persist_parse(norm, parsed)
        # the honest stat: when the disk already holds the new source,
        # keep the real mtime/size so the next scan's fingerprint
        # matches and reparses nothing (true §14.11/§14.12 synergy).
        size = len(new_source.encode("utf-8", errors="replace"))
        mtime = time.time()
        disk = self._root / norm
        try:
            stat = disk.stat()
            if disk.read_text(encoding="utf-8", errors="replace") == new_source:
                size, mtime = stat.st_size, stat.st_mtime
        except OSError:
            pass
        entry = FileEntry(
            path=norm,
            language=language,
            size=size,
            mtime=mtime,
            sha=parsed.sha,
            lines=new_source.count("\n") + 1,
            indexed_at=utc_now_iso(),
        )
        self._store.upsert_file(entry, is_test=parsed.is_test, is_parsed=True, engine=parsed.engine)
        self._cache_source(norm, new_source)

        # update the graph — this file only
        resolver = ImportResolver(self._store.known_paths())
        edges = build_dependency_edges(
            [(norm, parsed.imports, parsed.language)], resolver
        ).get(norm, [])
        self._store.replace_file_edges(norm, edges)
        if parsed.is_test:
            links = build_test_links(self._store, {norm: parsed})
            self._store.replace_file_test_links(norm, links.get(norm, []))
        else:
            self._store.replace_file_test_links(norm, [])
        resolve_references(self._store)

        old_names = {  # recompute honestly from the graph pass
            sym.qualified for sym in self._store.file_symbols(norm)
        }
        report = UpdateReport(
            file=norm,
            changed_region=region,
            method=method,
            symbols_before=symbols_before,
            symbols_after=len(parsed.symbols),
            symbols_updated=min(symbols_before, len(old_names)),
            edges_rebuilt=len(edges),
        )
        self._publish("index.live_updated", dict(report.to_dict()))
        return report

    # ------------------------------------------------------ §14 queries

    def search_symbols(
        self, query: str = "", kind: str = "", limit: int = 50
    ) -> list[Symbol]:
        return self._store.search_symbols(query=query, kind=kind, limit=limit)

    def file_symbols(self, path: str) -> list[Symbol]:
        return self._store.file_symbols(self._relative(path))

    def dependencies_of(self, path: str) -> list[str]:
        return DependencyGraph(self._store).dependencies_of(self._relative(path))

    def dependents_of(self, path: str) -> list[str]:
        return DependencyGraph(self._store).dependents_of(self._relative(path))

    def impact(self, path: str) -> list[str]:
        """Transitive impact set — what a change can break (§14.4)."""
        return DependencyGraph(self._store).impact_set(self._relative(path))

    def entry_points(self) -> list[str]:
        return DependencyGraph(self._store).entry_points()

    def hotspots(self, limit: int = 20) -> list[tuple[str, int]]:
        return DependencyGraph(self._store).hotspots(limit)

    def api_endpoints(self) -> list[ApiEndpoint]:
        return ApiGraph(self._store).endpoints()

    def route_table(self) -> dict[str, list[dict[str, str]]]:
        return ApiGraph(self._store).route_table()

    def tests_for(self, path: str) -> list[TestLink]:
        return TestGraph(self._store).tests_for(self._relative(path))

    def coverage_gaps(self) -> list[str]:
        return TestGraph(self._store).coverage_gaps()

    def test_links(self) -> list[TestLink]:
        return TestGraph(self._store).links()

    def repo_map(
        self, token_budget: int = 1024, focus: list[str] | None = None
    ) -> RepoMapResult:
        """The §14.8 map — ranked, budgeted, rendered."""
        return RepositoryMap(self._store).build(token_budget=token_budget, focus=focus)

    def architecture_map(self) -> list[LayerEntry]:
        """The §14.7 component view."""
        return ArchitectureMap(self._store).build()

    def stats(self) -> IndexStats:
        return self._store.stats()

    # -------------------------------------------------------- internals

    def _relative(self, path: str) -> str:
        norm = normalize_path(path)
        if norm in self._store.known_paths():
            return norm
        # allow rooted and backslashed spellings
        try:
            candidate = Path(path).resolve()
            candidate = candidate.relative_to(self._root)
        except (ValueError, OSError):
            return norm
        return normalize_path(str(candidate))

    def _walk(self) -> list[FileEntry]:
        """The §14.1 file scan — sorted, pruned, language-tagged."""
        out: list[FileEntry] = []
        for dirpath, dirnames, filenames in os.walk(self._root):
            dirnames[:] = sorted(
                d
                for d in dirnames
                if d not in IGNORED_DIRS and not d.startswith(".")
            )
            for name in sorted(filenames):
                suffix = os.path.splitext(name)[1].lower()
                if suffix in SKIP_SUFFIXES:
                    continue
                language = detect_language(name)
                full = Path(dirpath) / name
                try:
                    stat = full.stat()
                except OSError:
                    continue
                rel = normalize_path(str(full.relative_to(self._root)))
                out.append(
                    FileEntry(
                        path=rel,
                        language=language,
                        size=stat.st_size,
                        mtime=stat.st_mtime,
                    )
                )
        return out

    def _read_source(self, rel_path: str) -> str | None:
        try:
            return (self._root / rel_path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    def _persist_parse(self, path: str, parsed: ParsedFile) -> None:
        """Symbols + references + endpoints — one file, atomic."""
        self._store.replace_file_symbols(path, parsed.symbols)
        self._store.replace_file_references(
            path,
            [
                SymbolReference(
                    name=ref.name, file=path, line=ref.line, resolved_file=""
                )
                for ref in parsed.references
            ],
        )
        self._store.replace_file_endpoints(path, parsed.api_endpoints)

    def _cache_source(self, path: str, source: str) -> None:
        self._sources[path] = source
        while len(self._sources) > MAX_CACHED_SOURCES:
            self._sources.pop(next(iter(self._sources)))

    def _publish(self, name: str, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        self._bus.publish(name, payload=payload)


def build_codeintel_engine(
    root: str | Path,
    db_path: str | Path | None = None,
    prefer: str = "auto",
    bus: EventBus | None = None,
) -> CodeIntelEngine:
    """The §14.11 entry point — engine over one root."""
    return CodeIntelEngine(root=root, db_path=db_path, prefer=prefer, bus=bus)
