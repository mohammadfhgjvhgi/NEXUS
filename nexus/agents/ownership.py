"""Agent Ownership (Final Build Plan §6.6).

The plan fixes the record::

    resource
    owner

and the goal:

> لمنع Agentين من تعديل نفس الملف أو المورد بلا تنسيق
> («prevent two agents from modifying the same file or resource
> without coordination»).

:class:`OwnershipManager` is the NEXUS-owned coordination registry:

* ``acquire`` — an agent takes a resource; re-acquiring by the *same*
  owner is idempotent; acquiring a resource held by *another* owner
  raises :class:`ResourceOwnedError` carrying the current owner and
  task — the coordination signal, never a silent overwrite;
* ``release`` / ``release_owner`` — the owner (or its teardown)
  returns resources; only the owner may release;
* ``check`` — may this owner modify the resource? (free, or theirs);
* ``snapshot`` — the audit view (checkpoint / harness).

Scope of enforcement (documented decision): Phase 5's runtime is a
single process driven synchronously (Phase 1 concurrency note — only
the Event Bus is thread-safe), so in-process ownership is the honest,
complete enforcement for this phase. Cross-process file locking joins
later with the Tool system phases, on the same §6.6 contract.

Conflicts surface as :class:`ResourceOwnedError` observations — the
§6.2 loop converts them into a ``coordination`` message and a re-
decide (bounded by the loop's turn budget): coordination instead of
collision.

ملكية الموارد — سجل resource/owner يمنع وكيلين من تعديل المورد نفسه
بلا تنسيق؛ التعارض يتحول إلى رسالة تنسيق لا إلى كتابة فوق بعض.

Stdlib only.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger("nexus.agents")

#: The §6.6 fields, verbatim (harness-provable).
OWNERSHIP_FIELDS: tuple[str, ...] = ("resource", "owner")


class OwnershipError(Exception):
    """Ownership misuse (release by a non-owner, unknown resource…)."""


class ResourceOwnedError(OwnershipError):
    """A resource is held by another owner — the §6.6 coordination
    signal. Carries the current holder so the requester can
    coordinate instead of overwriting."""

    def __init__(
        self,
        resource: str,
        owner: str,
        requester: str,
        task_id: str | None = None,
    ) -> None:
        super().__init__(
            f"resource {resource!r} is owned by {owner!r}"
            f" (requested by {requester!r})"
            + (f" [task {task_id}]" if task_id else "")
        )
        self.resource = resource
        self.owner = owner
        self.requester = requester
        self.task_id = task_id


def _utc_now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()


@dataclass(frozen=True, slots=True)
class OwnershipEntry:
    """One held resource — ``resource`` + ``owner`` verbatim, plus
    bookkeeping (acquisition time, owning task)."""

    resource: str
    owner: str
    task_id: str | None = None
    acquired_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "resource": self.resource,
            "owner": self.owner,
            "task_id": self.task_id,
            "acquired_at": self.acquired_at,
        }


class OwnershipManager:
    """The §6.6 coordination registry (in-process, Phase 5 scope)."""

    def __init__(self) -> None:
        self._entries: dict[str, OwnershipEntry] = {}

    # ------------------------------------------------------------- verbs

    def acquire(
        self,
        resource: str,
        *,
        owner: str,
        task_id: str | None = None,
    ) -> OwnershipEntry:
        """Take a resource; idempotent for the same owner, a
        :class:`ResourceOwnedError` for anyone else."""
        if not resource.strip():
            raise OwnershipError("resource must be a non-empty string")
        if not owner.strip():
            raise OwnershipError("owner must be a non-empty string")
        existing = self._entries.get(resource)
        if existing is not None:
            if existing.owner == owner:
                return existing
            raise ResourceOwnedError(
                resource, existing.owner, owner, task_id or existing.task_id
            )
        entry = OwnershipEntry(
            resource=resource,
            owner=owner,
            task_id=task_id,
            acquired_at=_utc_now_iso(),
        )
        self._entries[resource] = entry
        logger.debug("ownership: %s -> %s", resource, owner)
        return entry

    def release(self, resource: str, *, owner: str) -> OwnershipEntry:
        """Return a resource; only the owner may release it."""
        entry = self._entries.get(resource)
        if entry is None:
            raise OwnershipError(f"resource {resource!r} is not held")
        if entry.owner != owner:
            raise OwnershipError(
                f"resource {resource!r} may only be released by its owner"
                f" {entry.owner!r}, not {owner!r}"
            )
        del self._entries[resource]
        return entry

    def release_owner(self, owner: str) -> tuple[OwnershipEntry, ...]:
        """Teardown — release every resource an owner holds."""
        released = [
            entry for entry in self._entries.values() if entry.owner == owner
        ]
        for entry in released:
            del self._entries[entry.resource]
        if released:
            logger.debug("ownership: %d resource(s) released for %s", len(released), owner)
        return tuple(released)

    # ------------------------------------------------------------- reads

    def owner_of(self, resource: str) -> str | None:
        """The current owner of a resource (``None`` = free)."""
        entry = self._entries.get(resource)
        return entry.owner if entry else None

    def check(self, resource: str, owner: str) -> bool:
        """May ``owner`` modify ``resource``? Free or owned by them."""
        entry = self._entries.get(resource)
        return entry is None or entry.owner == owner

    def entries(self) -> tuple[OwnershipEntry, ...]:
        return tuple(self._entries.values())

    def held_by(self, owner: str) -> tuple[OwnershipEntry, ...]:
        return tuple(e for e in self._entries.values() if e.owner == owner)

    def __len__(self) -> int:
        return len(self._entries)

    # ------------------------------------------------------------ teardown

    def clear(self) -> tuple[OwnershipEntry, ...]:
        """Runtime shutdown — release everything (audit-friendly)."""
        released = tuple(self._entries.values())
        self._entries.clear()
        if released:
            logger.debug("ownership: cleared %d resource(s) at shutdown", len(released))
        return released

    def snapshot(self) -> dict[str, Any]:
        """Serializable snapshot (checkpoint / audit)."""
        return {
            "count": len(self._entries),
            "entries": [entry.to_dict() for entry in self._entries.values()],
        }
