"""Code-intelligence contracts (New Plan §14.1–§14.8 / §14.10).

The phase thesis — the plan says it best::

    تمكين NEXUS من فهم المشاريع الكبيرة
    (letting NEXUS understand large projects)

The §14.12 live-index flow, verbatim from the operator's spec::

    file changed
    ↓
    parse affected region
    ↓
    update symbols
    ↓
    update graph

The §49 architecture (Master Spec), verbatim::

    Repository → File Scanner → Tree-sitter / parser → Symbol index
    → Dependency graph → API graph → Test map → Repo map
    → Semantic retrieval → Relevant context → Agent

    لا نرسل 400k سطر إلى النموذج
    (we never send 400k lines to the model)

§14.1 File Index · §14.2 Symbol Index · §14.3 AST · §14.4 Dependency
Graph · §14.5 API Graph · §14.6 Test Graph · §14.7 Architecture Map ·
§14.8 Repository Map — the shapes below are NEXUS-native (Plan §61:
*NEXUS owns code-intelligence semantics*). tree-sitter (§14.9, MODE
A) enters behind the parser interface as an optional engine; Aider
(§14.10, MODE D/C) contributed the repository-map *methodology* —
PageRank over the reference graph — and none of its code is imported.

عقود ذكاء الكود — فهرس الملفات والرموز والأشجار والمخططات
الثلاثة والخرائطتان؛ النواة تملك الدلالات والمحركات خلف الحدود.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ----------------------------------------------------------------- errors


class CodeIntelError(Exception):
    """Code-intelligence misuse or backend failure."""


class InvalidIndexError(CodeIntelError):
    """A file/symbol/graph record violates the §14 contract."""


class IndexNotReadyError(CodeIntelError):
    """Query before the §14.11 engine ever scanned a root."""


# ------------------------------------------------------- §14.1 file index

#: Code files the engine parses. Everything else is still *indexed*
#: (name/size/mtime/language) but never parsed — the honest budget.
PARSEABLE_SUFFIXES: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
}

#: Indexed but never parsed (docs/config/data — still visible to the
#: file index and the architecture map).
KNOWN_SUFFIXES: dict[str, str] = {
    ".json": "json",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".md": "markdown",
    ".txt": "text",
    ".cfg": "ini",
    ".ini": "ini",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
}

#: Directory names never entered by the scanner (vendor junk, caches,
#: build output). §14.11 large-project hygiene.
IGNORED_DIRS: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        ".venv",
        "venv",
        "env",
        "node_modules",
        "dist",
        "build",
        "target",
        "coverage",
        ".idea",
        ".vscode",
        "site-packages",
    }
)

#: Suffixes never indexed at all (artifacts and binaries).
SKIP_SUFFIXES: frozenset[str] = frozenset(
    {
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".exe",
        ".bin",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".ico",
        ".pdf",
        ".zip",
        ".gz",
        ".tar",
        ".whl",
        ".lock",
    }
)

#: Path fragments that mark a minified artifact (skip — noise, not code).
MINIFIED_MARKERS: tuple[str, ...] = (".min.js", ".min.css")

_NAME_RE = re.compile(r"^[\w.\-$]+$")


def detect_language(path: str) -> str:
    """Language for a path — ``""`` when the suffix is unknown."""
    lowered = path.lower()
    if any(lowered.endswith(marker) for marker in MINIFIED_MARKERS):
        return ""
    for suffix, language in PARSEABLE_SUFFIXES.items():
        if lowered.endswith(suffix):
            return language
    for suffix, language in KNOWN_SUFFIXES.items():
        if lowered.endswith(suffix):
            return language
    return ""


def is_parseable(language: str) -> bool:
    """True when the language owns a parser (§14.3) in this runtime."""
    return language in set(PARSEABLE_SUFFIXES.values())


def normalize_path(path: str) -> str:
    """Repository-relative, forward-slashed, no leading ``./``."""
    text = str(path).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.rstrip("/")


def sha256_text(text: str) -> str:
    """Content digest for change detection (house encoding: utf-8)."""
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def utc_now_iso() -> str:
    """UTC timestamp, ISO-8601 with microseconds (house format)."""
    return datetime.now(UTC).isoformat()


def new_symbol_id(seed: str = "") -> str:
    """Deterministic id for tests (seeded), random otherwise."""
    if seed:
        digest = hashlib.blake2b(seed.encode("utf-8"), digest_size=8).hexdigest()
    else:
        digest = secrets.token_hex(8)
    return f"sym_{digest}"


@dataclass(slots=True)
class FileEntry:
    """One indexed file — §14.1.

    ``path``      — repository-relative, forward slashes.
    ``language``  — ``python``/``javascript``/``json``/``""``…
    ``size``      — bytes.
    ``mtime``     — float epoch (change detection).
    ``sha``       — content digest (``""`` until first hash).
    ``lines``     — line count (0 until parsed).
    """

    path: str
    language: str
    size: int
    mtime: float
    sha: str = ""
    lines: int = 0
    indexed_at: str = field(default_factory=utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "language": self.language,
            "size": self.size,
            "mtime": self.mtime,
            "sha": self.sha,
            "lines": self.lines,
            "indexed_at": self.indexed_at,
        }

    def validate(self) -> None:
        if not self.path:
            raise InvalidIndexError("file path must be non-empty")
        if self.path != normalize_path(self.path):
            raise InvalidIndexError(f"path not normalized: {self.path!r}")
        if self.size < 0:
            raise InvalidIndexError("negative size")
        if self.mtime < 0:
            raise InvalidIndexError("negative mtime")

    def content_fingerprint(self) -> str:
        """Cheap change key: size + mtime (the pre-hash fast path)."""
        return f"{self.size}:{self.mtime:.6f}"


# ----------------------------------------------------- §14.2 symbol index


class SymbolKind:
    """Symbol vocabulary for the §14.2 index."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    CONSTANT = "constant"
    INTERFACE = "interface"
    TYPE = "type"
    TEST = "test"
    HANDLER = "handler"


SYMBOL_KINDS: tuple[str, ...] = (
    SymbolKind.MODULE,
    SymbolKind.CLASS,
    SymbolKind.FUNCTION,
    SymbolKind.METHOD,
    SymbolKind.VARIABLE,
    SymbolKind.CONSTANT,
    SymbolKind.INTERFACE,
    SymbolKind.TYPE,
    SymbolKind.TEST,
    SymbolKind.HANDLER,
)


@dataclass(slots=True)
class Symbol:
    """One definition — §14.2.

    ``name``       — the identifier as written.
    ``qualified``  — dotted container path (``pkg.mod.Class.method``).
    ``kind``       — one of SYMBOL_KINDS.
    ``file``       — repository-relative path.
    ``line``       — 1-based definition line.
    ``end_line``   — last line of the definition body.
    ``signature``  — human-readable (``def f(a: int) -> str``).
    ``container``  — qualified parent (``""`` at module top).
    ``language``   — parser that produced it.
    """

    name: str
    qualified: str
    kind: str
    file: str
    line: int
    end_line: int = 0
    signature: str = ""
    container: str = ""
    language: str = "python"
    symbol_id: str = field(default_factory=new_symbol_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol_id": self.symbol_id,
            "name": self.name,
            "qualified": self.qualified,
            "kind": self.kind,
            "file": self.file,
            "line": self.line,
            "end_line": self.end_line,
            "signature": self.signature,
            "container": self.container,
            "language": self.language,
        }

    def validate(self) -> None:
        if not self.name or not _NAME_RE.match(self.name):
            raise InvalidIndexError(f"bad symbol name: {self.name!r}")
        if self.kind not in SYMBOL_KINDS:
            raise InvalidIndexError(f"bad symbol kind: {self.kind!r}")
        if not self.file:
            raise InvalidIndexError("symbol file must be non-empty")
        if self.line < 1:
            raise InvalidIndexError("symbol line must be 1-based")
        if self.end_line and self.end_line < self.line:
            raise InvalidIndexError("end_line before line")

    @property
    def rank_weight(self) -> int:
        """Aider-style mention weight — bigger defs earn more map room."""
        base = {SymbolKind.CLASS: 3, SymbolKind.METHOD: 2}.get(self.kind, 1)
        span = max(1, self.end_line - self.line + 1)
        return base * min(span, 60)


@dataclass(slots=True)
class SymbolReference:
    """A use of a name — the raw material of the §14.4/§14.8 graphs."""

    name: str
    file: str
    line: int
    resolved_file: str = ""  # project file that defines it ("" = external)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "file": self.file,
            "line": self.line,
            "resolved_file": self.resolved_file,
        }


# ---------------------------------------------------------- §14.3 AST


@dataclass(slots=True)
class AstNode:
    """A lightweight, serializable AST node — §14.3.

    NEXUS does not keep whole parse trees; it keeps the *digest* the
    graphs need: type, span, name and children. tree-sitter trees and
    the stdlib ``ast`` module both fold into this shape.
    """

    type: str
    name: str = ""
    line: int = 0
    end_line: int = 0
    children: list[AstNode] = field(default_factory=list)

    def walk(self):
        """Depth-first iteration over this node and its children."""
        yield self
        for child in self.children:
            yield from child.walk()

    def node_count(self) -> int:
        return 1 + sum(child.node_count() for child in self.children)


@dataclass(slots=True)
class ParsedFile:
    """The parser output contract (§14.3) — language-neutral.

    ``symbols``       — definitions (§14.2 records).
    ``references``    — used names, imported or bare.
    ``imports``       — imported module strings, verbatim.
    ``api_endpoints`` — route decorators / registrations (§14.5).
    ``is_test``       — test-file detection (§14.6).
    ``ast``           — the digest tree (§14.3), may be empty.
    ``engine``        — which engine produced it (``stdlib-ast`` /
                        ``tree-sitter`` / ``regex``).
    """

    file: str
    language: str
    symbols: list[Symbol] = field(default_factory=list)
    references: list[SymbolReference] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    api_endpoints: list[ApiEndpoint] = field(default_factory=list)
    is_test: bool = False
    ast: AstNode | None = None
    engine: str = ""
    sha: str = ""

    @property
    def symbol_names(self) -> set[str]:
        return {sym.name for sym in self.symbols}

    def validate(self) -> None:
        if not self.file:
            raise InvalidIndexError("parsed file path must be non-empty")
        for sym in self.symbols:
            if sym.file != self.file:
                raise InvalidIndexError(
                    f"symbol {sym.name!r} claims file {sym.file!r}, "
                    f"parsed file is {self.file!r}"
                )


# ------------------------------------------- §14.4/§14.5/§14.6 graph edges


class EdgeKind:
    """Dependency-edge vocabulary (§14.4)."""

    IMPORT = "import"
    FROM_IMPORT = "from_import"
    REQUIRE = "require"
    DYNAMIC = "dynamic"


EDGE_KINDS: tuple[str, ...] = (
    EdgeKind.IMPORT,
    EdgeKind.FROM_IMPORT,
    EdgeKind.REQUIRE,
    EdgeKind.DYNAMIC,
)


@dataclass(slots=True)
class DependencyEdge:
    """One resolved project-internal import — §14.4.

    ``source``/``target`` — repository-relative file paths.
    ``kind``              — how the dependency is expressed.
    ``import_spec``       — the module string as written.
    """

    source: str
    target: str
    kind: str
    import_spec: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "kind": self.kind,
            "import": self.import_spec,
        }

    def validate(self) -> None:
        if not self.source or not self.target:
            raise InvalidIndexError("edge endpoints must be non-empty")
        if self.source == self.target:
            raise InvalidIndexError("self-edge is not a dependency")
        if self.kind not in EDGE_KINDS:
            raise InvalidIndexError(f"bad edge kind: {self.kind!r}")


@dataclass(slots=True)
class ApiEndpoint:
    """One HTTP surface — §14.5 API Graph.

    ``method``    — GET/POST/… (``""`` when not declared).
    ``path``      — the route literal.
    ``file``      — where the route is registered.
    ``handler``   — the function that answers it.
    ``line``      — registration line.
    ``framework`` — ``flask`` / ``fastapi`` / ``express`` style.
    """

    method: str = ""
    path: str = ""
    file: str = ""
    handler: str = ""
    line: int = 0
    framework: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "path": self.path,
            "file": self.file,
            "handler": self.handler,
            "line": self.line,
            "framework": self.framework,
        }

    def route_key(self) -> str:
        return f"{(self.method or 'ANY').upper()} {self.path}"

    def validate(self) -> None:
        if not self.path.startswith("/"):
            raise InvalidIndexError(f"route path must start with '/': {self.path!r}")
        if not self.file:
            raise InvalidIndexError("endpoint file must be non-empty")


@dataclass(slots=True)
class TestLink:
    """One test → target relation — §14.6 Test Graph.

    ``test_file`` — the file containing the tests.
    ``target``    — the file under test (project-internal).
    ``via``       — how the link was established: ``import`` or
                    ``naming`` (``test_foo.py`` → ``foo.py``).
    ``tests``     — count of test symbols targeting it.
    """

    test_file: str
    target: str
    via: str = "import"
    tests: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "test_file": self.test_file,
            "target": self.target,
            "via": self.via,
            "tests": self.tests,
        }

    def validate(self) -> None:
        if not self.test_file or not self.target:
            raise InvalidIndexError("test link endpoints must be non-empty")
        if self.test_file == self.target:
            raise InvalidIndexError("a file does not test itself")
        if self.tests < 1:
            raise InvalidIndexError("test count must be positive")


# -------------------------------------------- §14.7/§14.8 maps + stats


@dataclass(slots=True)
class MapEntry:
    """One rendered line group of the §14.8 Repository Map."""

    file: str
    score: float
    lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"file": self.file, "score": round(self.score, 6), "lines": self.lines}


@dataclass(slots=True)
class LayerEntry:
    """One component of the §14.7 Architecture Map."""

    layer: str
    files: int
    symbols: int
    depends_on: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer": self.layer,
            "files": self.files,
            "symbols": self.symbols,
            "depends_on": dict(self.depends_on),
        }


@dataclass(slots=True)
class IndexStats:
    """The honest ledger of one index run — §14.11."""

    files_indexed: int = 0
    files_parsed: int = 0
    files_skipped: int = 0
    symbols: int = 0
    references: int = 0
    dependency_edges: int = 0
    api_endpoints: int = 0
    test_links: int = 0
    reparsed_on_update: int = 0
    last_scan_at: str = ""
    last_engine: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "files_indexed": self.files_indexed,
            "files_parsed": self.files_parsed,
            "files_skipped": self.files_skipped,
            "symbols": self.symbols,
            "references": self.references,
            "dependency_edges": self.dependency_edges,
            "api_endpoints": self.api_endpoints,
            "test_links": self.test_links,
            "reparsed_on_update": self.reparsed_on_update,
            "last_scan_at": self.last_scan_at,
            "last_engine": self.last_engine,
        }


@dataclass(slots=True)
class UpdateReport:
    """What one §14.12 live update actually did — the honest trace."""

    file: str
    changed_region: tuple[int, int] = (0, 0)
    method: str = ""  # treesitter-incremental | ast-file | regex-file
    symbols_before: int = 0
    symbols_after: int = 0
    symbols_updated: int = 0
    edges_rebuilt: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "changed_region": list(self.changed_region),
            "method": self.method,
            "symbols_before": self.symbols_before,
            "symbols_after": self.symbols_after,
            "symbols_updated": self.symbols_updated,
            "edges_rebuilt": self.edges_rebuilt,
        }


#: Map token approximation — chars per token (map budget math).
CHARS_PER_TOKEN = 4

#: PageRank parameters (Aider's repomap methodology, MODE D/C —
#: damping 0.85, the reference-graph walk that ranks files by how
#: much the codebase leans on them).
PAGERANK_DAMPING = 0.85
PAGERANK_ITERATIONS = 100
PAGERANK_TOLERANCE = 1e-6
