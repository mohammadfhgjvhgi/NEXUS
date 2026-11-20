#!/usr/bin/env python3
"""Live llama-server integration proof (Plan §5.3, §0.2 COMPATIBILITY→INTEGRATE).

Opt-in counterpart of the CI harness: this file drives the REAL
llama-server binary against the NEXUS adapter — everything the CI
suite proves with the fake server, this proves against the actual
ggml-org/llama.cpp release pinned in docs/REPOSITORY-INTEGRATION.md
(release b10829, commit 5fdfa628).

Requirements (auto-detected, graceful skip when absent):

* ``NEXUS_LLAMA_SERVER`` — path to the llama-server executable
  (default ``build/llama-b10829/llama-server``);
* ``NEXUS_TEST_MODEL``   — path to a GGUF model
  (default ``models/Qwen3-0.6B-Q8_0.gguf`` — the first-pool member).

Exit codes: 0 = all checks passed (or skipped: missing binary/model);
1 = at least one live check failed.

Usage::

    python tests/phase04/integration_llama_server.py

البرهان الحي — نفس سلسلة المرحلة الرابعة لكن ضد خادم llama.cpp
الحقيقي المثبّت بالإصدار؛ يتخطى نفسه (exit 0) حين لا تتوفر
الثنائية أو النموذج حتى يبقى CI أخضر بلا اعتماديات خارجية.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from nexus.models.benchmark import BenchmarkSpec, run_benchmark  # noqa: E402
from nexus.models.llamacpp import LlamaCppProvider, resolve_binary  # noqa: E402
from nexus.models.manager import ModelManager  # noqa: E402
from nexus.models.provider import (  # noqa: E402
    GenerateRequest,
    ModelNotLoadedError,
)
from nexus.models.registry import Model, ModelRegistry  # noqa: E402
from nexus.models.router import ModelRouter  # noqa: E402

BINARY = os.environ.get(
    "NEXUS_LLAMA_SERVER", str(REPO / "build" / "llama-b10829" / "llama-server")
)
MODEL_PATH = os.environ.get(
    "NEXUS_TEST_MODEL", str(REPO / "models" / "Qwen3-0.6B-Q8_0.gguf")
)
CONTEXT = int(os.environ.get("NEXUS_TEST_CONTEXT", "2048"))
READY_TIMEOUT = float(os.environ.get("NEXUS_READY_TIMEOUT", "120"))

MODEL_ID = "qwen3-0.6b-integration"


class Runner:
    def __init__(self) -> None:
        self.passed = 0
        self.failed = 0
        self.failures: list[str] = []

    def check(self, label: str, condition: bool, detail: str = "") -> None:
        mark = "PASS" if condition else "FAIL"
        suffix = f"  [{detail}]" if detail else ""
        print(f"  {mark}  {label}{suffix}")
        if condition:
            self.passed += 1
        else:
            self.failed += 1
            self.failures.append(label)

    def summary(self) -> int:
        total = self.passed + self.failed
        print(f"\nintegration: {self.passed}/{total} checks passed")
        if self.failures:
            print("failed:", ", ".join(self.failures))
        return 1 if self.failed else 0


def build_model() -> Model:
    return Model(
        id=MODEL_ID,
        name="Qwen3 0.6B (integration)",
        context=CONTEXT,
        capabilities=("chat", "coding"),
        ram=700,  # registry estimate — the live RSS corrects it after load
        vram=0,
        language=("en",),
        path=MODEL_PATH,
    )


def provider() -> LlamaCppProvider:
    return LlamaCppProvider(
        binary=BINARY,
        host="127.0.0.1",
        context_size=CONTEXT,
        ready_timeout=READY_TIMEOUT,
    )


def main() -> int:
    if not Path(BINARY).is_file():
        print(f"[skip] llama-server not found at {BINARY}")
        print("[skip] set NEXUS_LLAMA_SERVER to run the live integration proof")
        return 0
    if not Path(MODEL_PATH).is_file():
        print(f"[skip] test model not found at {MODEL_PATH}")
        print("[skip] set NEXUS_TEST_MODEL to run the live integration proof")
        return 0

    print(f"[live] llama-server : {BINARY}")
    print(f"[live] model        : {MODEL_PATH}")
    print(f"[live] context      : {CONTEXT}")
    runner = Runner()
    started = time.monotonic()

    # ------------------------------------------------------------ binary
    resolved = resolve_binary(BINARY)
    runner.check("resolve_binary pins the real executable", resolved == BINARY)

    # ------------------------------------------------------ §5.4 load
    prov = provider()
    model = build_model()
    t0 = time.monotonic()
    info = prov.load(model)
    load_s = time.monotonic() - t0
    runner.check("load returns an endpoint", bool(info.detail), info.detail)
    runner.check("loaded_ids contains the model", MODEL_ID in prov.loaded_ids())
    runner.check(
        f"model resident in {load_s:.1f}s (ready_timeout {READY_TIMEOUT:.0f}s)",
        load_s < READY_TIMEOUT,
    )

    # ----------------------------------------------------- §5.1 health
    health = prov.health(MODEL_ID)
    runner.check("health ok against the real server", health.ok, health.status)
    server = prov._servers[MODEL_ID]  # noqa: SLF001 — live probe of the handle
    runner.check("server process alive", server.alive())
    pid = getattr(server, "pid", None)
    runner.check("process pid exposed for memory observation", isinstance(pid, int))

    # --------------------------------------------- resident memory (MODE A)
    rss = prov.resident_memory_mb(MODEL_ID)
    try:
        import psutil  # noqa: PLC0415 — probe for the report line

        have_psutil = True
    except ImportError:
        have_psutil = False
    if have_psutil:
        runner.check(
            "real RSS observed via psutil (estimate was 700MB)",
            isinstance(rss, int) and rss > 100,
            f"{rss}MB" if isinstance(rss, int) else "None",
        )
    else:
        runner.check(
            "resident_memory_mb honest None without psutil", rss is None
        )

    # ----------------------------------------------------- §5.1 generate
    request = GenerateRequest(
        model_id=MODEL_ID,
        prompt="The capital of France is",
        max_tokens=12,
        temperature=0.7,
        top_p=0.95,
    )
    result = prov.generate(request)
    runner.check("generate produced text", len(result.text.strip()) > 0,
                 repr(result.text[:40]))
    runner.check("token accounting is real (predicted_n > 0)",
                 result.generation_tokens > 0, f"{result.generation_tokens} tok")
    runner.check(
        "speeds computed from server timings",
        (result.generation_tokens_per_second or 0) > 0,
        f"{result.generation_tokens_per_second:.1f} tok/s",
    )

    # ------------------------------------------------------- §5.1 stream
    chunks = list(
        prov.stream(
            GenerateRequest(
                model_id=MODEL_ID,
                prompt="Count from one to five:",
                max_tokens=16,
                temperature=0.7,
            )
        )
    )
    joined = "".join(chunk.delta for chunk in chunks)
    runner.check("stream yielded token deltas", len(chunks) >= 2,
                 f"{len(chunks)} chunks")
    runner.check("final chunk done with stats",
                 chunks[-1].done and chunks[-1].result is not None)
    runner.check("stream text is non-empty", len(joined.strip()) > 0,
                 repr(joined[:40]))

    # ------------------------------------------------------ §5.5 benchmark
    spec = BenchmarkSpec(
        warmup_runs=1,
        prompt_tokens=128,
        generation_tokens=16,
        stability_runs=2,
        context=CONTEXT,
    )

    def memory_sampler() -> tuple[int, int]:
        rss_now = prov.resident_memory_mb(MODEL_ID) or 0
        return rss_now, 0

    bench = run_benchmark(
        prov, model, spec, memory_sampler=memory_sampler
    )
    runner.check("benchmark warmup ran", bench.warmup)
    runner.check("prompt speed measured on this machine",
                 (bench.prompt_speed or 0) > 0,
                 f"{bench.prompt_speed:.1f} tok/s" if bench.prompt_speed else "None")
    runner.check("generation speed measured on this machine",
                 (bench.generation_speed or 0) > 0,
                 f"{bench.generation_speed:.1f} tok/s"
                 if bench.generation_speed else "None")
    runner.check("stability = 1.0 (2/2 runs)", bench.stability == 1.0)
    runner.check("benchmark RAM is the real RSS",
                 bench.ram is not None and bench.ram > 100, f"{bench.ram}MB")
    print(
        f"\n[live] §5.5 profile — prompt {bench.prompt_speed:.1f} tok/s · "
        f"generation {bench.generation_speed:.1f} tok/s · "
        f"ram {bench.ram}MB · stability {bench.stability}"
    )

    # ------------------------------------------------- §5.4 manager cycle
    with tempfile.TemporaryDirectory() as tmp:
        registry = ModelRegistry(Path(tmp) / "registry.json")
        registry.register(model)
        manager = ModelManager(
            registry=registry,
            provider=prov,
            router=ModelRouter(),
            resources=None,
            bus=None,
            seed_mimo_edge=False,
        )
        record = manager.load(MODEL_ID, reason="live-integration")
        runner.check(
            "manager record carries the REAL footprint (§135)",
            record.ram_mb > 100 and record.ram_mb != model.ram,
            f"{record.ram_mb}MB (estimate was {model.ram}MB)",
        )
        out = manager.generate(
            GenerateRequest(model_id=MODEL_ID, prompt="2 + 2 =", max_tokens=4)
        )
        runner.check("manager generate round-trip works live",
                     isinstance(out.text, str))
        manager.unload(MODEL_ID, reason="live-integration")
        runner.check("manager unload returns the pool to empty",
                     MODEL_ID not in manager._loaded)  # noqa: SLF001

    # ------------------------------------------------------- §5.4 unload
    prov2 = provider()
    info2 = prov2.load(build_model())
    runner.check("second provider instance loads independently",
                 bool(info2.detail))
    pid2 = getattr(prov2._servers[MODEL_ID], "pid", None)  # noqa: SLF001
    prov2.unload(MODEL_ID)
    runner.check("unload stopped the server process", not prov2.loaded_ids())
    if isinstance(pid2, int) and have_psutil:
        import psutil  # noqa: PLC0415

        try:
            psutil.Process(pid2)
            gone = False
        except psutil.NoSuchProcess:
            gone = True
        runner.check("old pid is gone after unload", gone, f"pid {pid2}")

    try:
        prov.generate(request)
        raised = False
    except ModelNotLoadedError:
        raised = True
    runner.check("generate after unload raises ModelNotLoadedError", raised)

    elapsed = time.monotonic() - started
    print(f"\n[live] total wall time {elapsed:.1f}s")
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
