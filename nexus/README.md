# NEXUS Platform — Code Skeleton · هيكل كود المنصة

<div dir="rtl">

هيكل الوحدات الـ28 (خطة البناء §1.3) وربطها بالمكونات الـ24 المملوكة لـNEXUS (§0.5).
هذه الوحدات **ملك NEXUS بالكامل** — لا تُفوَّض لأي مستودع خارجي. المحركات الخارجية تدخل خلف adapters فقط.

</div>

28 modules per the Final Build Plan §1.3, mapped to the 24 NEXUS-owned components (§0.5).
These stay **wholly NEXUS-owned**; external engines only ever enter behind adapters.

| Module | Owned component(s) · المكوّن المملوك | Role |
|---|---|---|
| `core/` | NEXUS APIs · Task system · Task state | Configuration, session system, task engine & persistence — **✅ implemented (Phase 1, Plan §2)** · workspace/scope/policy core — **✅ implemented (Phase 2, Plan §3)** |
| `orchestration/` | Master Agent | Delegation, coordination, multi-agent orchestration — core loop foundation **✅ (Phase 5 §6.2–§6.3: `nexus.agents.loop` · `nexus.agents.master`)** |
| `harness/` | Agent Harness | The §41 layer (context/tools/memory/task state/rules/skills/observations → action/tool_call/delegation/decision) — ECC skills+rules+hooks · Cline session lifecycle · LangGraph checkpoints · Prime goals+heartbeats, all NEXUS-owned **✅ (Phase 6 §7.1–§7.5: `nexus.harness`)** |
| `agents/` | Agent Registry | Agent abstraction, runtime loop, contracts — **✅ implemented (Phase 5, Plan §6)**: §6.1 Agent (8 fields) · §6.2 loop (7 traced phases + strict decision contract + ToolSink seam) · §6.3 Master Agent (7 behaviors over the §2.4 machine) · §6.4 registry (4 verbs, atomic) · §6.5 messages (8 fields + transcript) · §6.6 ownership (resource→owner, conflicts become coordination) |
| `tools/` | Tool Registry · Tool Router | Unified tool layer, permissions, normalization — **✅ implemented (Phase 7, Plan §8)**: §8.1 registry (nine validated fields, upgrade-only, freezable) · §8.2 router (the verbatim 7-stage pipeline with proof traces: discovery→permission→scope→resource→execute→normalize→verify) · §8.3 nine native tools (filesystem · terminal · process · hardware · windows · clipboard · screen · git · github — stdlib, platform-honest) · §8.4/§8.5 MCP interop (official SDK v2 `[mcp]` extra behind the router; five audited servers behind NEXUS permission+scope) |
| `computer/` | Window Manager · Input Arbitration | **✅ implemented (Phase 8, Plan §9)**: §9.1 Computer API (eight domains, thin router clients) · §9.5 fallback hierarchy (Application API → UIA → DOM/a11y → Vision → Mouse/Keyboard, every attempt traced) · §9.4 native UIA client (ctypes COM) · §9.2 transports (foreground SendInput + message WM_CHAR, ADAPTed from windows-harness) · §9.3 pywinauto behind `[computer]` extra (MODE A, lazy) |
| `browser/` | Browser Runtime | **✅ implemented (Phase 10, Plan §11)**: §11.1 the Playwright engine (MODE A `[browser]` extra, channel ladder chromium→chrome→msedge) · §11.4 user/agent sessions isolated by construction behind the explicit §55 CDP gate · §11.5 the DPAPI vault — secrets never cross the tool interface (vault references, path/env storage, output scrubbing) · §11.3 self-healing selector ladder · the §9.5 dom_a11y rung · the façade over the §8.2 router (the 13th record) |
| `vision/` | Vision · OCR · Screen Understanding | **✅ implemented (Phase 11, Plan §12)**: §12.1 Screen Capture (full · window · region — GDI `PrintWindow(PW_RENDERFULLCONTENT)` + DWM extended-frame bounds in pure ctypes, one stdlib PNG encoder) · §12.2 the VisionProvider (analyze · locate · classify · compare) over the Phase 4 Model Runtime (`GenerateRequest.images` → llama-server base64 `image_data`, the §5.1 contract additive) · §12.5 the OCR candidates (winrt → tesseract → model, all honestly probeable) + the CER metric + the **device benchmark that decides** (GDI-drawn corpus, English · numbers · UI labels · documents) · the §9.5 chain's **vision rung** (locate by description → real input) · the 14th §8.1 record behind the router · UI-TARS/OpenCUA/Agent-S = Repository Round 8 REFERENCE/RESEARCH (never the runtime) |
| `models/` | Model Manager | ModelProvider abstraction, registry, router, benchmarks — **✅ implemented (Phase 4, Plan §5)**: §5.1 interface (7 members) · §5.2 registry (13 fields) · §5.3 llama.cpp adapter → llama-server · §5.4 dynamic loading per resources · §5.5 benchmark protocol (§135) · §5.6 MiMo Edge first pool · §5.7 router (§178) |
| `memory/` | Memory Manager | Hierarchy, retrieval, compaction (SQLite/Qdrant/Mem0 adapters) |
| `learning/` | Learning Engine | Lessons, skills creation, confidence, optimization |
| `verification/` | Verification Engine | Evidence-based acceptance, per-domain verifiers |
| `recovery/` | Recovery Engine · Checkpoint Manager | Checkpoints, reconciliation, stall detection |
| `workspace/` | Workspace | Workspace objects, isolation, cross-workspace reads — core registry foundation **✅ (Phase 2 §3.1: `nexus.core.workspace`)** |
| `windows/` | Window Manager · Human Parallelism | **✅ implemented (Phase 9, Plan §10)**: §10.1 the nine-field Window Registry (and the first real publisher of the canonical `window.opened`/`window.closed` events) · §10.2 USER/NEXUS/SHARED ownership (rules + explicit claims, safe USER default) · §10.3 per-window input arbitration as a `pre_tool_call` veto · §10.4 monitor topology + window placement (pure math + routed effects) · §10.5 the native ctypes overlay ("NEXUS is working" · Pause · Resume) · the `WindowManager` composer over the §9.1 Computer API |
| `git/` `github/` | — (capability layer) | Git engine + GitHub engine behind adapters |
| `research/` | — (capability layer) | Search pipelines, external AI consultation |
| `documents/` | — (capability layer) | Word/PPTX/PDF via Docling adapters |
| `speech/` `vision/` | — (capability layer) | sherpa-onnx STT · OCR/screen understanding |
| `plugins/` | Plugin System | Manifest, lifecycle, permissions |
| `skills/` | Skill System | Skill schema, verification, registration |
| `events/` | Event Bus | Central events, schemas, subscriptions — **✅ implemented (Phase 1, Plan §2)** |
| `resources/` | Resource Manager | CPU/RAM/VRAM budgets, pressure policies — **✅ implemented (Phase 3 §4.1–§4.5: hardware scanner · profile · change detection · 8 tracked resources · §92 degradation ladder)** |
| `security/` | Scope · Permissions | 3-layer gate, credential vault, redaction — core scope+policy foundation **✅ (Phase 2 §3.2–§3.5: `nexus.core.scope` · `nexus.core.policy`)** |
| `remote/` | Remote API | Remote protocol, sessions, file transfer |
| `ui/` | Desktop UI | Main window, activity, tray, overlay |
| `tests/` | — | Internal + fault-injection suites |
| `docs/` | — | Module-level documentation |
