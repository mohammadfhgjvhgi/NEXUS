"""Document memory (§18.2 *memory* stage) — documents persist *with
their provenance* into §12 Task/Project memory.

The house law, third application (§13.3 lessons → §17.5 research →
§18.2 documents): what a task used is remembered inside that task's
memory, never as free-floating chat.  The bridge is the §12 Memory
Engine:

* one ``FACT`` record per document (content = identity + counts,
  confidence = 1.0 — a document on disk is not a guess);
* its first text blocks ride as ``MemoryEvidence(method="document",
  uri=file://…, snippet=…)`` — provenance, always;
* one ``SUMMARY`` record per ingest session;
* ``recall`` searches back through the same engine — hits keep their
  sources.

ذاكرة المستندات — كل مستند يُحفظ بمصدره داخل ذاكرة المهمة/المشروع.

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

from .contracts import ParsedDocument


class DocumentMemory:
    """§18.2 — the documents↔memory bridge over one §12 engine."""

    source_name = "nexus.documents"

    def __init__(self, memory: Any) -> None:
        if memory is None or not hasattr(memory, "remember") or not hasattr(memory, "search"):
            raise TypeError("DocumentMemory needs a §12 MemoryEngine (remember + search)")
        self._memory = memory

    # ------------------------------------------------------------ remember

    def remember(
        self,
        parsed: ParsedDocument,
        *,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        max_evidence: int = 3,
    ) -> list[dict[str, Any]]:
        """Persist one parsed document — with provenance, scoped, auditable.

        Returns the record ids written (the document + the session
        summary).  Scope: TASK when a task is given, PROJECT when a
        project is given, KNOWLEDGE otherwise.
        """
        if project is None and task is None:
            scope = MemoryScope.KNOWLEDGE
        elif task:
            scope = MemoryScope.TASK
        else:
            scope = MemoryScope.PROJECT

        evidence_rows = tuple(
            MemoryEvidence(
                method="document",
                uri=parsed.uri,
                snippet=block.text[:400],
                captured_at=parsed.metadata.get("ingested_at", ""),
            )
            for block in parsed.blocks[: max(0, max_evidence)]
            if block.text.strip()
        )
        record = self._memory.remember(
            content=(
                f"document: {parsed.title or parsed.uri} [kind={parsed.kind} "
                f"blocks={len(parsed.blocks)} words={parsed.words()} parser={parsed.parser}]"
            ),
            type=MemoryType.FACT,
            scope=scope,
            source="documents",
            confidence=1.0,
            project=project,
            workspace=workspace,
            task=task,
            session=session,
            evidence=evidence_rows,
        )
        summary = self._memory.remember(
            content=(
                f"document ingest session: {parsed.title or parsed.uri!r} — kind={parsed.kind} "
                f"blocks={len(parsed.blocks)} words={parsed.words()}"
            ),
            type=MemoryType.SUMMARY,
            scope=scope,
            source="documents",
            confidence=1.0,
            project=project,
            workspace=workspace,
            task=task,
            session=session,
        )
        return [
            {"record_id": record.id, "claim": parsed.title or parsed.uri, "score": 1.0},
            {"record_id": summary.id, "claim": "document-ingest-summary", "score": 1.0},
        ]

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
        """Search what documents remembered — hits keep their provenance."""
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
