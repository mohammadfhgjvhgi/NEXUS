"""NEXUS Research Engine (New Plan §17) — *research becomes a runtime*.

The §17 sections, one module each::

    contracts   — §17.1 five surfaces · §17.3 six classes ·
                  §17.4 four confidence dimensions (all verbatim)
    providers   — §17.1: web · github · docs · forums · local files,
                  one adapter each, stdlib only
    classify    — §17.3: the six-class ladder, unknown is honest
    workflow    — §17.2: query → search → collect → deduplicate →
                  rank → compare → verify → evidence
    memory      — §17.5: findings persist with their sources into
                  §12 Task/Project memory
    engine      — the facade wiring all of the above

NEXUS owns the research semantics; every external search backend
enters behind :class:`SearchProvider` and is replaceable.
"""

from .classify import classify
from .contracts import (
    AUTHORITY_BY_CLASS,
    CONFIDENCE_DIMENSIONS,
    DEFAULT_WEIGHTS,
    FRESHNESS_HORIZON_DAYS,
    SOURCE_CLASSES,
    SOURCE_KINDS,
    ProviderError,
    ResearchError,
    SearchHit,
    SearchProvider,
    SourceClass,
    SourceConfidence,
    SourceKind,
    confidence_from_hit,
    extract_terms,
)
from .engine import ResearchEngine
from .memory import ResearchMemory
from .providers import (
    DocsSearchProvider,
    ForumSearchProvider,
    GitHubSearchProvider,
    LocalSearchProvider,
    WebSearchProvider,
)
from .workflow import (
    WORKFLOW_STAGES,
    EvidenceItem,
    Finding,
    ResearchReport,
    ResearchWorkflow,
    ScoredHit,
    StageState,
    StageTrace,
)

__all__ = [
    "AUTHORITY_BY_CLASS",
    "CONFIDENCE_DIMENSIONS",
    "DEFAULT_WEIGHTS",
    "DocsSearchProvider",
    "EvidenceItem",
    "FRESHNESS_HORIZON_DAYS",
    "Finding",
    "ForumSearchProvider",
    "GitHubSearchProvider",
    "LocalSearchProvider",
    "ProviderError",
    "ResearchEngine",
    "ResearchError",
    "ResearchMemory",
    "ResearchReport",
    "ResearchWorkflow",
    "SCORED_SHAPE",
    "SOURCE_CLASSES",
    "SOURCE_KINDS",
    "ScoredHit",
    "SearchHit",
    "SearchProvider",
    "SourceClass",
    "SourceConfidence",
    "SourceKind",
    "StageState",
    "StageTrace",
    "WebSearchProvider",
    "WORKFLOW_STAGES",
    "classify",
    "confidence_from_hit",
    "extract_terms",
]

#: contract cardinalities — asserted by the §17 exit gate.
SCORED_SHAPE = {
    "source_kinds": len(SOURCE_KINDS),
    "source_classes": len(SOURCE_CLASSES),
    "workflow_stages": len(WORKFLOW_STAGES),
    "confidence_dimensions": len(CONFIDENCE_DIMENSIONS),
}
