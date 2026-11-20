"""Phase 17 · §17.3 — the six-class ladder, first match wins, unknown honest."""

from __future__ import annotations

import pytest

from nexus.research import ResearchError, SearchHit, SourceClass, classify


def hit(uri: str, **metadata: str) -> SearchHit:
    return SearchHit(title="t", uri=uri, metadata=metadata)


def test_academic_rung() -> None:
    assert classify(hit("https://arxiv.org/abs/2401.99999")) == SourceClass.ACADEMIC
    assert classify(hit("https://www.nature.com/articles/x")) == SourceClass.ACADEMIC
    assert classify(hit("https://cambridge.edu/paper")) == SourceClass.ACADEMIC
    assert classify(hit("https://doi.org/10.1000/x")) == SourceClass.ACADEMIC


def test_documentation_beats_official() -> None:
    assert classify(hit("https://docs.python.org/3/library/os.html")) == SourceClass.DOCUMENTATION
    assert classify(hit("https://developer.mozilla.org/en-US/docs/Web")) == (
        SourceClass.DOCUMENTATION
    )
    assert classify(hit("https://nexus.readthedocs.io/latest/")) == SourceClass.DOCUMENTATION
    assert classify(hit("https://plain.org/docs/guide/intro.md")) == SourceClass.DOCUMENTATION


def test_official_rung() -> None:
    assert classify(hit("https://www.python.org/download/")) == SourceClass.OFFICIAL
    assert classify(hit("https://kernel.org/")) == SourceClass.OFFICIAL
    assert classify(hit("https://www.iso.org/standard/9999.html")) == SourceClass.OFFICIAL
    assert classify(hit("https://energy.gov/grants")) == SourceClass.OFFICIAL


def test_github_repo_is_official_but_issues_are_community() -> None:
    assert classify(hit("https://github.com/ggml-org/llama.cpp", github_type="repo")) == (
        SourceClass.OFFICIAL
    )
    assert classify(hit("https://github.com/o/r/issues/12", github_type="issue")) == (
        SourceClass.COMMUNITY
    )
    assert classify(hit("https://github.com/o/r/discussions/9", github_type="discussion")) == (
        SourceClass.COMMUNITY
    )
    assert classify(hit("https://github.com/o/r/wiki", github_type="wiki")) == (
        SourceClass.DOCUMENTATION
    )


def test_community_rung() -> None:
    assert classify(hit("https://www.reddit.com/r/LocalLLaMA/")) == SourceClass.COMMUNITY
    assert classify(hit("https://stackoverflow.com/q/1")) == SourceClass.COMMUNITY
    assert classify(hit("https://news.ycombinator.com/item?id=1")) == SourceClass.COMMUNITY
    assert classify(hit("https://talk.dev/x/t/some-topic/12")) == SourceClass.COMMUNITY


def test_personal_rung() -> None:
    assert classify(hit("https://alice.wordpress.com/post")) == SourceClass.PERSONAL
    assert classify(hit("https://bob.substack.com/p/x")) == SourceClass.PERSONAL
    assert classify(hit("https://blog.carol.dev/x")) == SourceClass.PERSONAL


def test_unknown_is_the_honest_fallback() -> None:
    assert classify(hit("https://strange-site.example.net/a/b")) == SourceClass.UNKNOWN


def test_local_files_classify_by_path() -> None:
    assert classify(hit("file:///C:/proj/docs/guide.md")) == SourceClass.DOCUMENTATION
    assert classify(hit("file:///C:/proj/data.bin")) == SourceClass.UNKNOWN


def test_explicit_metadata_wins_and_is_validated() -> None:
    assert classify(hit("https://x.example.net/a", nexus_class="academic")) == (
        SourceClass.ACADEMIC
    )
    with pytest.raises(ResearchError):
        classify(hit("https://x.example.net/a", nexus_class="conspiracy"))
