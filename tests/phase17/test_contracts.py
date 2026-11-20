"""Phase 17 · §17.1/§17.3/§17.4 contracts — verbatim vocab + confidence math."""

from __future__ import annotations

import pytest

from nexus.research import (
    AUTHORITY_BY_CLASS,
    CONFIDENCE_DIMENSIONS,
    DEFAULT_WEIGHTS,
    SOURCE_CLASSES,
    SOURCE_KINDS,
    ProviderError,
    ResearchError,
    SearchHit,
    SourceClass,
    SourceConfidence,
    SourceKind,
    confidence_from_hit,
    extract_terms,
)

# --------------------------------------------------------------- §17.1 kinds


def test_five_source_kinds_verbatim() -> None:
    assert SOURCE_KINDS == ("web", "github", "docs", "forums", "local")


def test_kind_constants_match_tuple() -> None:
    assert (SourceKind.WEB, SourceKind.GITHUB, SourceKind.DOCS, SourceKind.FORUMS,
            SourceKind.LOCAL) == SOURCE_KINDS


def test_hit_requires_title_and_uri() -> None:
    with pytest.raises(ResearchError):
        SearchHit(title="  ", uri="https://x")
    with pytest.raises(ResearchError):
        SearchHit(title="t", uri="")


def test_hit_rejects_unknown_kind() -> None:
    with pytest.raises(ResearchError):
        SearchHit(title="t", uri="u", kind="deep-web")


def test_hit_timestamps_itself() -> None:
    hit = SearchHit(title="t", uri="u")
    assert "T" in hit.fetched_at and hit.metadata == {}


# --------------------------------------------------------------- §17.3 class


def test_six_source_classes_verbatim() -> None:
    assert SOURCE_CLASSES == ("official", "documentation", "academic", "community",
                              "personal", "unknown")


def test_class_constants_match_tuple() -> None:
    assert (SourceClass.OFFICIAL, SourceClass.DOCUMENTATION, SourceClass.ACADEMIC,
            SourceClass.COMMUNITY, SourceClass.PERSONAL, SourceClass.UNKNOWN) == SOURCE_CLASSES


# --------------------------------------------------------------- §17.4 math


def test_four_confidence_dimensions_verbatim() -> None:
    assert CONFIDENCE_DIMENSIONS == ("authority", "relevance", "freshness", "evidence")


def test_default_weights_sum_to_one() -> None:
    assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9
    assert set(DEFAULT_WEIGHTS) == set(CONFIDENCE_DIMENSIONS)


def test_confidence_score_is_weighted_mean() -> None:
    conf = SourceConfidence(authority=1.0, relevance=0.0, freshness=0.0, evidence=0.0)
    assert conf.score() == pytest.approx(DEFAULT_WEIGHTS["authority"], abs=1e-3)
    assert conf.breakdown() == {"authority": 1.0, "relevance": 0.0, "freshness": 0.0,
                                "evidence": 0.0}


def test_confidence_bounds_enforced() -> None:
    with pytest.raises(ResearchError):
        SourceConfidence(authority=1.5, relevance=0.0, freshness=0.0, evidence=0.0)
    with pytest.raises(ResearchError):
        SourceConfidence(authority=0.0, relevance=0.0, freshness=0.0, evidence=-0.1)


def test_confidence_weights_must_sum_to_one() -> None:
    with pytest.raises(ResearchError):
        SourceConfidence(authority=0.5, relevance=0.5, freshness=0.5, evidence=0.5,
                         weights={"authority": 0.4, "relevance": 0.4, "freshness": 0.0,
                                  "evidence": 0.0})


def test_authority_prior_per_class() -> None:
    assert AUTHORITY_BY_CLASS[SourceClass.OFFICIAL] > AUTHORITY_BY_CLASS[SourceClass.ACADEMIC]
    assert AUTHORITY_BY_CLASS[SourceClass.ACADEMIC] > AUTHORITY_BY_CLASS[SourceClass.DOCUMENTATION]
    assert AUTHORITY_BY_CLASS[SourceClass.DOCUMENTATION] > AUTHORITY_BY_CLASS[SourceClass.COMMUNITY]
    assert AUTHORITY_BY_CLASS[SourceClass.COMMUNITY] > AUTHORITY_BY_CLASS[SourceClass.PERSONAL]
    assert AUTHORITY_BY_CLASS[SourceClass.PERSONAL] > AUTHORITY_BY_CLASS[SourceClass.UNKNOWN]


def test_relevance_is_term_overlap() -> None:
    hit = SearchHit(title="llama.cpp runs GGUF", uri="u",
                    snippet="llama.cpp runs GGUF models locally")
    conf = confidence_from_hit(hit, classification="official",
                               query_terms=("llama.cpp", "gguf", "local"))
    assert conf.relevance == pytest.approx(1.0, abs=1e-3)


def test_freshness_decays_and_hides_neutral() -> None:
    terms: tuple[str, ...] = ()
    fresh = SearchHit(title="t", uri="u", snippet="s",
                      metadata={"published": "2099-01-01T00:00:00+00:00"})
    stale = SearchHit(title="t", uri="u", snippet="s",
                      metadata={"published": "2000-01-01T00:00:00+00:00"})
    none = SearchHit(title="t", uri="u", snippet="s")
    assert confidence_from_hit(fresh, classification="official", query_terms=terms).freshness == 1.0
    assert confidence_from_hit(stale, classification="official", query_terms=terms).freshness == 0.0
    assert confidence_from_hit(none, classification="official", query_terms=terms).freshness == 0.5


def test_evidence_dimension_reads_the_snippet() -> None:
    terms = ("gguf", "ram")
    no_snippet = confidence_from_hit(SearchHit(title="t", uri="u"), classification="official",
                                     query_terms=terms)
    plain = confidence_from_hit(SearchHit(title="t", uri="u", snippet="a snippet"),
                                classification="official", query_terms=terms)
    backed = confidence_from_hit(SearchHit(title="t", uri="u", snippet="gguf needs ram"),
                                 classification="official", query_terms=terms)
    assert no_snippet.evidence == 0.0
    assert plain.evidence == 0.5
    assert backed.evidence == 1.0


def test_extract_terms_drops_noise_keeps_numbers() -> None:
    terms = extract_terms("The 7B model and the 13B model: what RAM?")
    assert "7b" in terms and "13b" in terms and "ram" in terms
    assert "the" not in terms and "what" not in terms


def test_provider_error_is_a_research_error() -> None:
    assert issubclass(ProviderError, ResearchError)
