"""Embedding providers — the semantic seam of the Memory System.

The vector stage (§12.5) needs numbers; three honest sources provide
them, all behind one contract:

* :class:`HashingEmbedder`  — stdlib, deterministic, zero-dep. Lexical
  overlap similarity, *not* real semantics — the always-available
  baseline that keeps the pipeline provable everywhere (CI included).
* :class:`ModelEmbedder`    — the production path: an
  embeddings-capable model through the §5.4 Model Manager (llama.cpp
  ``/embedding`` behind the §5.1 provider contract). Real semantics,
  real hardware, optional presence — probed honestly.
* external embedders (Qdrant fastembed & friends) — ride the same
  contract later; nothing in the engine knows their names.

The engine never imports an embedder directly — it receives one. The
factory (:func:`~nexus.memory.build_memory_engine`) picks the best
available and *reports* what it picked (house rule: no silent
degradation).

مزوّدات التضمين — المصفوفة الدلالية خلف عقد واحد: أساس التلبيد
دائمًا، ومزوّد النموذج عند توفره، وكل بديل لاحقًا عبر نفس العقد.

Stdlib only.
"""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

_TOKEN_PATTERN = re.compile(r"[\w]+", re.UNICODE)


def tokenize(text: str) -> list[str]:
    """Language-agnostic tokens (Arabic + Latin, case-folded, NFKC).

    ``unicodedata.normalize`` + ``\\w`` keeps Arabic letters intact —
    «الذاكرة» stays one token, not noise.
    """
    normalized = unicodedata.normalize("NFKC", text)
    return [token.casefold() for token in _TOKEN_PATTERN.findall(normalized)]


class EmbeddingProvider(ABC):
    """One method, one dimension, one name — the whole contract."""

    name: str
    dimension: int

    @abstractmethod
    def embed(self, text: str) -> list[float]: ...

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]


class HashingEmbedder(EmbeddingProvider):
    """Deterministic feature-hashing embedder (the §12.5 baseline).

    Bag-of-tokens → signed bucket sums → L2-normalized float vector.
    Similarity between two vectors ≈ lexical overlap — *semantic-ish*,
    honest about being lexical. Stable across runs and machines
    (blake2b, fixed seed) so restarts and CI never see drift.
    """

    def __init__(self, dimension: int = 384) -> None:
        if dimension < 8:
            raise ValueError("HashingEmbedder dimension must be >= 8")
        self.name = "hashing-baseline"
        self.dimension = dimension

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        tokens = tokenize(text)
        for token in tokens:
            digest = hashlib.blake2b(
                token.encode("utf-8"), digest_size=8, person=b"nexus-mem"
            ).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vec))
        if norm == 0.0:
            return vec
        return [value / norm for value in vec]


class ModelEmbedder(EmbeddingProvider):
    """Embeddings through the §5 Model Runtime (the production path).

    Wraps a ModelManager-like object (duck-typed: ``select`` +
    ``generate``, §5.4/§5.7 — kept duck-typed so this module stays
    importable stdlib-only): builds a §5.7 :class:`RoutingRequest`
    with ``required_capability="embeddings"``, routes to a model,
    sends a :class:`GenerateRequest` and parses the float vector from
    the answer (a JSON list — the llama-server ``/embedding`` shape,
    or a bracketed list). With no embeddings-capable model the probe
    *refuses* — the factory then falls back to the baseline and says
    so (a missing model is a fact to report, never a lie to hide).
    """

    def __init__(self, manager: Any, dimension: int = 0) -> None:
        self.name = "model-embedder"
        self._manager = manager
        self.dimension = dimension

    def _route(self) -> Any:
        """§5.7 routing — embeddings capability or refuse."""
        from nexus.models.router import RoutingRequest

        request = RoutingRequest(required_capability="embeddings")
        decision = self._manager.select(request)
        if getattr(decision, "selected_model_id", None) is None:
            raise RuntimeError("no embeddings-capable model available")
        return decision.selected_model_id

    def embed(self, text: str) -> list[float]:
        from nexus.models.provider import GenerateRequest

        model_id = self._route()
        request = GenerateRequest(model_id=model_id, prompt=text, max_tokens=4096)
        response = self._manager.generate(request)
        vector: Any = getattr(response, "embedding", None)
        if not vector:
            vector = _parse_floats(getattr(response, "text", ""))
        if not vector:
            raise RuntimeError("embeddings model returned no vector")
        values = [float(value) for value in vector]
        if self.dimension == 0:
            self.dimension = len(values)
        elif len(values) != self.dimension:
            raise RuntimeError(
                f"embedding dimension drifted: {len(values)} != {self.dimension}"
            )
        return values


def _parse_floats(raw: str) -> list[float]:
    """Parse a bracketed/JSON-ish float list out of a model answer."""
    import json

    text = raw.strip()
    if text.startswith("[") and text.endswith("]"):
        try:
            values = json.loads(text)
            if isinstance(values, list):
                return [float(value) for value in values]
        except (json.JSONDecodeError, TypeError, ValueError):
            pass
    return []
