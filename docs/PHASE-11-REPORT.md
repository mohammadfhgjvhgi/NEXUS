# PHASE 11 REPORT — Vision + OCR + Screen Understanding (Build Plan §12 / Spec §64–§65)

> Status: **Complete** · Commit: see `CHANGELOG.md` · Exit criteria: **118/118 + live vision/OCR proofs (local PASS 11/11 on real pixels · CI vision-live job · device benchmark pending the bridge gate)** · CI job: "Phases 1–11" + the vision-live job
>
> الهوية: «إعطاء NEXUS القدرة البصرية التي تحتاجها التطبيقات التي لا
> تقدم UI structure مفيدة» — عيّن فحدّد ثم انقر، والصورة داخل طلب
> النموذج، والتعرّف يُقرّره معيارٌ على الجهاز لا تخمين.

## 1. ما بُني (What landed)

```
nexus/vision/                    ← §12 the Vision Runtime (NEXUS-owned)
├── __init__.py                  exports · VISION_SECTIONS · the record
├── models.py                    the §12 vocabulary (data, not code)
├── capture.py                   §12.1 full · window · region (GDI/DWM/PrintWindow)
├── provider.py                  §12.2 VisionProvider (4 verbs) + pure parsers
├── ocr.py                       §12.5 the engine candidates + CER
├── benchmark.py                 §12.5 the device decision run + winner policy
├── layer.py                     the §9.5 vision rung (4th of 5)
├── api.py                       the façade over the §8.2 router
├── tools.py                     the record registration site
├── provider_state.py            the runtime-injected wiring
└── _winrt_support.py            the Windows.Media.Ocr marshaling (device-only)

nexus/tools/native/vision.py     the fourteenth §8.1 record (risk 1)
nexus/tools/__init__.py          build_tool_system(vision=…)
nexus/core/config/               vision_enabled · vision_ocr_engine (validated)
nexus/core/config/runtime.py     vision_runtime + the rung + provider_state + shutdown
nexus/models/provider.py         GenerateRequest.images (additive, default empty)
nexus/models/llamacpp.py         image_data base64 (llama-server multimodal)

tests/phase11/
├── verify_exit_criteria.py      118/118 (A–F + regressions 1–10, +7 bonus live)
└── live_vision_ci.py            the real-pixels roundtrip (CI + local)
```

### §12.1 Screen Capture — full screen · window · region (verbatim)

One layer, one injectable transport. `Win32Gdi` is pure ctypes:
`BitBlt` for screens/regions, and for **windows**
`PrintWindow(PW_RENDERFULLCONTENT)` — the only reliable way to see
DirectComposition content (Chrome/Edge/Electron) *and occluded
windows* — with the classic BitBlt fallback. Window bounds come
from the **DWM extended frame bounds** (`DwmGetWindowAttribute`) —
`GetWindowRect` lies by the invisible resize shadow on DWM
windows. Region math (clamping, intersection, refusal) is pure and
CI-tested; the PNG encoder is the Phase-7 stdlib one
(`encode_png`) — one encoder, one format, no imaging dependency.
Off win32 the layer refuses honestly; the region *math* still
proves itself anywhere.

### §12.2 Vision Adapter — the four verbs (verbatim)

`VisionProvider` is exactly `analyze · locate · classify ·
compare` (plus the honest `available()` probe the §9.5 chain
demands). The production backend, `ModelVisionProvider`, routes
through the **Phase 4 Model Runtime**: `manager.select` with
`required_capability="vision"` (the §5.7 router picks the pool's
vision model), then `manager.generate` — where the §5.1
`GenerateRequest` gained one **additive optional field**,
`images: Sequence[bytes] = ()`. Empty by default: the Phase-4
text-only contract is byte-for-byte intact, and
`encode_completion_request` emits the exact Phase-4 body until
images ride — then llama-server's documented multimodal
`image_data` (base64) carries them (an mmproj-equipped GGUF is
the device's business, Phase 4's registry tracks the model).

Every model-shaped concern lives in **pure functions**:
`analyze_prompt` · `locate_prompt` · `classify_prompt` ·
`compare_prompt` and the tolerant parsers — `parse_json_block`
survives prose-wrapped answers and markdown fences;
`parse_locate` takes the house JSON bbox dialect, a bare list, or
**the UI-TARS action space** (`click(start_box='(197,525)')` → a
clickable point-box — Repository Round 8's single documented
REFERENCE adoption); `parse_classify` **never invents** a category
outside the given set; `parse_compare` degrades honestly on
prose. Local models are models — the tolerance is the contract.

### §12.3/§12.4 UI-TARS · OpenCUA · Agent-S — REFERENCE/RESEARCH, never the runtime

Repository Round 8 (the full record: `docs/REPOSITORY-INTEGRATION.md`):

| Repository | Pinned | Ruling |
|---|---|---|
| bytedance/UI-TARS | 582f3a7 · Apache-2.0 | **REFERENCE/BENCHMARK** — the plan's own words: «لا تجعله النموذج الأساسي لجهازك الحالي». One documented adoption: the action-space parse tolerance. |
| xlang-ai/OpenCUA | dfc91ba · MIT | **RESEARCH** — studied, shelved; the screenshot→action shape was already the §9.5 chain's design. |
| simular-ai/Agent-S | 3aa272d · Apache-2.0 | **RESEARCH** — a bookmark for Plan §15 (the S3 skill-library indirection). |

Zero imports, zero extras, zero runtime presence — `nexus/vision/`
is 100% NEXUS-owned stdlib. The three clones live in
`vendor-staging` for study, exactly as §12.4 orders («Clone
للاختبار/الدرسة … لا تدخلها كلها إلى production runtime»).

### §12.5 OCR — the benchmark decides, on the device

> اختيار OCR النهائي يجب أن يتم بالـbenchmark على جهازك.

NEXUS ships **candidates and a yardstick, not a decision**:

* `WinrtOcrEngine` — `Windows.Media.Ocr`, the OS-native engine
  (offline, zero models, excellent English/numbers on UI labels;
  lazy `winsdk`/`winrt` projection, honest refusal without it).
* `TesseractOcrEngine` — the classic (`[ocr]` extra:
  pytesseract + Pillow + the binary; honest refusal without).
* `ModelOcrEngine` — the local VLM through the §12.2 provider
  (zero *new* dependencies when a vision model runs).

`character_error_rate` (Levenshtein, case/whitespace-normalized)
is the metric; `benchmark.py` is the decision run: the four §12.5
requirement categories **verbatim** (English · numbers · UI
labels · documents — 16 truths), rendered on the device by **the
OS itself** (GDI `DrawTextW` into the memory DC — pixel-honest
ground truth, no downloaded dataset; Pillow renders on CI so the
machinery proves itself live there). The winner policy is pure
and strict: lowest mean CER, ties break on total seconds, **one
engine alone is no contest**, and a leader above 0.30 CER wins
nothing (an engine that cannot read is not a winner, it is a
survivor). Failures count 1.0 — a crashing engine is bad-engine
data, never an exception. The verdict is plain JSON
(`OcrBenchmarkReport`) ready for `M:\NEXUS\proofs\`.

### The §9.5 chain gains its vision rung (4th of 5)

The seam Phase 8 left open is closed: `VisionLayer` —
`inspect` → the provider's `analyze`; `click`/`invoke` → `locate`
→ the **real mouse click at the located center** through the
router; `type`/`set_value` → locate → click → keyboard `type`.
Availability is honest (win32 capture + provider + runtime, or a
reason); a not-found locate raises `LayerError` so the chain
falls through to raw input — degradation, never silence. The
chain remains a chain of router clients: no second gate.

## 2. التوصيل (Integration)

* **The 14th §8.1 record** (`native:vision`, risk 1 — reading
  pixels and running inference; the only mutation is the capture
  PNG, path-scoped like every screenshot): ops
  `capture · analyze · locate · classify · compare · ocr`;
  verification contracts bind to keys the handler **always**
  emits (`path_size · report · found · category · same · text`)
  — the Phase-10 §8.2 lesson, applied from the first line.
* **Capability is per-op honest**: the probe reports
  capture/inference/ocr availability separately — on Linux CI
  with tesseract the tool is available for `ocr` while `capture`
  refuses at execute *as data* (a platform truth, not a lie at
  discovery).
* `tools.vision_enabled` (default true, additive) +
  `tools.vision_ocr_engine` (`"auto"` | a candidate name,
  validated) — `false` leaves the Phase-10 runtime byte for
  byte (13 records, no rung, no provider state).
* The runtime wires `VisionRuntime` + `VisionLayer` over the
  live `ModelManager`, injects `provider_state` (shutdown unwires
  it — a re-boot injects fresh), and the OCR preference rides
  config to `resolve_ocr_engine`.
* **§5.1 additive**: `GenerateRequest.images` (default `()`,
  `to_dict` counts, never embeds) + llamacpp `image_data` —
  text-only bodies are byte-for-byte the Phase-4 encoding.

## 3. الإثباتات (Evidence)

* **`tests/phase11/verify_exit_criteria.py` — 118/118 (A=20 ·
  B=30 · C=21 · D=9 · E=31 · F=17) + 7 bonus** live on this
  sandbox (the corpus rendered through Pillow, the real
  tesseract race: CER **0.0** on all four categories, the
  §8.2-router ocr roundtrip on real PNG bytes), with Phases
  1–10 re-run green as subprocesses (98 · 143 · 104 · 106 · 116
  · 88 · 88 · 80 · 84 · 70).
* **`tests/phase11/live_vision_ci.py` — PASS 11/11 locally**
  (real renderer → real engine race → real router ocr →
  parser tolerance → honest platform refusal); the CI
  **vision-live** job runs the same on GitHub's runner with
  apt-tesseract.
* **The device decision run** (`nexus.vision.benchmark.main` /
  `live_proof_device.py`) — the §12.5 benchmark **belongs on the
  operator's box** (GDI-drawn corpus, the winrt candidate in the
  race, the model candidate over the live Model Runtime): the
  verdict lands in `M:\NEXUS\proofs\phase11_ocr_benchmark.json`
  and pins `tools.vision_ocr_engine` to the winner. **Status:
  the bridge's trust gate is closed at build time** (Task 55's
  documented R4<R3 quarantine — both tunnels health-ok, execute
  blocked); the deploy script (`tools/deploy_phase11_bearer.py`)
  and the device proof are staged and waiting for the gate —
  the honest state, not a silent skip.

## 4. جولة المستودعات (Round 8)

UI-TARS REFERENCE/BENCHMARK (the plan's explicit ruling — not
the primary model) · OpenCUA RESEARCH · Agent-S RESEARCH (a
bookmark for §15) — pinned clones in `vendor-staging`
(582f3a7 · dfc91ba · 3aa272d), zero imports, full cycle record
in `docs/REPOSITORY-INTEGRATION.md`.

## 5. Bugs the proofs caught (the honest ledger)

* **The discovery stage lied by granularity** (first live run):
  the router's §8.2 discovery gate refused *every* vision op on
  Linux because `capabilities()` folded the whole surface into
  the GDI capture probe — while `ocr` worked fine through
  tesseract. Fix: the capability is **per-family honest**
  (capture / inference / ocr probed separately; any serving
  family makes the tool available, and a refused family fails
  at execute as data). The lesson generalizes the Phase-10 one:
  contracts must match what the handler actually does *per op*,
  not what the platform does *in general*.
* **Phase-4's exact-field assertion** (expected on re-reading):
  the §5.1 GenerateRequest field-set equality needed the same
  forward-tolerant re-expression the Phase-10 "12 records" check
  got — `images` is additive with a default, the contract is
  the *presence* of the nine §5.1 fields. Same for Phase-10's
  13/12 record counts (now ≥13/≥12 floors). The pattern is now
  a house law: **exact-set assertions belong to the phase that
  owns the set; later phases relax them to floors.**

## 6. لماذا العمارة كما هي (Why the architecture is what it is)

* **The provider is an interface, the runtime is the backend** —
  §12.2 asks for the four verbs, and NEXUS already owns a model
  runtime (Phase 4). Extending `GenerateRequest` additively
  keeps one Model API, one router, one budget/keep-warm
  lifecycle — a second vision gate would have been a duplicate
  authority (the §8.2 law, applied at the model layer).
* **The benchmark decides, not the loudest blog post** — the
  §12.5 text is explicit, and the NEXUS-native way to honor it
  is a yardstick (CER), a corpus the OS itself draws, and a
  strict winner policy — *on the device*, where winrt exists
  and the real models run.
* **UI-TARS as REFERENCE is a strength**: the action-space
  tolerance means a future UI-TARS-family model (or any
  GUI-grounded model trained on that dialect) plugs into
  `ModelVisionProvider` with zero NEXUS changes — the reference
  is absorbed as *protocol tolerance*, never as dependency.

---

*The §9.5 chain is now four of five rungs strong
(application API → UIA → DOM/a11y → **vision** → input). The
next seam: Plan §13 — Memory.*
