"""Code parsers (New Plan §14.3 / §14.9) — the AST factory.

Three engines fold into one output contract
(:class:`~nexus.codeintel.contracts.ParsedFile`):

* **stdlib-ast**  — the Python path that ships with NEXUS (zero
                    wheels, full signatures). Always present.
* **tree-sitter** — §14.9 **MODE A**: the real ``tree-sitter``
                    runtime behind the ``[codeintel]`` extra — the
                    multi-language engine (JavaScript/TypeScript,
                    which stdlib cannot touch) and the *incremental*
                    engine (§14.12: ``tree.edit`` → reparse with the
                    old tree — the affected region only).
* **regex**       — the honest fallback for JS-family files when
                    neither tree-sitter nor anything else is there.

The registry resolves per language — ``auto`` prefers stdlib for
Python (richest signatures) and tree-sitter for everything else;
``prefer="tree-sitter"`` routes Python through tree-sitter too (the
MODE A live path). Every engine reports its name honestly in
``ParsedFile.engine``; nothing is faked.

Reference extraction (§14.8 raw material): stdlib-ast walks
``ast.Name`` loads; tree-sitter walks ``identifier`` nodes minus
builtin noise — both capped by :data:`MAX_REFERENCES_PER_FILE`
(budget honesty at §14.11's 400k scale).

المحلّلات الثلاثة — ast القياسية وtree-sitter الحقيقية والاحتياط
النصي؛ كلها تُخرج عقدًا واحدًا وكل واحدة تُسمّي نفسها بصدق.

Stdlib core; tree-sitter enters only behind the optional import.
"""

from __future__ import annotations

import ast as pyast
import builtins
import re
from typing import Any

from .contracts import (
    ApiEndpoint,
    AstNode,
    ParsedFile,
    Symbol,
    SymbolKind,
    SymbolReference,
    detect_language,
    normalize_path,
    sha256_text,
)

# ----------------------------------------------------------------- limits

#: Budget honesty at §14.11 scale — per file, not per project.
MAX_SYMBOLS_PER_FILE = 1000
MAX_REFERENCES_PER_FILE = 2000
#: Live tree cache bound (§14.12 keeps old trees for incremental edits).
MAX_CACHED_TREES = 64

#: Test-file naming (§14.6).
_PY_TEST_FILE_RE = re.compile(r"(^|/)(test_[\w]*|[\w]*_test)\.py$")
_JS_TEST_FILE_RE = re.compile(r"(^|/)[\w.-]*\.(test|spec)\.[cm]?[jt]sx?$")

#: Express-style route registration (§14.5).
_EXPRESS_METHODS = ("get", "post", "put", "delete", "patch", "all", "options")
_EXPRESS_CALL_RE = re.compile(
    r"^[\w$]+\.(?P<method>" + "|".join(_EXPRESS_METHODS) + r")\s*\(\s*['\"](?P<path>[^'\"]+)['\"]"
)
#: Flask / FastAPI route decorator (§14.5).
_FLASK_RE = re.compile(
    r"@?(?P<obj>[\w.]+)\.(?P<method>route|get|post|put|delete|patch)\s*\(\s*['\"](?P<path>[^'\"]+)['\"]"
)

#: Regex fallback symbol patterns (JS family).
_RE_JS_FUNCTION = re.compile(
    r"^[ \t]*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[\w$]+)", re.MULTILINE
)
_RE_JS_CLASS = re.compile(r"^[ \t]*(?:export\s+)?class\s+(?P<name>[\w$]+)", re.MULTILINE)
_RE_JS_CONST = re.compile(
    r"^[ \t]*(?:export\s+)?(?:const|let|var)\s+(?P<name>[\w$]+)\s*=", re.MULTILINE
)
_RE_JS_IMPORT = re.compile(
    r"""^[ \t]*import\s+[^;'"]*?from\s+['"](?P<spec>[^'"]+)['"]"""
    r"""|^[ \t]*import\s+['"](?P<spec2>[^'"]+)['"]""",
    re.MULTILINE,
)
_RE_JS_REQUIRE = re.compile(r"""require\(\s*['"](?P<spec>[^'"]+)['"]\s*\)""")
_RE_EXPRESS_LINE = re.compile(
    r"""^[ \t]*(?:const|let|var\s+)?[\w$.]+\.(?P<method>"""
    + "|".join(_EXPRESS_METHODS)
    + r""")\s*\(\s*['"](?P<path>[^'"]+)['"]""",
    re.MULTILINE,
)

_BUILTIN_NAMES: frozenset[str] | None = None


def builtin_names() -> frozenset[str]:
    """Python builtins — excluded from reference-extraction noise."""
    global _BUILTIN_NAMES  # noqa: PLW0603
    if _BUILTIN_NAMES is None:
        _BUILTIN_NAMES = frozenset(dir(builtins))
    return _BUILTIN_NAMES


# --------------------------------------------------- §14.9 tree-sitter

try:  # MODE A — the real runtime, optional import (Plan §0.2)
    from tree_sitter import Language as _TS_Language  # type: ignore[import-not-found]
    from tree_sitter import Parser as _TS_Parser  # type: ignore[import-not-found]

    _TS_ROOT = True
except ImportError:  # pragma: no cover — CI without the extra
    _TS_Language = None  # type: ignore[assignment]
    _TS_Parser = None  # type: ignore[assignment]
    _TS_ROOT = False

#: Grammar module → symbol-builder name per language. The stdlib
# convention is ``language()``; tree-sitter-typescript ships two
# symbols (``language_typescript`` / ``language_tsx``).
_GRAMMAR_SYMBOLS: dict[str, tuple[str, str]] = {
    "python": ("tree_sitter_python", "language"),
    "javascript": ("tree_sitter_javascript", "language"),
    "typescript": ("tree_sitter_typescript", "language_typescript"),
    "tsx": ("tree_sitter_typescript", "language_tsx"),
}


def _ts_language_for(language: str) -> Any | None:
    """Build the real tree-sitter :class:`Language` or ``None``."""
    entry = _GRAMMAR_SYMBOLS.get(language)
    if entry is None or not _TS_ROOT:
        return None
    module_name, symbol_name = entry
    try:
        grammar = __import__(module_name)
        builder = getattr(grammar, symbol_name)
        language_cls: Any = _TS_Language  # None only when _TS_ROOT is False
        return language_cls(builder())
    except Exception:
        return None


def tree_sitter_status() -> dict[str, bool]:
    """Which grammars this runtime really has — the honest report."""
    status: dict[str, bool] = {"tree-sitter": _TS_ROOT}
    if not _TS_ROOT:
        return status
    for language in _GRAMMAR_SYMBOLS:
        status[language] = _ts_language_for(language) is not None
    return status


class TreeSitterEngine:
    """§14.9 MODE A — the real tree-sitter runtime behind NEXUS.

    ``parse``        — full parse: symbols + imports + references.
    ``live_reparse`` — §14.12: byte-diff the old/new source,
                       ``tree.edit`` the changed region, reparse with
                       the old tree (the affected region only) and
                       return the fresh parse plus the changed line
                       range.
    """

    engine_name = "tree-sitter"

    def __init__(self) -> None:
        if not _TS_ROOT:
            raise RuntimeError("tree-sitter is not installed in this runtime")
        self._parsers: dict[str, Any] = {}
        self._trees: dict[str, Any] = {}
        parser_cls: Any = _TS_Parser  # None only when _TS_ROOT is False
        for language in _GRAMMAR_SYMBOLS:
            ts_language = _ts_language_for(language)
            if ts_language is None:
                continue
            try:
                self._parsers[language] = parser_cls(ts_language)
            except Exception:
                continue

    @property
    def languages(self) -> set[str]:
        return set(self._parsers)

    def supports(self, language: str) -> bool:
        return language in self._parsers

    # ------------------------------------------------------------- parse

    def parse(self, path: str, source: str) -> ParsedFile:
        language = detect_language(path)
        parser = self._parsers.get(language)
        if parser is None:
            raise RuntimeError(f"tree-sitter has no grammar for {language!r}")
        data = source.encode("utf-8", errors="replace")
        tree = parser.parse(data)
        self._cache_tree(path, tree)
        return self._extract(path, language, source, data, tree)

    def live_reparse(
        self, path: str, old_source: str, new_source: str
    ) -> tuple[ParsedFile, tuple[int, int]]:
        """§14.12 — edit the old tree, reparse incrementally.

        Returns the fresh parse and the changed **1-based line range**.
        """
        language = detect_language(path)
        parser = self._parsers.get(language)
        if parser is None:
            raise RuntimeError(f"tree-sitter has no grammar for {language!r}")
        old_data = old_source.encode("utf-8", errors="replace")
        new_data = new_source.encode("utf-8", errors="replace")
        tree = self._trees.get(path)
        if tree is not None and old_data != new_data:
            start_byte, old_end, new_end, start_pt, old_end_pt, new_end_pt = _byte_edit(
                old_data, new_data
            )
            tree.edit(  # type: ignore[union-attr]
                start_byte=start_byte,
                old_end_byte=old_end,
                new_end_byte=new_end,
                start_point=start_pt,
                old_end_point=old_end_pt,
                new_end_point=new_end_pt,
            )
            tree = parser.parse(new_data, tree)
        elif tree is not None and old_data == new_data:
            pass  # unchanged: reuse the cached tree as-is
        else:
            tree = parser.parse(new_data)
        self._cache_tree(path, tree)
        parsed = self._extract(path, language, new_source, new_data, tree)
        start_line, end_line = _line_edit(old_source, new_source)
        return parsed, (start_line, end_line)

    def cached_tree_for(self, path: str) -> Any | None:
        """The cached old tree (§14.12 state) — engine-side use."""
        return self._trees.get(path)

    def _cache_tree(self, path: str, tree: Any) -> None:
        self._trees[path] = tree
        while len(self._trees) > MAX_CACHED_TREES:
            self._trees.pop(next(iter(self._trees)))

    # ---------------------------------------------------------- extract

    def _extract(
        self, path: str, language: str, source: str, data: bytes, tree: Any
    ) -> ParsedFile:
        lines = source.splitlines()
        root = tree.root_node
        symbols: list[Symbol] = []
        references: list[SymbolReference] = []
        imports: list[str] = []
        endpoints: list[ApiEndpoint] = []

        if language == "python":
            self._extract_python(
                path, data, root, symbols, references, imports, endpoints, lines
            )
        else:
            self._extract_js(
                path, data, root, symbols, references, imports, endpoints
            )

        is_test = bool(_PY_TEST_FILE_RE.search(path) or _JS_TEST_FILE_RE.search(path))
        if not is_test and language == "python":
            is_test = any(s.kind == SymbolKind.TEST for s in symbols)
        digest = self._digest(root, depth=0)
        return ParsedFile(
            file=normalize_path(path),
            language=language,
            symbols=symbols[:MAX_SYMBOLS_PER_FILE],
            references=references[:MAX_REFERENCES_PER_FILE],
            imports=imports,
            api_endpoints=endpoints,
            is_test=is_test,
            ast=digest,
            engine=self.engine_name,
            sha=sha256_text(source),
        )

    def _digest(self, node: Any, depth: int) -> AstNode:
        """Fold the tree into the §14.3 lightweight digest."""
        keep = (
            "function_definition",
            "class_definition",
            "decorated_definition",
            "function_declaration",
            "class_declaration",
            "method_definition",
            "lexical_declaration",
            "interface_declaration",
            "type_alias_declaration",
        )
        children: list[AstNode] = []
        if depth < 6:
            children = [
                self._digest(child, depth + 1)
                for child in node.children
                if child.type in keep
            ][:24]
        return AstNode(
            type=str(node.type),
            line=node.start_point[0] + 1,
            end_line=node.end_point[0] + 1,
            children=children,
        )

    def _extract_python(
        self,
        path: str,
        data: bytes,
        root: Any,
        symbols: list[Symbol],
        references: list[SymbolReference],
        imports: list[str],
        endpoints: list[ApiEndpoint],
        lines: list[str],
    ) -> None:
        norm = normalize_path(path)

        def _visit(node: Any, container: str) -> None:
            kind = node.type
            if kind == "decorated_definition":
                inner = node.child_by_field_name("definition")
                inner_name = ""
                if inner is not None:
                    name_node = inner.child_by_field_name("name")
                    if name_node is not None:
                        inner_name = _node_text(name_node, data)
                before = len(endpoints)
                for child in node.children:
                    _visit(child, container)
                for endpoint in endpoints[before:]:
                    if not endpoint.handler and inner_name:
                        endpoint.handler = inner_name
                return
            if kind == "function_definition":
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = _node_text(name_node, data)
                    line = node.start_point[0] + 1
                    end_line = node.end_point[0] + 1
                    params_node = node.child_by_field_name("parameters")
                    params = (
                        _node_text(params_node, data) if params_node is not None else "()"
                    )
                    sig = f"def {name}{params}"
                    head = lines[line - 1].strip() if line - 1 < len(lines) else ""
                    if head.startswith("async "):
                        sig = f"async def {name}{params}"
                    qualified = f"{container}.{name}" if container else name
                    if name.startswith("test_"):
                        sym_kind = SymbolKind.TEST
                    elif container:
                        sym_kind = SymbolKind.METHOD
                    else:
                        sym_kind = SymbolKind.FUNCTION
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified=qualified,
                            kind=sym_kind,
                            file=norm,
                            line=line,
                            end_line=end_line,
                            signature=sig[:200],
                            container=container,
                            language="python",
                        )
                    )
                for child in node.children:
                    _visit(child, container)
                return
            if kind == "class_definition":
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = _node_text(name_node, data)
                    qualified = f"{container}.{name}" if container else name
                    sym_kind = SymbolKind.TEST if name.startswith("Test") else SymbolKind.CLASS
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified=qualified,
                            kind=sym_kind,
                            file=norm,
                            line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=f"class {name}",
                            container=container,
                            language="python",
                        )
                    )
                    for child in node.children:
                        _visit(child, qualified)
                return
            if kind == "import_statement":
                text = _node_text(node, data)
                imports.append(_clean_import(text))
                for part in re.findall(r"[\w.]+", text):
                    references.append(
                        SymbolReference(name=part, file=norm, line=node.start_point[0] + 1)
                    )
                return
            if kind == "import_from_statement":
                text = _node_text(node, data)
                imports.append(_clean_import(text))
                module = re.match(r"from\s+([\w.]+)", text)
                if module:
                    references.append(
                        SymbolReference(
                            name=module.group(1).split(".")[0],
                            file=norm,
                            line=node.start_point[0] + 1,
                        )
                    )
                imported = re.search(r"import\s+(.+)$", text)
                if imported:
                    for name in re.findall(r"\w+", imported.group(1)):
                        references.append(
                            SymbolReference(
                                name=name, file=norm, line=node.start_point[0] + 1
                            )
                        )
                return
            if kind == "decorator":
                endpoint = _endpoint_from_decorator(
                    _node_text(node, data), path, node.start_point[0] + 1
                )
                if endpoint is not None:
                    endpoints.append(endpoint)
                return
            if kind == "identifier":
                name = _node_text(node, data)
                if (
                    len(references) < MAX_REFERENCES_PER_FILE
                    and name not in builtin_names()
                ):
                    references.append(
                        SymbolReference(name=name, file=norm, line=node.start_point[0] + 1)
                    )
                return
            for child in node.children:
                _visit(child, container)

        for child in root.children:
            _visit(child, "")

    def _extract_js(
        self,
        path: str,
        data: bytes,
        root: Any,
        symbols: list[Symbol],
        references: list[SymbolReference],
        imports: list[str],
        endpoints: list[ApiEndpoint],
    ) -> None:
        language = detect_language(path)
        norm = normalize_path(path)

        def _visit(node: Any, container: str) -> None:
            kind = node.type
            if kind == "export_statement":
                for child in node.children:
                    _visit(child, container)
                return
            if kind == "function_declaration":
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = _node_text(name_node, data)
                    qualified = f"{container}.{name}" if container else name
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified=qualified,
                            kind=SymbolKind.FUNCTION,
                            file=norm,
                            line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=f"function {name}()",
                            container=container,
                            language=language,
                        )
                    )
                for child in node.children:
                    _visit(child, container)
                return
            if kind == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = _node_text(name_node, data)
                    qualified = f"{container}.{name}" if container else name
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified=qualified,
                            kind=SymbolKind.CLASS,
                            file=norm,
                            line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=f"class {name}",
                            container=container,
                            language=language,
                        )
                    )
                    for child in node.children:
                        _visit(child, qualified)
                return
            if kind == "method_definition":
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = _node_text(name_node, data)
                    qualified = f"{container}.{name}" if container else name
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified=qualified,
                            kind=SymbolKind.METHOD,
                            file=norm,
                            line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=f"{name}()",
                            container=container,
                            language=language,
                        )
                    )
                return
            if kind == "variable_declarator":
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = _node_text(name_node, data)
                    value_node = node.child_by_field_name("value")
                    is_fn = value_node is not None and value_node.type in (
                        "arrow_function",
                        "function_expression",
                    )
                    if is_fn:
                        sym_kind = SymbolKind.FUNCTION
                    elif name.isupper():
                        sym_kind = SymbolKind.CONSTANT
                    else:
                        sym_kind = SymbolKind.VARIABLE
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified=f"{container}.{name}" if container else name,
                            kind=sym_kind,
                            file=norm,
                            line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=f"{name} = ()" if is_fn else f"{name} =",
                            container=container,
                            language=language,
                        )
                    )
                return
            if kind in ("interface_declaration", "type_alias_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    name = _node_text(name_node, data)
                    is_interface = kind == "interface_declaration"
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified=name,
                            kind=SymbolKind.INTERFACE if is_interface else SymbolKind.TYPE,
                            file=norm,
                            line=node.start_point[0] + 1,
                            end_line=node.end_point[0] + 1,
                            signature=f"{'interface' if is_interface else 'type'} {name}",
                            container=container,
                            language=language,
                        )
                    )
                return
            if kind == "import_statement":
                imports.append(_clean_import(_node_text(node, data)))
                return
            if kind == "call_expression":
                full = _node_text(node, data)
                if full.startswith("require"):
                    spec = re.search(r"['\"]([^'\"]+)['\"]", full)
                    if spec is not None:
                        imports.append(f"require '{spec.group(1)}'")
                else:
                    endpoint = _endpoint_from_express(full, path, node.start_point[0] + 1)
                    if endpoint is not None:
                        endpoints.append(endpoint)
                for child in node.children:
                    _visit(child, container)
                return
            if kind == "identifier":
                if len(references) < MAX_REFERENCES_PER_FILE:
                    name = _node_text(node, data)
                    references.append(
                        SymbolReference(name=name, file=norm, line=node.start_point[0] + 1)
                    )
                return
            for child in node.children:
                _visit(child, container)

        for child in root.children:
            _visit(child, "")


# ----------------------------------------------------- stdlib-ast engine


class StdlibAstParser:
    """§14.3 Python path — the ``ast`` module, zero wheels.

    Full signatures (``ast.unparse``), module/class-scope symbols only
    (function locals are noise, not index material), and the same
    reference walk (``ast.Name`` loads minus builtins).
    """

    engine_name = "stdlib-ast"

    def supports(self, language: str) -> bool:
        return language == "python"

    def parse(self, path: str, source: str) -> ParsedFile:
        path = normalize_path(path)
        try:
            tree = pyast.parse(source)
        except SyntaxError:
            return ParsedFile(
                file=path,
                language="python",
                symbols=[],
                imports=[],
                is_test=bool(_PY_TEST_FILE_RE.search(path)),
                engine=self.engine_name,
                sha=sha256_text(source),
            )
        symbols: list[Symbol] = []
        references: list[SymbolReference] = []
        imports: list[str] = []
        endpoints: list[ApiEndpoint] = []

        def visit(node: pyast.AST, container: str, scope: str) -> None:
            """``scope`` — "module" | "class" | "function" of the child."""
            for child in pyast.iter_child_nodes(node):
                if isinstance(child, pyast.FunctionDef | pyast.AsyncFunctionDef):
                    name = child.name
                    qualified = f"{container}.{name}" if container else name
                    if name.startswith("test_"):
                        child_kind = SymbolKind.TEST
                    elif scope == "class":
                        child_kind = SymbolKind.METHOD
                    else:
                        child_kind = SymbolKind.FUNCTION
                    sig_args: list[str] = []
                    args = child.args
                    for arg in list(args.posonlyargs) + list(args.args):
                        text = arg.arg
                        if arg.annotation is not None:
                            text += f": {pyast.unparse(arg.annotation)}"
                        sig_args.append(text)
                    if args.vararg is not None:
                        sig_args.append(f"*{args.vararg.arg}")
                    for arg in args.kwonlyargs:
                        text = arg.arg
                        if arg.annotation is not None:
                            text += f": {pyast.unparse(arg.annotation)}"
                        sig_args.append(text)
                    if args.kwarg is not None:
                        sig_args.append(f"**{args.kwarg.arg}")
                    prefix = (
                        "async def"
                        if isinstance(child, pyast.AsyncFunctionDef)
                        else "def"
                    )
                    returns = (
                        f" -> {pyast.unparse(child.returns)}"
                        if child.returns is not None
                        else ""
                    )
                    signature = f"{prefix} {name}({', '.join(sig_args)}){returns}"
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified=qualified,
                            kind=child_kind,
                            file=path,
                            line=child.lineno or 0,
                            end_line=getattr(child, "end_lineno", None)
                            or child.lineno
                            or 0,
                            signature=signature[:200],
                            container=container,
                            language="python",
                        )
                    )
                    for dec in child.decorator_list:
                        endpoint = _endpoint_from_decorator(
                            pyast.unparse(dec),
                            path,
                            dec.lineno or child.lineno or 0,
                            handler=name,
                        )
                        if endpoint is not None:
                            endpoints.append(endpoint)
                    visit(child, qualified, "function")
                    continue
                if isinstance(child, pyast.ClassDef):
                    name = child.name
                    qualified = f"{container}.{name}" if container else name
                    symbols.append(
                        Symbol(
                            name=name,
                            qualified=qualified,
                            kind=SymbolKind.TEST
                            if name.startswith("Test")
                            else SymbolKind.CLASS,
                            file=path,
                            line=child.lineno or 0,
                            end_line=getattr(child, "end_lineno", None)
                            or child.lineno
                            or 0,
                            signature=f"class {name}",
                            container=container,
                            language="python",
                        )
                    )
                    for base in child.bases:
                        base_name = pyast.unparse(base)
                        references.append(
                            SymbolReference(
                                name=base_name.split(".")[-1],
                                file=path,
                                line=child.lineno or 0,
                            )
                        )
                    visit(child, qualified, "class")
                    continue
                if isinstance(child, pyast.Import):
                    for alias in child.names:
                        imports.append(f"import {alias.name}")
                        references.append(
                            SymbolReference(
                                name=alias.name.split(".")[0],
                                file=path,
                                line=child.lineno or 0,
                            )
                        )
                    continue
                if isinstance(child, pyast.ImportFrom):
                    module = "." * (child.level or 0) + (child.module or "")
                    imports.append(
                        f"from {module} import {', '.join(a.name for a in child.names)}"
                    )
                    root_name = (child.module or "").split(".")[0]
                    if root_name:
                        references.append(
                            SymbolReference(
                                name=root_name, file=path, line=child.lineno or 0
                            )
                        )
                    for alias in child.names:
                        references.append(
                            SymbolReference(
                                name=alias.name, file=path, line=child.lineno or 0
                            )
                        )
                    continue
                if isinstance(child, pyast.Assign | pyast.AnnAssign) and scope in (
                    "module",
                    "class",
                ):
                    targets = (
                        child.targets
                        if isinstance(child, pyast.Assign)
                        else [child.target]
                    )
                    for target in targets:
                        if isinstance(target, pyast.Name):
                            qualified = (
                                f"{container}.{target.id}" if container else target.id
                            )
                            symbols.append(
                                Symbol(
                                    name=target.id,
                                    qualified=qualified,
                                    kind=SymbolKind.CONSTANT
                                    if target.id.isupper()
                                    else SymbolKind.VARIABLE,
                                    file=path,
                                    line=target.lineno or 0,
                                    end_line=getattr(target, "end_lineno", None)
                                    or target.lineno
                                    or 0,
                                    signature=f"{target.id} =",
                                    container=container,
                                    language="python",
                                )
                            )
                    visit(child, container, scope)  # walk the value for references
                    continue
                if isinstance(child, pyast.Name) and isinstance(child.ctx, pyast.Load):
                    if (
                        child.id not in builtin_names()
                        and len(references) < MAX_REFERENCES_PER_FILE
                    ):
                        references.append(
                            SymbolReference(name=child.id, file=path, line=child.lineno or 0)
                        )
                    continue
                if isinstance(child, pyast.Attribute):
                    base = child
                    while isinstance(base, pyast.Attribute):
                        base = base.value
                    if (
                        isinstance(base, pyast.Name)
                        and base.id not in builtin_names()
                        and len(references) < MAX_REFERENCES_PER_FILE
                    ):
                        references.append(
                            SymbolReference(
                                name=base.id, file=path, line=base.lineno or 0
                            )
                        )
                    continue
                visit(child, container, scope)

        visit(tree, "", "module")
        digest = self._digest(tree)
        is_test = bool(_PY_TEST_FILE_RE.search(path)) or any(
            s.kind == SymbolKind.TEST for s in symbols
        )
        return ParsedFile(
            file=path,
            language="python",
            symbols=symbols[:MAX_SYMBOLS_PER_FILE],
            references=references[:MAX_REFERENCES_PER_FILE],
            imports=imports,
            api_endpoints=endpoints,
            is_test=is_test,
            ast=digest,
            engine=self.engine_name,
            sha=sha256_text(source),
        )

    def _digest(self, tree: pyast.Module) -> AstNode:
        """Fold the stdlib tree into the §14.3 lightweight digest."""

        def convert(node: pyast.AST, depth: int) -> AstNode:
            children: list[AstNode] = []
            if depth < 6:
                for child in pyast.iter_child_nodes(node):
                    if isinstance(
                        child,
                        pyast.FunctionDef
                        | pyast.AsyncFunctionDef
                        | pyast.ClassDef
                        | pyast.Assign
                        | pyast.If
                        | pyast.Try,
                    ):
                        children.append(convert(child, depth + 1))
                    if len(children) >= 24:
                        break
            name = ""
            if isinstance(node, pyast.FunctionDef | pyast.AsyncFunctionDef):
                name = node.name
            elif isinstance(node, pyast.ClassDef):
                name = node.name
            elif isinstance(node, pyast.Assign):
                for target in node.targets:
                    if isinstance(target, pyast.Name):
                        name = target.id
                        break
            return AstNode(
                type=type(node).__name__,
                name=name,
                line=getattr(node, "lineno", 0) or 0,
                end_line=getattr(node, "end_lineno", 0)
                or getattr(node, "lineno", 0)
                or 0,
                children=children,
            )

        return convert(tree, 0)


# --------------------------------------------------------- regex engine


class RegexParser:
    """The honest JS-family fallback — lines, not trees.

    Used only when tree-sitter is absent and the file is JS-family: a
    coarse symbol/import/route scan that keeps the §14.11 index usable
    on any runtime. ``engine`` reports ``regex`` — never a fake
    tree-sitter claim.
    """

    engine_name = "regex"

    def supports(self, language: str) -> bool:
        return language in ("javascript", "typescript", "tsx", "jsx")

    def parse(self, path: str, source: str) -> ParsedFile:
        path = normalize_path(path)
        language = detect_language(path)
        symbols: list[Symbol] = []
        imports: list[str] = []
        endpoints: list[ApiEndpoint] = []
        for match in _RE_JS_FUNCTION.finditer(source):
            symbols.append(
                self._sym(match, "function", path, language, f"function {match.group('name')}()")
            )
        for match in _RE_JS_CLASS.finditer(source):
            symbols.append(
                self._sym(match, "class", path, language, f"class {match.group('name')}")
            )
        for match in _RE_JS_CONST.finditer(source):
            name = match.group("name")
            symbols.append(
                self._sym(
                    match,
                    "constant" if name.isupper() else "variable",
                    path,
                    language,
                    f"{name} =",
                )
            )
        for match in _RE_JS_IMPORT.finditer(source):
            spec = match.group("spec") or match.group("spec2") or ""
            if spec:
                # quoted on purpose: the §14.4 resolver's specifier regex
                # looks for the quotes (same shape as a real statement)
                imports.append(f"import '{spec}'")
        for match in _RE_JS_REQUIRE.finditer(source):
            imports.append(f"require '{match.group('spec')}'")
        for match in _RE_EXPRESS_LINE.finditer(source):
            endpoints.append(
                ApiEndpoint(
                    method=match.group("method").upper(),
                    path=match.group("path"),
                    file=path,
                    line=match.string.count("\n", 0, match.start()) + 1,
                    framework="express",
                )
            )
        is_test = bool(_JS_TEST_FILE_RE.search(path))
        return ParsedFile(
            file=path,
            language=language,
            symbols=symbols[:MAX_SYMBOLS_PER_FILE],
            references=[],
            imports=imports,
            api_endpoints=endpoints,
            is_test=is_test,
            ast=AstNode(type="regex-scan", name=path, line=1, end_line=source.count("\n") + 1),
            engine=self.engine_name,
            sha=sha256_text(source),
        )

    def _sym(
        self, match: re.Match[str], kind: str, path: str, language: str, signature: str
    ) -> Symbol:
        name = match.group("name")
        line = match.string.count("\n", 0, match.start()) + 1
        end = match.string.count("\n", 0, match.end()) + 1
        return Symbol(
            name=name,
            qualified=name,
            kind=kind,
            file=path,
            line=line,
            end_line=end,
            signature=signature,
            language=language,
        )


# ------------------------------------------------------- §14.3 registry


class ParserRegistry:
    """Resolves one parser per language — §14.3, honest preference.

    ``prefer="auto"``        — Python → stdlib-ast (richest
                               signatures); JS-family → tree-sitter,
                               regex when tree-sitter is absent.
    ``prefer="tree-sitter"`` — everything tree-sitter can hold; the
                               MODE A live path (§14.12 incremental).
    ``prefer="stdlib"``      — stdlib-ast / regex only, zero wheels.
    """

    def __init__(self, prefer: str = "auto") -> None:
        if prefer not in ("auto", "tree-sitter", "stdlib"):
            raise ValueError(f"unknown parser preference: {prefer!r}")
        self._prefer = prefer
        self._stdlib = StdlibAstParser()
        self._regex = RegexParser()
        self._tree_sitter: TreeSitterEngine | None = None
        if _TS_ROOT:
            try:
                self._tree_sitter = TreeSitterEngine()
            except Exception:
                self._tree_sitter = None

    @property
    def preference(self) -> str:
        return self._prefer

    @property
    def tree_sitter(self) -> TreeSitterEngine | None:
        """The live MODE A engine when this runtime holds it."""
        return self._tree_sitter

    def engine_status(self) -> dict[str, Any]:
        status: dict[str, Any] = {
            "preference": self._prefer,
            "stdlib-ast": True,
            "regex": True,
            "tree-sitter": self._tree_sitter is not None,
        }
        if self._tree_sitter is not None:
            status["tree-sitter-languages"] = sorted(self._tree_sitter.languages)
        return status

    def parser_for(self, language: str) -> Any:
        """The engine that parses this language here and now."""
        # "stdlib" = zero wheels, for any language — the honest floor
        tree_sitter = (
            None if self._prefer == "stdlib" else self._tree_sitter
        )
        if language == "python":
            if (
                self._prefer == "tree-sitter"
                and tree_sitter is not None
                and tree_sitter.supports("python")
            ):
                return tree_sitter
            return self._stdlib
        if language in ("javascript", "typescript", "tsx", "jsx"):
            if tree_sitter is not None and tree_sitter.supports(language):
                return tree_sitter
            return self._regex
        return self._regex

    def parse(self, path: str, source: str) -> ParsedFile:
        language = detect_language(path)
        parser = self.parser_for(language)
        return parser.parse(path, source)


# ------------------------------------------------------------ helpers


def _node_text(node: Any, data: bytes) -> str:
    try:
        return data[node.start_byte : node.end_byte].decode("utf-8", errors="replace")
    except Exception:
        return ""


def _clean_import(text: str) -> str:
    return " ".join(text.split())[:200]


def _endpoint_from_decorator(
    text: str, path: str, line: int, handler: str = ""
) -> ApiEndpoint | None:
    """Flask / FastAPI route decorator → §14.5 endpoint."""
    text = text.strip()
    if text.startswith("@"):
        text = text[1:]
    match = _FLASK_RE.match(text)
    if match is None:
        return None
    method = match.group("method")
    if method == "route":
        declared = re.search(r"methods\s*=\s*\[(.*?)\]", text)
        if declared:
            verbs = {
                verb
                for pair in re.findall(r"'(\w+)'|\"(\w+)\"", declared.group(1))
                for verb in pair
                if verb
            }
            method = "/".join(sorted(verbs)) if verbs else ""
        else:
            method = ""
    framework = "flask" if match.group("obj") in ("app", "application") else "fastapi"
    return ApiEndpoint(
        method=method.upper(),
        path=match.group("path"),
        file=normalize_path(path),
        handler=handler,
        line=line,
        framework=framework,
    )


def _endpoint_from_express(text: str, path: str, line: int) -> ApiEndpoint | None:
    """Express route registration → §14.5 endpoint."""
    match = _EXPRESS_CALL_RE.match(" ".join(text.split()))
    if match is None:
        return None
    return ApiEndpoint(
        method=match.group("method").upper(),
        path=match.group("path"),
        file=normalize_path(path),
        handler="",
        line=line,
        framework="express",
    )


def _byte_edit(
    old: bytes, new: bytes
) -> tuple[int, int, int, tuple[int, int], tuple[int, int], tuple[int, int]]:
    """The changed byte range between two sources (prefix/suffix match)."""
    if old == new:
        return 0, 0, 0, (0, 0), (0, 0), (0, 0)
    start = 0
    limit = min(len(old), len(new))
    while start < limit and old[start] == new[start]:
        start += 1
    end_old, end_new = len(old), len(new)
    while end_old > start and end_new > start and old[end_old - 1] == new[end_new - 1]:
        end_old -= 1
        end_new -= 1
    start_point = _point_at(old, start)
    old_end_point = _point_at(old, end_old)
    new_end_point = _point_at(new, end_new)
    return start, end_old, end_new, start_point, old_end_point, new_end_point


def _point_at(data: bytes, offset: int) -> tuple[int, int]:
    head = data[:offset]
    row = head.count(b"\n")
    last_nl = head.rfind(b"\n")
    col = offset - (last_nl + 1) if last_nl >= 0 else offset
    return (row, col)


def _line_edit(old: str, new: str) -> tuple[int, int]:
    """Changed 1-based line range between two sources."""
    old_lines = old.splitlines()
    new_lines = new.splitlines()
    start = 0
    while (
        start < len(old_lines)
        and start < len(new_lines)
        and old_lines[start] == new_lines[start]
    ):
        start += 1
    end_old, end_new = len(old_lines), len(new_lines)
    while (
        end_old > start
        and end_new > start
        and old_lines[end_old - 1] == new_lines[end_new - 1]
    ):
        end_old -= 1
        end_new -= 1
    return start + 1, max(end_old, end_new)


def build_registry(prefer: str = "auto") -> ParserRegistry:
    """The §14.3 registry entry point."""
    return ParserRegistry(prefer=prefer)


def line_edit(old: str, new: str) -> tuple[int, int]:
    """Public §14.12 helper — the changed 1-based line range."""
    return _line_edit(old, new)
