"""The §18.2 document pipeline — verbatim: Document → Parse → Structure
→ Extract → Index → Memory.

Five stages after the document itself, one honest verdict per stage
(:class:`StageTrace`), the same discipline the research workflow
brought in §17.2:

* **parse** — the first backend that accepts the bytes wins; a
  missing optional engine is *unavailable*, not *failed*;
* **structure** — the pages/slides/headings tree, counted;
* **extract** — the text blocks, counted (content never rides events);
* **index** — into the §18.2 index (honest ``skipped`` when no index
  is bound);
* **memory** — into §12 Task/Project memory (honest ``skipped``
  likewise).

مرحلة السير الخمسي — حكم صادق لكل مرحلة، والمحتوى لا يركب الحافات.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

from nexus.events import EventName

from .contracts import (
    PIPELINE_STAGES,
    DocumentError,
    DocumentSource,
    ParseBackend,
    ParsedDocument,
    ParseError,
    StageState,
    StageTrace,
    UnsupportedDocumentError,
    utc_now_iso,
)

#: stage name → its final (state, detail) — the bookkeeping currency.
_Trace = dict[str, tuple[StageState, str]]


@dataclass(frozen=True, slots=True)
class DocumentReport:
    """The §18.2 answer — one document, five stage verdicts."""

    source: DocumentSource
    stages: tuple[StageTrace, ...]
    document: ParsedDocument | None = None
    index_id: int | None = None
    memory_records: int = 0
    errors: tuple[str, ...] = ()
    closed_at: str = ""

    def stage(self, name: str) -> StageTrace:
        for trace in self.stages:
            if trace.name == name:
                return trace
        raise DocumentError(f"no stage named {name!r} in this report")

    @property
    def reached(self) -> str:
        for trace in self.stages:
            if trace.state in (StageState.FAILED, StageState.SKIPPED):
                return trace.name
        return self.stages[-1].name if self.stages else ""

    @property
    def ok(self) -> bool:
        """True when the document was parsed and no stage failed.

        The mandatory stages (parse · structure · extract) must all be
        OK; ``index``/``memory`` are honest when unbound (``skipped``)
        — a skipped stage was never promised, so it cannot fail the
        run, but a failed one always does.
        """
        mandatory_ok = all(
            trace.state is StageState.OK
            for trace in self.stages
            if trace.name in ("parse", "structure", "extract")
        )
        return (
            mandatory_ok
            and all(trace.state is not StageState.FAILED for trace in self.stages)
            and self.document is not None
            and bool(self.stages)
            and self.stages[-1].name == "memory"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.as_dict(),
            "stages": [s.as_dict() for s in self.stages],
            "document": self.document.as_dict() if self.document else None,
            "index_id": self.index_id,
            "memory_records": self.memory_records,
            "errors": list(self.errors),
            "ok": self.ok,
        }


def _traces(traces: _Trace) -> tuple[StageTrace, ...]:
    """The final verdict tuple — PIPELINE_STAGES order, frozen shapes."""
    return tuple(
        StageTrace(name=name, state=traces[name][0], detail=traces[name][1])
        for name in PIPELINE_STAGES
    )


class DocumentPipeline:
    """The five-stage pipeline — backends in, an indexed memory record out."""

    def __init__(
        self,
        backends: list[ParseBackend],
        *,
        index: Any | None = None,
        memory: Any | None = None,
        bus: Any | None = None,
    ) -> None:
        self._backends = list(backends)
        self._index = index
        self._memory = memory
        self._bus = bus

    # ---------------------------------------------------------------- run

    def run(self, source: DocumentSource) -> DocumentReport:
        traces: _Trace = {name: (StageState.PENDING, "") for name in PIPELINE_STAGES}
        errors: list[str] = []
        parsed: ParsedDocument | None = None
        index_id: int | None = None
        memory_records = 0

        # ---- parse: the first backend that accepts the bytes wins
        if not self._backends:
            traces["parse"] = (StageState.FAILED, "no backends registered")
            return self._close(source, traces, None, None, 0, ("no backends",))
        for backend in self._backends:
            try:
                parsed = backend.parse(source)
            except UnsupportedDocumentError:
                continue
            except (ParseError, DocumentError) as exc:
                errors.append(f"{backend.name}: {exc}")
                continue
            except Exception as exc:  # noqa: BLE001 — a backend crash is a parse failure
                errors.append(f"{backend.name}: {type(exc).__name__}: {exc}")
                continue
            traces["parse"] = (
                StageState.OK,
                f"parser={backend.name} blocks={len(parsed.blocks)}",
            )
            break
        if parsed is None:
            detail = "; ".join(errors)[:160] or f"no backend serves kind {source.kind!r}"
            traces["parse"] = (StageState.FAILED, detail)
            return self._close(source, traces, None, None, 0, tuple(errors))

        # ---- structure
        traces["structure"] = (
            StageState.OK,
            f"nodes={len(parsed.structure)}",
        )

        # ---- extract
        traces["extract"] = (
            StageState.OK,
            f"blocks={len(parsed.blocks)} words={parsed.words()}",
        )

        # ---- index (honest skip when unbound)
        if self._index is None:
            traces["index"] = (StageState.SKIPPED, "no index bound")
        else:
            try:
                index_id = self._index.add(_stamped(parsed))
                traces["index"] = (StageState.OK, f"indexed id={index_id}")
            except Exception as exc:  # noqa: BLE001 — index failure is honest
                traces["index"] = (StageState.FAILED, f"{type(exc).__name__}: {exc}"[:160])
                errors.append(f"index: {exc}")

        # ---- memory (honest skip when unbound or index failed)
        if traces["index"][0] is StageState.FAILED:
            traces["memory"] = (StageState.SKIPPED, "index failed — nothing to remember")
        elif self._memory is None:
            traces["memory"] = (StageState.SKIPPED, "no memory bound")
        else:
            try:
                written = self._memory.remember(_stamped(parsed))
                memory_records = len(written)
                traces["memory"] = (StageState.OK, f"records={memory_records}")
            except Exception as exc:  # noqa: BLE001 — memory failure is honest
                traces["memory"] = (StageState.FAILED, f"{type(exc).__name__}: {exc}"[:160])
                errors.append(f"memory: {exc}")

        return self._close(source, traces, parsed, index_id, memory_records, tuple(errors))

    # ------------------------------------------------------------ plumbing

    def _close(
        self,
        source: DocumentSource,
        traces: _Trace,
        parsed: ParsedDocument | None,
        index_id: int | None,
        memory_records: int,
        errors: tuple[str, ...],
    ) -> DocumentReport:
        report = DocumentReport(
            source=source,
            stages=_traces(traces),
            document=parsed,
            index_id=index_id,
            memory_records=memory_records,
            errors=errors,
            closed_at=utc_now_iso(),
        )
        if self._bus is not None:
            payload = {
                "tool": "documents.pipeline",
                "kind": source.kind,
                "stages": len(report.stages),
                "blocks": len(parsed.blocks) if parsed else 0,
                "words": parsed.words() if parsed else 0,
                "memory_records": memory_records,
            }
            self._bus.publish(
                EventName.TOOL_COMPLETED if report.ok else EventName.TOOL_FAILED,
                payload=payload,
                source="nexus.documents",
            )
        return report


def _stamped(parsed: ParsedDocument) -> ParsedDocument:
    """Provenance for the index — the ingest time rides metadata only."""
    return replace(parsed, metadata={**parsed.metadata, "ingested_at": utc_now_iso()})
