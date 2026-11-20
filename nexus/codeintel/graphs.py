"""The three graphs (New Plan §14.4 / §14.5 / §14.6).

* **DependencyGraph** (§14.4) — project-internal imports resolved to
  file edges: adjacency, reverse adjacency, transitive impact set,
  entry points (nothing depends on them), hotspots (most depended
  upon), layer ordering.
* **ApiGraph** (§14.5) — the HTTP surface: routes by file/method,
  handler back-links to symbols.
* **TestGraph** (§14.6) — test files → tested files via imports and
  the naming convention (``test_foo.py`` → ``foo.py``); coverage
  gaps (code files with zero tests).

Import resolution (the §14.4 raw material):

* Python ``import a.b.c`` / ``from a.b import x`` — absolute module
  path → ``a/b/c.py`` or ``a/b/c/__init__.py``; relative levels
  resolved against the importing file's package directory.
* JS ``import './x'`` / ``require('./x')`` — specifier relative to
  the importing file: extension ladder (``.js``/``.ts``/``.tsx``/
  ``.jsx``/``.mjs``/``.cjs``/``.py``-style ``__init__`` fallback via
  ``index.*``). Bare specifiers are external — never edges.

Reference resolution (§14.8 raw material) — every
:class:`~nexus.codeintel.contracts.SymbolReference` whose name is
defined somewhere in the project gets ``resolved_file`` pointing at
the defining files; multi-definition names resolve to *all* of them
(overloads, re-exports).

المخططات الثلاثة — التبعية والـAPI والاختبار، مع حلّ الاستيرادات
المرجعية إلى ملفات المشروع نفسه.

Stdlib only.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable

from .contracts import (
    ApiEndpoint,
    DependencyEdge,
    EdgeKind,
    ParsedFile,
    TestLink,
    normalize_path,
)
from .store import SQLiteCodeIntelStore

#: Import-spec patterns (python).
_PY_FROM_RE = None  # resolved lazily below via re
import re  # noqa: E402

_PY_FROM_IMPORT_RE = re.compile(r"^from\s+(?P<module>[\w.]*)\s+import")
_PY_PLAIN_IMPORT_RE = re.compile(r"^import\s+(?P<module>[\w.]+)")
_RELATIVE_RE = re.compile(r"^(?P<dots>\.+)(?P<rest>[\w.]*)")

#: JS-family specifier forms.
_JS_SPEC_RE = re.compile(r"['\"](?P<spec>[^'\"]+)['\"]")

#: Extension ladder for JS-family resolution.
_JS_EXTENSIONS = (".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs")

#: Test-file naming (§14.6 conventions).
_PY_TEST_FILE_RE = re.compile(r"(^|/)(?P<stem>test_[\w]*|[\w]*_test)\.py$")
_PY_TEST_FN_RE = re.compile(r"^test_")



def _join_rel(base_dir: str, spec: str) -> str:
    """Relative-specifier join with ``.``/``..`` segment handling."""
    segments: list[str] = (base_dir.split("/") if base_dir else []) + spec.split("/")
    resolved: list[str] = []
    for segment in segments:
        if segment in ("", "."):
            continue
        if segment == "..":
            if resolved:
                resolved.pop()
            continue
        resolved.append(segment)
    return "/".join(resolved)


# ------------------------------------------------------- §14.4 resolver


class ImportResolver:
    """Resolves import specs to project files — §14.4's raw material."""

    def __init__(self, project_files: Iterable[str]) -> None:
        self._files: set[str] = {normalize_path(f) for f in project_files}

    @property
    def files(self) -> set[str]:
        return self._files

    def resolve_python(self, import_spec: str, importer: str) -> str:
        """One resolved target for a python import (``""`` = external)."""
        spec = " ".join(import_spec.split())
        match = _PY_FROM_IMPORT_RE.match(spec)
        kind = EdgeKind.FROM_IMPORT
        if match is None:
            match = _PY_PLAIN_IMPORT_RE.match(spec)
            kind = EdgeKind.IMPORT
        if match is None:
            return ""
        module = match.groupdict().get("module", "") or ""
        relative = _RELATIVE_RE.match(module)
        if relative is not None:
            dots = len(relative.group("dots"))
            rest = relative.group("rest")
            base = importer.rsplit("/", 1)[0] if "/" in importer else ""
            for _ in range(dots - 1):
                base = base.rsplit("/", 1)[0] if "/" in base else ""
            module = f"{base}/{rest}".strip("/") if rest else base
            return self._python_module_file(module)
        if module:
            return self._python_module_file(module)
        del kind
        return ""

    def resolve_js(self, import_spec: str, importer: str) -> str:
        """One resolved target for a JS-family specifier."""
        match = _JS_SPEC_RE.search(import_spec)
        if match is None:
            return ""
        spec = match.group("spec")
        if not spec.startswith("."):
            return ""  # bare specifier — external package
        base_dir = importer.rsplit("/", 1)[0] if "/" in importer else ""
        target = _join_rel(base_dir, spec)
        if target in self._files:
            return target
        for extension in _JS_EXTENSIONS:
            candidate = target + extension
            if candidate in self._files:
                return candidate
        for extension in _JS_EXTENSIONS:
            candidate = f"{target}/index{extension}"
            if candidate in self._files:
                return candidate
        stripped = target
        for extension in _JS_EXTENSIONS:
            if stripped.endswith(extension):
                stripped = stripped[: -len(extension)]
                break
        if stripped in self._files:
            return stripped
        return ""

    def resolve(self, import_spec: str, importer: str, language: str) -> str:
        """The unified entry: spec + importer + language → target."""
        if language == "python":
            return self.resolve_python(import_spec, importer)
        if language in ("javascript", "typescript", "tsx", "jsx"):
            return self.resolve_js(import_spec, importer)
        return ""

    def _python_module_file(self, module: str) -> str:
        module = module.replace(".", "/")
        if f"{module}.py" in self._files:
            return f"{module}.py"
        if f"{module}/__init__.py" in self._files:
            return f"{module}/__init__.py"
        return ""


def build_dependency_edges(
    parsed_files: Iterable[tuple[str, list[str], str]],
    resolver: ImportResolver,
) -> dict[str, list[DependencyEdge]]:
    """``(file, imports, language)`` tuples → per-file edges.

    Returns ``{source: [edges]}`` so the engine can persist one
    file's edges atomically (§14.12: update the graph for the changed
    file only).
    """
    out: dict[str, list[DependencyEdge]] = {}
    for file, imports, language in parsed_files:
        norm = normalize_path(file)
        edges: list[DependencyEdge] = []
        seen: set[tuple[str, str]] = set()
        for spec in imports:
            target = resolver.resolve(spec, norm, language)
            if not target or target == norm:
                continue
            key = (target, spec)
            if key not in seen:
                seen.add(key)
                kind = (
                    EdgeKind.REQUIRE
                    if spec.startswith("require")
                    else EdgeKind.IMPORT
                    if spec.startswith("import ")
                    else EdgeKind.FROM_IMPORT
                )
                edges.append(
                    DependencyEdge(
                        source=norm, target=target, kind=kind, import_spec=spec
                    )
                )
            # python from-import submodule semantics: «from pkg import mod»
            # also loads pkg/mod.py — the edge the test graph needs.
            for sub_target in _from_import_submodules(spec, resolver):
                key = (sub_target, spec)
                if key in seen or sub_target == norm:
                    continue
                seen.add(key)
                edges.append(
                    DependencyEdge(
                        source=norm,
                        target=sub_target,
                        kind=EdgeKind.FROM_IMPORT,
                        import_spec=spec,
                    )
                )

        out[norm] = edges
    return out


def _from_import_submodules(spec: str, resolver: ImportResolver) -> list[str]:
    """``from pkg import name`` → ``pkg/name.py`` when it exists."""
    match = re.match(r"^from\s+(?P<module>[\w.]+)\s+import\s+(?P<names>[\w, ]+)", spec)
    if match is None or spec.startswith("from ."):
        return []
    module = match.group("module")
    names = [name.strip() for name in match.group("names").split(",") if name.strip()]
    targets: list[str] = []
    for name in names:
        candidate = f"{module}/{name}".replace(".", "/")
        if f"{candidate}.py" in resolver.files:
            targets.append(f"{candidate}.py")
    return targets


def resolve_references(
    store: SQLiteCodeIntelStore,
) -> int:
    """Fill ``resolved_file`` for every unresolved reference.

    Returns the number of reference rows resolved. Multi-definition
    names expand: one row per defining file (the §14.8 graph wants
    edges, not dedup).
    """
    definitions = store.definition_map()
    unresolved = store.unresolved_references()
    if not unresolved:
        return 0
    resolutions: list[tuple[str, str, int, str]] = []
    for ref in unresolved:
        targets = definitions.get(ref.name, ())
        for target in sorted(targets):
            if target and target != ref.file:
                resolutions.append((ref.name, ref.file, ref.line, target))
            elif target and target == ref.file:
                # same-file definition: mark resolved to itself so it is
                # not re-resolved forever (self-edges are dropped at
                # graph build time).
                resolutions.append((ref.name, ref.file, ref.line, target))
    if resolutions:
        store.set_reference_resolutions(resolutions)
    return len(resolutions)


# ---------------------------------------------------- §14.4 dep queries


class DependencyGraph:
    """The §14.4 graph — queries over the persisted edges."""

    def __init__(self, store: SQLiteCodeIntelStore) -> None:
        self._store = store

    def dependencies_of(self, path: str) -> list[str]:
        """Files this file imports (direct)."""
        return sorted({edge.target for edge in self._store.edges_from(path)})

    def dependents_of(self, path: str) -> list[str]:
        """Files that import this file (direct reverse edges)."""
        return sorted({edge.source for edge in self._store.edges_to(path)})

    def impact_set(self, path: str) -> list[str]:
        """Transitive dependents — what a change here can break."""
        graph = self._store.adjacency()
        reverse: dict[str, list[str]] = {}
        for source, targets in graph.items():
            for target in targets:
                reverse.setdefault(target, []).append(source)
        start = normalize_path(path)
        seen: set[str] = set()
        queue: deque[str] = deque(reverse.get(start, []))
        while queue:
            node = queue.popleft()
            if node in seen or node == start:
                continue
            seen.add(node)
            queue.extend(reverse.get(node, []))
        return sorted(seen)

    def entry_points(self) -> list[str]:
        """Files nothing depends on — the natural roots."""
        graph = self._store.adjacency()
        parsed = self._store.parsed_paths()
        targets = {target for values in graph.values() for target in values}
        return sorted(parsed - targets)

    def hotspots(self, limit: int = 20) -> list[tuple[str, int]]:
        """Most depended-upon files — the architecture's load-bearing walls."""
        edges = self._store.all_edges()
        counts: dict[str, int] = {}
        for edge in edges:
            counts[edge.target] = counts.get(edge.target, 0) + 1
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
        return ranked[: max(1, limit)]


# ---------------------------------------------------- §14.5 api queries


class ApiGraph:
    """The §14.5 graph — the HTTP surface as a graph."""

    def __init__(self, store: SQLiteCodeIntelStore) -> None:
        self._store = store

    def endpoints(self) -> list[ApiEndpoint]:
        return self._store.all_endpoints()

    def by_file(self, path: str) -> list[ApiEndpoint]:
        return [
            endpoint
            for endpoint in self._store.all_endpoints()
            if endpoint.file == normalize_path(path)
        ]

    def route_table(self) -> dict[str, list[dict[str, str]]]:
        """path → its registered handlers (the printed API map)."""
        table: dict[str, list[dict[str, str]]] = {}
        for endpoint in self._store.all_endpoints():
            table.setdefault(endpoint.path, []).append(
                {
                    "method": endpoint.method or "ANY",
                    "handler": endpoint.handler,
                    "file": endpoint.file,
                    "framework": endpoint.framework,
                }
            )
        return table

    def handler_symbols(self, endpoint: ApiEndpoint) -> list[str]:
        if not endpoint.handler:
            return []
        return [
            sym.qualified
            for sym in self._store.symbols_by_name(endpoint.handler)
            if sym.file == endpoint.file
        ]


# --------------------------------------------------- §14.6 test queries


class TestGraph:
    """The §14.6 graph — tests → tested code."""

    def __init__(self, store: SQLiteCodeIntelStore) -> None:
        self._store = store

    def links(self) -> list[TestLink]:
        return self._store.all_test_links()

    def tests_for(self, path: str) -> list[TestLink]:
        return self._store.tests_for(path)

    def coverage_gaps(self) -> list[str]:
        """Parsed code files with no test links pointing at them."""
        links = self._store.all_test_links()
        tested = {link.target for link in links}
        test_files = self._store.test_paths()
        code_files = self._store.parsed_paths()
        return sorted(
            path for path in code_files if path not in tested and path not in test_files
        )


def build_test_links(
    store: SQLiteCodeIntelStore, parsed: dict[str, ParsedFile]
) -> dict[str, list[TestLink]]:
    """Per test file: its §14.6 links — imports + naming convention.

    ``import`` links  — project files the test imports.
    ``naming`` links  — ``test_foo.py`` → sibling ``foo.py``.
    """
    edges = store.all_edges()
    by_source: dict[str, list[DependencyEdge]] = {}
    for edge in edges:
        by_source.setdefault(edge.source, []).append(edge)

    out: dict[str, list[TestLink]] = {}
    for path, parsed_file in parsed.items():
        if not parsed_file.is_test:
            continue
        norm = normalize_path(path)
        links: list[TestLink] = []
        seen: set[str] = set()
        for edge in by_source.get(norm, []):
            if edge.target in seen or edge.target == norm:
                continue
            seen.add(edge.target)
            links.append(
                TestLink(test_file=norm, target=edge.target, via="import", tests=1)
            )
        # naming convention — test_foo.py → foo.py / foo_test.py → foo.py
        match = _PY_TEST_FILE_RE.search(norm)
        if match is not None:
            stem = match.group("stem")
            base = stem.removeprefix("test_").removesuffix("_test")
            directory = norm.rsplit("/", 1)[0] if "/" in norm else ""
            for candidate in (f"{directory}/{base}.py" if directory else f"{base}.py",):
                candidate = normalize_path(candidate)
                if candidate in store.known_paths() and candidate != norm and candidate not in seen:
                    seen.add(candidate)
                    links.append(
                        TestLink(test_file=norm, target=candidate, via="naming", tests=1)
                    )
        test_symbols = sum(1 for sym in parsed_file.symbols if sym.kind == "test")
        for link in links:
            link.tests = max(1, test_symbols or 1)
        out[norm] = links
    return out
