"""Research memory (New Plan §17.5) — findings persist *with their sources*.

The §17.5 law: information a project used is remembered inside that
project's/task's memory — never as free-floating chat.  The bridge is
the §12 Memory Engine, NEXUS-owned semantics (Plan §61):

* one ``FACT`` record per finding (``content`` = the claim,
  ``confidence`` = the §17.4 score), scope TASK when a task is given,
  PROJECT when a project is given, KNOWLEDGE otherwise;
* every backing hit becomes a ``MemoryEvidence(method="research",
  uri=…, snippet=…)`` — the source rides the record, always;
* one ``SUMMARY`` record per research session (query · counts), so a
  later task can see *what was researched*, not just what was found;
* ``recall`` searches back through the same engine — context
  assembly stays §12.7's job, research only scopes it.

ذاكرة البحث — ما استُخدم في مشروع يحفظ داخل ذلك المشروع، ومصدره معه
دائمًا: خريطة §17.5 فوق محرك §12 لا بديلًا عنه.

Stdlib only.
"""

from __future__ import annotations

from typing import Any

from nexus.memory.contracts import (
    MemoryEvidence,
    MemoryQuery,
    MemoryScope,
    MemoryType,
)

from .workflow import ResearchReport


class ResearchMemory:
    """§17.5 — the research↔memory bridge over one §12 engine."""

    source_name = "nexus.research"

    def __init__(self, memory: Any) -> None:
        if memory is None or not hasattr(memory, "remember") or not hasattr(memory, "search"):
            raise TypeError("ResearchMemory needs a §12 MemoryEngine (remember + search)")
        self._memory = memory

    # ------------------------------------------------------------ remember

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
        max_evidence: int = 4,
    ) -> list[dict[str, Any]]:
        """Persist a report's findings — with sources, scoped, auditable.

        Returns the record ids written (findings + the session summary).
        Findings below ``min_confidence`` (or unverified while
        ``verified_only``) are skipped — silence is a filter, not a lie.
        """
        if project is None and task is None:
            scope = MemoryScope.KNOWLEDGE
        elif task:
            scope = MemoryScope.TASK
        else:
            scope = MemoryScope.PROJECT

        written: list[dict[str, Any]] = []
        for finding in report.findings:
            if verified_only and finding not in report.verified:
                continue
            score = finding.best.score
            if score < min_confidence:
                continue
            evidence_rows = tuple(
                MemoryEvidence(
                    method="research",
                    uri=item.uri,
                    snippet=item.snippet[:400],
                    captured_at=report.closed_at,
                )
                for item in report.evidence_of(finding)[: max(0, max_evidence)]
                if item.uri or item.snippet
            )
            record = self._memory.remember(
                content=f"{finding.claim} [research:{report.query}]",
                type=MemoryType.FACT,
                scope=scope,
                source="research",
                confidence=score,
                project=project,
                workspace=workspace,
                task=task,
                session=session,
                evidence=evidence_rows,
            )
            written.append({"record_id": record.id, "claim": finding.claim, "score": score})

        summary = self._memory.remember(
            content=(
                f"research session: {report.query!r} — {len(report.findings)} findings · "
                f"{len(report.verified)} verified · {len(report.conflicts)} conflicts · "
                f"{len(report.errors)} errors"
            ),
            type=MemoryType.SUMMARY,
            scope=scope,
            source="research",
            confidence=1.0,
            project=project,
            workspace=workspace,
            task=task,
            session=session,
        )
        written.append({"record_id": summary.id, "claim": "research-session-summary", "score": 1.0})
        return written

    # -------------------------------------------------------------- recall

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
        """Search what research remembered — hits keep their sources."""
        hits = self._memory.search(
            MemoryQuery(
                text=prompt,
                project=project,
                workspace=workspace,
                task=task,
                session=session,
                limit=limit,
            )
        )
        out: list[dict[str, Any]] = []
        for hit in hits:
            record = hit.record
            out.append(
                {
                    "id": record.id,
                    "content": record.content,
                    "type": record.type,
                    "scope": record.scope,
                    "confidence": record.confidence,
                    "task": record.task,
                    "project": record.project,
                    "sources": [
                        {"method": e.method, "uri": e.uri, "snippet": e.snippet}
                        for e in record.evidence
                    ],
                }
            )
        return out
