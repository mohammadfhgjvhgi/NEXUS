"""The five §17.1 search surfaces — one adapter each, stdlib only.

The plan's surfaces, verbatim::

    web   github   docs   forums   local files

Every provider speaks the §17.1 :class:`SearchProvider` contract and
nothing else — the §17.2 workflow stays vendor-blind (Plan §61's law
applied to sources).  All five are honest:

* *no results* is an empty list;
* *the surface failed* is a raised :class:`ProviderError` — the
  workflow records it, it never hides it;
* a GitHub read needs no credential (public reads, §124 unchanged).

مزوّدات البحث الخمسة — سطح واحد لكل منها، مكتبة قياسية فقط، والصمت
نتيجة لا عذر: فراغ قائمة يعني لا نتائج، ورفع خطأ يعني أن السطح فشل.

Stdlib only (urllib for HTTP).
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .contracts import (
    ProviderError,
    SearchHit,
    SearchProvider,
    SourceKind,
    utc_now_iso,
)


class _JsonSearchProvider(SearchProvider):
    """Shared HTTP machinery for the JSON-speaking surfaces (web/forums).

    One GET per query; the response must be JSON with the hits under
    ``result_key``; each hit maps through ``field_map`` (title/uri/
    snippet) — a surface that answers oddly raises
    :class:`ProviderError` with the status it actually got.
    """

    kind = SourceKind.WEB

    def __init__(
        self,
        base_url: str,
        *,
        name: str,
        query_param: str = "q",
        extra_params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        result_key: str = "results",
        field_map: dict[str, str] | None = None,
        uri_template: str | None = None,
        strip_html: bool = False,
        timeout: float = 15.0,
    ) -> None:
        if not base_url.strip():
            raise ProviderError(f"{name}: base_url must be non-empty")
        self.base_url = base_url
        self.name = name
        self.query_param = query_param
        self.extra_params = dict(extra_params or {})
        self.headers = {"User-Agent": "NEXUS-Research/0.17 (local-first; +https://nexus.local)"}
        self.headers.update(headers or {})
        self.result_key = result_key
        self.field_map = {
            "title": "title",
            "uri": "url",
            "snippet": "snippet",
            **(field_map or {}),
        }
        self.uri_template = uri_template
        self.strip_html = strip_html
        self.timeout = timeout

    # ------------------------------------------------------------ contract

    def search(self, query: str, *, max_results: int = 10) -> list[SearchHit]:
        query = (query or "").strip()
        if not query:
            return []
        params = {self.query_param: query, **self.extra_params}
        url = f"{self.base_url}?{urllib.parse.urlencode(params)}"
        payload = self._fetch(url)
        rows = self._rows(payload)
        hits: list[SearchHit] = []
        for row in rows[: max(1, max_results)]:
            if not isinstance(row, dict):
                continue
            title = str(row.get(self.field_map["title"], "")).strip()
            uri = str(row.get(self.field_map["uri"], "")).strip()
            if self.uri_template and title:
                uri = self.uri_template.format(
                    title=urllib.parse.quote(title.replace(" ", "_"))
                )
            if not uri:
                continue
            snippet = str(row.get(self.field_map["snippet"], "")).strip()
            if self.strip_html:
                snippet = re.sub(r"<[^>]+>", "", snippet).strip()
            hits.append(
                SearchHit(
                    title=title or uri,
                    uri=uri,
                    snippet=snippet,
                    provider=self.name,
                    kind=self.kind,
                    fetched_at=utc_now_iso(),
                    metadata={k: str(v) for k, v in row.items() if isinstance(v, (str, int, float))
                              and k not in self.field_map.values()},
                )
            )
        return hits

    # ------------------------------------------------------------ plumbing

    def _fetch(self, url: str) -> Any:
        request = urllib.request.Request(url, headers=self.headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                if resp.status != 200:
                    raise ProviderError(f"{self.name}: HTTP {resp.status} from {url}")
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raise ProviderError(f"{self.name}: HTTP {exc.code} from {url}") from exc
        except urllib.error.URLError as exc:
            raise ProviderError(f"{self.name}: the surface is unreachable ({exc.reason})") from exc
        except OSError as exc:
            raise ProviderError(f"{self.name}: {exc}") from exc
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise ProviderError(f"{self.name}: response is not JSON") from exc

    def _rows(self, payload: Any) -> list[Any]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            node: Any = payload
            for part in self.result_key.split("."):  # dotted paths: "query.search"
                if isinstance(node, dict):
                    node = node.get(part)
                else:
                    node = None
                    break
            if isinstance(node, list):
                return node
        raise ProviderError(
            f"{self.name}: no '{self.result_key}' list in the response — "
            "point result_key/field_map at the actual shape"
        )


class WebSearchProvider(_JsonSearchProvider):
    """§17.1 *web* — an HTTP JSON search endpoint, behind the contract.

    Defaults fit a generic ``?q=`` JSON engine returning
    ``{"results": [{"title","url","snippet"}]}``; real engines enter by
    setting ``result_key``/``field_map`` — the workflow cannot tell.
    """

    def __init__(
        self,
        base_url: str,
        *,
        name: str = "web",
        query_param: str = "q",
        result_key: str = "results",
        field_map: dict[str, str] | None = None,
        uri_template: str | None = None,
        strip_html: bool = False,
        extra_params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> None:
        super().__init__(
            base_url,
            name=name,
            query_param=query_param,
            result_key=result_key,
            field_map=field_map,
            uri_template=uri_template,
            strip_html=strip_html,
            extra_params=extra_params,
            headers=headers,
            timeout=timeout,
        )
        self.kind = SourceKind.WEB


class ForumSearchProvider(_JsonSearchProvider):
    """§17.1 *forums* — a Discourse-style ``/search.json`` adapter.

    Defaults read ``{"topics": [{"title","url","blurb"}]}`` — the
    documented Discourse shape; other forums re-map like any surface.
    """

    def __init__(
        self,
        base_url: str,
        *,
        name: str = "forums",
        result_key: str = "topics",
        field_map: dict[str, str] | None = None,
        extra_params: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float = 15.0,
    ) -> None:
        super().__init__(
            base_url,
            name=name,
            result_key=result_key,
            field_map={"title": "title", "uri": "url", "snippet": "blurb", **(field_map or {})},
            extra_params=extra_params,
            headers=headers,
            timeout=timeout,
        )
        self.kind = SourceKind.FORUMS


class GitHubSearchProvider(SearchProvider):
    """§17.1 *github* — the §16.2 engine behind the research contract.

    Repository search only (public, credential-free — §124); each hit
    carries ``github_type=repo`` so §17.3 reads a repo as its
    project's official home, and the star count rides ``metadata``.
    """

    kind = SourceKind.GITHUB

    def __init__(self, engine: Any, *, name: str = "github") -> None:
        self.engine = engine
        self.name = name

    def search(self, query: str, *, max_results: int = 10) -> list[SearchHit]:
        query = (query or "").strip()
        if not query:
            return []
        candidates = self.engine.search(query)
        now = utc_now_iso()
        hits: list[SearchHit] = []
        for candidate in candidates[: max(1, max_results)]:
            data = candidate.as_dict()
            hits.append(
                SearchHit(
                    title=f"{data['owner']}/{data['name']}",
                    uri=data["url"],
                    snippet=str(data.get("description", "")),
                    provider=self.name,
                    kind=self.kind,
                    fetched_at=now,
                    metadata={
                        "github_type": "repo",
                        "stars": str(data.get("stars", 0)),
                        "language": str(data.get("language") or ""),
                        "pushed_at": str(data.get("pushed_at", "")),
                    },
                )
            )
        return hits


class _CorpusProvider(SearchProvider):
    """Shared local-corpus machinery (docs + local files).

    Walks real directories, matches the query's significant terms in
    the file's name and body, returns ``file://`` hits whose snippet
    is the matching line — evidence with an address, §17.4-grade.
    """

    max_file_bytes = 2_000_000

    def __init__(
        self,
        roots: tuple[str | Path, ...] | list[str | Path],
        *,
        name: str,
        extensions: tuple[str, ...] | None,
    ) -> None:
        roots_clean: list[Path] = []
        for root in roots:
            path = Path(root)
            if not path.is_dir():
                raise ProviderError(f"{name}: corpus root is not a directory: {path}")
            roots_clean.append(path)
        if not roots_clean:
            raise ProviderError(f"{name}: a corpus needs at least one root")
        self.roots = tuple(roots_clean)
        self.name = name
        self.extensions = extensions

    def _files(self) -> list[Path]:
        files: list[Path] = []
        for root in self.roots:
            for path in sorted(root.rglob("*")):
                if not path.is_file():
                    continue
                if self.extensions is not None and path.suffix.lower() not in self.extensions:
                    continue
                files.append(path)
        return files

    def search(self, query: str, *, max_results: int = 10) -> list[SearchHit]:
        from .contracts import extract_terms

        terms = extract_terms(query)
        if not terms:
            return []
        now = utc_now_iso()
        scored: list[tuple[float, Path, str]] = []
        for path in self._files():
            try:
                if path.stat().st_size > self.max_file_bytes:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue  # unreadable is honest absence — skip, do not fail
            lowered = text.lower()
            name_hits = sum(1 for term in terms if term in path.name.lower())
            body_hits = sum(1 for term in terms if term in lowered)
            if name_hits == 0 and body_hits == 0:
                continue
            snippet = ""
            best_line_score = 0
            for line in text.splitlines():
                lowered_line = line.lower()
                line_score = sum(1 for term in terms if term in lowered_line)
                if line_score > best_line_score:
                    best_line_score = line_score
                    snippet = line.strip()[:300]
            score = float(name_hits * 2 + body_hits)
            scored.append((score, path, snippet))
        scored.sort(key=lambda item: (-item[0], str(item[1])))
        hits: list[SearchHit] = []
        for _score, path, snippet in scored[: max(1, max_results)]:
            kind = SourceKind.DOCS if self.kind == SourceKind.DOCS else SourceKind.LOCAL
            hits.append(
                SearchHit(
                    title=path.name,
                    uri=path.resolve().as_uri(),
                    snippet=snippet,
                    provider=self.name,
                    kind=kind,
                    fetched_at=now,
                    metadata={"mtime": str(int(path.stat().st_mtime))},
                )
            )
        return hits


class DocsSearchProvider(_CorpusProvider):
    """§17.1 *docs* — a local documentation corpus (md/rst/txt/html)."""

    kind = SourceKind.DOCS

    def __init__(
        self,
        roots: tuple[str | Path, ...] | list[str | Path],
        *,
        name: str = "docs",
        extensions: tuple[str, ...] = (".md", ".rst", ".txt", ".html"),
    ) -> None:
        super().__init__(roots, name=name, extensions=extensions)


class LocalSearchProvider(_CorpusProvider):
    """§17.1 *local files* — any local tree, any text file."""

    kind = SourceKind.LOCAL

    def __init__(
        self,
        roots: tuple[str | Path, ...] | list[str | Path],
        *,
        name: str = "local",
        extensions: tuple[str, ...] | None = None,
    ) -> None:
        super().__init__(roots, name=name, extensions=extensions)
