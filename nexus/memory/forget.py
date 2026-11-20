"""Memory forget operations (New Plan §12.9).

Three verbs::

    forget exact memory     — one record id
    forget category         — every active record of a type
    forget scope            — every active record of a scope
                              (containers may narrow it; GLOBAL refuses
                              without an explicit ``allow_global=True``
                              — a two-key guard for the whole-system wipe)

Forget is a *tombstone*, not a shredder: the record leaves every read
path (visibility, lexical, vector, context) but the §12.4 audit table
keeps its metadata — id, type, scope, source, reason, who, when —
forever. Content is dropped from the audit by design: «مع الحفاظ على
audit metadata حيث يلزم» — the metadata survives, the memory does not.

النسيان ثلاث درجات مع سجل تدقيق يُبقي الميتاداتا ويُسقط المحتوى.

Stdlib only.
"""

from __future__ import annotations

from .contracts import (
    MEMORY_SCOPES,
    ForgetResult,
    InvalidMemoryError,
    MemoryScope,
)
from .store import SQLiteMemoryStore

FORGET_ACTIONS: tuple[str, ...] = ("forget_exact", "forget_category", "forget_scope")


class ForgetOps:
    """§12.9 operations over the §12.4 store (engine delegates here)."""

    def __init__(self, store: SQLiteMemoryStore) -> None:
        self._store = store

    def forget_exact(
        self,
        record_id: str,
        *,
        reason: str = "operator request",
        requested_by: str = "operator",
    ) -> ForgetResult:
        """Forget one memory by id (no-op on unknown ids — audited)."""
        count = self._store.tombstone(
            [record_id],
            action="forget_exact",
            reason=reason,
            requested_by=requested_by,
        )
        return ForgetResult(
            forgotten=(record_id,) if count else (),
            action="forget_exact",
            reason=reason,
            audit_rows=count,
        )

    def forget_category(
        self,
        type: str,  # noqa: A002 — §12.9 «forget category» verb
        *,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        reason: str = "operator request",
        requested_by: str = "operator",
    ) -> ForgetResult:
        """Forget every *active* record of one type, optionally narrowed
        to a container (project/workspace/task)."""
        ids: list[str] = []
        for record in self._store.iter_records(active_only=True):
            if record.type != type:
                continue
            if project is not None and record.project != project:
                continue
            if workspace is not None and record.workspace != workspace:
                continue
            if task is not None and record.task != task:
                continue
            ids.append(record.id)
        self._store.tombstone(
            ids,
            action="forget_category",
            reason=f"{reason} (category={type})",
            requested_by=requested_by,
        )
        return ForgetResult(
            forgotten=tuple(ids),
            action="forget_category",
            reason=reason,
            audit_rows=len(ids),
        )

    def forget_scope(
        self,
        scope: str,
        *,
        project: str | None = None,
        workspace: str | None = None,
        task: str | None = None,
        session: str | None = None,
        agent: str | None = None,
        reason: str = "operator request",
        requested_by: str = "operator",
        allow_global: bool = False,
    ) -> ForgetResult:
        """Forget every *active* record of one scope.

        Container scopes demand their container (forgetting PROJECT
        needs ``project=``; forgetting GLOBAL needs the explicit
        ``allow_global=True`` guard — wiping the whole system by typo
        must be impossible).
        """
        if scope not in MEMORY_SCOPES:
            raise InvalidMemoryError(
                f"forget scope must be one of the twelve §12.2 scopes, "
                f"got {scope!r}"
            )
        if scope == MemoryScope.GLOBAL and not allow_global:
            raise InvalidMemoryError(
                "forgetting the GLOBAL scope wipes every cross-project memory — "
                "pass allow_global=True to confirm"
            )
        if scope == MemoryScope.PROJECT and not project:
            raise InvalidMemoryError("forgetting PROJECT requires project=")
        if scope == MemoryScope.WORKSPACE and not workspace:
            raise InvalidMemoryError("forgetting WORKSPACE requires workspace=")
        if scope == MemoryScope.TASK and not task:
            raise InvalidMemoryError("forgetting TASK requires task=")
        if scope == MemoryScope.SESSION and not session:
            raise InvalidMemoryError("forgetting SESSION requires session=")
        if scope == MemoryScope.AGENT and not agent:
            raise InvalidMemoryError("forgetting AGENT requires agent=")

        ids: list[str] = []
        for record in self._store.iter_records(active_only=True, scope=scope):
            if scope == MemoryScope.PROJECT and record.project != project:
                continue
            if scope == MemoryScope.WORKSPACE and record.workspace != workspace:
                continue
            if scope == MemoryScope.TASK and record.task != task:
                continue
            if scope == MemoryScope.SESSION and record.session != session:
                continue
            if scope == MemoryScope.AGENT and record.agent != agent:
                continue
            ids.append(record.id)
        self._store.tombstone(
            ids,
            action="forget_scope",
            reason=f"{reason} (scope={scope})",
            requested_by=requested_by,
        )
        return ForgetResult(
            forgotten=tuple(ids),
            action="forget_scope",
            reason=reason,
            audit_rows=len(ids),
        )
