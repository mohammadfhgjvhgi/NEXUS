"""NEXUS Memory System (Final Build Plan §13 / New Plan §12 — PHASE 12).

*From persistence to a Memory Engine.*

========================  ======================================  ==========
Component                 Plan source                             Module
========================  ======================================  ==========
Contracts (five names)   §12.1                                   contracts
Hierarchy (12 scopes)    §12.2                                   contracts
Metadata (11 fields)     §12.3                                   contracts
SQLite index + relations §12.4                                   store
Qdrant semantic layer    §12.5 (MODE A, optional)                vectors
Local vector fallback     — (always available)                   vectors
Embedding seam            §12.5                                  embeddings
Mem0 adapter              §12.6 (MODE B, optional)               mem0_adapter
Retrieval pipeline        §12.7                                  engine
Conflict ladder           §12.8                                  conflict
Forget + audit            §12.9                                  forget
Compression               §12.10                                 compression
Memory Manager verbs      §13.1                                  engine
========================  ======================================  ==========

The seven §13.1 verbs — ``remember · retrieve · search · update ·
forget · summarize · link`` — live on
:class:`~nexus.memory.engine.MemoryEngine` (the default provider) and
on :class:`~nexus.memory.mem0_adapter.Mem0MemoryProvider` (the §12.6
engine candidate). Everything external (qdrant-client, mem0ai) enters
behind an adapter and is replaceable (Plan §61: *NEXUS owns Memory
semantics*).

The core stays stdlib-only: ``pip install nexus-core[qdrant]`` /
``[mem0]`` are optional, and every absence is *reported*, never
faked (:func:`~nexus.memory.vectors.qdrant_probe`,
:func:`~nexus.memory.mem0_adapter.mem0_probe`).

نظام الذاكرة — من الحفظ إلى المحرّك: عقود ومستويات وفهرس
وذاكرة دلالية وحلّ تعارض ونسيان وضغط، كلها خلف سبعة أفعال.

Stdlib only.
"""

from .compression import (
    COMPRESS_CHAR_THRESHOLD,
    COMPRESS_TURN_THRESHOLD,
    COMPRESSION_STAGES,
    CompressionResult,
    MemoryCompressor,
    should_compress,
)
from .conflict import (
    CONFLICT_PRIORITY,
    ConflictOutcome,
    ConflictResolver,
    conflict_level,
)
from .contracts import (
    CONTAINER_SCOPES,
    EVIDENCE_FIELDS,
    EVIDENCE_METHODS,
    MEMORY_QUERY_FIELDS,
    MEMORY_RECORD_FIELDS,
    MEMORY_SCOPES,
    MEMORY_TYPES,
    RELATIONSHIPS,
    ForgetResult,
    InvalidMemoryError,
    MemoryError,
    MemoryEvidence,
    MemoryNotFoundError,
    MemoryProvider,
    MemoryQuery,
    MemoryRecord,
    MemoryScope,
    MemorySearchHit,
    MemoryType,
    new_memory_id,
    scope_visible,
    utc_now_iso,
)
from .embeddings import (
    EmbeddingProvider,
    HashingEmbedder,
    ModelEmbedder,
    tokenize,
)
from .engine import (
    BLOCK_ORDER,
    RANK_WEIGHTS,
    RECENCY_HALF_LIFE_DAYS,
    SCOPE_FIT,
    SEMANTIC_STRONG,
    ContextBlock,
    MemoryContext,
    MemoryEngine,
    build_memory_engine,
    rank_score,
)
from .forget import FORGET_ACTIONS, ForgetOps
from .mem0_adapter import MEM0_SCOPE_MAP, Mem0MemoryProvider, mem0_probe
from .store import SCHEMA_VERSION, AuditEntry, SQLiteMemoryStore
from .vectors import (
    VECTOR_FILTER_KEYS,
    LocalVectorIndex,
    MemoryBackendError,
    QdrantVectorIndex,
    VectorHit,
    VectorIndex,
    cosine_similarity,
    payload_matches,
    qdrant_probe,
    record_payload,
    resolve_vector_index,
)

__all__ = [
    # contracts (§12.1–§12.3)
    "CONTAINER_SCOPES",
    "EVIDENCE_FIELDS",
    "EVIDENCE_METHODS",
    "ForgetResult",
    "InvalidMemoryError",
    "MEMORY_QUERY_FIELDS",
    "MEMORY_RECORD_FIELDS",
    "MEMORY_SCOPES",
    "MEMORY_TYPES",
    "MemoryError",
    "MemoryEvidence",
    "MemoryNotFoundError",
    "MemoryProvider",
    "MemoryQuery",
    "MemoryRecord",
    "MemoryScope",
    "MemorySearchHit",
    "MemoryType",
    "RELATIONSHIPS",
    "new_memory_id",
    "scope_visible",
    "utc_now_iso",
    # store (§12.4)
    "SCHEMA_VERSION",
    "AuditEntry",
    "SQLiteMemoryStore",
    # embeddings + vectors (§12.5)
    "EmbeddingProvider",
    "HashingEmbedder",
    "ModelEmbedder",
    "VECTOR_FILTER_KEYS",
    "VectorHit",
    "VectorIndex",
    "LocalVectorIndex",
    "QdrantVectorIndex",
    "MemoryBackendError",
    "cosine_similarity",
    "payload_matches",
    "qdrant_probe",
    "record_payload",
    "resolve_vector_index",
    "tokenize",
    # conflict (§12.8)
    "CONFLICT_PRIORITY",
    "ConflictOutcome",
    "ConflictResolver",
    "conflict_level",
    # forget (§12.9)
    "FORGET_ACTIONS",
    "ForgetOps",
    # compression (§12.10)
    "COMPRESS_CHAR_THRESHOLD",
    "COMPRESS_TURN_THRESHOLD",
    "COMPRESSION_STAGES",
    "CompressionResult",
    "MemoryCompressor",
    "should_compress",
    # engine (§13.1 / §12.7)
    "BLOCK_ORDER",
    "ContextBlock",
    "MemoryContext",
    "MemoryEngine",
    "RANK_WEIGHTS",
    "RECENCY_HALF_LIFE_DAYS",
    "SCOPE_FIT",
    "SEMANTIC_STRONG",
    "build_memory_engine",
    "rank_score",
    # mem0 adapter (§12.6)
    "MEM0_SCOPE_MAP",
    "Mem0MemoryProvider",
    "mem0_probe",
]
