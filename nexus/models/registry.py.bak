"""Model Registry (Final Build Plan §5.2 / Spec §134).

The twelve model fields are verbatim from the plan (plus the benchmark
value, which the plan lists as the thirteenth field)::

    id
    name
    format
    backend
    size
    context
    capabilities
    ram
    vram
    language
    benchmark
    status

Units and vocabulary:

* ``ram`` / ``vram`` — requirements in **MB**;
* ``size``           — on-disk model size in **bytes** (approximate
  until the file is measured on the device);
* ``format``         — ``"GGUF"`` for the llama.cpp pool;
* ``backend``        — Spec §253 contract value, e.g. ``"llama.cpp"``;
* ``language``       — language codes the model serves;
* ``status``         — :class:`ModelStatus` lifecycle value.

The registry persists atomically (temp file + ``os.replace`` +
``fsync``) as ``models.registry.json`` under ``NexusPaths.models``.
The pool is **never fixed**: register and unregister freely (Plan §5.6
— the MiMo Edge five are only the *first* pool).

السجل — الحقول حرفيًا من الخطة؛ التخزين ذرّي، والقائمة ليست ثابتة.

Stdlib only.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .benchmark import ModelBenchmark

REGISTRY_SCHEMA = "nexus.models.registry"
REGISTRY_VERSION = 1
REGISTRY_FILE = "models.registry.json"
REGISTRY_HISTORY_LIMIT = 8  # benchmark runs kept per model

#: Common backend / format values (Spec §253, §93).
BACKEND_LLAMA_CPP = "llama.cpp"
FORMAT_GGUF = "GGUF"


class ModelStatus:
    """Model record lifecycle (values are stable strings)."""

    REGISTERED = "registered"      # in the registry, no benchmark yet
    BENCHMARKED = "benchmarked"    # carries a benchmark profile
    LOADED = "loaded"              # resident in the provider
    UNLOADED = "unloaded"          # was loaded, now released
    ERROR = "error"                # last load/generate failed
    UNAVAILABLE = "unavailable"    # model file missing on this device


class RegistryError(Exception):
    """Registry misuse (duplicate id, unknown model, bad record…)."""


@dataclass(slots=True)
class Model:
    """One registered model — the §5.2 fields, verbatim order.

    ``path`` is auxiliary (not one of the plan's fields): the local
    weights file, resolved by the manager when loading. It is persisted
    so a registered model survives reboots.
    """

    id: str
    name: str
    format: str = FORMAT_GGUF
    backend: str = BACKEND_LLAMA_CPP
    size: int = 0  # bytes (approximate until measured)
    context: int = 8192
    capabilities: tuple[str, ...] = ()
    ram: int = 0  # MB required
    vram: int = 0  # MB required
    language: tuple[str, ...] = ("en",)
    benchmark: ModelBenchmark | None = None
    status: str = ModelStatus.REGISTERED
    # auxiliary (documented, not a §5.2 field):
    path: str | None = None
    benchmark_history: tuple[ModelBenchmark, ...] = ()

    # ------------------------------------------------------------ helpers

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities

    def fits(self, *, ram_mb: int | None, vram_mb: int | None) -> bool:
        """True when the model's requirements fit the given budgets."""
        if ram_mb is not None and self.ram > ram_mb:
            return False
        if vram_mb is not None and self.vram > vram_mb:
            return False
        return True

    def with_status(self, status: str) -> Model:
        return replace(self, status=status)

    # -------------------------------------------------------- serialization

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "format": self.format,
            "backend": self.backend,
            "size": self.size,
            "context": self.context,
            "capabilities": list(self.capabilities),
            "ram": self.ram,
            "vram": self.vram,
            "language": list(self.language),
            "benchmark": self.benchmark.to_dict() if self.benchmark else None,
            "status": self.status,
            "path": self.path,
            "benchmark_history": [
                b.to_dict() for b in self.benchmark_history[-REGISTRY_HISTORY_LIMIT:]
            ],
        }
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Model:
        try:
            benchmark_raw = data.get("benchmark")
            benchmark = (
                ModelBenchmark.from_dict(benchmark_raw)
                if isinstance(benchmark_raw, dict)
                else None
            )
            history_raw = data.get("benchmark_history") or []
            history = tuple(
                ModelBenchmark.from_dict(h) for h in history_raw if isinstance(h, dict)
            )
            return cls(
                id=str(data["id"]),
                name=str(data["name"]),
                format=str(data.get("format", FORMAT_GGUF)),
                backend=str(data.get("backend", BACKEND_LLAMA_CPP)),
                size=int(data.get("size", 0)),
                context=int(data.get("context", 8192)),
                capabilities=tuple(str(c) for c in data.get("capabilities", ())),
                ram=int(data.get("ram", 0)),
                vram=int(data.get("vram", 0)),
                language=tuple(str(x) for x in data.get("language", ("en",))),
                benchmark=benchmark,
                status=str(data.get("status", ModelStatus.REGISTERED)),
                path=data.get("path"),
                benchmark_history=history[-REGISTRY_HISTORY_LIMIT:],
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise RegistryError(f"invalid model record: {exc}") from exc


@dataclass(slots=True)
class ModelSummary:
    """Registry listing row (id/name/status — the cheap view)."""

    id: str
    name: str
    backend: str
    status: str


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Crash-safe write: temp file + fsync + ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp_path, path)


class ModelRegistry:
    """Persistent registry of models — register, query, update, drop.

    The registry is pure bookkeeping: it never spawns processes and
    never touches resources (that is the §5.4 Model Manager's job).
    """

    def __init__(self, registry_path: str | Path) -> None:
        self._path = Path(registry_path)
        self._models: dict[str, Model] = {}
        self._load()

    # ------------------------------------------------------------ lifecycle

    @property
    def registry_path(self) -> Path:
        return self._path

    def _load(self) -> bool:
        """Load the persisted registry; a missing file is a fresh start."""
        if not self._path.is_file():
            return False
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise RegistryError(f"failed to read {self._path}: {exc}") from exc
        if raw.get("schema") != REGISTRY_SCHEMA:
            raise RegistryError(
                f"unexpected registry schema {raw.get('schema')!r} in {self._path}"
            )
        self._models = {
            str(item["id"]): Model.from_dict(item)
            for item in raw.get("models", [])
            if isinstance(item, dict)
        }
        return True

    def save(self) -> Path:
        """Persist atomically (temp + fsync + replace)."""
        data = {
            "schema": REGISTRY_SCHEMA,
            "version": REGISTRY_VERSION,
            "count": len(self._models),
            "models": [m.to_dict() for m in self._models.values()],
        }
        _atomic_write_json(self._path, data)
        return self._path

    # ------------------------------------------------------------- mutation

    def register(self, model: Model, *, replace: bool = False) -> Model:
        """Add one model (or replace it when ``replace`` is set)."""
        model_id = model.id.strip()
        if not model_id:
            raise RegistryError("model id must be a non-empty string")
        if model_id in self._models and not replace:
            raise RegistryError(f"model already registered: {model_id!r}")
        record = model if model.id == model_id else _with_id(model, model_id)
        self._models[model_id] = record
        return record

    def unregister(self, model_id: str) -> Model:
        """Drop one model — the pool is never fixed (Plan §5.6)."""
        model = self._models.pop(model_id, None)
        if model is None:
            raise RegistryError(f"unknown model: {model_id!r}")
        return model

    def upsert(self, model: Model) -> Model:
        """Replace one record (same id) — used by status/benchmark updates."""
        if model.id not in self._models:
            raise RegistryError(f"unknown model: {model.id!r}")
        self._models[model.id] = model
        return model

    def mark_status(self, model_id: str, status: str) -> Model:
        """Update one model's §5.2 ``status`` field."""
        model = self.get(model_id)
        updated = model.with_status(status)
        self._models[model_id] = updated
        return updated

    def attach_benchmark(
        self, model_id: str, benchmark: ModelBenchmark
    ) -> Model:
        """Persist one benchmark onto the record (§5.5 «ثم يحفظ
        benchmark») + append to bounded history; status → benchmarked."""
        model = self.get(model_id)
        history = tuple(
            list(model.benchmark_history[-(REGISTRY_HISTORY_LIMIT - 1):])
            + [benchmark]
        )
        updated = replace(
            model,
            benchmark=benchmark,
            benchmark_history=history,
            status=(
                ModelStatus.BENCHMARKED
                if model.status
                not in (ModelStatus.LOADED, ModelStatus.ERROR)
                else model.status
            ),
        )
        self._models[model_id] = updated
        return updated

    # --------------------------------------------------------------- queries

    def get(self, model_id: str) -> Model:
        model = self._models.get(model_id)
        if model is None:
            raise RegistryError(f"unknown model: {model_id!r}")
        return model

    def find(self, model_id: str) -> Model | None:
        return self._models.get(model_id)

    def list_models(self) -> tuple[Model, ...]:
        return tuple(self._models.values())

    def summaries(self) -> tuple[ModelSummary, ...]:
        return tuple(
            ModelSummary(id=m.id, name=m.name, backend=m.backend, status=m.status)
            for m in self._models.values()
        )

    def find_by_capability(self, capability: str) -> tuple[Model, ...]:
        return tuple(m for m in self._models.values() if m.has_capability(capability))

    def __len__(self) -> int:
        return len(self._models)

    def __contains__(self, model_id: str) -> bool:
        return model_id in self._models


def _with_id(model: Model, model_id: str) -> Model:
    return replace(model, id=model_id)


def new_model_id(name: str) -> str:
    """Derive a registry id from a display name (Qwen2.5-Coder-1.5B →
    qwen2.5-coder-1.5b). Collision-checking stays with the caller."""
    lowered = name.strip().lower()
    cleaned = "".join(ch if ch.isalnum() or ch in ".-_" else "-" for ch in lowered)
    return cleaned.strip("-.") or "model"


#: Field order documented for audit (the §5.2 list, verbatim).
MODEL_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "format",
    "backend",
    "size",
    "context",
    "capabilities",
    "ram",
    "vram",
    "language",
    "benchmark",
    "status",
)

__all__ = [
    "BACKEND_LLAMA_CPP",
    "FORMAT_GGUF",
    "MODEL_FIELDS",
    "Model",
    "ModelRegistry",
    "ModelStatus",
    "ModelSummary",
    "RegistryError",
    "REGISTRY_FILE",
    "REGISTRY_HISTORY_LIMIT",
    "REGISTRY_SCHEMA",
    "REGISTRY_VERSION",
    "new_model_id",
]
