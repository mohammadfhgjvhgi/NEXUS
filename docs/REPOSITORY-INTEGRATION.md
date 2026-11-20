# NEXUS Repository Integration Record — Round 1

This file is the permanent record of every external repository that
entered NEXUS, following the Final Build Plan §0.2 intake cycle:

```
DISCOVER → CLONE TO STAGING → LICENSE AUDIT → SECURITY REVIEW →
ARCHITECTURE REVIEW → COMPATIBILITY REVIEW → SELECT INTEGRATION MODE →
ADAPTER / EXTRACT / USE → INTEGRATE INTO NEXUS → TEST →
PIN VERSION/COMMIT → DOCUMENT
```

Rule §0.5 holds everywhere below: the integrated pieces never own a
§0.5 component — they sit *under* NEXUS interfaces.

---

## 1. ggml-org/llama.cpp — MODE B (ADAPT)

| Field | Value |
|---|---|
| Role | Primary local inference backend (Plan §5.3) |
| Pinned release | **b10829** (published 2026-09-06) |
| Pinned commit | **5fdfa6282936576d2f352d4b97f397a109f207a6** |
| License | MIT — «Copyright (c) 2023-2026 The ggml authors» |
| Staging clone | `vendor-staging/llama.cpp/` (gitignored, 210 MB shallow) |
| NEXUS entry point | `nexus/models/llamacpp.py` (the adapter) |

### 1.1 Cycle record

* **DISCOVER** — the Build Plan names it explicitly (§5.3: «Repository:
  ggml-org/llama.cpp»).
* **CLONE** — shallow clone of tag `b10829` to `vendor-staging/llama.cpp`.
* **LICENSE AUDIT** — MIT (permissive, commercial use OK, attribution
  required). The adapter embeds the attribution in its module docstring
  and this record; no llama.cpp source is redistributed inside NEXUS
  (we spawn the user-installed binary, we never copy its code).
* **SECURITY REVIEW** — execution boundary: llama-server runs as a
  localhost-only child process (`--host 127.0.0.1`), one process per
  loaded model, terminated on unload (`terminate → wait → kill`).
  No dynamic code loading from the repo; the binary comes from the
  project's official GitHub release artifacts (ubuntu-x64 used for the
  live proof; win-cpu / win-vulkan / win-cuda assets exist for the
  user's Windows box).
* **ARCHITECTURE REVIEW** — server + HTTP contract (llama-server, SSE
  streaming) rather than library linkage: exactly the §0.4 shape
  `NEXUS Model API → Adapter → llama-server`. The Model Manager
  imports nothing from llama.cpp (Spec §93 proven in Phase 4).
* **COMPATIBILITY REVIEW (live, 2026-09-07)** — the wire contract was
  probed against the real binary *before* trusting the adapter:
  * `GET /health` → `{"status":"ok"}` when ready;
  * `POST /completion` → `{"content": …, "timings": {"prompt_n",
    "prompt_ms", "predicted_n", "predicted_ms", …}, "stop": true, …}`;
  * `POST /completion` (stream) → `data: {json}` SSE token deltas
    whose final event carries `"stop": true` and **empty** `content`
    (the text lives in the accumulated deltas — the Phase 4 fake
    server modeled this exactly);
  * argv: `-m <gguf> -c <ctx> --host H --port P -ngl N [-t T]
    [-ctk q -ctv q]` — all flags accepted as the adapter builds them.
* **SELECT INTEGRATION MODE** — **B (ADAPT)**: NEXUS never imports
  llama.cpp internals; `LlamaCppProvider` + `LlamaServerProcess` are
  the only files that know the binary exists.
* **ADAPTER / INTEGRATE / TEST** — see §1.2.
* **PIN** — release `b10829`, commit `5fdfa628…` (both the audited
  clone and the live-proof binary report exactly this build).
* **DOCUMENT** — this record + `CHANGELOG.md` + the module docstrings.

### 1.2 The live proof (and what it caught)

`tests/phase04/integration_llama_server.py` — opt-in (needs the binary
+ a GGUF; CI keeps running the fake-server chain). Result on the dev
sandbox (2 CPU cores):

```
integration: 26/26 checks passed
§5.5 profile — prompt 147.5 tok/s · generation 29.7 tok/s
               · ram 1588MB (real RSS) · stability 1.0
manager record: 1588MB REAL vs 700MB registry estimate (§135)
```

The proof caught one real defect the 106/106 fake-server suite could
never see: **the port disagreement bug**. `load()` built the argv with
`--port 0` while `LlamaServerProcess` polled a different self-chosen
port — the real server bound an unknowable ephemeral port and the
adapter would wait forever ("alive but unreachable"). Fixed by
`_resolve_port()`: an explicit `--port > 0` in the argv wins; otherwise
the chosen free port is written back INTO the argv so the server binds
exactly the port we poll. (Fake servers ignore ports — which is why
only the live proof could catch it. Lesson recorded for Phase 5+.)

### 1.3 Deployment path (the user's Windows box)

Official release assets for `b10829` (same pinned commit):

* `llama-b10829-bin-win-cpu-x64.zip` — CPU (AVX-only host, §88);
* `llama-b10829-bin-win-vulkan-x64.zip` — any-GPU via Vulkan;
* `llama-b10829-bin-win-cuda-12.4-x64.zip` / `-cuda-13.3-` — NVIDIA.

`config/models/models.toml → models.llama_server` points at the
extracted `llama-server.exe`; the adapter spawns it with
`CREATE_NO_WINDOW`.

---

## 2. Qwen/Qwen3-0.6B-GGUF — first-pool model artifact

| Field | Value |
|---|---|
| Role | The live-proof GGUF (also a §5.6 first-pool member) |
| File | `Qwen3-0.6B-Q8_0.gguf` — 639,446,688 bytes |
| License | Apache-2.0 (Qwen model card) |
| Location | `models/` (gitignored — downloaded per install, §1.2 layout) |

Not a code dependency: a *model artifact*. Recorded here because the
same §0.2 discipline applies to anything entering the runtime —
license checked, size verified, GGUF magic validated, and it flows
through the Model Registry like every future model.

---

## 3. giampaolo/psutil — MODE A (DIRECT USE)

| Field | Value |
|---|---|
| Role | Cross-platform system-observation gaps (Plan §4.6 «system information libraries») |
| Pinned release | **7.2.2** |
| Pinned commit | **9eea97dd6f1d16ea33f5144c8925f1ce7a0688e1** |
| License | BSD 3-Clause («Jay Loden, Dave Daeschler, Giampaolo Rodola») |
| Staging clone | `vendor-staging/psutil/` (gitignored, 6.4 MB shallow) |
| Install path | optional dependency `nexus-core[hardware]` (pinned `>=7.2,<8`) |

### 3.1 Cycle record

* **DISCOVER** — Plan §4.6 lists «system information libraries» as the
  sanctioned Phase 3 helper class; psutil is the field standard.
* **CLONE** — shallow clone of tag `release-7.2.2`.
* **LICENSE AUDIT** — BSD 3-Clause: permissive, compatible, attribution
  in this record and the import sites.
* **SECURITY REVIEW** — pure observation library (no exec, no network);
  C extension with a long maintenance history; imported lazily so a
  compromised/absent install can never break core import paths.
* **ARCHITECTURE REVIEW** — library, no process model, no state — a
  textbook MODE A. §0.4 is honored by *where* it is used: behind
  NEXUS-owned functions only.
* **COMPATIBILITY REVIEW** — live on the dev sandbox (7.2.2, py3.12):
  `Process(pid).memory_info().rss` measured the real llama-server
  footprint (1578–1588 MB across loads) — the number the Model Manager
  now writes into its §5.4 records.
* **MODE A (DIRECT USE)** — pip dependency behind three NEXUS-owned
  functions, each degrading to the stdlib floor when psutil is absent
  (CI runs without it — 104/104 and 106/106 stay green):
  * `nexus/resources/samplers.py::process_rss_mb` — self RSS,
    cross-platform (Windows previously returned `None`);
  * `nexus/models/llamacpp.py::resident_memory_mb` — the spawned
    llama-server's RSS (duck-typed: fakes without `pid` → honest
    `None`, never invented numbers);
  * `nexus/resources/scanner.py::_psutil_max_clock_mhz` — POSIX CPU
    max frequency (previously always `None`).
* **INTEGRATE / TEST** — the §5.4 load path now *corrects* the
  predictive registry estimate with the observed RSS (Spec §135
  «نتائج الجهاز الحقيقي بدل التخمين»): budget gate still runs on the
  estimate (§91/§92), the LoadedModel record and ResourceManager
  accounting carry the real number. Proven live (26/26) and in
  regression (98/143/104/106 all green).
* **PIN** — 7.2.2 / `9eea97d…`, `pyproject.toml` constraint
  `psutil>=7.2,<8`.

### 3.2 Windows-only companions (documented, deferred)

`pyproject.toml [project.optional-dependencies].windows` pins the
Plan §4.6 set with platform markers (installable/testable only on the
user's box — Linux CI must never need them):

* `pywin32` (PSF license) — COM/registry access beyond ctypes;
* `wmi` (MIT) — CIM queries beyond the PowerShell bridge;
* `pynvml` (MIT) — NVIDIA VRAM observation for §4.4/§5.5.

These enter through the same NEXUS-owned seams when the Windows box
runs Phase 3+ for real.

---

## 4. Deferred / reference-only (MODE D watchlist)

Nothing cloned yet under MODE D. Candidates for upcoming phases (to
pass the same cycle before any use):

* Phase 5 Agent Runtime — no external agent framework will own the
  Master Agent (§0.5); anything cloned will be reference-only.
* Phase 10 Browser Runtime, Phase 11 Vision/OCR, Phase 15 Git tooling —
  evaluate when the phase starts.

## 5. Verdict

| Repository | Mode | Pinned | Live proof | Regression |
|---|---|---|---|---|
| ggml-org/llama.cpp | B (ADAPT) | b10829 / 5fdfa628 | 26/26 | 106/106 (fake chain) |
| Qwen3-0.6B-GGUF | artifact | Q8_0 639 MB | in the 26 | registry flows |
| giampaolo/psutil | A (DIRECT) | 7.2.2 / 9eea97d | RSS 1588MB | 104/104 + 106/106 |

The «لا تعِد كتابة قدرات موجودة بكفاءة في المشاريع المفتوحة المصدر»
principle now has teeth: NEXUS owns the architecture (§0.5 list
untouched) and reuses battle-tested engines under adapters (§0.4) —
with the pins, proofs and audit trail to keep it that way.

---

# NEXUS Repository Integration Record — Round 2 (Phase 5 · Agent Runtime)

Round 2 serves **PHASE 5 — Agent Runtime** (Build Plan §6). The
governing decision was written *before* this phase started (see §4 of
the Round-1 record above): **no external agent framework will own the
Master Agent or the Agent Registry (§0.5) — anything cloned for
Phase 5 is reference-only (MODE D)**. The user's directive for this
round — «راجع المهام السابقة… وسحب المستودعات» — was answered by
the audit below, then executed: three clones, three full §0.2 cycles,
zero imports from their code.

## 0. The audit that opened Round 2

| Phase | Named / needed repository | Mode | Status after Round 1 |
|---|---|---|---|
| 0–2 | none named (stdlib-only by design) | — | nothing to pull |
| 3 | «system information libraries» → psutil | A | ✅ pulled, pinned 7.2.2 |
| 4 | ggml-org/llama.cpp (§5.3 names it) | B | ✅ pulled, pinned b10829 |
| 5 | no repo named in §6; the master spec names the references for exactly this layer: **LangGraph** (§44, §3674 «Orchestration | LangGraph | USE/ADAPT», §7418) and **AutoGen** (§5507), and the plan names **deepagents** (§7.6) with §7210: «نستفيد من Cline/ECC/LangGraph/Prime/Deep Agents كمرجعيات ومكونات عبر adapters» | **D** | ➜ this round |
| 6+ | affaan-m/ecc, cline/cline, PrimeIntellect-ai/prime-agent, MCP SDK, browser/vision/memory repos… | D/E later | watchlist — pull when the phase starts |

Verdict: the three Phase-5 references are **langchain-ai/langgraph**,
**microsoft/autogen** and **langchain-ai/deepagents** — each a mature,
trusted, actively-maintained project covering exactly one §6 concern
(loop shape · registry semantics · delegation flow). All entered as
**MODE D (REFERENCE)**: studied in staging, patterns applied to
NEXUS-owned code, nothing imported.

## 1. langchain-ai/langgraph — MODE D (REFERENCE)

| Field | Value |
|---|---|
| Role | The §6.2 loop-shape reference (Spec §44: «stateful orchestration وlong-running workflows… persistence/checkpoint concepts قوية») |
| Pinned release | **1.2.11** |
| Pinned commit | **644815f9e5bc52ad8f7a5227a456227e9c3e639b** |
| License | MIT — «Copyright (c) 2024 LangChain, Inc.» |
| Staging clone | `vendor-staging/langgraph/` (gitignored, 19 MB shallow) |
| NEXUS landing | `nexus/agents/loop.py` (pattern only) |

### 1.1 Cycle record

* **DISCOVER** — Spec §44 names LangGraph for stateful orchestration;
  §3674 maps it USE/ADAPT; §7418 repeats it as the 2026 reference.
* **CLONE** — shallow clone of tag `1.2.11`.
* **LICENSE AUDIT** — MIT (permissive; no NEXUS redistribution of
  their code happens at all in MODE D, and the attribution lives in
  this record + the module docstring of `nexus/agents/loop.py`).
* **SECURITY REVIEW** — reference-only: nothing executes, nothing is
  imported; the clone sits in gitignored staging for study.
* **ARCHITECTURE REVIEW** — studied
  `libs/langgraph/langgraph/pregel/_loop.py` / `_algo.py` /
  `_checkpoint.py`: their engine is a Pregel-style superstep loop
  (tick → route → execute → join) with interrupt/continue edges and
  checkpointed state. The NEXUS-relevant patterns: **(a)** an
  explicit, inspectable loop object (their `PregelLoop` context
  manager) rather than a buried `while`; **(b)** continuation decided
  by a *routing function on the state*, not by exceptions; **(c)** a
  verify/interrupt gate that can send the run back for one more step.
* **COMPATIBILITY REVIEW** — LangGraph is async-first, Pydantic-heavy
  and would drag the whole LangChain runtime into the Core — the
  exact dependency the Plan §2 goal forbids. Rejected for any deeper
  mode; the *shapes* port cleanly to stdlib dataclasses.
* **SELECT INTEGRATION MODE** — **D (REFERENCE)**.
* **WHAT NEXUS TOOK** — the §6.2 `AgentLoop` is an explicit,
  step-recorded cycle (`LOOP_PHASES` + `LoopStep` audit trail) whose
  CONTINUE decision is a returned value from the verify gate (never
  an exception), and whose done-gate can send the run back for a
  bounded repair — the langgraph interrupt/continue discipline in
  NEXUS-owned, stdlib-only form. Zero lines of their code.
* **PIN** — 1.2.11 / `644815f…`.
* **DOCUMENT** — this record + `nexus/agents/loop.py` docstring +
  `CHANGELOG.md` (Phase 5 section).

## 2. microsoft/autogen — MODE D (REFERENCE)

| Field | Value |
|---|---|
| Role | The §6.4 registry + §6.5 messaging semantics reference (Spec §5507) |
| Pinned release | **v0.4.4** (python packages line) |
| Pinned commit | **bd5a24ba72ba01c4ec7509f027caaa7454b5f6d0** |
| License | **MIT for code** (`autogen/LICENSE-CODE`, «Copyright (c) Microsoft Corporation») · CC-BY-4.0 for docs (`autogen/LICENSE`) |
| Staging clone | `vendor-staging/autogen/` (gitignored, 70 MB shallow) |
| NEXUS landing | `nexus/agents/registry.py` + `nexus/agents/messages.py` (patterns only) |

### 2.1 Cycle record

* **DISCOVER** — Spec §5507 names AutoGen as the multi-agent runtime
  reference.
* **CLONE** — shallow clone of tag `v0.4.4`.
* **LICENSE AUDIT** — code MIT (the LICENSE-CODE file governs the
  python packages we studied); docs CC-BY-4.0. MODE D copies nothing,
  so only attribution obligations remain — recorded here.
* **SECURITY REVIEW** — reference-only (gitignored staging, no
  import, no execution).
* **ARCHITECTURE REVIEW** — studied
  `python/packages/autogen-core/src/autogen_core/` (`_agent_id.py`,
  `_agent_type.py`, `_agent_runtime.py`, `_closure_agent.py`,
  `_default_subscription.py`, `_cancellation_token.py`) and
  `autogen-agentchat/…/conditions/` + `messages.py` + `teams/`:
  their runtime registers agent *types* with factories, routes
  messages by topic subscriptions (an agent becomes reachable by
  subscribing a closure over its id), treats termination as
  first-class *conditions* composed into policies, and keeps message
  envelopes header-light with the payload structured.
* **COMPATIBILITY REVIEW** — autogen-core requires an async event
  loop, its own serialization layer and its runtime process model —
  heavier than the single-threaded Phase-1 engine design. Their
  *registry semantics* and *message routing* port cleanly.
* **SELECT INTEGRATION MODE** — **D (REFERENCE)**.
* **WHAT NEXUS TOOK** — the four §6.4 verbs with an open roster and
  discover-by-role/capability (their register/subscribe semantics,
  NEXUS-shaped); the §6.5 envelope with a closed type vocabulary and
  a delivery lifecycle routed to per-agent mailboxes (their
  topic-subscription idea, distilled); bounded termination as an
  explicit policy (their `conditions/`) — visible as
  `VerificationPolicy.max_repairs` and `AgentsConfig.loop_max_turns`.
  Zero lines of their code.
* **PIN** — v0.4.4 / `bd5a24b…`.
* **DOCUMENT** — this record + the two module docstrings +
  `CHANGELOG.md`.

## 3. langchain-ai/deepagents — MODE D (REFERENCE)

| Field | Value |
|---|---|
| Role | The §6.3 Master-Agent delegation reference (Plan §7.6 names it; §7210 lists it among the reference components) |
| Pinned release | **deepagents==0.7.13** (core package tag) |
| Pinned commit | **1aae3746682a65c837c5dd0f165b685253fe9465** |
| License | MIT — «Copyright (c) LangChain, Inc.» |
| Staging clone | `vendor-staging/deepagents/` (gitignored, 83 MB shallow) |
| NEXUS landing | `nexus/agents/master.py` (pattern only) |

### 3.1 Cycle record

* **DISCOVER** — the Build Plan §7.6 names `langchain-ai/deepagents`
  explicitly; the master spec §7210 lists Deep Agents among the
  references «عبر adapters». Its whole thesis is the §6.3 shape: a
  planning tool + subagent delegation + a virtual filesystem — the
  canonical Master Agent pattern of 2026.
* **CLONE** — shallow clone of the core package tag
  `deepagents==0.7.13`.
* **LICENSE AUDIT** — MIT. Reference-only ⇒ attribution here and in
  the `nexus/agents/master.py` docstring.
* **SECURITY REVIEW** — reference-only (staging study; their sandbox
  backends and shell middleware are *not* imported — NEXUS's tool
  phases will design their own seams under §0.4).
* **ARCHITECTURE REVIEW** — studied
  `libs/deepagents/deepagents/middleware/subagents.py` +
  `async_subagents.py` + `permissions.py` and
  `backends/filesystem.py`: the Master Agent exposes a **`task`
  tool** that spins a subagent per description, subagents report back
  as tool results, planning state is a structured task list the agent
  mutates, permissions gate the filesystem, and every delegation is
  tracked (pending → running → done) — the exact «يوزع العمل ·
  يتابع · يستقبل النتائج · يقرر الاستمرار» loop of §6.3.
* **COMPATIBILITY REVIEW** — deepagents is welded to
  `langchain.agents`, LangGraph, LangSmith and Pydantic — a
  dependency avalanche the Plan forbids for the Core. The
  *delegation flow* ports cleanly.
* **SELECT INTEGRATION MODE** — **D (REFERENCE)**.
* **WHAT NEXUS TOOK** — the §6.3 `MasterAgent` structure: the
  seven-behavior choreography with subtasks landing on the §2.5
  `task.plan.steps` (their structured task list, on NEXUS's own
  persisted field), per-step delegation through a §6.5 TASK message
  to a discovered agent (their `task` tool, as a message — no code),
  step statuses tracked, failed steps re-run inside a bounded repair
  ladder, and the master deciding when the task reaches
  Verification. Zero lines of their code.
* **PIN** — deepagents==0.7.13 / `1aae374…`.
* **DOCUMENT** — this record + the master module docstring +
  `CHANGELOG.md`.

## 4. Verdict (Round 2)

| Repository | Mode | Pinned | Imported into NEXUS | Proven by |
|---|---|---|---|---|
| langchain-ai/langgraph | D (REFERENCE) | 1.2.11 / 644815f | **nothing** — loop-shape patterns | 116/116 (§6.2 trace proof) |
| microsoft/autogen | D (REFERENCE) | v0.4.4 / bd5a24b | **nothing** — registry/messaging patterns | 116/116 (§6.4/§6.5 proofs) |
| langchain-ai/deepagents | D (REFERENCE) | 0.7.13 / 1aae374 | **nothing** — delegation patterns | 116/116 (§6.3 choreography) |

The proof that the §0.4/§0.5 iron rules held under real temptation:
the three most famous agent frameworks of the ecosystem sat in
staging for the whole phase — and the Core still imports none of
them (`rg "from (langgraph|autogen|deepagents)" nexus/` → zero
hits; `pyproject.toml` `dependencies = []`). Their patterns are in
the NEXUS-owned shapes, their pins are in this record, and the
watchlist for the next rounds (ECC · Cline · Prime · MCP · browser
· vision · memory repos) keeps the same discipline.

---

# NEXUS Repository Integration Record — Round 3 (Phase 6 · Harness Integration)

Round 3 serves **PHASE 6 — Harness Integration** (Build Plan §7). The
plan *names all five repositories explicitly* for this phase — this is
the first round where the plan itself prescribes the pull list
(§7.1 ECC · §7.2 Cline · §7.3 LangGraph · §7.4 Prime Agent · §7.5 Deep
Agents) with per-repo integration modes. Round 2 had cloned the two
LangChain repos for Phase-5 reference; the Round-3 clones below are
fresh pins (the sandbox staging directory is disposable by design —
this record is the durable source of truth).

The governing rules carried into this round: §0.4 (NEXUS Interface →
Adapter → External Project — nothing imports a vendored repo),
§0.5 (the harness layer is a NEXUS-owned component — external repos
contribute **patterns** through NEXUS-native shapes, never code),
the 28-event registry stays binding, and stdlib-only stays binding
(`pyproject.toml` `dependencies = []` — the proof: `rg "from
(ecc|cline|langgraph|prime|deepagents)" nexus/` → zero hits).

## 0. The audit that opened Round 3

| Plan §7 section | Repository | Plan's mode | Round-3 decision | Why |
|---|---|---|---|---|
| 7.1 | affaan-m/ecc | CLONE → REVIEW → ADAPT | **B (ADAPT)** | the skills/rules/hooks *format discipline* becomes NEXUS-owned loaders |
| 7.2 | cline/cline | ADAPT | **B (ADAPT)** | the session-lifecycle + stateful-core pattern, study `sdk/packages/{core,agents}` |
| 7.3 | langchain-ai/langgraph | USE/ADAPT | **B (ADAPT)** | checkpoint/durability patterns; USE (hard dep) rejected — stdlib-only iron rule, §0.5 owns the harness |
| 7.4 | PrimeIntellect-ai/prime-agent | REFERENCE/ADAPT | **D+B (REFERENCE → ADAPT)** | goals/heartbeats/continual-harness patterns; no code (their runtime is TS) |
| 7.5 | langchain-ai/deepagents | REFERENCE/ADAPT | **D+B (REFERENCE → ADAPT)** | subagent/skill/backend shapes already internalized in Phase 5; the skill-file format is the Phase-6 take |

## 1. affaan-m/ecc — MODE B (ADAPT)

| Field | Value |
|---|---|
| Role | Harness patterns: skills structure, rules, hooks, agent specialization, verification, memory, research, security (Plan §7.1) |
| Pinned commit | **e04ea0b9cc8248686edf5ac751cadff550e162b8** (main, 2026-09-07) |
| License | MIT — «Copyright (c) 2026 Affaan Mustafa» |
| Staging clone | `vendor-staging/ecc/` (gitignored, 94 MB shallow) |
| NEXUS entry point | `nexus/harness/skills.py` · `nexus/harness/rules.py` · `nexus/harness/hooks.py` |

### 1.1 Cycle record

* **DISCOVER** — Plan §7.1 names `affaan-m/ecc` verbatim.
* **CLONE** — shallow `--depth 1` @ e04ea0b.
* **LICENSE AUDIT** — MIT, permissive; nothing of their tree is
  redistributed (the skill/rule *markdown format* is a convention, not
  code; NEXUS writes its own files).
* **SECURITY REVIEW** — ECC is a prompt/rules corpus with install
  scripts (`install.ps1`/`install.sh` — never executed in NEXUS);
  nothing from the clone enters the runtime; skills/rules load from
  the *user's* `<root>/skills` and `<root>/rules` dirs only, and
  malformed files are skipped (a bad skill never breaks the boot).
* **ARCHITECTURE REVIEW** — studied `skills/*/SKILL.md` (frontmatter
  `name`/`description`/`metadata.origin` + "When to Use"/"How it
  Works" body), `rules/<topic>/` organization, `hooks/hooks.json`
  (declarative lifecycle wiring), `agents/*.md` specialization docs.
* **COMPATIBILITY REVIEW** — the SKILL.md format is tool-agnostic
  markdown; NEXUS's subset parser (YAML-ish frontmatter fences)
  accepts the real files from the wild (proven on their
  `skills/accessibility/SKILL.md` shape).
* **SELECT INTEGRATION MODE** — **B (ADAPT)**.
* **WHAT NEXUS TOOK** — the SKILL.md/RULE.md discipline (frontmatter
  contract + body), the enabled/disabled switch, topic scopes
  (`security` carried verbatim as the curation hook), priority
  ordering, and the 8-point hook registry shape (their hook moments
  mapped onto NEXUS's canonical event surface). Zero lines of their
  code.
* **PIN** — e04ea0b… (recorded here; re-clone: `git clone --depth 1
  https://github.com/affaan-m/ecc.git`).
* **DOCUMENT** — this record + the module docstrings + `CHANGELOG.md`.

## 2. cline/cline — MODE B (ADAPT)

| Field | Value |
|---|---|
| Role | Agent runtime architecture reference: session lifecycle, tool system, events, plugin architecture, stateful runtime (Plan §7.2) |
| Pinned commit | **c21b17255b228e88a1518c18a73a473ee5876362** (main, 2026-09-07) |
| License | Apache-2.0 |
| Staging clone | `vendor-staging/cline/` (gitignored, 100 MB shallow) |
| NEXUS entry point | `nexus/harness/session.py` · the hooks surface in `nexus/harness/hooks.py` |

### 2.1 Cycle record

* **DISCOVER** — Plan §7.2 names `cline/cline` verbatim, pointing at
  `shared/llms/agents/core`.
* **CLONE** — shallow `--depth 1` @ c21b172.
* **LICENSE AUDIT** — Apache-2.0 (permissive, attribution + NOTICE
  convention; no code redistributed → nothing to carry).
* **SECURITY REVIEW** — the SDK is TS; nothing executes. The
  *separation lesson* is the take: stateful core isolated from the
  loop, sessions as first-class records, hooks on the core surface.
* **ARCHITECTURE REVIEW** — studied `sdk/packages/core/src` (`session/`,
  `tasks/`, `hooks/`, `runtime/`, `extensions/`) and
  `sdk/packages/agents/src/agent-runtime.ts`: the session lifecycle
  and the stateful-core/loop split.
* **COMPATIBILITY REVIEW** — their session lifecycle is TS-async;
  NEXUS's is a synchronous five-state machine with atomic JSON
  persistence (the §2.4 discipline applied to sessions).
* **SELECT INTEGRATION MODE** — **B (ADAPT)**.
* **WHAT NEXUS TOOK** — the session lifecycle vocabulary
  (CREATED→ACTIVE→PAUSED→RESUMED→CLOSED with CLOSED terminal and
  illegal transitions raising), the "stateful core separate from the
  agent loop" boundary (the tracker is runtime-owned, the loop never
  touches it), and the master firing session_start/session_end
  lifecycle hooks around `handle()` (their core-hooks shape). Zero
  lines of their code.
* **PIN** — c21b172….
* **DOCUMENT** — this record + `nexus/harness/session.py` docstring.

## 3. langchain-ai/langgraph — MODE B (ADAPT)

| Field | Value |
|---|---|
| Role | Orchestration + persistence: graph execution, state, checkpoints, recovery patterns, subgraphs, durability (Plan §7.3) |
| Pinned commit | **81bf17b23123e4ef8b9d5f49fa09a0122fc2edd1** (main, 2026-09-06) |
| License | MIT — «Copyright (c) 2024 LangChain, Inc.» |
| Staging clone | `vendor-staging/langgraph/` (gitignored, 20 MB shallow) |
| NEXUS entry point | `nexus/harness/checkpoint.py` |

### 3.1 Cycle record

* **DISCOVER** — Plan §7.3 names `langchain-ai/langgraph` with mode
  **USE/ADAPT**; Round 2 had already cloned it as MODE D.
* **CLONE** — fresh shallow `--depth 1` @ 81bf17b (Round-2 pin was
  1.2.11/644815f — superseded by this record).
* **LICENSE AUDIT** — MIT (unchanged).
* **SECURITY REVIEW** — pure library, no install executed.
* **ARCHITECTURE REVIEW** — studied `libs/checkpoint` (the
  `BaseCheckpointSaver` contract: save/list/get per thread, the
  serializer seam) and `libs/langgraph` pregel execution (superstep
  checkpoints, the resume-from-state flow).
* **COMPATIBILITY REVIEW** — **the decisive review**: a literal USE
  would make `langgraph` a hard dependency of the NEXUS core, pulling
  `langchain-core` + pydantic into a stdlib-only runtime and putting
  a §0.5-owned component (the harness) under an external project's
  release cadence. **Rejected.** The checkpoint *pattern* ports
  cleanly: one JSONL ledger, per-task retention, atomic appends,
  state dicts, resume-by-latest.
* **SELECT INTEGRATION MODE** — **B (ADAPT)** (USE considered and
  rejected on the stdlib/§0.5 iron rules — recorded here as a
  documented decision).
* **WHAT NEXUS TOOK** — the durability vocabulary (NONE / MEMORY /
  DISK), the checkpoint record (id + task + state + reason + time),
  save/list/latest/resume semantics, per-task retention pruning, and
  the auto-checkpoint-on-transition seam (their superstep snapshots →
  NEXUS's §2.2 task lifecycle events, publishing the canonical
  `checkpoint.created`). Zero lines of their code.
* **PIN** — 81bf17b….
* **DOCUMENT** — this record + `nexus/harness/checkpoint.py` docstring.

## 4. PrimeIntellect-ai/prime-agent — MODE D+B (REFERENCE → ADAPT)

| Field | Value |
|---|---|
| Role | Long-horizon / continual execution: goals, persistent sessions, heartbeats, schedules, continual harness, memories, skills, subagents, refinement (Plan §7.4) |
| Pinned commit | **2ce443175b55a32075aa23ae41676a16b771d662** (main, 2026-09-07) |
| License | MIT — «Copyright (c) 2025 Mario Zechner» |
| Staging clone | `vendor-staging/prime-agent/` (gitignored, 32 MB shallow) |
| NEXUS entry point | `nexus/harness/goals.py` |

### 4.1 Cycle record

* **DISCOVER** — Plan §7.4 names it verbatim (REFERENCE/ADAPT).
* **CLONE** — shallow `--depth 1` @ 2ce4431.
* **LICENSE AUDIT** — MIT.
* **SECURITY REVIEW** — TS/Go runtime, nothing executes. Spec §45's
  caution (an open August-2026 issue on continual-harness state
  access) is why the mode stays reference-heavy: no code, patterns
  only — «لا نعامل المشروع كمرجع مضمون بلا عيوب».
* **ARCHITECTURE REVIEW** — studied `packages/agent/src`
  (`agent-loop.ts`, `agent.ts`, `types.ts`) and
  `prime-agent-runtime/src/rlm`: persistent goals with status +
  progress, the heartbeat interval contract, resume/background
  sessions, the RLM-runtime / Continual-Harness split.
* **COMPATIBILITY REVIEW** — their runtime is TS with a daemon; the
  goal/heartbeat *ledger* pattern ports to atomic JSON + in-memory
  beats. The full heartbeat/stall **system** stays Plan §23 (PHASE
  22) — Phase 6 lands the harness-level pattern it builds on.
* **SELECT INTEGRATION MODE** — **D+B**: reference for the runtime
  split, adapt for the goal/heartbeat ledgers.
* **WHAT NEXUS TOOK** — the Goal record (id/description/status with
  the four-state lifecycle + append-only progress log), the goal
  store with reboot persistence, the goals-as-context section
  («goals outlive this task»), and the Heartbeat last-beat ledger
  (record/last/stalled — unknown ≠ stalled). Zero lines of their
  code.
* **PIN** — 2ce4431….
* **DOCUMENT** — this record + `nexus/harness/goals.py` docstring.

## 5. langchain-ai/deepagents — MODE D+B (REFERENCE → ADAPT)

| Field | Value |
|---|---|
| Role | Deep-agent pattern / subagents / skills / backends (Plan §7.5) |
| Pinned commit | **07d2952d346d81d06bd181db8c560a77f2b51bc8** (main, 2026-09-07) |
| License | MIT — «Copyright (c) LangChain, Inc.» |
| Staging clone | `vendor-staging/deepagents/` (gitignored, 84 MB shallow) |
| NEXUS entry point | the skill-file format shared with §7.1 + the §6 subagent seams |

### 5.1 Cycle record

* **DISCOVER** — Plan §7.5 names it verbatim (REFERENCE/ADAPT).
* **CLONE** — fresh shallow `--depth 1` @ 07d2952 (supersedes the
  Round-2 pin 0.7.13/1aae374).
* **LICENSE AUDIT** — MIT (unchanged).
* **SECURITY REVIEW** — Python lib, nothing installed into NEXUS.
* **ARCHITECTURE REVIEW** — studied `libs/deepagents/deepagents/`
  (`graph.py`, `middleware/`, `profiles/`, `backends/`): the
  skill-file loading, the middleware stacking, the backend seam.
* **COMPATIBILITY REVIEW** — their subagent/delegation patterns were
  already internalized in Phase 5 (Round 2); the Phase-6 take is the
  skill-file format discipline (shared with ECC's SKILL.md — the two
  ecosystems converge on the same frontmatter contract, which is why
  NEXUS's single parser serves both).
* **SELECT INTEGRATION MODE** — **D+B**.
* **WHAT NEXUS TOOK** — confirmation of the skill-file frontmatter
  contract (one parser, both ecosystems) and the profile notion
  (their `profiles/` → NEXUS's per-agent §6.1 policies, already
  owned). Zero lines of their code.
* **PIN** — 07d2952….
* **DOCUMENT** — this record.

## 6. Verdict (Round 3)

| Repository | Mode | Pinned | Imported into NEXUS | Proven by |
|---|---|---|---|---|
| affaan-m/ecc | B (ADAPT) | e04ea0b | **nothing** — SKILL.md/RULE.md + hooks discipline | 88/88 (A/B/C sections) |
| cline/cline | B (ADAPT) | c21b172 | **nothing** — session lifecycle pattern | 88/88 (D section + master wiring) |
| langchain-ai/langgraph | B (ADAPT) | 81bf17b | **nothing** — checkpoint/durability patterns | 88/88 (E section + event-driven proof) |
| PrimeIntellect-ai/prime-agent | D+B | 2ce4431 | **nothing** — goals/heartbeat ledgers | 88/88 (F §7.4 checks) |
| langchain-ai/deepagents | D+B | 07d2952 | **nothing** — skill-file contract confirmation | 88/88 (A section, one parser) |

The USE candidate of this round (LangGraph, §7.3) was **considered and
rejected on the record** — the stdlib-only and §0.5 iron rules win
over the plan's permissive «USE/ADAPT», and the checkpoint layer it
would have provided is exactly what `nexus/harness/checkpoint.py`
now proves NEXUS-owned (88/88, canonical events only). The Super-
Harness rule (§275) held: five ecosystems studied, zero imports,
`rg "from (ecc|cline|langgraph|prime|deepagents)" nexus/` → zero
hits, `dependencies = []` unchanged.


---

# NEXUS Repository Integration Record — Round 4 (Phase 7 · Tool System / Plan §8)

Opened 2026-09-07. The plan mandates (§8.4): **modelcontextprotocol —
the interoperability layer; use the official SDK behind the NEXUS Tool
Router**, and (§8.5) clone only the servers the capability needs —
each behind NEXUS permission + NEXUS scope. Three repositories entered
the intake cycle this round.

## 0. The audit that opened Round 4

* **DISCOVER** — Plan §8.4 names `modelcontextprotocol` verbatim; §8.5
  names the five servers (filesystem · git · fetch · memory ·
  database). GitHub API probe: python-sdk MIT · 24k★ · active;
  servers 90k★ · active (license NOASSERTION at root — transition);
  servers-archived MIT.
* **CLONE** — shallow single-branch, token-transient (remote removed
  immediately): `mcp-python-sdk` @ 08a3bc8 · `mcp-servers` @ d73f99e
  (2.5 MB) · `mcp-servers-archived` @ 9be4674.
* **PIN** — round4-pins.txt (vendor-staging).

## 1. modelcontextprotocol/python-sdk — MODE A (USE)

| Field | Value |
|---|---|
| Role | MCP interoperability layer — the official Python SDK (Plan §8.4) |
| Pinned dist | **mcp 2.1.1 (PyPI, the v2 stable line — operator pin `mcp>=2.0,<3`)** |
| Pinned clone | 08a3bc8 (main, 2026-09-07) |
| License | MIT — «Copyright (c) 2024 Anthropic, PBC» |
| NEXUS entry point | `nexus/tools/mcp/adapter.py` behind the §8.2 Tool Router |
| Install surface | optional extra `[mcp]` — the core stays `dependencies = []` |

### 1.1 Cycle record

* **DISCOVER** — §8.4 + the operator's directive (v2 stable line,
  tools/resources/prompts, stdio + Streamable HTTP + SSE).
* **CLONE** — 08a3bc8 (governance review: LICENSE, SECURITY.md,
  DEPENDENCY_POLICY.md, VERSIONING.md all present — a healthy repo).
* **LICENSE AUDIT** — MIT (Anthropic PBC). Compatible.
* **SOURCE CHECK** — `src/mcp/`: `client/` (ClientSession, stdio/
  streamable_http/sse transports) · `server/` (MCPServer — v2 renamed
  from FastMCP) · `types/` (pydantic models) · `shared/`. Deps are
  dynamic (pydantic, anyio, httpx…, all pinned by their release
  process).
* **SECURITY REVIEW** — the SDK is a protocol library: our adapter
  spawns servers via `StdioServerParameters` (list-argv, env control)
  and never evaluates remote content; the NEXUS gates sit in front
  (§71). Auth surfaces (OAuth resource-server) are unused in stdio
  mode.
* **ARCHITECTURE REVIEW** — client session is asyncio-native; NEXUS's
  sync runtime bridges via a session thread + `run_coroutine_threadsafe`
  (the sanctioned pattern), timeout-bounded per server config.
* **COMPATIBILITY REVIEW** — requires-python >=3.10 (NEXUS >=3.11 ✓);
  Windows note: stdio subprocess needs the Proactor loop — `asyncio.run`
  defaults to Proactor on win32 since 3.8 ✓.
* **SELECT INTEGRATION MODE** — **A (USE)** — the operator's explicit
  instruction and §8.4's letter; it stays an optional extra, never a
  core dependency (§0.5 intact: the Tool Registry/Router/native tools
  are 100% NEXUS-owned stdlib).
* **WHAT NEXUS TOOK** — the SDK as a whole, behind the router; zero
  lines copied.
* **PIN** — PyPI 2.1.1 / clone 08a3bc8.
* **DOCUMENT** — this record + `nexus/tools/mcp/adapter.py` +
  PHASE-7-REPORT §3.1.

### 1.2 v2 API deltas found live (recorded for the next auditor)

* `FastMCP` → **`MCPServer`** (`mcp.server.MCPServer`) — v1 code
  raises `ModuleNotFoundError` with a migration pointer.
* `CallToolResult.isError` → **`is_error`** (snake_case pydantic).
* The current official **Python servers** (git/fetch 0.6.x, sqlite)
  pin `mcp>=1.29,<2` *server-side* — they run under `uvx` in their own
  environments (no conflict with NEXUS's v2 client); wire-level
  interop is the initialize handshake's job. The **cross-SDK bonus
  proof** (official TS server + official Python v2 client) passed.

## 2. modelcontextprotocol/servers — MODE B (operational clones)

| Field | Value |
|---|---|
| Role | The official reference servers (Plan §8.5) |
| Pinned clone | d73f99e (main, 2026-09-07) |
| License | **transition: MIT → Apache-2.0** (root LICENSE states new code Apache-2.0, pre-consent contributions stay MIT) — both permissive; NEXUS takes **no code**, only launches servers |
| NEXUS entry point | `config/tools/mcp.toml` launch commands + the §8.5 gates |

### 2.1 Cycle record (per server)

* **filesystem 0.6.3 (TypeScript)** — license Apache-2.0 (src
  LICENSE); security: `path-validation.ts` reviewed — null-byte
  rejection, normalize+resolve, absolute check, allowed-directory
  allowlist (matches NEXUS's own scope philosophy); deps: the TS SDK,
  diff, glob, minimatch, zod. Launched via `npx -y @modelcontextprotocol/
  server-filesystem <roots>`; NEXUS adds `scope_paths=["path"]` so the
  §8.2 Scope stage gates every path argument. **Proven live in the
  exit criteria (bonus check): 14 tools, cross-SDK roundtrip.**
* **git 0.6.2 (Python)** — license MIT (src LICENSE); deps click,
  gitpython, mcp<2 (their side), pydantic. Write ops (commit/branch/)
  exist — NEXUS gates the repo path via scope and the risk ceiling;
  launched via `uvx mcp-server-git --repository <repo>`.
* **fetch 0.6.3 (Python)** — license MIT; deps httpx, markdownify,
  mcp<2, protego (robots.txt), readabilipy. SSRF surface noted:
  NEXUS's network policy (§3.5) + the router's network gate are the
  controlling fences; launched via `uvx mcp-server-fetch`.
* **memory 0.6.3 (TypeScript)** — the local knowledge-graph server
  (JSON file store); risk ceiling 1; launched via `npx -y
  @modelcontextprotocol/server-memory`.
* **database → servers-archived/sqlite 0.6.2 (Python)** — see §3.

All five ship **disabled by default** in `config/tools/mcp.toml` —
"clone only what the task needs" is a per-machine decision; each
entry carries `risk_ceiling`, `allowed_tools`/`blocked_tools`
(refused **before any stdio byte**) and `scope_paths`.

## 3. modelcontextprotocol/servers-archived — MODE B

| Field | Value |
|---|---|
| Role | The §8.5 «database» server (sqlite was moved out of the main repo) |
| Pinned clone | 9be4674 (main, 2026-09-07) |
| License | MIT |
| NEXUS entry point | `config/tools/mcp.toml` `[[servers]] database` |

* **sqlite 0.6.2 (Python)** — deps: `mcp[cli]>=1.6.0`. Exposes
  read_query/write_query — inherent SQL authority: NEXUS clamps the
  risk ceiling at 2, gates the db path via scope, and the router's
  permission stage sits in front. Launched via `uvx mcp-server-sqlite
  --db-path <db>`.

## 4. Verdict (Round 4)

| Repository | Mode | Pinned | Imported into NEXUS | Proven by |
|---|---|---|---|---|
| modelcontextprotocol/python-sdk | **A (USE)** | dist 2.1.1 · clone 08a3bc8 | the SDK whole, behind the router (optional `[mcp]` extra) | 88/88 (D section) + cross-SDK bonus |
| modelcontextprotocol/servers | B (operational) | d73f99e | **no code** — launch commands + gates (filesystem/git/fetch/memory) | 88/88 (D) + filesystem server live roundtrip |
| modelcontextprotocol/servers-archived | B (operational) | 9be4674 | **no code** — the database launch + gates | 88/88 (D §8.5 declarations) |

The §0.5 iron rule holds where it applies: the **Tool Registry, the
Tool Router and the nine native tools are 100% NEXUS-owned stdlib**
(the core still declares `dependencies = []`); the official SDK is
exactly what §8.4 orders — a USE'd interoperability layer **behind**
the router, entering as an optional pinned extra the way psutil did
(Round 1). Spec §71 is enforced by construction: every MCP tool is a
§8.1 record, every call passes discovery → permission → scope →
resource before any stdio byte, and blocked tools never even register.

## Round 5 — Plan §9 (Windows Computer Runtime)

Two repositories, the full §0.2 cycle (the mandatory 18-step
sub-phase loop), executed 2026-09-07.

### 5.1 browser-use/windows-harness — ADAPT (zero imports)

| Field | Value |
|---|---|
| Role | Primary experimental Windows automation backend (Plan §9.2) |
| Pinned clone | 46a37cf (main, 2026-08-26) |
| License | MIT (Copyright 2026 warmshao) |
| Activity | 65★ · 7 forks · active (pushed 2026-08-26) |
| NEXUS entry point | none — patterns only |

**Source audit** (11 modules, ~6.0k lines): three-transport input
design (`inject.py`, 1857 lines — ported from trycua/cua MIT:
`pen` InjectSyntheticPointerInput · `message` PostMessageW ·
`foreground` cloaked SetForegroundWindow + SendInput with health
fallbacks), honest background dispatch (`delivery.py` refuses instead
of silently fronting), DWM cloak detection, SECURITY.md ("treat
third-party UI as untrusted; don't run elevated"). Dependencies are
heavy (pywin32 · pillow · uiautomation · browser-harness) and the
project is **Experimental** — exactly the §9.2 ruling: **ADAPT BEHIND
COMPUTER API**, NEXUS depends on none of it.

**What was adapted (rewritten, NEXUS-owned, stdlib):**

* the two-transport contract (foreground SendInput / background
  WM_CHAR) with honest refusal where the harness uses the third
  (pen injection needs a per-process kernel enable — out of §9
  scope, documented here as not taken);
* `ForegroundError` as a distinct class from injection failure;
* the "background dispatch refuses honestly; only the agent
  escalates" policy (the hierarchy's input layer is the last resort).

### 5.2 pywinauto/pywinauto — MODE A «USE»

| Field | Value |
|---|---|
| Role | Windows UI Automation backend (Plan §9.3: Win32 · UIA · controls · mouse/keyboard · text extraction) |
| Pinned clone | 18d2a95 (master, 2026-05-23) |
| License | BSD-3-Clause (Mark Mc Mahon and Contributors) |
| Activity | 6158★ · 788 forks · mature and active |
| NEXUS entry point | optional extra `[computer]` → `nexus/computer/adapters/pywinauto_backend.py` |

**Source audit**: dual backend registry (win32 · uia · atspi on
linux), wrapper surface (`type_keys` · `click_input` · `set_focus` ·
`set_edit_text` · `children` · `rectangle`), `keyboard.send_keys`
combo mini-language. **Integration ruling**: USE behind the Computer
API — imported lazily per method (the harness source-verifies no
module-level import in `nexus/`), the probe reports honestly, every
failure wrapped. The **native ctypes client (§9.4) stays the first
layer**; pywinauto only deepens the §9.5 uia layer for control
matching and per-control typing.

### 5.3 Verdict (Round 5)

| Repository | Mode | Pinned | Imported into NEXUS | Proven by |
|---|---|---|---|---|
| browser-use/windows-harness | **ADAPT** | 46a37cf | **no code** — the transport contract + honest-refusal policy, rewritten | 80/80 (D) + live device proofs |
| pywinauto/pywinauto | **A (USE)** | 18d2a95 | the library whole, behind the Computer API (optional `[computer]` extra) | 80/80 (E) + BONUS on win32 with the extra |

The §0.5 iron rule holds: `nexus/computer/` core (api · hierarchy ·
uia_native · input_engine) and the three mechanics tools are **100%
NEXUS-owned stdlib**; pywinauto is an optional pinned extra the way
psutil (Round 1) and the MCP SDK (Round 4) are — the core still
declares `dependencies = []`.

---

## Round 6 — Plan §10 (Window Manager + Human Parallelism) — NEXUS-native by plan

**§10 names no external repositories.** The DISCOVER step of the §0.2
cycle concludes *no intake* this round: every primitive the phase
needs — window enumeration and geometry (user32), monitor topology
(EnumDisplayMonitors/GetMonitorInfoW), window placement
(SetWindowPos), the overlay surface (CreateWindowExW · GDI ·
Win32 messaging) — is OS-native and covered by the stdlib-only
discipline the platform already holds.

The two *pattern* references this phase leans on were absorbed in
earlier rounds:

| Pattern | Original source | Absorbed in |
|---|---|---|
| the pre-call veto seam (`pre_tool_call`) | ECC/Cline hooks | Round 3 (§7.1/§7.2 — `nexus/harness/hooks.py`) |
| honest input-transport discipline (typed ctypes calls, refusal over silent no-op) | windows-harness | Round 5 (§9.2 — `nexus/computer/input_engine.py`) |

### 6.1 Cycle record (abridged, by plan)

* **DISCOVER** — the §10 requirement set (window registry ·
  ownership · arbitration · monitors · overlay) maps one-to-one to
  Win32 surface; no candidate repository offers anything the OS
  does not, and the overlay/pywinauto-style wrappers would violate
  the §0.5 rule for zero capability gain.
* **CLONE / LICENSE / SECURITY** — not applicable (zero external
  bytes).
* **INTEGRATE** — `nexus/windows/` (7 modules, 100% NEXUS-owned
  stdlib) + additive operations on the §8.3 `windows`/`screen`
  records.

### 6.2 Verdict (Round 6)

| Repository | Mode | Pinned | Imported into NEXUS | Proven by |
|---|---|---|---|---|
| *(none — by plan)* | — | — | **nothing** | 84/84 + live device proofs (PASS) |

The §0.5 iron rule holds trivially: `nexus/windows/` and the
extended tool operations are **100% NEXUS-owned stdlib**; the core
still declares `dependencies = []`.

---

## Round 7 — Plan §11 (Browser Runtime)

### 7.1 Intake (the §0.2 cycle)

| Repository | Pinned | License | Activity | Audit highlights |
|---|---|---|---|---|
| microsoft/playwright | clone **312030cd** · PyPI dist **1.62.0** | Apache-2.0 | 95.8k★ · active daily | the execution engine: sync API · launch_persistent_context · connect_over_cdp · channel system; the Python package ships the driver + node runtime |
| browser-use/browser-use | clone **e25ab65** | MIT | 112.9k★ · 129 releases | two-layer BrowserSession (events for agents + direct CDP/Playwright); BrowserProfile → persistent contexts; **heavy pinned deps (aiohttp · pydantic · posthog · google-api-core …) — importing would drag the stack** |
| browser-use/browser-harness | clone **eba1021** | MIT | 17.4k★ | thin editable CDP harness; self-healing behavior; tools family (tabs · navigation · click · type · upload · screenshot); auth flows; daemon/IPC layout |

### 7.2 Rulings

* **microsoft/playwright — MODE A «USE»** behind the §8.2 router
  (the `[browser]` extra, lazy imports, honest probe). The §0.5
  rule holds the way pywinauto's does: the engine adapter
  (`nexus/browser/engine.py`) is NEXUS-owned; Playwright executes.
* **browser-use/browser-use — ADAPT, zero imports**: the
  session/profile split, the persistent-workflow semantics and
  the action-registry pattern are rewritten in
  `nexus/browser/{sessions,models}.py` (stdlib). The dependency
  audit is the documented reason — MODE A would have violated the
  stdlib-core identity for zero capability gain.
* **browser-use/browser-harness — ADAPT (Round 5 continued)**:
  the self-healing ladder lands as
  `nexus/browser/selfheal.py` (selector fallbacks · honest
  ledger · bounded retries); the CDP explicit-gate philosophy
  lands as the §55 consent flow; the input-transport lessons were
  already absorbed in Round 5.

### 7.3 Verdict (Round 7)

| Repository | Mode | Pinned | Imported into NEXUS | Proven by |
|---|---|---|---|---|
| microsoft/playwright | **A (USE)** | dist 1.62.0 | the library whole, behind the router (`[browser]` extra) | 70/70 + local Chromium 15/15 + device PASS |
| browser-use/browser-use | **ADAPT** | e25ab65 | **no code** — the session/profile/action-registry patterns, rewritten | 70/70 (B/E) + the device two-session proof |
| browser-use/browser-harness | **ADAPT** | eba1021 | **no code** — the self-healing ladder + the explicit CDP gates | 70/70 (D) + the device CDP attach |

The §0.5 iron rule holds: `nexus/browser/` core is **100%
NEXUS-owned stdlib** (`dependencies = []`); playwright is a pinned
optional extra exactly like pywinauto (Round 5) and the MCP SDK
(Round 4).

---

## Round 8 — Plan §12 (Vision + OCR + Screen Understanding)

### 8.1 Intake (the §0.2 cycle)

| Repository | Pinned | License | Activity | Audit highlights |
|---|---|---|---|---|
| bytedance/UI-TARS | clone **582f3a7** | Apache-2.0 | 11.4k★ | the GUI-agent vision reference: the grounded action space (`click(start_box='(x,y)')`), System 2 reasoning + action grounding, the coordinate-output tutorial (Qwen2.5-VL box semantics, `round_by_factor` smart-resize math) |
| xlang-ai/OpenCUA | clone **dfc91ba** | MIT | 833★ · NeurIPS 2025 Spotlight | the open computer-use stack: VLM-driven screenshot agent, screenshot→action loop, AgentNet tooling; **research foundation, heavy model-gateway dependencies** |
| simular-ai/Agent-S | clone **3aa272d** | Apache-2.0 | 12.2k★ | the S3 skill-library framework (Pydantic-first, OSWorld-grounded): the exact GUI grounding models, the knowledge/skill indirection we will revisit at Plan §13 (memory) and §15 (skills) |

### 8.2 Rulings — the plan is explicit (§12.3/§12.4)

> **UI-TARS: Research/reference for GUI agent vision and action.**
> لا تجعله النموذج الأساسي لجهازك الحالي. **Integration:
> REFERENCE/BENCHMARK.**
> **Clone للاختبار/الدراسة … لكن لا تدخلها كلها إلى production
> runtime.**

* **bytedance/UI-TARS — REFERENCE/BENCHMARK, zero runtime
  dependency**: the *only* adoption is the documented parse
  tolerance in `nexus/vision/provider.py` — a model answer in the
  UI-TARS action-space form
  (`Action: click(start_box='(197,525)')`) parses to the same
  bbox pixels as the house JSON dialect. Never imported, never a
  model, never a server. The plan's own words stand: **not** the
  primary model on the operator's device.
* **xlang-ai/OpenCUA — RESEARCH CLONE, nothing absorbed**: the
  screenshot→action loop's *shape* informed the §9.5 vision rung
  design (locate → input), which was already dictated by the
  Phase-8 chain. No code, no pattern rewrite — the round's honest
  ruling is "studied, shelved, available in `vendor-staging`".
* **simular-ai/Agent-S — RESEARCH CLONE, a bookmark for later
  rounds**: the S3 skill-library indirection maps onto Plan §15
  (Skills) — noted for that phase's intake, **zero imports now**.

### 8.3 Verdict (Round 8)

| Repository | Mode | Pinned | Imported into NEXUS | Proven by |
|---|---|---|---|---|
| bytedance/UI-TARS | **REFERENCE/BENCHMARK** | 582f3a7 | **no code** — one documented parse tolerance (action-space answers) | 118/118 (B: the UI-TARS tolerance check) |
| xlang-ai/OpenCUA | **RESEARCH** | dfc91ba | **no code** — studied, shelved | this record |
| simular-ai/Agent-S | **RESEARCH** | 3aa272d | **no code** — a bookmark for Plan §15's intake | this record |

The §0.5 iron rule holds unchanged: `nexus/vision/` is **100%
NEXUS-owned stdlib**; the OCR candidates are optional extras
(`[ocr]`) and the vision backend is the Phase-4 Model Runtime
itself (llama-server's multimodal `image_data` — the §5.1 request
gained an additive optional field, nothing else).

---

# NEXUS Repository Integration Record — Round 9 (Phase 12 · Memory System / New Plan §12)

Round 9 opens the Track-B (Intelligence) build per the New Plan §0
execution rule. Two engines entered, both behind adapters (Plan §61:
*NEXUS owns Memory semantics*), both optional extras — the Core
still runs stdlib-only.

## 1. qdrant/qdrant — MODE A (USE, via qdrant-client)

* **DISCOVER** — New Plan §12.5 names it explicitly: *semantic
  retrieval · similarity search · filtered retrieval*.
* **CLONE** — shallow @ `6ab21cac` (v1.19.1, 2026-09-03) to
  `vendor-staging/phase-12/qdrant`.
* **LICENSE AUDIT** — Apache-2.0 (permissive, commercial OK,
  attribution required — this record is the attribution). No Qdrant
  source is redistributed inside NEXUS: we speak **only** to the
  official `qdrant-client` PyPI distribution.
* **SECURITY REVIEW** — the Rust server never runs as part of NEXUS
  by default: the adapter's default is **local mode**
  (`QdrantClient(path=…)` — embedded, no server, no sockets). A
  server URL is an explicit operator configuration. Point ids are
  deterministic UUID5 of our record ids (local mode only accepts
  UUIDs); payloads carry the NEXUS filterable subset
  (`VECTOR_FILTER_KEYS`); deletion maps 1:1. The single-instance
  storage lock (local mode) is honored via `close()` — documented
  in the adapter, tested by the restart proofs.
* **COMPATIBILITY** — `qdrant-client>=1.19,<2` (PyPI), Python 3.11+,
  local mode needs no server and no grpc.
* **INTEGRATE** — `nexus/memory/vectors.py::QdrantVectorIndex` over
  the house `VectorIndex` protocol (`upsert · search · delete ·
  count`); `resolve_vector_index(auto|local|qdrant)` with the honest
  `qdrant_probe()`. `query_points` (the 1.10+ API — the deprecated
  `search()` is not used), `Filter(must=[FieldCondition…])` payload
  filters, cosine distance.
* **TEST** — `tests/phase12/verify_exit_criteria.py` C (BONUS live
  roundtrip when installed) + `tests/phase12/live_memory_ci.py`
  **PASS 10/10 on the real engine** (embed → engine → search AR/EN
  → filter → conflict → forget → restart) — also the new CI
  **memory-live** job.
* **PIN** — `[qdrant]` extra: `qdrant-client>=1.19,<2`.
* **DOCUMENT** — this record + `nexus/memory/vectors.py` docstring +
  `docs/PHASE-12-REPORT.md`.

## 2. mem0ai/mem0 — MODE B (ADAPT)

* **DISCOVER** — New Plan §12.6 / Build Plan §13.4: *persistent
  memory engine candidate* — memory extraction, retrieval patterns.
* **CLONE** — shallow @ `73e7b876` (v2.0.20 line, 2026-09-08) to
  `vendor-staging/phase-12/mem0`.
* **LICENSE AUDIT** — Apache-2.0 (permissive; attribution in this
  record). No mem0 source is redistributed or imported into NEXUS.
* **SECURITY / COMPATIBILITY REVIEW** — the real `mem0ai` wheel
  drags an LLM-stack dependency tree (litellm/openai-class clients,
  Qdrant/OpenAI vector stores) that violates the stdlib-core law and
  the local-first policy when imported eagerly. **Ruling**: the
  wheel is an optional `[mem0]` extra for operators who want the
  engine; the adapter is duck-typed (add/search/get_all/update/
  delete) so tests prove the mapping against a deterministic fake —
  the real wheel plugs into the same hole on the device.
* **EXTRACT/ADAPT** — the two behaviors the plan names:
  (1) *memory extraction* — mem0's `add(infer)` pattern (structured
  facts out of raw conversation) is adapted as the deterministic
  bilingual `MemoryCompressor` (§12.10 — AR+EN markers, no model
  calls, CI-provable); (2) *retrieval patterns* — mem0's
  user/agent/run scoping maps onto our §12.2 containers
  (`MEM0_SCOPE_MAP`: `agent_id→AGENT, run_id→SESSION, app→PROJECT`).
  The side `SQLiteMemoryStore` keeps NEXUS-owned semantics (ids,
  scopes, links, §12.9 audit) — the engine is replaceable, the
  semantics are not (Plan §61).
* **TEST** — `tests/phase12/verify_exit_criteria.py` J (the §13.4
  behavior mapping over a FakeMem0 + the honest absence probe).
* **PIN** — `[mem0]` extra: `mem0ai>=2.0,<3`.
* **DOCUMENT** — this record + `nexus/memory/mem0_adapter.py`.

## 3. Verdict (Round 9)

| Repository | Mode | Pinned | Imported into NEXUS | Proven by |
|---|---|---|---|---|
| qdrant/qdrant | **A — USE** (via qdrant-client dist) | 6ab21cac / client >=1.19,<2 | **no source** — `QdrantVectorIndex` adapter only | live_memory_ci **10/10** + CI memory-live |
| mem0ai/mem0 | **B — ADAPT** | 73e7b876 / wheel >=2.0,<3 | **no source** — `Mem0MemoryProvider` adapter + extraction patterns | phase12 §J (FakeMem0 mapping) |

The §0.5 iron rule holds: `nexus/memory/` is **100% NEXUS-owned
stdlib**; both engines are optional extras behind one-contract
adapters, and every absence is *reported, never faked*.


# NEXUS Repository Integration Record — Round 10 (Phase 13 · Learning System / New Plan §13)

Round 10 continues the Track-B (Intelligence) build: the plan's §13.5/
§13.6/§13.7 name three reference repositories — letta-code, prime-agent
and DSPy — for the *ideas* behind persistent learning agents, not for
their code. All three run MODE D (REFERENCE) here: cloned, audited,
pinned, zero imports (Plan §61 — *NEXUS owns Learning semantics*; the
six §13.1 kinds, the §13.2 record and the §13.4 skill candidate are
NEXUS-native contracts).

## 1. Intake (Round 10)

| Repo | Pin (shallow) | License | Mode | Plan |
|---|---|---|---|---|
| `letta-ai/letta-code` | `e073938` (2026-09-08) | Apache-2.0 | **D — REFERENCE** | §13.5 |
| `PrimeIntellect-ai/prime-agent` | `bf8894a` (2026-09-08) | MIT (© 2025 Mario Zechner) | **D — REFERENCE** (B-shaped ideas) | §13.6 |
| `stanfordnlp/dspy` | `f70d08a` (2026-09-05) | MIT (© 2023 Stanford) | **D — REFERENCE** (deferred use) | §13.7 |

All three live in `vendor-staging/phase-13/` per the New Plan §55
staging law — nothing is copied into `nexus/`, nothing is installed,
the core stays stdlib-only (`pyproject.toml` `dependencies == []`).

## 2. Audit (Round 10)

* **letta-code** (TypeScript) — the *persistent identity* reference:
  `src/agent/` (the continual agent core), `src/skills/` (builtin
  skills + skill dispatching tests), memory blocks + agent state held
  by the Letta server; the agent survives sessions by design.
  Security: local-first, no telemetry into the core; the server
  dependency is exactly what NEXUS *does not* want (state must live
  in NEXUS-owned SQLite, §61) — hence MODE D, not A/B.
* **prime-agent** (TypeScript, packages `agent/ai/coding-agent/tui`
  + `prime-agent-runtime`) — the *continual harness* reference:
  persistent goals, skills and memories across runs, subagents and a
  heartbeat loop. The ideas (harness continuity, heartbeat-driven
  learning triggers) map to our §13.3 pipeline + the future §23
  Heartbeat; the TS runtime maps to nothing we need to import.
* **dspy** (Python, `dspy/teleprompt/` + `dspy/evaluate/` +
  `dspy/propose/`) — the *evaluation-driven refinement* reference:
  prompt/workflow optimization against metrics. The plan itself says
  «مرحلة لاحقة» — a later, methodical phase; the seam we keep open is
  the confidence rule (§13.3 stage 4 is pure and swappable for a
  metric-driven scorer later).

## 3. Verdict (Round 10)

Zero code enters the core. What *does* enter, already NEXUS-native:
the §13.1 six kinds, the §13.2 Learning Record, the §13.3 six-stage
pipeline, the §13.4 SkillCandidate + WorkflowMiner, the §12-engine
promotion seam (source `learning`, `conflict_key = lsig_…`), and the
confidence rule — all proven by `tests/phase13/` (gate + live proofs).
DSPy's optimization is **deferred with an open seam** (DW-5).

---

# NEXUS Repository Integration Record — Round 11 (Phase 14 · Code Intelligence / New Plan §14)

Round 11 opens Track A's code-intelligence build: the §14.9
**tree-sitter/tree-sitter** (MODE A «USE») and the §14.10
**Aider-AI/aider** (MODE D/C) intake — the two repositories the
operator named for this phase.

## 1. Intake (Round 11)

| Repo | Pin (this round) | License | Mode |
|---|---|---|---|
| `tree-sitter/tree-sitter` | commit `8351896` (shallow, main) | MIT | **A — USE** (via the PyPI dists: `tree-sitter` 0.26.0 · `tree-sitter-python` 0.25.0 · `tree-sitter-javascript` · `tree-sitter-typescript`) |
| `Aider-AI/aider` | commit `5dc9490` (shallow, main) | Apache-2.0 | **D/C — REFERENCE/EXTRACT** (the Repository-Map methodology) |

Clones: `vendor-staging/phase-14/` (sandbox staging, disposable by
design; pins re-fetchable with the exact commands below).

```bash
# Round 11 (Phase 14 — Code Intelligence)
git clone --depth 1 --single-branch https://github.com/tree-sitter/tree-sitter.git
git clone --depth 1 --single-branch https://github.com/Aider-AI/aider.git
# The runtime installs from PyPI (MODE A): pip install "nexus-core[codeintel]"
```

## 2. Audit (Round 11)

* **tree-sitter** (C core + Python binding) — the parser-generator
  runtime the Master Spec §50 pins as «Use»: fast, error-tolerant,
  incremental by construction. The Python binding ships wheels for
  CPython (the device runs 3.14 — supported). Security posture: pure
  local library, no network, no subprocess; grammar packages are
  data+code from the same org. **MODE A** behind the `[codeintel]`
  extra, exactly like qdrant/mem0 before it: Core stays stdlib-only,
  `engine_status()` reports absence honestly, `type: ignore[import-not-found]`
  on the CI without wheels (house law since Phase 12).
* **aider** (Python) — audited for one thing: **how the repo map
  works**. `aider/repomap.py`: tree-sitter tags → identifier
  references → weighted PageRank (damping 0.85) with a
  personalization vector scaled by file "interest", rendered under a
  token budget with per-file key definitions. That *method* is
  §14.8. What NEXUS rejects: the packaging (aider is a chat tool
  with LLM client plumbing, git shell-outs and prompt templates —
  all §61-foreign). Zero imports; the proof greps `sys.modules` and
  the whole `nexus/` tree for any aider import.

## 3. Verdict (Round 11)

* tree-sitter: **real runtime in production position** — the JS/TS
  parsing path (a language family stdlib cannot touch) and the §14.12
  incremental live-index engine (`tree.edit` → `parse(new, old_tree)`).
  Proven live: 21/21 in `tests/phase14/live_codeintel_ci.py`, both
  Python and JavaScript through `treesitter-incremental`.
* aider: **methodology extracted** (~90 NEXUS-native lines:
  deterministic PageRank, sorted iteration, out-degree
  personalization, `CHARS_PER_TOKEN` budget, focus files). The §127
  behavior — «Files + Important symbols + Signatures + Relations»
  under a token budget — is proven by the I-section (hub ranks
  first, budget respected, focus pins, deterministic).
* The Core remains **stdlib-only**; every engine degrades honestly
  (`engine_status`, the J-section proves both the present and the
  absent path).

