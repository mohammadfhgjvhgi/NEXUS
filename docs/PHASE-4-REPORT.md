# PHASE 4 — Local Model Runtime · Completion Report

> Final Build Plan §5 · Concept: **local intelligence enters the machine, on its own resources**
> المصدر الحاكم: `docs/reference/NEXUS-Final-Build-Plan-v1.0.md` (§5.1–§5.7) + `NEXUS-Master-Technical-Specification-v1.0.md` (§87–§88, §93, §134–§138, §178, §253)

## الملخص التنفيذي

<div dir="rtl">

المرحلة الرابعة تُدخل **الذكاء المحلي** إلى NEXUS: واجهة `ModelProvider` بأعضائها السبعة حرفيًّا (§5.1)، سجل نماذج بحقوله الاثني عشر + الـbenchmark (§5.2)، محوّل llama.cpp يحرّك `llama-server` عبر HTTP (§5.3 — Backend الاستدلال المحلي الأساسي، والمدير مستقل عنه)، تحميل ديناميكي بأفعاله الخمسة **وفق الموارد**: الحجز قبل التشغيل، وإخلاء الخاملين LRU عند الضغط، والرفض فقط حين يستحيل الإيواء (§5.4)، بروتوكول قياس بترتيب المواصفة §135 حرفيًّا يُحفظ على السجل (§5.5)، أول مجموعة نماذج من نتائج جهاز المستخدم نفسه (§5.6 — نتائج MiMo Edge من المواصفة §88، والقائمة **ليست ثابتة**)، وموجّه يُخرج **معرّف النموذج المختار** من المدخلات الست الحرفية (§5.7). بلا أسماء أحداث جديدة — الأحداث الأربعة §2.2 للنماذج هي كل ما يُنشر.

</div>

Phase 4 brings **local intelligence** into NEXUS: the `ModelProvider` interface with its seven members verbatim (§5.1), a model registry with its twelve fields + benchmark (§5.2), the llama.cpp adapter driving `llama-server` over HTTP (§5.3 — the primary local inference backend, with the manager independent of it), dynamic loading with its five verbs **per resources** — budget before boot, LRU idle eviction under pressure, refusal only when hosting is impossible (§5.4), the benchmark protocol in the verbatim Spec §135 order, persisted onto the record (§5.5), the first model pool seeded from the user's own measured results (§5.6 — the MiMo Edge numbers of Spec §88, and the list is **not fixed**), and a router whose output is the **selected model id** from the six verbatim inputs (§5.7). No new event names — the four §2.2 model events are all this module publishes.

---

## 1 · Deliverables vs. Plan (مقابل الخطة)

| Plan section | Spec support | Delivered | Location |
|---|---|---|---|
| §5.1 Model Abstraction | §137, §253 | `ModelProvider` ABC with the **seven members verbatim** (`load unload generate stream health capabilities benchmark`) + the NEXUS Model API contracts: `GenerateRequest` (system/prompt/sampling/stop/seed/auto_load), `GenerateResult` (text + prompt/generation token & second accounting + tokens/s properties), `StreamChunk` (deltas, final chunk carries the stats), `ProviderHealth`, `LoadInfo`; error hierarchy `ProviderError` → `ModelNotLoadedError` / `UnsupportedModelError` | `nexus/models/provider.py` |
| §5.2 Model Registry | §134, §253 | `Model` dataclass with the **twelve fields verbatim** (`id name format backend size context capabilities ram vram language benchmark status`; RAM/VRAM in MB, size in bytes) + two documented auxiliary fields (`path`, bounded `benchmark_history`); `ModelRegistry` — register/unregister/upsert/mark_status/attach_benchmark, atomic persistence (`models.registry.json` under `NexusPaths.models`, temp + `os.replace` + `fsync`, envelope `nexus.models.registry` v1); `ModelStatus` lifecycle (registered → benchmarked → loaded/unloaded · error · unavailable); **the pool is never fixed** — register and drop freely | `nexus/models/registry.py` |
| §5.3 llama.cpp Integration | §93, §137, §253 | `LlamaCppProvider` — the Adapter over **ggml-org/llama.cpp** `llama-server`: `build_server_args` (`-m -c --host --port -ngl -t` + `-ctk/-ctv` KV-Q4 from the §88 device learnings + explicit `extra_args`), `LlamaServerProcess` (Popen with Windows `CREATE_NO_WINDOW`, free-port pick, `/health` ready-poll with process-death detection, terminate→wait→kill on stop), stdlib HTTP via urllib (`/completion` JSON + SSE `data:` streaming), `encode_completion_request` / `parse_completion_response` / `parse_sse_event` pure functions, binary resolution with a clear error when llama.cpp is absent (the core still imports and boots without it). **The chain literal: NEXUS Model API → llama.cpp Adapter → llama-server → Model** | `nexus/models/llamacpp.py` |
| §5.4 Dynamic Loading | §87, §91, §92 | `ModelManager` — the five verbs: `select` (§5.7 router with live budgets) · `load` (**predictive budget gate** → LRU idle eviction → provider load → allocation → events; refusal only when hosting is impossible, one task never crashes the machine) · `run` (`generate`/`stream`, auto-load on request) · `keep_warm` (per-model TTL + `unload_idle`) · `unload` (provider release + allocation release + event). `apply_pressure` reacts to the §4.5/§92 ladder (unload idlest / free LRU for the switch); `shutdown` releases everything. Publishes **only** `model.loading`, `model.loaded`, `model.unloaded`, `model.error` | `nexus/models/manager.py` |
| §5.5 Model Benchmarking | §135 | `ModelBenchmark` with the **seven fields verbatim** (`warmup prompt_speed generation_speed context ram vram stability`) + provenance (source `measured`/`mimo_edge`, device, timestamp, notes); `run_benchmark` executes the **Spec §135 order verbatim**: Load → Warm-up → Prompt benchmark → Generation benchmark → Context benchmark → Memory usage (RAM/VRAM sampler) → Stability (repeats) → *Register profile* (persisted via the registry); the manager wraps it in the §5.4 discipline (budget-checked load → run → release) | `nexus/models/benchmark.py` |
| §5.6 MiMo Edge Profile | §88 | `mimo_edge_pool()` — the five models verbatim (`Qwen2.5-Coder-1.5B LFM2.5-1.2B Qwen3-0.6B DS-Coder-1.3B Yi-Coder-1.5B`) carrying the **user's measured results** as the initial baseline (9.57 · 7.54 · 11.66 · 29.14 tok/s @ ctx 8192; Yi honestly awaits its run — no number invented); §88 device learnings kept as benchmark notes (KV-Q4 ≈ 4× KV reduction on Qwen3-0.6B · GPU offload on DS-Coder · Flash-Attention unsuitable for the AVX-only host — hence off by default); `seed_mimo_edge_pool` idempotent, never overrides newer benchmarks, never blocks unregister — **«لا تجعل هذه القائمة ثابتة»** | `nexus/models/mimo.py` |
| §5.7 Model Router | §136, §178, §87 | `RoutingRequest` with the **six inputs verbatim** (task type · complexity · required capability · RAM · VRAM · current workload) → `RoutingDecision.selected_model_id` (**the output literal**). Spec §87 filters first (capability / RAM·VRAM fit / context / blocked statuses), then the **Spec §178 score verbatim**: task fit + capabilities + RAM + VRAM + latency + context + observed reliability (+ warm bonus under workload); complexity blends depth-over-cheapness; §136 examples proven (delete file → fast tiny · chat → small general · coding → coder · large project → long-context candidate · vision/speech → honest `None` with reason — nothing is invented) | `nexus/models/router.py` |
| Reference provider | — | `SimulatedProvider` — deterministic in-process backend: the whole §5 stack (router, budgets, benchmarks, events) runs CI-green without llama.cpp; speed math tokens ÷ tok/s; full call log for the §135 order audit | `nexus/models/simulated.py` |
| Integration | Plan §5 | `NexusRuntime.boot(model_provider=…)` wires the ModelManager (default: the llama.cpp adapter from the §2.1 config; **llama-server only starts on an explicit load** — boot never spawns anything); first boot seeds the §5.6 pool once; shutdown unloads every resident model before closing; payload `phase: 4`; config gains the additive §5 keys (`llama_server` · `llama_host` · `llama_port` · `keep_warm_seconds`) with defaults — the six-section §2.1 tree stays backward compatible | `nexus/core/config/runtime.py`, `nexus/core/config/schema.py` |

## 2 · Exit criteria proof (إثبات معايير الخروج) — `tests/phase04/verify_exit_criteria.py`

**106/106 checks passed (0 failed), exit code 0.** Sections:

| Section | Scope | Checks |
|---|---|---|
| A — Model Abstraction | §5.1 | **12** |
| B — Model Registry | §5.2 | **17** |
| C — llama.cpp Integration | §5.3 | **16** |
| D — Dynamic Loading | §5.4 | **22** |
| E — Model Benchmarking | §5.5 | **8** |
| F — MiMo Edge · Router · integration | §5.6–§5.7 | **31** |
| **Total** | | **106** |

Key proofs: the seven §5.1 members == the ABC's abstractmethods; the twelve §5.2 and seven §5.5 field lists match the plan verbatim; argv/JSON/SSE pure-function round trips; the **full fake-server chain** (adapter spawns llama-server with `-m <path>` → POST `/completion` → SSE stream → `/health` → stop on unload); missing binary → clear `ProviderError`; the manager source **never imports the adapter** (backend independence, Spec §93/§137); the §5.4 cycle with events in order (`model.loading` → `model.loaded` → … → `model.unloaded`); over-budget load refuses and marks `error` without allocating; LRU eviction frees exactly enough; TTL expiry; §92 `unload_model`/`switch_model` reactions; shutdown releases everything; the Spec §135 order audited from the provider's call log; benchmarks persist and survive reload; the §88 numbers carried to two decimals; Yi honest-None; §136 routing examples; VRAM filtering; warm-bonus; complexity shifts the ranking; runtime wiring across **two boots** (seed once, no re-seed, custom model survives); phase-4 payload; config keys; event-name guard (all published ⊆ the 28); Phases 1–3 re-run inside §F: **98/98 · 143/143 · 104/104**.

## 3 · Quality gates (بوابات الجودة)

- `ruff check nexus tests` — **All checks passed**
- `pyright` (standard, 3.11) — **0 errors, 0 warnings, 0 informations**
- `tests/phase01` — **98/98** · `tests/phase02` — **143/143** · `tests/phase03` — **104/104** (regressions, also re-run inside §F)
- `tests/phase04` — **106/106**

## 4 · Documented design decisions (قرارات موثقة)

1. **No new event names.** The module publishes exactly the four §2.2 model events (`model.loading`, `model.loaded`, `model.unloaded`, `model.error`); the 28-event registry stays the single authority. Guarded by a §D/§F check.
2. **Manager-independent of the backend (Spec §93/§137).** `ModelManager` accepts any `ModelProvider` and never imports `llamacpp`; the harness proves it from the source itself. Swapping the runtime later = one new adapter.
3. **Nothing spawns at boot.** The registry seeds and loads; llama-server starts only on an explicit `load()`. A missing llama.cpp binary fails that load with a clear error — never the boot, never the import.
4. **Predictive budget gate (§5.4 «بحسب الموارد»).** Phase 3 semantics: `ResourceManager.load_model` never denies (over-allocation → pressure). The §5.4 gate therefore checks the RAM/VRAM budgets **before** allocating, evicts keep-warm idlers LRU-first, and refuses the load only when the model still cannot be hosted — one task never crashes the machine (Spec §91), and refusal happens at load time (the router re-selects a smaller model — the Spec §92 switch), never mid-task.
5. **§5.2 fields verbatim + two documented auxiliary fields.** `path` (the local GGUF file) and `benchmark_history` (bounded at 8) are infrastructure, not plan fields; both flagged in the docstring and in this report.
6. **Spec §88 numbers are the user's device, nothing else.** Seeded benchmarks carry `source="mimo_edge"` + the device tag; sizes/RAM are documented estimates pending the on-device §5.5 run; Yi-Coder-1.5B carries **no** invented number. Flash Attention stays off (AVX-only host learning); KV-Q4 flags exist because the user measured their value.
7. **Unbenchmarked never outranks measured (Spec §135's «بدل التخمين»).** The router's unknown-latency default (0.35) sits below every measured model of the §88 pool; measured 7.5 tok/s beats the unknown.
8. **Complexity is a real §5.7 input.** It blends the §178 weights — rising complexity leans toward depth (context, capability richness) and away from cheapness (latency, RAM headroom). Proven by the harness: the long-context pick changes between complexity 0 and 1.
9. **Honest `None`.** A vision or speech request with no such model in the pool returns no selection plus the reason — inventing a winner would defeat the routing contract.
10. **`long_context` is quantitative, not qualitative.** The §136 «long-context candidate» is any pool model whose context covers the need (token filter + score), not a capability tag — the first pool has 8K models and the router selects them.
11. **Benchmark loads honor the §5.4 discipline.** `manager.benchmark()` loads through the budget gate (evicting idlers if needed), runs the §135 protocol, then releases — the measurement itself never violates the resource rules it measures for.
12. **The config tree grows additively.** Four new `models` keys with defaults (`llama_server`, `llama_host`, `llama_port`, `keep_warm_seconds`); the §2.1 six-section structure and all Phase-1 checks remain intact (98/98 regression proves it).
13. **Port choice is the OS's.** Each llama-server gets a free port from the kernel (bind-0 probe); the tiny race window is acceptable for a localhost inference server and documented.
14. **`run` = `generate` + `stream`.** The §5.4 verb list is served by the two API methods; the harness checks both.

## 5 · Inventory (الجرد)

- **Package** — `nexus/models/`: `provider.py` (§5.1 abstraction + contracts) · `registry.py` (§5.2) · `benchmark.py` (§5.5) · `router.py` (§5.7) · `llamacpp.py` (§5.3 adapter) · `manager.py` (§5.4) · `mimo.py` (§5.6) · `simulated.py` (reference backend) · `__init__.py`
- **Modified** — `nexus/core/config/schema.py` (ModelsConfig + 4 additive keys + validators) · `nexus/core/config/runtime.py` (ModelManager wiring, `model_provider` injection, phase 4 payload, shutdown unload) · `nexus/__init__.py` (0.4.0, NEXUS_PHASE=4) · `tests/phase03/verify_exit_criteria.py` (phase-payload check forward-compatible `≥ 3`) · `pyproject.toml` (0.4.0) · `nexus/README.md` (ownership map row)
- **Removed** — `nexus/models/.gitkeep` (the module now carries real files)
- **Tests** — `tests/phase04/verify_exit_criteria.py` (A–F, 106 checks, runs Phases 1–3 as subprocesses)
- **Docs** — README roadmap & structure, CHANGELOG, `config/models/models.toml` example, this report

## 6 · Reproduce (إعادة الإثبات)

```bash
python tests/phase04/verify_exit_criteria.py     # 106/106 + 98/98 + 143/143 + 104/104, exit code 0
python tests/phase01/verify_exit_criteria.py     # 98/98
python tests/phase02/verify_exit_criteria.py     # 143/143
python tests/phase03/verify_exit_criteria.py     # 104/104
ruff check nexus tests && pyright                # clean
```

On the Windows machine with llama.cpp installed and a GGUF pool under `M:\NEXUS\models\`, the same §5.4 lifecycle runs against the real backend:

```bash
python -c "from nexus.core.config import NexusRuntime as R; rt=R.boot(r'M:\NEXUS');
m=rt.model_manager; m.load('qwen3-0.6b');
print(m.generate(__import__('nexus.models',fromlist=['GenerateRequest']).GenerateRequest(model_id='qwen3-0.6b',prompt='hello',max_tokens=32)).text)"
```

---

**Status: PHASE 4 — Implemented + Integrated + Tested + Verified + Documented. Next: PHASE 5 — Agent Runtime (Plan §6).**
