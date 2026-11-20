"""Vector index — the §12.5 semantic layer behind one contract.

Two backends, one protocol:

* :class:`LocalVectorIndex`   — stdlib cosine over float32 rows in the
  §12.4 SQLite store. Zero deps, survives restarts (same file), and
  proves the whole pipeline anywhere (CI, device, cold start).
* :class:`QdrantVectorIndex` — **MODE A** adapter over
  ``qdrant-client`` (Apache-2.0, pinned via the ``[qdrant]`` extra —
  the PyPI distro of qdrant/qdrant). Local mode (``:memory:`` or a
  path — no server) or a live server (``http://…:6333``); filtered
  retrieval maps our payload dictionaries to Qdrant ``Filter`` musts.

The house law: absence is *reported*, never faked.
:func:`qdrant_probe` answers exactly why the adapter can't load, and
the factory falls back to the local index with the reason recorded in
the engine's backend report.

Integration record (Plan §54, full cycle in
docs/REPOSITORY-INTEGRATION.md §11/§12): qdrant/qdrant @ Apache-2.0,
staged at ``vendor-staging/phase-12/qdrant``; NEXUS speaks to it only
through the ``qdrant-client`` distribution — never to its Rust
internals — so the backend stays replaceable (Plan §61).

الطبقة الدلالية — محركان خلف عقد واحد: المحلي دائم الحضور،
وكودرانت عند تثبيته؛ الغياب يُقال ولا يُخفى.

Stdlib only (qdrant-client is optional).
"""

from __future__ import annotations

import math
from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .contracts import MemoryRecord

#: Payload keys mirrored into the vector index (§12.5 filtered retrieval).
VECTOR_FILTER_KEYS: tuple[str, ...] = (
    "scope",
    "type",
    "project",
    "workspace",
    "task",
    "session",
    "agent",
    "conflict_key",
)


def record_payload(record: MemoryRecord) -> dict[str, Any]:
    """The filterable subset of a record — what rides the vector."""
    payload: dict[str, Any] = {"scope": record.scope, "type": record.type}
    for key in ("project", "workspace", "task", "session", "agent", "conflict_key"):
        value = getattr(record, key)
        if value is not None:
            payload[key] = value
    return payload


def payload_matches(payload: Mapping[str, Any], flt: Mapping[str, Any]) -> bool:
    """Subset semantics: every filter key must equal the payload's."""
    return all(payload.get(key) == value for key, value in flt.items())


def cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine of two vectors — 0.0 for dimension mismatch (no crash)."""
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


@dataclass(frozen=True, slots=True)
class VectorHit:
    """One similarity hit — record id, score, and the payload back."""

    record_id: str
    score: float
    payload: dict[str, Any] = field(default_factory=dict)


class VectorIndex(ABC):
    """upsert · search · delete · count — the whole §12.5 surface."""

    name: str

    @abstractmethod
    def upsert(
        self,
        points: Sequence[tuple[str, Sequence[float], Mapping[str, Any]]],
    ) -> None: ...

    @abstractmethod
    def search(
        self,
        vector: Sequence[float],
        *,
        limit: int = 16,
        flt: Mapping[str, Any] | None = None,
    ) -> list[VectorHit]: ...

    @abstractmethod
    def delete(self, record_ids: Sequence[str]) -> None: ...

    @abstractmethod
    def count(self) -> int: ...


class LocalVectorIndex(VectorIndex):
    """Cosine over the SQLite ``memory_vectors`` table (§12.4).

    Restarts survive because the rows live in the same single DB file
    as the metadata — the exit gate's «Restart persistence ✅» covers
    semantics too, with zero moving parts.
    """

    def __init__(self, store: object) -> None:
        # Duck-typed store (SQLiteMemoryStore) — keeps imports lazy.
        self.name = "local-sqlite"
        self._store = store

    def upsert(
        self,
        points: Sequence[tuple[str, Sequence[float], Mapping[str, Any]]],
    ) -> None:
        for record_id, vector, payload in points:
            self._store.upsert_vector(record_id, list(vector), dict(payload))  # type: ignore[attr-defined]

    def search(
        self,
        vector: Sequence[float],
        *,
        limit: int = 16,
        flt: Mapping[str, Any] | None = None,
    ) -> list[VectorHit]:
        flt = flt or {}
        scored: list[VectorHit] = []
        for record_id, stored, payload in self._store.iter_vectors():  # type: ignore[attr-defined]
            if not payload_matches(payload, flt):
                continue
            score = cosine_similarity(vector, stored)
            if score > 0.0:
                scored.append(
                    VectorHit(record_id=record_id, score=score, payload=payload)
                )
        scored.sort(key=lambda hit: (-hit.score, hit.record_id))
        return scored[:limit]

    def delete(self, record_ids: Sequence[str]) -> None:
        for record_id in record_ids:
            self._store.delete_vector(record_id)  # type: ignore[attr-defined]

    def count(self) -> int:
        return int(self._store.count_vectors())  # type: ignore[attr-defined]


# ------------------------------------------------------------ qdrant MODE A


def qdrant_probe() -> str | None:
    """Return None when qdrant-client is importable, else the reason."""
    try:
        import qdrant_client  # type: ignore[import-not-found]  # noqa: F401 — probe
    except ImportError as exc:
        return f"qdrant-client not installed: {exc}"
    return None


class QdrantVectorIndex(VectorIndex):
    """§12.5 adapter — qdrant-client behind the VectorIndex contract.

    ``location``: ``":memory:"`` (tests), a directory path (local
    persisted mode, no server), or a URL like ``http://host:6333``.
    One collection (``nexus_memory``), recreated on dimension change;
    payload filters map to Qdrant must-conditions.
    """

    COLLECTION = "nexus_memory"

    @staticmethod
    def _make_client(location: str):
        """Build the right client for each §12.5 deployment mode:

        ``":memory:"`` → in-memory (tests) · ``http(s)://…`` → server ·
        anything else → a local persisted path, no server ever needed.
        """
        from qdrant_client import QdrantClient  # type: ignore[import-not-found]

        if location == ":memory:":
            return QdrantClient(location=":memory:")
        if location.startswith(("http://", "https://")):
            return QdrantClient(url=location)
        return QdrantClient(path=location)

    def __init__(
        self,
        location: str = ":memory:",
        *,
        dimension: int = 384,
        distance: str = "Cosine",
    ) -> None:
        from qdrant_client.models import (  # type: ignore[import-not-found]
            Distance,
            VectorParams,
        )

        is_url = location.startswith(("http://", "https://"))
        self.name = "qdrant" if is_url else "qdrant-local"
        self._client = self._make_client(location)
        self._dimension = dimension
        self._distance = distance
        self._models_distance: Any = (
            Distance.COSINE if distance == "Cosine" else distance
        )
        existing = self._client.get_collections().collections
        names = {collection.name for collection in existing}
        if self.COLLECTION in names:
            info = self._client.get_collection(self.COLLECTION)
            vectors = getattr(info.config.params, "vectors", None)
            current_dim = getattr(vectors, "size", None)
            if current_dim is not None and current_dim != dimension:
                self._client.delete_collection(self.COLLECTION)
                names.discard(self.COLLECTION)
        if self.COLLECTION not in names:
            self._client.create_collection(
                collection_name=self.COLLECTION,
                vectors_config=VectorParams(
                    size=dimension, distance=self._models_distance
                ),
            )

    def _point_id(self, record_id: str) -> str:
        """Deterministic UUID5 for our ids — Qdrant's local mode only
        accepts UUID point ids, and uuid5 keeps the mapping reversible
        without a lookup table (the real id rides the payload too)."""
        import uuid

        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"nexus-memory:{record_id}"))

    def _point(self, record_id: str, vector: Sequence[float], payload: Mapping[str, Any]):
        from qdrant_client.models import PointStruct  # type: ignore[import-not-found]

        body = dict(payload)
        body["record_id"] = record_id
        return PointStruct(
            id=self._point_id(record_id), vector=list(vector), payload=body
        )

    def _filter(self, flt: Mapping[str, Any]):
        from qdrant_client.models import (  # type: ignore[import-not-found]
            FieldCondition,
            Filter,
            MatchValue,
        )

        return Filter(
            must=[
                FieldCondition(key=key, match=MatchValue(value=value))
                for key, value in flt.items()
            ]
        )

    def upsert(
        self,
        points: Sequence[tuple[str, Sequence[float], Mapping[str, Any]]],
    ) -> None:
        if not points:
            return
        self._client.upsert(
            collection_name=self.COLLECTION,
            points=[
                self._point(record_id, vector, payload)
                for record_id, vector, payload in points
            ],
        )

    def search(
        self,
        vector: Sequence[float],
        *,
        limit: int = 16,
        flt: Mapping[str, Any] | None = None,
    ) -> list[VectorHit]:
        result = self._client.query_points(
            collection_name=self.COLLECTION,
            query=list(vector),
            limit=limit,
            query_filter=self._filter(flt) if flt else None,
            with_payload=True,
        )
        hits = []
        for point in result.points:
            payload = dict(point.payload or {})
            hits.append(
                VectorHit(
                    record_id=str(payload.get("record_id", point.id)),
                    score=float(point.score),
                    payload=payload,
                )
            )
        return hits

    def delete(self, record_ids: Sequence[str]) -> None:
        from qdrant_client.models import PointIdsList  # type: ignore[import-not-found]

        if not record_ids:
            return
        self._client.delete(
            collection_name=self.COLLECTION,
            points_selector=PointIdsList(
                points=[self._point_id(record_id) for record_id in record_ids]
            ),
        )

    def count(self) -> int:
        info = self._client.count(self.COLLECTION, exact=True)
        return int(info.count)

    def close(self) -> None:
        """Release the local storage lock (single-instance per path —
        Qdrant's law, documented in their local-mode errors)."""
        try:
            self._client.close()
        except Exception:  # noqa: BLE001 — closing must never raise
            pass


def resolve_vector_index(
    store: object,
    *,
    backend: str = "auto",
    dimension: int = 384,
    qdrant_location: str = ":memory:",
) -> tuple[VectorIndex, str]:
    """§12.5 backend resolution — auto → qdrant when present, local else.

    Returns ``(index, report)`` — the report names the backend and, on
    fallback, *why* (the probe message, verbatim).
    """
    if backend in ("qdrant", "auto"):
        reason = qdrant_probe()
        if reason is None:
            return (
                QdrantVectorIndex(location=qdrant_location, dimension=dimension),
                "qdrant-client loaded — §12.5 semantic retrieval on Qdrant",
            )
        if backend == "qdrant":
            raise MemoryBackendError(
                f"qdrant requested explicitly but unavailable: {reason}"
            )
        local = LocalVectorIndex(store)
        return (
            local,
            f"qdrant unavailable ({reason}) — LocalVectorIndex fallback engaged",
        )
    if backend == "local":
        return LocalVectorIndex(store), "local backend requested — LocalVectorIndex"
    raise ValueError(f"unknown vector backend {backend!r} (auto|local|qdrant)")


class MemoryBackendError(Exception):
    """An explicitly requested §12.5 backend cannot load."""
