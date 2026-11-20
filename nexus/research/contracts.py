"""Research-engine contracts (New Plan §17.1 · §17.3 · §17.4).

Three vocabularies are verbatim from the plan:

§17.1 — the five search surfaces::

    web   github   docs   forums   local files

§17.3 — the six source classes::

    official   documentation   academic   community   personal   unknown

§17.4 — the four confidence dimensions, per source::

    authority   relevance   freshness   evidence

NEXUS owns the research semantics (Plan §61's law applied to sources):
every external search backend (a web engine, a Discourse forum, the
GitHub REST API, a local corpus) enters behind :class:`SearchProvider`
as an adapter — the §17.2 workflow never sees a vendor type.  This
module owns vocabulary, shapes and the confidence algebra.

عقود محرك البحث — أسطح البحث الخمسة والتصنيف الست وأبعاد الثقة الأربعة
حرفيًا كما في الخطة؛ كل محرك بحث خارجي يدخل كمحول خلف العقد الواحد.

Stdlib only.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# ----------------------------------------------------------------- errors


class ResearchError(Exception):
    """Research-engine misuse or operation failure."""


class ProviderError(ResearchError):
    """One search surface failed — the workflow records it, never hides it."""


# ------------------------------------------------------------ §17.1 kinds


class SourceKind:
    """The five §17.1 search surfaces, verbatim vocabulary."""

    WEB = "web"
    GITHUB = "github"
    DOCS = "docs"
    FORUMS = "forums"
    LOCAL = "local"


SOURCE_KINDS: tuple[str, ...] = (
    SourceKind.WEB,
    SourceKind.GITHUB,
    SourceKind.DOCS,
    SourceKind.FORUMS,
    SourceKind.LOCAL,
)


class SearchProvider(ABC):
    """One §17.1 surface — the only shape the workflow knows.

    ``name`` is a stable id (appears in evidence and events); ``kind``
    is one of the five §17.1 kinds.  ``search`` returns honest hits —
    an empty list means *no results*, a raise means *the surface
    failed* (the workflow records the difference; it never guesses).
    """

    name: str
    kind: str

    @abstractmethod
    def search(self, query: str, *, max_results: int = 10) -> list[SearchHit]:
        """Run the query on this surface — honest hits or an honest raise."""


# ------------------------------------------------------------------ hits


@dataclass(frozen=True, slots=True)
class SearchHit:
    """One raw result from one surface (§17.1) — pre-interpretation.

    ``uri`` is the stable identity (URL, ``file://`` path, API link);
    ``snippet`` is the extract the hit carries (the §17.4 evidence
    dimension reads it); ``metadata`` carries provider facts (e.g. a
    GitHub hit's ``github_type``) that §17.3's ladder may consult.
    """

    title: str
    uri: str
    snippet: str = ""
    provider: str = ""
    kind: str = SourceKind.WEB
    fetched_at: str = ""
    metadata: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.title.strip():
            raise ResearchError("search hit needs a title")
        if not self.uri.strip():
            raise ResearchError("search hit needs a uri (evidence without a location is noise)")
        if self.kind not in SOURCE_KINDS:
            raise ResearchError(f"hit kind must be one of {SOURCE_KINDS}, got {self.kind!r}")
        if not self.fetched_at:
            object.__setattr__(self, "fetched_at", utc_now_iso())

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "uri": self.uri,
            "snippet": self.snippet,
            "provider": self.provider,
            "kind": self.kind,
            "fetched_at": self.fetched_at,
            "metadata": dict(self.metadata),
        }


# ------------------------------------------------------------ §17.3 class


class SourceClass:
    """The six §17.3 classes, verbatim vocabulary."""

    OFFICIAL = "official"
    DOCUMENTATION = "documentation"
    ACADEMIC = "academic"
    COMMUNITY = "community"
    PERSONAL = "personal"
    UNKNOWN = "unknown"


SOURCE_CLASSES: tuple[str, ...] = (
    SourceClass.OFFICIAL,
    SourceClass.DOCUMENTATION,
    SourceClass.ACADEMIC,
    SourceClass.COMMUNITY,
    SourceClass.PERSONAL,
    SourceClass.UNKNOWN,
)


# ------------------------------------------------------------- §17.4 math


#: §17.4 — the four dimensions, verbatim.
CONFIDENCE_DIMENSIONS: tuple[str, ...] = ("authority", "relevance", "freshness", "evidence")

#: The documented weighting (sums to 1.0) — authority leads, the rest
#: split the remainder; a source's §17.4 score is this weighted mean.
DEFAULT_WEIGHTS: dict[str, float] = {
    "authority": 0.35,
    "relevance": 0.25,
    "freshness": 0.20,
    "evidence": 0.20,
}

#: §17.4 authority prior per §17.3 class — documented, explainable, no ML.
AUTHORITY_BY_CLASS: dict[str, float] = {
    SourceClass.OFFICIAL: 0.95,
    SourceClass.ACADEMIC: 0.90,
    SourceClass.DOCUMENTATION: 0.85,
    SourceClass.COMMUNITY: 0.55,
    SourceClass.PERSONAL: 0.40,
    SourceClass.UNKNOWN: 0.30,
}

#: Freshness decay horizon (days) — a hit this old (or older) scores 0.
FRESHNESS_HORIZON_DAYS = 720

_STOPWORDS: frozenset[str] = frozenset(
    """a an and are as at be by for from has have how in is it its of on or
    that the this to was what when where which who will with عن في من على
    الى إلى ما هل كيف اين أين هذا هذه ذلك التي الذي""".split()
)

_WORD_RE = re.compile(r"[\w]+", re.UNICODE)
_NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def utc_now_iso() -> str:
    """UTC timestamp, ISO-8601 with microseconds (house format)."""
    return datetime.now(UTC).isoformat()


def extract_terms(text: str) -> tuple[str, ...]:
    """Significant lowercase terms — the workflow's shared yardstick.

    Words minus a tiny stopword list; digits keep their value (compare
    uses them for the conflict rule).  Deterministic order (first seen).
    """
    seen: list[str] = []
    for word in _WORD_RE.findall(text.lower()):
        if word in _STOPWORDS or not word.strip("_"):
            continue
        if word not in seen:
            seen.append(word)
    return tuple(seen)


def parse_iso_day(value: str) -> datetime | None:
    """Best-effort ISO date parse (``Z`` tolerated) — None when absent."""
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class SourceConfidence:
    """§17.4 — the four per-source dimensions and their weighted score.

    Every dimension is clamped to [0.0, 1.0]; ``score()`` is the
    documented weighted mean (:data:`DEFAULT_WEIGHTS`).
    """

    authority: float
    relevance: float
    freshness: float
    evidence: float
    weights: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_WEIGHTS))

    def __post_init__(self) -> None:
        for name in CONFIDENCE_DIMENSIONS:
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ResearchError(f"confidence.{name} must be within [0.0, 1.0], got {value}")
        if abs(sum(self.weights.values()) - 1.0) > 1e-6:
            raise ResearchError("confidence weights must sum to 1.0")

    def score(self) -> float:
        """The §17.4 weighted mean — round(3) for stable reports."""
        total = sum(getattr(self, name) * self.weights[name] for name in CONFIDENCE_DIMENSIONS)
        return round(min(max(total, 0.0), 1.0), 3)

    def breakdown(self) -> dict[str, float]:
        """The four dimensions verbatim — reports show their work."""
        return {name: round(getattr(self, name), 3) for name in CONFIDENCE_DIMENSIONS}

    def as_dict(self) -> dict[str, Any]:
        return {"score": self.score(), **self.breakdown()}


def confidence_from_hit(
    hit: SearchHit,
    *,
    classification: str,
    query_terms: tuple[str, ...],
) -> SourceConfidence:
    """§17.4 — compute the four dimensions for one hit.

    * ``authority``  — the §17.3 class prior (:data:`AUTHORITY_BY_CLASS`);
    * ``relevance``  — term overlap between the query and title+snippet;
    * ``freshness``  — linear decay to zero across
      :data:`FRESHNESS_HORIZON_DAYS` from ``metadata["published"]`` —
      a date the *surface itself reported*; a hit with no reported
      date is graded honestly neutral (0.5), never optimistically
      fresh (``fetched_at`` is provenance, not an age claim);
    * ``evidence``   — 0.0 no snippet · 0.5 snippet present · 1.0
      snippet actually contains a query term.
    """
    authority = AUTHORITY_BY_CLASS.get(classification, AUTHORITY_BY_CLASS[SourceClass.UNKNOWN])
    text = f"{hit.title} {hit.snippet}".lower()
    if query_terms:
        found = sum(1 for term in query_terms if term in text)
        relevance = found / len(query_terms)
    else:
        relevance = 0.0
    day = parse_iso_day(hit.metadata.get("published", ""))
    if day is None:
        freshness = 0.5
    else:
        if day.tzinfo is None:
            day = day.replace(tzinfo=UTC)
        age_days = max(0.0, (datetime.now(UTC) - day).total_seconds() / 86400.0)
        freshness = max(0.0, 1.0 - age_days / FRESHNESS_HORIZON_DAYS)
    snippet = hit.snippet.strip()
    if not snippet:
        evidence = 0.0
    elif any(term in snippet.lower() for term in query_terms):
        evidence = 1.0
    else:
        evidence = 0.5
    return SourceConfidence(
        authority=authority,
        relevance=round(min(relevance, 1.0), 3),
        freshness=round(freshness, 3),
        evidence=evidence,
    )
