"""NEXUS Code Intelligence (New Plan §14 — PHASE 14).

*تمكين NEXUS من فهم المشاريع الكبيرة* — letting NEXUS understand
large projects.

========================  ======================================  ==========
Component                 Plan source                             Module
========================  ======================================  ==========
File Index                §14.1                                   contracts
Symbol Index              §14.2                                   contracts
AST                       §14.3                                   parsers
Dependency Graph          §14.4                                   graphs
API Graph                 §14.5                                   graphs · parsers
Test Graph                §14.6                                   graphs
Architecture Map          §14.7                                   repomap
Repository Map            §14.8                                   repomap
Tree-sitter (MODE A)      §14.9                                   parsers
Aider methodology (D/C)   §14.10                                  repomap
Large Project Engine      §14.11                                  engine
Live Index Update         §14.12                                  engine
========================  ======================================  ==========

The §49 pipeline — *File Scanner → parser → Symbol index →
Dependency graph → API graph → Test map → Repo map → relevant
context* — runs end-to-end on
:class:`~nexus.codeintel.engine.CodeIntelEngine.scan`, and the §14.12
live flow (file changed → parse affected region → update symbols →
update graph) on :meth:`CodeIntelEngine.live_update`.

    لا نرسل 400k سطر إلى النموذج — نرسل الخريطة.
    (we never send 400k lines to the model — we send the map.)

Architecture invariant (Plan §61): *NEXUS owns code-intelligence
semantics*. tree-sitter (§14.9) is the MODE A engine behind the
``[codeintel]`` extra — the runtime that parses the languages stdlib
cannot (JavaScript/TypeScript) and the incremental §14.12 path
(``tree.edit`` → reparse with the old tree). Aider (§14.10)
contributed the Repository-Map methodology — PageRank over the
symbol-reference graph, damping 0.85, token-budgeted rendering — as
MODE D/C: studied in ``vendor-staging/phase-14/``, zero imports.
The Core stays stdlib-only; every engine degrades honestly
(:meth:`CodeIntelEngine.engine_status`).

ذكاء الكود — الفهرس والرموز والمخططات والخرائط؛ محرّك واحد
للمشاريع الضخمة مع تحديث حيّ لكل تغيير.

Stdlib only (tree-sitter optional behind the ``[codeintel]`` extra).
"""

from .contracts import (
    CHARS_PER_TOKEN,
    EDGE_KINDS,
    IGNORED_DIRS,
    KNOWN_SUFFIXES,
    MINIFIED_MARKERS,
    PAGERANK_DAMPING,
    PAGERANK_ITERATIONS,
    PAGERANK_TOLERANCE,
    PARSEABLE_SUFFIXES,
    SKIP_SUFFIXES,
    SYMBOL_KINDS,
    ApiEndpoint,
    AstNode,
    CodeIntelError,
    DependencyEdge,
    EdgeKind,
    FileEntry,
    IndexNotReadyError,
    IndexStats,
    InvalidIndexError,
    LayerEntry,
    MapEntry,
    ParsedFile,
    Symbol,
    SymbolKind,
    SymbolReference,
    TestLink,
    UpdateReport,
    detect_language,
    is_parseable,
    new_symbol_id,
    normalize_path,
    sha256_text,
)
from .engine import (
    DEFAULT_PARSE_BUDGET,
    FILE_BATCH,
    MAX_CACHED_SOURCES,
    CodeIntelEngine,
    build_codeintel_engine,
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
from .parsers import (
    MAX_CACHED_TREES,
    MAX_REFERENCES_PER_FILE,
    MAX_SYMBOLS_PER_FILE,
    RegexParser,
    StdlibAstParser,
    TreeSitterEngine,
    build_registry,
    builtin_names,
    line_edit,
    tree_sitter_status,
)
from .repomap import (
    ArchitectureMap,
    RepoMapResult,
    RepositoryMap,
    pagerank,
)
from .store import SCHEMA_VERSION, SQLiteCodeIntelStore

__all__ = [
    # contracts
    "ApiEndpoint",
    "AstNode",
    "CHARS_PER_TOKEN",
    "CodeIntelError",
    "DependencyEdge",
    "EdgeKind",
    "EDGE_KINDS",
    "FileEntry",
    "IGNORED_DIRS",
    "IndexNotReadyError",
    "IndexStats",
    "InvalidIndexError",
    "KNOWN_SUFFIXES",
    "LayerEntry",
    "MapEntry",
    "MAX_CACHED_TREES",
    "MAX_CACHED_SOURCES",
    "MAX_REFERENCES_PER_FILE",
    "MAX_SYMBOLS_PER_FILE",
    "MINIFIED_MARKERS",
    "PAGERANK_DAMPING",
    "PAGERANK_ITERATIONS",
    "PAGERANK_TOLERANCE",
    "PARSEABLE_SUFFIXES",
    "ParsedFile",
    "SKIP_SUFFIXES",
    "Symbol",
    "SymbolKind",
    "SYMBOL_KINDS",
    "SymbolReference",
    "TestLink",
    "UpdateReport",
    "builtin_names",
    "detect_language",
    "is_parseable",
    "new_symbol_id",
    "normalize_path",
    "sha256_text",
    # engine
    "DEFAULT_PARSE_BUDGET",
    "FILE_BATCH",
    "CodeIntelEngine",
    "build_codeintel_engine",
    # graphs
    "ApiGraph",
    "DependencyGraph",
    "ImportResolver",
    "TestGraph",
    "build_dependency_edges",
    "build_test_links",
    "resolve_references",
    # parsers
    "RegexParser",
    "StdlibAstParser",
    "TreeSitterEngine",
    "build_registry",
    "line_edit",
    "tree_sitter_status",
    # repomap
    "ArchitectureMap",
    "RepoMapResult",
    "RepositoryMap",
    "pagerank",
    # store
    "SCHEMA_VERSION",
    "SQLiteCodeIntelStore",
]
