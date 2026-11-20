"""Speech memory (§19.4 *Task* stage) — voice tasks persist *with
their provenance* into §12 Task/Project memory.

The house law, fourth application (§13.3 lessons → §17.5 research →
§18.2 documents → §19.4 voice): what a task said is remembered inside
that task's memory, never as free-floating chat.  The bridge is the
§12 Memory Engine:

* one ``FACT`` record per voice task (intent · confidence · provider),
* the transcript rides as ``MemoryEvidence(method="voice",
  uri=voice://…, snippet=…)`` — provenance, always;
* one ``SUMMARY`` record per voice session;
* ``recall`` searches back through the same engine — hits keep their
  sources.

ذاكرة الصوت — كل مهمة صوتية تُحفظ بنصها ومصدرها داخل ذاكرة المهمة.
"""

from __future__ import annotations

from typing import Any

from nexus.memory.contracts import (
    MemoryEvidence,
    MemoryQuery,
    MemoryScope,
    MemoryType,
)

from .contracts import VoiceTask


class SpeechMemory:
    """§19.4 — the voice↔memory bridge over one §12 engine."""

    source_name = "nexus.speech"

    def __init__(self, memory: Any) -> None:
        if memory is None or not hasattr(memory, "remember") or not hasattr(memory, "search"):
            raise TypeError("SpeechMemory needs a §12 MemoryEngine (remember + search)")
        self._memory = memory

    # ------------------------------------------------------------ remember

    def remember_task(
        self,
        task: VoiceTask,
        *,
        transcript: str = "",
        provider: str = "",
        project: str | None = None,
        workspace: str | None = None,
        task_id: str | None = None,
        session: str | None = None,
    ) -> list[dict[str, Any]]:
        """Persist one voice task — with provenance, scoped, auditable.

        Scope: TASK when a task id is given, PROJECT when a project is
        given, KNOWLEDGE otherwise.  Returns the record ids written.
        """
        if task_id is None and project is None:
            scope = MemoryScope.KNOWLEDGE
        elif task_id:
            scope = MemoryScope.TASK
        else:
            scope = MemoryScope.PROJECT

        evidence_rows = ()
        if transcript.strip():
            evidence_rows = (
                MemoryEvidence(
                    # the §12 evidence vocabulary's honest slot for a
                    # spoken utterance — the voice:// uri keeps the
                    # audio provenance explicit
                    method="user_statement",
                    uri=task.audio_uri or f"voice://{task.intent}",
                    snippet=transcript[:400],
                    captured_at=task.created_at,
                ),
            )
        record = self._memory.remember(
            content=(
                f"voice task: {task.intent} — {task.utterance[:200]} "
                f"[task_kind={task.task_kind} provider={provider or task.provider} "
                f"confidence={task.confidence}]"
            ),
            type=MemoryType.FACT,
            scope=scope,
            source="speech",
            confidence=max(0.0, min(1.0, task.confidence)) if task.confidence >= 0 else 0.5,
            project=project,
            workspace=workspace,
            task=task_id,
            session=session,
            evidence=evidence_rows,
        )
        summary = self._memory.remember(
            content=(
                f"voice session: intent={task.intent} kind={task.task_kind} "
                f"argument={task.argument[:80]!r}"
            ),
            type=MemoryType.SUMMARY,
            scope=scope,
            source="speech",
            confidence=1.0,
            project=project,
            workspace=workspace,
            task=task_id,
            session=session,
        )
        return [
            {"record_id": record.id, "claim": task.intent, "score": task.confidence},
            {"record_id": summary.id, "claim": "voice-session-summary", "score": 1.0},
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
        """Search what the voice remembered — hits keep their provenance."""
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
