"""The §17.2 research workflow — eight stages, verbatim, in order::

    query → search → collect → deduplicate → rank → compare → verify → evidence

One :meth:`ResearchWorkflow.run` walks a query through the whole
pipeline and returns a :class:`ResearchReport` whose every stage keeps
a verdict (:class:`StageState`) — honest, replayable, event-bearing.

What each stage owns:

* ``query``       — normalize + extract the significant terms;
* ``search``      — fan out to the §17.1 providers; a failing surface
  is recorded, it never sinks the run (all failing does);
* ``collect``     — classify every hit (§17.3) and score it (§17.4);
* ``deduplicate`` — collapse identical URIs and identical content
  fingerprints, keeping the better-scoring carrier;
* ``rank``        — order by §17.4 score, keep the top ``k``;
* ``compare``     — cluster agreeing hits into findings; disagreeing
  numbers on overlapping claims surface as *conflicts*;
* ``verify``      — a finding is verified only by corroboration: ≥
  ``min_corroboration`` distinct sources with authority ≥
  ``min_authority``, and no unresolved conflict;
* ``evidence``    — attach the per-source evidence rows and close the
  report.

سير البحث الثماني — كل مرحلة حكم صريح، والفشل يُعلن لا يُطوّى.

Stdlib only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from nexus.events import EventName

from .classify import classify
from .contracts import (
    ResearchError,
    SearchHit,
    SearchProvider,
    SourceConfidence,
    confidence_from_hit,
    extract_terms,
    utc_now_iso,
)

#: §17.2 — the eight stages, verbatim order.
WORKFLOW_STAGES: tuple[str, ...] = (
    "query",
    "search",
    "collect",
    "deduplicate",
    "rank",
    "compare",
    "verify",
    "evidence",
)

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

#: two hits join one finding when their significant-term Jaccard ≥ this.
_CLUSTER_JACCARD = 0.34


class StageState(Enum):
    """A stage verdict — pending / ok / failed / skipped."""

    PENDING = "pending"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class StageTrace:
    """One stage's outcome — name, state, an honest detail line."""

    name: str
    state: StageState = StageState.PENDING
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"name": self.name, "state": self.state.value, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    """One backing artifact (§17.2 *evidence* rung / §17.4 dimensions)."""

    uri: str
    title: str
    snippet: str
    source_class: str
    provider: str
    kind: str
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "uri": self.uri,
            "title": self.title,
            "snippet": self.snippet,
            "source_class": self.source_class,
            "provider": self.provider,
            "kind": self.kind,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class ScoredHit:
    """A hit after §17.3 + §17.4 — the dedup/rank currency."""

    hit: SearchHit
    source_class: str
    confidence: SourceConfidence

    @property
    def score(self) -> float:
        return self.confidence.score()

    def as_dict(self) -> dict[str, Any]:
        return {
            "hit": self.hit.as_dict(),
            "source_class": self.source_class,
            "confidence": self.confidence.as_dict(),
        }


@dataclass(frozen=True, slots=True)
class Finding:
    """One research finding — a claim with its (agreeing) sources.

    ``contested`` — the §17.2 *compare* verdict: sources on this claim
    report conflicting numbers.  A contested finding never verifies.
    """

    claim: str
    hits: tuple[ScoredHit, ...]
    terms: tuple[str, ...]
    numbers: tuple[str, ...] = ()
    contested: bool = False

    @property
    def distinct_sources(self) -> int:
        return len({sh.hit.uri for sh in self.hits})

    @property
    def mean_authority(self) -> float:
        if not self.hits:
            return 0.0
        return sum(sh.confidence.authority for sh in self.hits) / len(self.hits)

    @property
    def best(self) -> ScoredHit:
        return max(self.hits, key=lambda sh: sh.score)

    def as_dict(self, *, verified: bool | None = None, evidence: tuple[EvidenceItem, ...] = (),
                ) -> dict[str, Any]:
        return {
            "claim": self.claim,
            "terms": list(self.terms),
            "distinct_sources": self.distinct_sources,
            "mean_authority": round(self.mean_authority, 3),
            "contested": self.contested,
            "verified": verified,
            "evidence": [e.as_dict() for e in evidence],
            "hits": [sh.as_dict() for sh in self.hits],
        }


def _finding_key(finding: Finding) -> str:
    from hashlib import blake2b

    return blake2b(finding.claim.encode("utf-8"), digest_size=8).hexdigest()


@dataclass(frozen=True, slots=True)
class ResearchReport:
    """The §17.2 answer — stages, findings, conflicts, evidence."""

    query: str
    terms: tuple[str, ...]
    stages: tuple[StageTrace, ...]
    findings: tuple[Finding, ...] = ()
    verified: tuple[Finding, ...] = ()
    conflicts: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    closed_at: str = ""
    evidence_index: dict[str, tuple[EvidenceItem, ...]] = field(default_factory=dict)

    def stage(self, name: str) -> StageTrace:
        for trace in self.stages:
            if trace.name == name:
                return trace
        raise ResearchError(f"no stage named {name!r} in this report")

    @property
    def reached(self) -> str:
        for trace in self.stages:
            if trace.state in (StageState.FAILED, StageState.SKIPPED):
                return trace.name
        return self.stages[-1].name if self.stages else ""

    @property
    def ok(self) -> bool:
        return (
            all(trace.state is not StageState.FAILED for trace in self.stages)
            and bool(self.findings)
            and self.stages[-1].name == "evidence"
        )

    def evidence_of(self, finding: Finding) -> tuple[EvidenceItem, ...]:
        """The evidence rows of one finding."""
        return self.evidence_index.get(_finding_key(finding), ())

    def to_dict(self) -> dict[str, Any]:
        verified_ids = {id(f) for f in self.verified}
        return {
            "query": self.query,
            "terms": list(self.terms),
            "reached": self.reached,
            "ok": self.ok,
            "stages": [s.as_dict() for s in self.stages],
            "findings": [
                f.as_dict(verified=id(f) in verified_ids, evidence=self.evidence_of(f))
                for f in self.findings
            ],
            "conflicts": list(self.conflicts),
            "errors": list(self.errors),
            "closed_at": self.closed_at,
        }


class ResearchWorkflow:
    """The §17.2 pipeline over any §17.1 providers."""

    source_name = "nexus.research"

    def __init__(
        self,
        providers: list[SearchProvider] | tuple[SearchProvider, ...] = (),
        *,
        bus: Any = None,
    ) -> None:
        self.providers: list[SearchProvider] = list(providers)
        self._bus = bus
        for provider in self.providers:
            if provider.kind not in ("web", "github", "docs", "forums", "local"):
                raise ResearchError(
                    f"provider {provider.name!r}: unknown §17.1 kind {provider.kind!r}"
                )

    def add_provider(self, provider: SearchProvider) -> None:
        self.providers.append(provider)

    # ------------------------------------------------------------ plumbing

    def _emit(self, ok: bool, payload: dict[str, Any]) -> None:
        if self._bus is None:
            return
        self._bus.publish(
            EventName.TOOL_COMPLETED if ok else EventName.TOOL_FAILED,
            payload=payload,
            source=self.source_name,
        )

    # ---------------------------------------------------------------- run

    def run(
        self,
        query: str,
        *,
        max_per_provider: int = 10,
        top_k: int = 8,
        min_corroboration: int = 2,
        min_authority: float = 0.5,
    ) -> ResearchReport:
        """Walk the eight stages — every stage keeps its verdict."""
        query = (query or "").strip()
        traces: dict[str, StageTrace] = {
            name: StageTrace(name=name) for name in WORKFLOW_STAGES
        }
        errors: list[str] = []

        def set_stage(name: str, state: StageState, detail: str = "") -> None:
            traces[name] = StageTrace(name=name, state=state, detail=detail)

        # 1 — query ------------------------------------------------------
        if not query:
            set_stage("query", StageState.FAILED, "empty query")
            report = ResearchReport(
                query=query, terms=(), stages=tuple(traces[n] for n in WORKFLOW_STAGES),
                errors=("empty query",), closed_at=utc_now_iso(),
            )
            self._emit(False, {"tool": "research.run", "error": "empty query"})
            return report
        terms = extract_terms(query)
        set_stage("query", StageState.OK, f"{len(terms)} terms")

        # 2 — search -----------------------------------------------------
        raw_hits: list[SearchHit] = []
        surface_notes: list[str] = []
        if not self.providers:
            set_stage("search", StageState.FAILED, "no providers registered")
        else:
            for provider in self.providers:
                try:
                    found = provider.search(query, max_results=max_per_provider)
                except Exception as exc:  # noqa: BLE001 — a surface may fail many ways
                    errors.append(f"{provider.name}: {type(exc).__name__}: {exc}")
                    surface_notes.append(f"{provider.name}=error")
                    continue
                raw_hits.extend(found)
                surface_notes.append(f"{provider.name}={len(found)}")
            if all(note.endswith("=error") for note in surface_notes):
                set_stage("search", StageState.FAILED, "every surface failed: " + ", ".join(errors))
            else:
                set_stage("search", StageState.OK, " ".join(surface_notes))

        if traces["search"].state is StageState.FAILED:
            report = ResearchReport(
                query=query, terms=terms, stages=tuple(traces[n] for n in WORKFLOW_STAGES),
                errors=tuple(errors), closed_at=utc_now_iso(),
            )
            self._emit(False, {"tool": "research.run", "terms": len(terms), "errors": len(errors)})
            return report

        # 3 — collect ----------------------------------------------------
        collected: list[ScoredHit] = []
        for hit in raw_hits:
            source_class = classify(hit)
            collected.append(
                ScoredHit(
                    hit=hit,
                    source_class=source_class,
                    confidence=confidence_from_hit(
                        hit, classification=source_class, query_terms=terms
                    ),
                )
            )
        set_stage("collect", StageState.OK, f"{len(collected)} hits classified+scored")

        # 4 — deduplicate ------------------------------------------------
        deduped = self._deduplicate(collected)
        set_stage("deduplicate", StageState.OK, f"{len(collected)} → {len(deduped)} unique")

        # 5 — rank -------------------------------------------------------
        ranked = sorted(deduped, key=lambda sh: sh.score, reverse=True)[: max(1, top_k)]
        set_stage("rank", StageState.OK, f"top {len(ranked)} by §17.4 score")

        # 6 — compare ----------------------------------------------------
        findings, conflicts = self._compare(ranked)
        set_stage(
            "compare",
            StageState.OK,
            f"{len(findings)} findings · {len(conflicts)} contested",
        )

        # 7 — verify -----------------------------------------------------
        verified = tuple(
            f for f in findings
            if f.distinct_sources >= min_corroboration
            and f.mean_authority >= min_authority
            and not f.contested
        )
        set_stage(
            "verify",
            StageState.OK,
            f"{len(verified)}/{len(findings)} verified (≥{min_corroboration} sources)",
        )

        # 8 — evidence ---------------------------------------------------
        evidence_index: dict[str, tuple[EvidenceItem, ...]] = {}
        for finding in findings:
            items = tuple(
                EvidenceItem(
                    uri=sh.hit.uri,
                    title=sh.hit.title,
                    snippet=sh.hit.snippet,
                    source_class=sh.source_class,
                    provider=sh.hit.provider,
                    kind=sh.hit.kind,
                    confidence=sh.score,
                )
                for sh in sorted(finding.hits, key=lambda s: s.score, reverse=True)
            )
            evidence_index[_finding_key(finding)] = items
        set_stage("evidence", StageState.OK, f"{sum(len(v) for v in evidence_index.values())} rows")

        self._emit(
            True,
            {
                "tool": "research.run",
                "terms": len(terms),
                "findings": len(findings),
                "verified": len(verified),
                "contested": len(conflicts),
            },
        )
        return ResearchReport(
            query=query,
            terms=terms,
            stages=tuple(traces[n] for n in WORKFLOW_STAGES),
            findings=tuple(findings),
            verified=verified,
            conflicts=tuple(conflicts),
            errors=tuple(errors),
            closed_at=utc_now_iso(),
            evidence_index=evidence_index,
        )

    # ---------------------------------------------------------- stage bodies

    @staticmethod
    def _fingerprint(hit: SearchHit) -> str:
        from hashlib import blake2b

        payload = " ".join(extract_terms(f"{hit.title} {hit.snippet}"))
        return blake2b(payload.encode("utf-8"), digest_size=8).hexdigest()

    def _deduplicate(self, hits: list[ScoredHit]) -> list[ScoredHit]:
        """URI-exact first, then content fingerprint — best carrier wins."""
        by_uri: dict[str, ScoredHit] = {}
        for scored in hits:
            key = scored.hit.uri.strip()
            current = by_uri.get(key)
            if current is None or scored.score > current.score:
                by_uri[key] = scored
        by_content: dict[str, ScoredHit] = {}
        for scored in by_uri.values():
            fp = self._fingerprint(scored.hit)
            current = by_content.get(fp)
            if current is None or scored.score > current.score:
                by_content[fp] = scored
        return list(by_content.values())

    @staticmethod
    def _jaccard(a: tuple[str, ...], b: tuple[str, ...]) -> float:
        sa, sb = set(a), set(b)
        if not sa or not sb:
            return 0.0
        return len(sa & sb) / len(sa | sb)

    def _compare(
        self,
        ranked: list[ScoredHit],
    ) -> tuple[list[Finding], list[str]]:
        """Cluster agreeing hits; a cluster whose sources report
        conflicting numbers becomes a *contested* finding."""
        clusters: list[list[ScoredHit]] = []
        terms_per_cluster: list[tuple[str, ...]] = []
        for scored in ranked:
            hit_terms = extract_terms(f"{scored.hit.title} {scored.hit.snippet}")
            if not hit_terms:
                continue
            placed = False
            for idx, cluster_terms in enumerate(terms_per_cluster):
                if self._jaccard(hit_terms, cluster_terms) >= _CLUSTER_JACCARD:
                    clusters[idx].append(scored)
                    merged = tuple(dict.fromkeys(terms_per_cluster[idx] + hit_terms))
                    terms_per_cluster[idx] = merged
                    placed = True
                    break
            if not placed:
                clusters.append([scored])
                terms_per_cluster.append(hit_terms)

        findings: list[Finding] = []
        conflicts: list[str] = []
        for cluster, terms in zip(clusters, terms_per_cluster, strict=True):
            best = max(cluster, key=lambda sh: sh.score)
            claim = (
                best.hit.title
                if len(cluster) > 1
                else f"{best.hit.title} — {best.hit.snippet[:120]}"
            )
            number_sets = [
                frozenset(_NUMBER_RE.findall(f"{scored.hit.title} {scored.hit.snippet}"))
                for scored in cluster
            ]
            numbers = tuple(sorted(set().union(*number_sets))) if number_sets else ()
            contested_pair = self._contested_pair(number_sets)
            if contested_pair is not None:
                left, right = contested_pair
                conflicts.append(
                    f"conflicting numbers within one claim: {claim[:60]!r} "
                    f"{sorted(left)} vs {sorted(right)}"
                )
            findings.append(
                Finding(
                    claim=claim,
                    hits=tuple(cluster),
                    terms=terms,
                    numbers=numbers,
                    contested=contested_pair is not None,
                )
            )
        return findings, conflicts

    @staticmethod
    def _contested_pair(
        number_sets: list[frozenset[str]],
    ) -> tuple[frozenset[str], frozenset[str]] | None:
        """Two sources disagree when their reported numbers overlap in
        neither direction — same claim, incompatible quantities."""
        for i, first in enumerate(number_sets):
            if not first:
                continue
            for second in number_sets[i + 1:]:
                if not second:
                    continue
                if first == second or first <= second or second <= first:
                    continue
                return first, second
        return None
