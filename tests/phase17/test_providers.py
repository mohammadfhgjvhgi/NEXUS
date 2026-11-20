"""Phase 17 · §17.1 — the five surfaces, one adapter each, all honest."""

from __future__ import annotations

from pathlib import Path

import pytest
from fixtures import SurfaceServer, make_docs_corpus, make_local_tree

from nexus.github import GitHubClient, GitHubEngine
from nexus.research import (
    DocsSearchProvider,
    ForumSearchProvider,
    GitHubSearchProvider,
    LocalSearchProvider,
    ProviderError,
    SearchProvider,
    SourceKind,
    WebSearchProvider,
)

# ------------------------------------------------------------- machinery


@pytest.fixture()
def server() -> SurfaceServer:
    surface = SurfaceServer().start()
    yield surface
    surface.stop()


# ------------------------------------------------------------------- web


def test_web_provider_hits_the_endpoint(server: SurfaceServer) -> None:
    web = WebSearchProvider(f"{server.base}/web")
    hits = web.search("llama.cpp gguf ram", max_results=10)
    assert len(hits) == 5
    assert hits[0].kind == SourceKind.WEB and hits[0].provider == "web"
    assert hits[0].uri.startswith("https://")


def test_web_provider_maps_custom_fields(server: SurfaceServer) -> None:
    forum = ForumSearchProvider(f"{server.base}/search.json")
    hits = forum.search("llama.cpp ram")
    assert len(hits) == 2
    assert hits[0].kind == SourceKind.FORUMS
    assert "4 GB" in hits[0].snippet


def test_web_provider_is_honest_on_500(server: SurfaceServer) -> None:
    web = WebSearchProvider(f"{server.base}/broken")
    with pytest.raises(ProviderError, match="500"):
        web.search("anything")


def test_web_provider_is_honest_on_404(server: SurfaceServer) -> None:
    web = WebSearchProvider(f"{server.base}/nope")
    with pytest.raises(ProviderError):
        web.search("anything")


def test_empty_query_is_empty_not_an_error(server: SurfaceServer) -> None:
    web = WebSearchProvider(f"{server.base}/web")
    assert web.search("   ") == []


def test_providers_are_search_providers() -> None:
    for cls in (WebSearchProvider, ForumSearchProvider, GitHubSearchProvider,
                DocsSearchProvider, LocalSearchProvider):
        assert issubclass(cls, SearchProvider)


# ---------------------------------------------------------------- github


def test_github_provider_wraps_the_16_2_engine(server: SurfaceServer) -> None:
    engine = GitHubEngine(client=GitHubClient(base=server.base, timeout=10))
    provider = GitHubSearchProvider(engine)
    hits = provider.search("llama.cpp")
    assert len(hits) == 1
    assert hits[0].kind == SourceKind.GITHUB
    assert hits[0].metadata["github_type"] == "repo"
    assert hits[0].uri == "https://github.com/ggml-org/llama.cpp"


def test_github_provider_marks_repos_so_classification_reads_official(
    server: SurfaceServer,
) -> None:
    from nexus.research import classify

    engine = GitHubEngine(client=GitHubClient(base=server.base, timeout=10))
    hit = GitHubSearchProvider(engine).search("llama.cpp")[0]
    assert classify(hit) == "official"


# ------------------------------------------------------------------ docs


def test_docs_provider_walks_a_real_corpus(tmp_path: Path) -> None:
    docs_dir = make_docs_corpus(tmp_path)
    docs = DocsSearchProvider([docs_dir])
    hits = docs.search("gguf memory requirements", max_results=5)
    assert hits, "the corpus must answer a corpus-shaped question"
    assert all(h.kind == SourceKind.DOCS for h in hits)
    assert all(h.uri.startswith("file:") for h in hits)
    assert hits[0].snippet, "the corpus hit carries its matching line"


def test_docs_provider_rank_name_matches_above_body(tmp_path: Path) -> None:
    docs_dir = make_docs_corpus(tmp_path)
    docs = DocsSearchProvider([docs_dir])
    hits = docs.search("llama.cpp", max_results=5)
    assert hits[0].title == "llama-cpp.md"


def test_docs_provider_rejects_missing_root(tmp_path: Path) -> None:
    with pytest.raises(ProviderError, match="not a directory"):
        DocsSearchProvider([tmp_path / "nope"])


# ----------------------------------------------------------------- local


def test_local_provider_finds_code_and_notes(tmp_path: Path) -> None:
    tree = make_local_tree(tmp_path)
    local = LocalSearchProvider([tree])
    hits = local.search("llama.cpp benchmark")
    titles = {h.title for h in hits}
    assert "todo.txt" in titles and "bench.py" in titles
    assert "shopping.txt" not in titles, "unrelated files stay out"


def test_local_provider_honest_absence(tmp_path: Path) -> None:
    tree = make_local_tree(tmp_path)
    local = LocalSearchProvider([tree])
    assert local.search("quantum chromodynamics warp drive") == []
