"""The Research Engine (New Plan §17) — one facade over §17.1–§17.5.

``ResearchEngine`` composes the section the plan names and nothing
more:

* §17.1 — the five surfaces behind :class:`SearchProvider` adapters;
* §17.2 — the eight-stage workflow (:meth:`run` → a full report);
* §17.3/§17.4 — classification and the four-dimension confidence,
  applied inside the workflow's collect stage;
* §17.5 — :meth:`remember` / :meth:`recall` through the §12 Memory
  Engine, sources riding every record.

Every run publishes canonical §2.2 tool events only — query shapes
and counts travel, source *content* stays out of the bus.

محرك البحث — واجهة واحدة فوق الأسطح الخمسة والسير الثماني والتصنيف
والثقة والذاكرة؛ والحافات canonical فقط.

Stdlib only.
"""

from __future__ import annotations

from typing import Any

from nexus.events import EventName

from .memory import ResearchMemory
from .providers import (
    DocsSearchProvider,
    ForumSearchProvider,
    GitHubSearchProvider,
    LocalSearchProvider,
    WebSearchProvider,
)
from .workflow import ResearchReport, ResearchWorkflow

__all__ = [
    "DocsSearchProvider",
    "ForumSearchProvider",
    "GitHubSearchProvider",
    "LocalSearchProvider",
    "ResearchEngine",
    "ResearchReport",
    "WebSearchProvider",
]


class ResearchEngine:
    """The §17 facade — providers in, verified evidence out."""

    source_name = "nexus.research"

    def __init__(
        self,
        providers: list[Any] | tuple[Any, ...] = (),
        *,
        bus: Any = None,
        memory: Any = None,
    ) -> None:
        self._workflow = ResearchWorkflow(providers, bus=bus)
        self._bus = bus
        self._memory = ResearchMemory(memory) if memory is not None else None

    # ------------------------------------------------------------- §17.2

    def run(
        self,
        query: str,
        *,
        max_per_provider: int = 10,
        top_k: int = 8,
        min_corroboration: int = 2,
        min_authority: float = 0.5,
    ) -> ResearchReport:
        """The eight-stage pipeline — one query in, one report out."""
        report = self._workflow.run(
            query,
            max_per_provider=max_per_provider,
            top_k=top_k,
            min_corroboration=min_corroboration,
            min_authority=min_authority,
        )
        if self._bus is not None:
            self._bus.publish(
                EventName.TOOL_COMPLETED if report.ok else EventName.TOOL_FAILED,
                payload={
                    "tool": "research.engine",
                    "terms": len(report.terms),
                    "findings": len(report.findings),
                    "verified": len(report.verified),
                    "conflicts": len(report.conflicts),
                },
                source=self.source_name,
            )
        return report

    #: the §17 verb — same surface, plan vocabulary.
    research = run

    def add_provider(self, provider: Any) -> None:
        self._workflow.add_provider(provider)

    # ------------------------------------------------------------- §17.5

    def remember(
        self,
        report: ResearchReport,
        *,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        min_confidence: float = 0.0,
        verified_only: bool = False,
    ) -> list[dict[str, Any]]:
        """§17.5 — persist findings with their sources into Task/Project memory."""
        if self._memory is None:
            from .contracts import ResearchError

            raise ResearchError(
                "research memory needs a §12 MemoryEngine — pass memory=ResearchEngine(...)"
            )
        written = self._memory.remember(
            report,
            project=project,
            workspace=workspace,
            task=task,
            session=session,
            min_confidence=min_confidence,
            verified_only=verified_only,
        )
        if self._bus is not None and written:
            self._bus.publish(
                EventName.MEMORY_CREATED,
                payload={"tool": "research.remember", "records": len(written)},
                source=self.source_name,
            )
        return written

    def recall(
        self,
        prompt: str,
        *,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """§17.5 — search what research remembered (sources included)."""
        if self._memory is None:
            from .contracts import ResearchError

            raise ResearchError(
                "research memory needs a §12 MemoryEngine — pass memory=ResearchEngine(...)"
            )
        return self._memory.recall(
            prompt,
            project=project,
            workspace=workspace,
            task=task,
            session=session,
            limit=limit,
        )
