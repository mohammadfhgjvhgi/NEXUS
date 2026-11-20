# Changelog — NEXUS

All notable changes to the NEXUS project are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to the **Build Plan rule**: no phase is complete
until *Implemented + Integrated + Tested + Verified + Documented + Committed*.

## [Unreleased]

### Added — 2026-09-10 (PHASE 25 — Long-Horizon Execution, New Plan §25)

*«خذ المهمة واشتغل لحد ما تخلص.»*
(Take the task and work until it's done.) The goal outlives the
session: persisted to disk, worked by a real background thread,
state true between steps, heartbeat riding every step, checkpoints on
a cadence, resume never blind, and a deadline that stops honestly.

- **§25.1 Goal persistence** — every goal in its own directory as
  `goal.json` written atomically (temp + `os.replace` + `fsync`) with
  an append-only `progress.jsonl` journal; a rebooted process finds
  every goal exactly as the dying one left it.
- **§25.2 Background workers** — one real `threading.Thread` per run;
  `start()` returns a `HorizonHandle` immediately; the caller keeps
  observing (`state()` from disk, `progress()`, `wait()`, `pause()`)
  without blocking the work.
- **§25.3 Long-running state** — the durable ladder `pending →
  running → paused/completed/failed/deadline_hit` with the transition
  law enforced (`IllegalTransitionError`); every worker decision
  re-reads `goal.json` — the state is true between steps, not only at
  the ends.
- **§25.4 Heartbeat** — the §23 `HeartbeatMonitor` beaten `agent` per
  step and `task` at the milestones; silence stays the clock's
  verdict, never an exception's.
- **§25.5 Checkpoints** — a real §22 `CheckpointManager` captures
  `PERIODIC` checkpoints every N steps (default 5) and the returned
  id is persisted with the goal — the resume path will verify it.
- **§25.6 Resume** — the §22.4 law again: the `ResumeInspector`
  re-reads the persisted evidence (readable state · resumable state ·
  intact §25.7 vocabulary · the recorded checkpoint really in the §22
  store) and refuses with every reason named (`BlindResumeError`).
  The generation lease retires a superseded worker before it can
  write a single note.
- **§25.7 Deadline** — the four verbatim kinds (`30_minutes` ·
  `2_hours` · `8_hours` · `until_completion`) with honest windows
  (1800/7200/28800s/none); a bounded deadline is a **wall** deadline
  (epoch seconds — it survives a reboot) enforced at step granularity;
  hitting it stops with `deadline_hit`, never a fake completion; a
  deadline bounds ONE RUN — resuming re-arms a fresh window.
- Tests 54/54 · live proof 11/11 (real threads, real disk, real
  walls) · exit gate 21/21 with the full 15–24 regression green.

### Added — 2026-09-10 (PHASE 24 — Multi-Agent Orchestration, New Plan §24)

*نقل NEXUS من Agent واحد إلى Agent system.*
(Move NEXUS from one agent to an agent system.) The single agent
becomes a system: one master, one user channel walled by identity,
thirteen specialists on the existing registry, three conjunctive
parallelism gates, and ownership every agent knows.

- **§24.1 Master Agent** — يبقى الوكيل الوحيد الذي يتعامل مع
  المستخدم: the `UserChannel` refuses every non-master writer
  (`MasterOnlyChannelError` — the attempt is the violation, the
  error is the wall); the master's single door in is
  `submit_user_goal` and its single voice out is `report_to_user`;
  the transcript is the audit of what the user was told.
- **§24.2 Specialist Agents** — the thirteen verbatim roles
  (Planner · Researcher · Architect · Coder · Browser · Computer ·
  Tester · Debugger · Security · Reviewer · Git · Recovery ·
  Learning), each a §6.1 Agent record registered through the §6.4
  AgentRegistry with a deterministic `ag_spec_<role>` id; the tree
  (master → thirteen leaves) is validated on build and tampering
  raises `TreeError` — a tangled web never ships.
- **§24.3 Parallelism** — يُسمح به عندما: Tasks independent · Files
  independent · Resources available. Three conjunctive gates decided
  pairwise (`ParallelismGate.decide`) — every denial names its
  reason — composed deterministically into waves
  (`plan_waves`, greedy first-fit: a dependency always lands in a
  strictly earlier wave, conflicting files never share one) and run
  on real threads (`ran_parallel` is the decision; the live proof
  meets at a `threading.Barrier` — a sequential runner deadlocks).
- **§24.4 Agent Ownership** — كل Agent يعرف: task · scope · parent ·
  children · owned resources (the five verbatim fields as a frozen
  `OwnershipSpec`); scope violations are refused *before* work
  starts (empty scope = a no-file agent — narrower by default);
  resource coordination rides the §6.6 OwnershipManager — a conflict
  surfaces as an honest failed result naming the holder, never an
  overwrite, and claims return when the wave ends.
- **Integration, not duplication** — the §23 HeartbeatMonitor beats
  `agent` on every dispatch and `task` on every completed wave; the
  §6.1/§6.4 records persist and survive a reboot; the orchestration
  core stays stdlib-only.
- Tests 56/56 · live proof 11/11 (real threads, real walls, real
  waves) · exit gate 22/22 with the full 15–23 regression green.

### Added — 2026-09-10 (PHASE 23 — Heartbeat + Health, New Plan §23)

*منع التوقف الصامت.*
(Prevent the silent stall.) Health is time-based before it is
exception-based: silence is derived from the clock, loops are named
from real observations, and recovery walks a ladder whose every rung
is on the record.

- **§23.1 Heartbeat** — the seven verbatim watch targets (Core ·
  Agent · Model · Tool · Browser · Computer · Task) each owing the
  monitor a beat; the status is derived per check (alive inside the
  fresh window · degraded when late or self-reported · stalled when a
  finding named it · silent past the stale window — التوقف الصامت) and
  a fresh beat is the only thing that clears a stall — recovery is
  proven by the component, never granted by the monitor.
- **§23.2 Stall Detection** — the four loop shapes verbatim (same
  action · same error · same state · no progress) over one sliding
  window per component; empty fields are never judged, a finding
  fires once per evidence (no alert spam while the loop keeps
  looping), and `reset()` re-arms after a recovery.
- **§23.3 Recovery** — the ladder verbatim (detect → diagnose →
  retry → alternate method → replan) with every rung observable in
  the outcome: a refuted finding ends honestly at detect, an absent
  rung climbs past honestly, a raising rung escalates without dying,
  and replan hands the problem upward. The §22 law rides along: every
  world-mutating rung (retry · alternate method) is announced through
  the `before_rung` hook — the caller wires it to the §22.2
  BEFORE_RISKY_CHANGE trigger, and a failed announcement refuses the
  rung: no checkpoint, no risky change.
- The `HealthSupervisor` ties the section together — each watched
  component owns a private detector (a loop is a per-component
  story), §23.1 silence becomes a `no_progress` finding with the
  truth in its detail, every confirmed finding walks the ladder and
  marks its component STALLED until the component beats again, and
  silence is reported once per silence era (a new beat seq is a new
  era).
- Live proof `tests/phase23/live_heartbeat_ci.py` — 11/11 rungs: a
  real thread beats and really stops (silence caught by the clock), a
  real action really fails three times (same_error), a real frozen
  loop traces its shapes, the ladder climbs through all three
  resolutions, and a real CheckpointManager captures a
  BEFORE_RISKY_CHANGE checkpoint before every mutating rung.

### Added — 2026-09-10 (PHASE 22 — Recovery + Checkpoints, New Plan §22)

*أي Task كبيرة يجب أن تكون قابلة للاستعادة.*
(Any large Task must be recoverable.) Checkpoints are data on disk,
recovery is a measured walk — and the §22.4 law is structural: no
resume without six live surfaces agreeing.

- **§22.1 Checkpoint Manager** — four capture targets (Task ·
  Project · Git · State) over one disk store: sha256 digests, file
  blobs, atomic manifests (tmp + replace), per-scope retention,
  escape-proof blob paths.
- **§22.2 Trigger Events** — the six verbatim events (task start ·
  phase complete · major change · critical test · before risky
  change · periodic); the periodic one flows through an interval
  policy that honestly declines when too soon.
- **§22.3 Recovery** — the chain Crash → Checkpoint → Actual
  environment → Reconciliation → Resume walked stage by stage with
  every stage observable in the outcome; repair re-applies the
  captured blobs (digest-checked) and the re-reconciled resume is a
  *verified* resume; a lost or corrupt checkpoint is UNRECOVERABLE
  and aborts, never fakes.
- **§22.4 No Blind Resume** — the six surfaces (Files · Git ·
  Processes · Windows · Browser · Task state) probed live every
  time; each surface alone blocks the resume; `resume()` raises
  `NoBlindResumeError` on any drifted report — the verdict AND the
  error list are both checked (a forged RESUME_READY header cannot
  sneak through); honest probes distinguish not-a-repository from
  unreadable and degrade to empty facts rather than invented ones.
- Live proof `tests/phase22/live_recovery_ci.py` — 10/10 rungs: a
  real process is started, captured from the real process table and
  killed to prove `process_dead`; a real git head diverges to prove
  the wall; a real edit, a real tamper — and every repair re-earns
  the resume.


### Added — 2026-09-10 (PHASE 21 — Security System, New Plan §21)

*Full capability + controlled execution.* The §156 triad (Scope +
Permission + Execution Gate) behind one pipeline that walks the v0.1
§57 order — scope → permission → gate → audit — with every verdict
audited (deny included) and the §21.10 doors guarded structurally.

- **§21.1 Scope Engine Integration** — the §3.3 resolution is the
  first check of every admission (`ScopeEngineIntegration.scope_for`
  → `ScopeContext`); cross-workspace requests ride §3.4's audited
  carve, histories never merge.
- **§21.2 Permission Engine** — the verbatim §163 risk ladder
  (read=low · edit=medium · delete/high=high · push release=high)
  combined with the §3.5 policy decision. Blueprint §79 honoured:
  an explicit policy denial is the only wall; L4 (FULL) executes
  high risk inside the task and its policy (audited), below FULL it
  escalates to confirmation.
- **§21.3 Tool Gate** — a registry with declared §163 risks and
  confirm-first flags; blocked tools are denied, ghost tools
  (neither registered nor named) escalate — never silently allowed.
- **§21.4 MCP Gate** — a server registry with per-server tool
  allow-lists; blocked servers denied, unregistered servers and
  out-of-list tools escalated.
- **§21.5 Plugin Gate** — declared permissions only
  (`filesystem_read/write · network · process · memory · secrets`);
  requesting `secrets` is denied unless explicitly granted — secret
  access is never a plugin default (the §21.6 law); high-risk
  permissions need a trusted plugin or a human.
- **§21.6 Secret Handling** — the Spec §160 reference law: the
  credential carries six fields (ID · Provider · Scope · Reference ·
  Created · last-used) and the text never leaves the vault;
  `resolve` is audited without the text and advances last-used;
  `scrub` removes every stored secret's exact text from arbitrary
  payloads — catching secrets that match no pattern.
- **§21.7 Redaction** — ten pattern families (AWS · GitHub · Slack ·
  sk-style keys · Google · JWT · bearer headers · private-key
  headers · credentials-in-URLs · secret assignments) replaced by
  `[REDACTED:<kind>]`; sensitive-named JSON keys are redacted whole;
  benign text is untouched (proven).
- **§21.8 Audit** — the §164 five fields verbatim
  (Who | What | When | Where | Result) on every record, JSONL
  artifacts, filters, and the §165 split: `ActivityFeed` stays a
  separate, guarded, human-friendly surface.
- **§21.9 Trivy** — `aquasecurity/trivy` over the four verbatim
  kinds (dependency · secret · license · vulnerability): MODE A runs
  the real CLI (`trivy fs --format json --scanners …`) and parses
  its JSON; MODE B is an honest stdlib baseline — real manifest
  inventory, real secret detection, real license detection, and a
  vulnerability report that never invents findings (the reason sits
  in `notes`). Finding snippets are redacted before they are stored.
- **§21.10 Security Rules** — secrets reach none of Memory · Normal
  chat · Logs · Activity: every door runs two passes (vault-exact
  then patterns) and `SecretLeakError` is the hard stop; the audit
  log and activity feed accept the guards directly, so the rule is
  enforced structurally, not by caller discipline.

82/82 sandbox tests · 19/19 exit gate (A–F, no regression on 15–20) ·
10/10 live rungs. Stdlib only.

### Added — 2026-09-09 (PHASE 20 — Verification Engine, New Plan §20)

The engine that proves the engine.
*لا يكفي أن NEXUS يعمل — يجب أن يثبت أنه يعمل* — the §20.1 framework
(`Verifier` · `Evidence` · `Criterion` · `Result`), the §20.2 nine
verification domains each behind its own honest verifier, the §20.3
five-field evidence sealed as sha256 artifacts, and the §20.4 repair
loop (Fail → Diagnose → Fix → Retest → Verify) — stdlib only, honest
SKIPs everywhere, no capability row invented without proof.

- **§20.1 Framework** — the four nouns verbatim: `Criterion` (a claim
  with one of the nine domains and a real check callable), `Verifier`
  (an ABC that judges its declared criteria), `Result` (a status of
  PASS / FAIL / ERROR / SKIP with duration and message) and `Evidence`
  (one observation). The judging law: a check returning a string is a
  PASS with that observation; an `AssertionError` is a FAIL; a
  `CriterionSkipped` raise is an honest SKIP; anything else is an
  ERROR — a broken probe is never disguised.
- **§20.2 Domains** — nine verifiers in the plan's order: Software
  (imports, version integrity, stdlib-only core), Windows (honest
  platform probes — judged on the real box, SKIP elsewhere),
  Browser (§11 vocabulary + a playwright availability probe),
  Documents (§18 vocabulary + the docling MODE A/B probe), Research
  (§17 surface), Git (a real binary, a real HEAD sha read with
  stdlib), Memory (an actual §12 engine roundtrip closed before
  cleanup), Models (§5 vocabulary + honest llama.cpp probe),
  System (python floor, temp write, disk free, CPU observation).
- **§20.3 Evidence** — five fields verbatim (method · output ·
  timestamp · artifact · result); every observation persisted as a
  JSON artifact sealed with its own sha256, tampering detected on
  read-back, unlabelled observations refused, identical observations
  sharing one artifact.
- **§20.4 Repair Loop** — the plan's chain verbatim and ordered:
  Fail → Diagnose → Fix → Retest → Verify, every stage leaving
  sealed evidence; a `RuleDiagnostician` names failure classes
  (missing-directory · locked-handle · transient · missing-file ·
  unknown) and declared strategies repair them (create-directory ·
  gc-unlock with the Windows handle lesson · backoff); a repaired
  PASS is labelled `repaired after N attempt(s)` — never mistaken
  for a first-try PASS — and an unrepairable failure stops honestly.
- **Verification engine** — one `VerificationEngine` run over the
  nine domains produces a `VerificationReport` with per-domain
  tallies and an honest overall verdict: PASS (nothing failed and
  something really passed), DEGRADED (parts of the truth live
  elsewhere) or FAIL (any failure, any error, or nothing proven).
- **55 phase-20 tests** (contracts 11 · evidence 8 · domains 13 ·
  engine 5 · repair 13 · gate 26 checks) plus the 10-rung live proof
  (`live_verification_ci.py`) — vocabulary verbatim ×4, the engine
  over all nine domains, sealed evidence on every result, the report
  persisted with its digest, the repair chain over a real missing
  directory, per-stage sealed evidence, and the honest SKIP observed.


### Added — 2026-09-09 (PHASE 19 — Speech System, New Plan §19)

Local voice control arrives.
*التحكم الصوتي المحلي وصل* — the §19.1 Speech API (`SpeechProvider` ·
`transcribe` · `detect_language`), the §19.2 sherpa-onnx integration
(MODE A/B + the Windows SAPI zero-install floor), the §19.3 six-condition
benchmark over real audio fixtures and the §19.4 five-stage pipeline
(Microphone → STT → Normalization → Intent → Task) — all stdlib floors,
one documented optional pin, honest probes everywhere.

- **§19.1 Speech API** — one `SpeechProvider` contract with
  `transcribe` → `TranscriptionResult` and `detect_language` →
  `LanguageDetection` (the detection *method* is always stated:
  native / script-inference / configured); a stdlib WAV floor
  (`wavio`) that parses real RIFF/WAVE and refuses corrupt,
  truncated and foreign payloads; confidence is the engine's own
  number or `CONFIDENCE_UNREPORTED` — never an invented 0.0.
- **§19.2 sherpa-onnx** — `k2-fsa/sherpa-onnx` behind the contract:
  MODE A (direct use) when the engine *and* a whisper model are
  present, an honest probe (`installed` · `version` · `model_found`)
  with one documented pin `sherpa-onnx>=1.10,<2` (the `[speech]`
  extra), native language detection from whisper's token — and the
  Windows SAPI 5.1 dictation floor (`System.Speech`,
  `SetInputToWaveFile` → `DictationGrammar` → `Recognize`) as MODE A
  with zero installs; when neither exists the null provider refuses
  with the install hint.
- **§19.3 Benchmark** — six real conditions verbatim (Arabic ·
  Arabic technical · English · Mixed Arabic-English · Fast speech ·
  Noise) over *real neural speech fixtures* committed as text-safe
  base64 with a provenance manifest (generator, expected text,
  whisper-tiny reference transcript); WER/CER scoring through the
  normalizer, intent verdicts per case, a JSON report that states
  numbers without inventing verdicts.
- **§19.4 Pipeline** — `Microphone → STT → Normalization → Intent →
  Task` verbatim, a `StageTrace` verdict per stage, honest failure
  traces that stop at the first failed stage; a bilingual intent
  router (six NEXUS intents, Arabic + English triggers over
  normalized forms, an honest `unknown`); the *Task* stage lands a
  real `VoiceTask` (intent → task kind) remembered into the §12
  Memory Engine with `MemoryEvidence(method="user_statement",
  uri="voice://…")` provenance.
- Tests 104/104 in `tests/phase19`; live proof 9/9 (`live_speech_ci.py`)
  including a real whisper MODE B rung (WER 0.00 English, native `ar`
  detection) wherever a model exists; exit gate 26/26 with zero
  regression across phases 15–18; CI gains the Phase 19 harness and a
  `speech-live` job.

### Added — 2026-09-09 (PHASE 18 — Document Intelligence, New Plan §18)

Real documents get real support.
*الوثائق الحقيقية تحصل على دعم حقيقي* — the §18.1 docling integration
(MODE A/B behind the NEXUS ParseBackend contract), the §18.2 five-stage
pipeline (Document → Parse → Structure → Extract → Index → Memory),
the §18.3 DOCX verbs, the §18.4 PPTX verbs and the §18.5 PDF verbs —
all stdlib-only floors, one documented optional pin, verdicts per
stage, provenance riding every record.

- **§18.1 Docling** — `docling-project/docling` behind the NEXUS
  `ParseBackend` contract: MODE A (direct use) when installed, MODE B
  (the adapter) always; an honest availability probe (`installed`,
  `version`, `detail`) with one documented pin `docling>=2.25,<3`;
  when absent, `BackendUnavailableError` — and the native stdlib
  floors keep every document flowing.
- **§18.2 Pipeline** — `Document → Parse → Structure → Extract →
  Index → Memory` verbatim, a `StageTrace` verdict per stage; the
  first serving backend wins at parse; `index`/`memory` are honest
  `skipped` when unbound. The `DocumentIndex` is a real inverted
  SQLite index (documents · blocks · postings) whose hits answer
  *where* a word lives — `page 3`, `slide 2`, `paragraph 7` — with
  explicit `close()` (the WinError-32 Windows law, kept).
- **§18.3 DOCX** — read · create · edit · format · save · verify over
  real OOXML: minimal valid packages Word/LibreOffice open, real
  round trips (paragraphs, runs, Heading1–6, bold/italic/underline,
  sizes, alignment, tables) and a verify verb that re-opens what was
  saved (zip integrity · main part · XML parse · text roundtrip).
- **§18.4 PPTX** — create · slides · images · layout · sources ·
  save · verify: a real minimal package (presentation + slide master
  + slide layout + theme + slides + media), embedded real images with
  EMU placement, `sources()` extracting per-slide text provenance,
  and verify that catches title drift and corruption.
- **§18.5 PDF** — read · search · extract · summarize · analyze: a
  stdlib object parser (xref-less trailer resolution, catalog → page
  tree → content streams, FlateDecode, `Tj/TJ/'/"` show-text,
  escapes + hex strings, cp1252), case-insensitive search with page
  numbers and context, extractive summarization in document order,
  and an analyze report (per-page counts, fonts, empty pages). The
  parser reports what it cannot read — CID/Type0 and encryption are
  honest refusals, never invented text.
- **Memory + events** — documents persist into §12 Task/Project
  memory as FACT records with `MemoryEvidence(method="document",
  uri, snippet)` provenance plus a session SUMMARY; only canonical
  §2.2 tool events leave the engine — counts travel, content never
  does.
- **Tests + gate + proof** — 80/80 pytest against real files; the §18
  exit gate 29/29 with zero regression on 15·16·17; the live proof
  7/7 rungs (real DOCX/PPTX/PDF roundtrips, a real file-backed index,
  the honest docling probe, §12 memory with provenance); CI gains the
  Phase 18 step and the `documents-live` job.
- **Identity** — `nexus-core 0.18.0`, `NEXUS_PHASE = 18`.


### Added — 2026-09-09 (PHASE 17 — Research Engine, New Plan §17)

Research becomes a runtime, not a chat side-effect.
*البحث يصبح جزءًا من runtime وليس أثرًا جانبيًا للمحادثة* — the §17.1
Search abstraction over five surfaces, the §17.2 eight-stage workflow,
the §17.3 six-class Source Classification, the §17.4 four-dimension
Source Confidence, and the §17.5 Research Memory over the §12 engine —
all stdlib-only, all events on the canonical §2.2 wire, sources riding
every finding.

- **§17.1 Search abstraction** — five surfaces verbatim (`web ·
  github · docs · forums · local files`) behind one `SearchProvider`
  contract: `WebSearchProvider`/`ForumSearchProvider` (stdlib `urllib`
  JSON adapters with `result_key`/`field_map`/`uri_template`/
  `strip_html` mapping — any engine fits), `GitHubSearchProvider`
  (the §16.2 engine, public credential-free reads), and
  `DocsSearchProvider`/`LocalSearchProvider` (real corpus walkers that
  return `file://` hits whose snippet is the best matching line).
  Honest semantics everywhere: empty means *no results*, a raise
  means *the surface failed* — never guessed.
- **§17.2 Research workflow** — `Query → Search → Collect →
  Deduplicate → Rank → Compare → Verify → Evidence`, a verdict per
  stage (`StageTrace`); one failing surface is recorded and the run
  continues, all failing (or none) fails honestly; URI + content
  dedup keeps the best carrier; rank orders by §17.4 score; compare
  clusters agreeing hits and marks contested numbers (`4 GB` vs
  `64 GB` on one claim) — contested findings never verify; verify
  requires ≥N distinct sources with mean authority ≥ threshold;
  evidence attaches per-source rows with real addresses.
- **§17.3 Source Classification** — six classes verbatim
  (`official · documentation · academic · community · personal ·
  unknown`) over a documented deterministic ladder; explicit provider
  metadata wins, `unknown` is the honest fallback, and GitHub repos
  read as their project's official home while issues/discussions read
  as community.
- **§17.4 Source Confidence** — four dimensions verbatim
  (`authority · relevance · freshness · evidence`) with published
  weights (0.35/0.25/0.20/0.20), per-class authority priors, term
  overlap relevance, linear freshness decay over 720 days from a
  surface-reported date (no date → neutral 0.5, never optimistically
  fresh), and snippet-grounded evidence.
- **§17.5 Research Memory** — `ResearchMemory` over the §12 Memory
  Engine: one `FACT` record per finding (confidence = the §17.4
  score, scope TASK/PROJECT/KNOWLEDGE by container), every backing
  hit becomes `MemoryEvidence(method="research", uri, snippet)`, one
  `SUMMARY` record per session, and `recall` returns records *with
  their sources*; the §12.2 ladder keeps Task memories task-private.
- **Tests & proofs** — 73/73 pytest (contracts · classification ·
  providers · workflow · memory · engine, all against real local HTTP
  servers and real corpora), a 23-check exit gate
  (`tests/phase17/verify_exit_criteria.py`) with zero regression on
  14·15·16, and a 6-rung live proof
  (`tests/phase17/live_research_ci.py`): real GitHub search, real
  public web search (Wikipedia → DuckDuckGo fallback), the repo's own
  docs/ and nexus/ trees, the full workflow, the four dimensions, and
  a remember→recall roundtrip with sources.

### Added — 2026-09-09 (PHASE 16 — Git / GitHub, New Plan §16)

GitHub becomes part of the runtime, not just a storage place.
*جعل GitHub جزءًا من runtime وليس مجرد مكان تخزين* — the §16.1 Git
Engine, the §16.2 GitHub Engine, the §16.3 eight-stage Repository
Lifecycle, and the §16.4 Parallel Agents strategy, all stdlib-only
(`subprocess` + `urllib`), all events on the canonical §2.2 wire.

- **§16.1 Git Engine** — the eight operations `status · diff ·
  branch · worktree · commit · merge · tag · rollback` over the real
  `git` binary; `diff` reports untracked files honestly (git alone
  would hide them); hard `rollback` saves a safety branch by default;
  a dirty tree refuses destructive checkout/merge; plus §198's
  `clone`/`pull`/`push` helpers shared with the GitHub engine.
- **§16.2 GitHub Engine** — `search · clone · pull · push · branch ·
  PR · issue · release` over the REST API (`urllib`, no SDK); the
  token arrives only as a §124 credential reference (env / file /
  command) and is *resolved lazily, never logged, never stored* —
  without one, writes refuse with `TokenNotAvailableError` while
  public reads still work; 404 stays honest and 403 rate limits
  surface `RateLimitExceededError` with the `X-RateLimit-Reset` epoch.
- **§16.3 Repository Lifecycle** — `Discover → Clone → Index →
  Modify → Test → Commit → Review → Push` with an explicit per-stage
  report (OK / SKIPPED / FAILED / PENDING never silent); the test
  stage runs only whitelisted commands; the review stage can stop
  the pipeline with `ReviewRejectedError`; push requires a passed
  GitHub engine or an explicit pusher — never a guessed remote.
- **§16.4 Parallel Agents** — `feature branch · worktree ·
  checkpoint` chosen by task kind (§123 strategy): a major feature
  gets a real `feature/<task>` branch, risky work gets an annotated
  `checkpoint/<task>` tag first, and parallel agents get a real
  `git worktree` fleet with a teardown path.
- **Proof** — 64/64 unit tests (real temp git repos + a real local
  HTTP server); the exit gate 28/28 with §14/§15 regression; a live
  10/10 rung proof (the eight real git operations + a real github.com
  clone + the full lifecycle over a bare mirror); CI gains the
  phase-16 harness step and a `git-github-live` job.

### Added — 2026-09-09 (PHASE 15 — Coding System, New Plan §15)

The platform writes code. *تحويل NEXUS إلى Developer Agent حقيقي* —
the seven-operation Coding Agent Contract, the ten specialists, and
the eight-stage Coding Loop that ends in a review verdict or an
honest bounded rejection — never an infinite spin.

- **§15.1 Coding Agent Contract** — one `execute` dispatcher over
  seven operations (analyze · plan · edit · run · test · debug ·
  review); analyze reuses the §14 code-intel engine, edit is
  Cline-shaped search/replace with before/after digests, run/test
  are real subprocesses with timeout + capture, debug turns failing
  tests into named findings with hypotheses, review re-runs the
  tests and renders a verdict with reasons.
- **§15.2 Specialist Agents** — the ten roles (architect · frontend ·
  backend · database · devops · debugger · tester · security ·
  performance · reviewer) as declarative specs registered into the
  §6.4 Agent Registry, each mapped to real NEXUS modules and loop
  stages.
- **§15.6 Coding Loop** — Understand → Plan → Edit → Build → Test →
  Debug → Retest → Review, verbatim order, recorded stage-by-stage
  over the §2.4 task machine (ANALYZING → PLANNING → EXECUTING →
  VERIFYING), canonical §2.2 events only, bounded Debug→Retest
  cycles, the skeleton always eight-wide with extra cycles appended.
- **§15.5 Session trail** — the Cline-inspired CodingSession: files
  read · files edited · tool calls · atomic persistence · revival.
- **References (Round 12)** — OpenHands + OpenCode MODE B/D, Cline
  MODE D: architecture references only, zero imports
  (docs/REPOSITORY-INTEGRATION.md).

### Added — 2026-09-08 (PHASE 14 — Code Intelligence, New Plan §14)

The platform reads code. *تمكين NEXUS من فهم المشاريع الكبيرة* —
scan once, index incrementally, update live on every change, and
hand the model a budgeted **map** instead of 400k lines.

- **§14.1 File Index** — full-tree scan with ignore rules
  (node_modules · dist · __pycache__ · hidden dirs · binaries ·
  minified artifacts); language map; change detection
  (size+mtime fast path, content sha only on change).
- **§14.2 Symbol Index** — ten-kind vocabulary, definitions with
  lines/signatures/containers, kind+file+prefix search, per-file
  atomic replace.
- **§14.3 AST** — three engines, one `ParsedFile` contract:
  **stdlib-ast** (Python, full signatures, zero wheels — the
  default), **tree-sitter** (§14.9 MODE A), **regex** (the honest
  JS-family fallback); the lightweight `AstNode` digest.
- **§14.4 Dependency Graph** — python import resolution (absolute,
  relative dots, **from-import submodule semantics** — `from pkg
  import mod` links both `pkg/__init__.py` and `pkg/mod.py`) and JS
  relative specifiers (`.`/`..` joins); dependents, transitive
  impact sets, entry points, hotspots.
- **§14.5 API Graph** — Flask · FastAPI · Express routes (method,
  path, handler, framework, line) + the route table.
- **§14.6 Test Graph** — test→target links via imports *and* the
  naming convention; per-link counts; coverage gaps.
- **§14.7 Architecture Map** — layers (top-level dirs) with
  aggregated inter-layer edges.
- **§14.8 Repository Map** — the Aider §127 methodology, NEXUS-native:
  weighted **PageRank** (damping 0.85) over the file reference graph,
  out-degree personalization, token-budgeted rendering, deterministic,
  `focus` pins the edited file first. *لا نرسل 400k سطر إلى النموذج.*
- **§14.9 tree-sitter MODE A** — the real runtime behind the
  `[codeintel]` extra: JS/TS parsing (languages stdlib cannot touch)
  and the **§14.12 incremental engine** (`tree.edit` → reparse with
  the old tree). Absent → `engine_status()` says so; stdlib answers.
- **§14.10 Aider MODE D/C** — methodology only; zero imports (proven
  by grep + `sys.modules`), pinned `5dc9490` in vendor-staging.
- **§14.11 Large Project Engine** — the 100k rung live (100,000
  files: 6.0s generate, 5.5s scan, honest 2,500-parse budget, crawl
  continuation across restarts, deletion pruning, steady-state
  rescan reparses **zero**); batched WAL persistence in one
  `codeintel.db`.
- **§14.12 Live Index Update** — the verbatim flow: file changed →
  parse affected region → update symbols → update graph (this file
  only), every step in the honest `UpdateReport`.
- **Events** — `index.scan_started` · `index.updated` (stats +
  seconds) · `index.live_updated` (the §14.12 trace).
- **Bugs the proof caught** (fixed at the root): the sha-wipe
  upsert (every rescan reparsed everything), the SQLite reserved
  word `references`, `language()` called as an attribute, JS
  relative-path joins, live-update vs disk stat drift.
- **Proofs** — gate **97/97 +1 bonus** · live CI **21/21**
  (tree-sitter + 100k + child-process restart) · device proof on
  the real Windows box (`proofs/phase14_live.json`, NEXUS indexing
  its own tree) · CI job `codeintel-live` on every push.

### Added — 2026-09-08 (PHASE 13 — Learning System, New Plan §13)

The platform learns. *«يتذكر» is not «يتعلم»* — memory (PHASE 12)
persists what happened; **learning** turns what happened into
lessons, decisions and skills that future tasks already know.

- **§13.1 Experience Extractor + six kinds** — `success · failure ·
  decision · pattern · lesson · skill_candidate`, verbatim vocabulary;
  one finished TaskResult → audit-grade experiences (task id, honest
  summary, §12.1 evidence objects, §12.2 containers).
- **§13.2 Learning Record** — `experience_id · lesson · source_task ·
  evidence · confidence · scope` verbatim, plus the seams the
  pipeline needs (status pending→promoted, occurrences, signature,
  memory_id link). Confidence is capped at 0.95 — a lesson is
  corrigible by design.
- **§13.3 Learning Pipeline** — Experience → Candidate lesson →
  **Evidence check** (an opinion with no evidence is refused but
  audited) → **Confidence** (pure rule: kind prior + distinct capture
  methods + repeats) → **Store** (SQLite `learning.db`, merge by
  signature — the same lesson re-learned is ONE record with rising
  occurrences) → **Future retrieval** (promotion into the §12 Memory
  Engine: source `"learning"`, `conflict_key` the lesson signature;
  `recall()` surfaces promoted + still-pending lessons; the §12.7
  retrieve of a future task already carries the lesson). The §12.8
  ladder stays in force — an old lesson never overrides the
  operator's now.
- **§13.4 Skill Candidate + WorkflowMiner** — Task A, Task B, Task C
  with the same steps fold into ONE pattern → skill candidate
  (occurrences 3, per-task evidence), maximal windows only (a
  sub-window of a kept workflow is noise); promotion writes a SKILL
  record into the §12 engine.
- **References (MODE D, zero imports, Plan §61)** — letta-code
  `e073938` (persistent identity/skills), prime-agent `bf8894a`
  (continual harness/goals/heartbeat), dspy `f70d08a` (evaluation-
  driven refinement — §13.7 deferred with an open seam, DW-5).
- **Events** — `learning.record.created/promoted/refused` +
  `learning.skill.found` on the real §2.2 bus, defensively emitted.
- **Proofs** — 60-check exit gate (A–K, includes Phases 1–12
  regression), live CI proof (14 checks, real child-process restart,
  bilingual AR/EN), device live proof on the real Windows box
  (§13.1/§13.3/§13.4 + restart across a process boundary);
  `nexus-core 0.13.0`, `NEXUS_PHASE=13`, CI jobs `phase13` +
  `learning-live`.

### Added — 2026-09-08 (PHASE 12 — Memory System, New Plan §12 / Build Plan §13)

The platform gains its **Memory Engine** — from persistence to a
real engine: seven verbatim verbs, a twelve-scope hierarchy with
strict isolation, one SQLite index file that survives restarts, two
semantic engines behind one contract, a conflict ladder that the
current prompt wins, audited forgetting, and deterministic
compression of long conversations.

- **§12.1–§12.3 Contracts** — the five names verbatim
  (`MemoryProvider · MemoryRecord · MemoryQuery · MemoryScope ·
  MemoryEvidence`), the twelve §12.2 scopes, the eleven §12.3
  metadata fields, construct-time validation (bad id/scope/type/
  ∞ confidence/empty content all refused), evidence provenance
  (method vocabulary + uri/snippet — no provenance, no evidence).
- **§12.4 SQLite index** — one file, five tables (records ·
  evidence · relationships · audit · **vectors as float64 blobs**),
  WAL + explicit transactions, parameterized statements only; the
  local semantic layer persists *in the same file*.
- **§12.5 Semantic layer** — `VectorIndex` (upsert/search/delete/
  count + payload filters) with **`LocalVectorIndex`** (stdlib
  cosine, always available) and **`QdrantVectorIndex`** (MODE A
  over the official `qdrant-client`, `[qdrant]` extra — local
  persisted mode with **no server**, UUID5 point mapping, the
  single-instance lock honored via `close()`); `auto|local|qdrant`
  resolution with the honest `qdrant_probe` (absence reported,
  never faked). The embedding seam: `HashingEmbedder` (deterministic,
  Arabic intact) + `ModelEmbedder` (§5.7 routing → §5.1 request →
  llama-server `/embedding` shape; refuses without a model).
- **§12.6 Mem0 adapter** — MODE B: `Mem0MemoryProvider` wraps a
  duck-typed mem0 backend behind our contract; the NEXUS-owned side
  store keeps ids/scopes/links/audit (Plan §61); the §13.4
  behaviors adapted: extraction → the deterministic compressor,
  user/agent/run scoping → our containers (`MEM0_SCOPE_MAP`).
- **§12.7 Retrieval pipeline** — staged exactly: query → candidate
  search (vector ∪ lexical, **visibility in every stage**) →
  ranking (`0.45 semantic + 0.20 lexical + 0.15 recency (14-day
  half-life) + 0.10 confidence + 0.10 scope-fit`) → conflict
  resolution → budget-capped context assembly with honest drop
  counts and per-stage provenance.
- **§12.8 Conflict ladder** — verbatim priority (current_prompt >
  current_task > workspace_rules > project_decisions >
  user_preferences > old_lessons) with §13.7 «الجديد يفوز» as the
  recency term; **losers documented, never deleted**.
- **§12.9 Forget** — exact/category/scope tombstones + the audit
  trail (metadata kept, content dropped), container guards, the
  GLOBAL two-key wipe guard, expiry swept at every search.
- **§12.10 Compression** — the five stages verbatim; bilingual
  AR+EN extraction markers; >50 turns / >24k chars triggers; the
  compact summary linked `compressed_from` to every extraction.
- **Repository Round 9** — qdrant/qdrant **6ab21cac MODE A** (via
  the qdrant-client dist — no source, no server by default) ·
  mem0ai/mem0 **73e7b876 MODE B** (wheel optional, patterns
  adapted, zero imports) — full cycle in
  `docs/REPOSITORY-INTEGRATION.md`.
- **Bugs the proofs caught**: the vector stage leaked scope
  (visibility now enforced in *every* stage — task B could be seen
  from task A's semantic search); float32 vector drift (→ float64);
  Qdrant local-mode laws (UUID point ids → UUID5 mapping; the
  single-instance storage lock → `close()` lifecycle).
- **Exit criteria** — `tests/phase12/verify_exit_criteria.py`:
  **137/137** (126 section checks + 11 regression lines) with
  **Phases 1–11 green as subprocesses**; **`live_memory_ci.py` PASS 11/11 on the real
  Qdrant engine** (bilingual corpus, filtered retrieval, live
  conflict, forget, restart persistence) — the new CI
  **memory-live** job; the device proof `live_proof_device.py`
  deploys through the tunnel (verdict JSON to `M:\NEXUS\proofs\`).
- **Governance** — `docs/DEFERRED-WORK.md` + `docs/KNOWN-ISSUES.md`
  created per the New Plan §59/§60 discipline.
- **Version** — `nexus-core` 0.12.0, `NEXUS_PHASE = 12`, CI jobs
  "Phases 1–12" + **memory-live**.

### Added — 2026-09-07 (PHASE 11 — Vision + OCR + Screen Understanding, Plan §12)

The platform gains its **visual capability** — the eyes for the applications with no useful UI structure: locate by description, then real input; the image rides the Model Runtime's own request; and the OCR engine is chosen by a benchmark on the operator's device, not by a guess.

- **§12.1 Screen Capture** — `nexus/vision/capture.py`: **full screen · window · region** (verbatim) over one injectable GDI transport — `PrintWindow(PW_RENDERFULLCONTENT)` (DWM/occluded content) with the BitBlt fallback, **DWM extended-frame bounds** over the lying `GetWindowRect`, pure region math (clamp · intersect · refuse), the Phase-7 stdlib PNG encoder (one encoder, no imaging dep), honest refusal off win32.
- **§12.2 Vision Adapter** — `VisionProvider` = **analyze · locate · classify · compare** (verbatim) + the honest `available()` probe; `ModelVisionProvider` routes through the Phase 4 Model Runtime (`§5.7 required_capability="vision"` → `manager.generate`). **`GenerateRequest.images`** — one additive optional field (default empty: the Phase-4 text-only contract byte-for-byte) — rides llama-server's multimodal **base64 `image_data`**; pure prompt builders + tolerant parsers (prose-wrapped JSON, fences, bare bboxes, and the **UI-TARS action space** as Round 8's single REFERENCE adoption); `parse_classify` never invents a category; every degradation is honest.
- **§12.5 OCR — the benchmark decides, on the device** («اختيار OCR النهائي يجب أن يتم بالـbenchmark على جهازك»): three candidates — **winrt** (Windows.Media.Ocr, OS-native, offline) · **tesseract** (`[ocr]` extra) · **model** (the local VLM via §12.2) — all with honest probes; `character_error_rate` (Levenshtein) as the metric; the corpus is the four requirements **verbatim** (English · numbers · UI labels · documents), **drawn by the OS itself** (GDI `DrawTextW`; Pillow on CI so the machinery proves live); the winner policy is strict — lowest CER, ties → fastest, **one engine is no contest**, a >0.30-CER leader wins nothing, failures count 1.0 — the verdict is JSON for `M:\NEXUS\proofs\`.
- **The §9.5 chain gains its vision rung (4th of 5)** — `VisionLayer`: inspect → analyze; click/invoke → locate → the real router mouse click at the located center; type → locate → click → keyboard; not-found raises `LayerError` so the chain degrades to input, never silently.
- **The 14th §8.1 record** (`native:vision`, risk 1): `capture · analyze · locate · classify · compare · ocr` behind the §8.2 router; the only mutation is the path-scoped capture PNG; verification contracts bind to always-emitted keys (`path_size · report · found · category · same · text`) — the Phase-10 lesson from line one; **per-family capability honesty** (capture / inference / ocr probe separately — on Linux+tesseract the tool serves ocr while capture refuses at execute as data).
- **Integration** — `tools.vision_enabled` (additive, default true) + `tools.vision_ocr_engine` (validated: auto/winrt/tesseract/model); the runtime wires the façade + the rung + `provider_state` (shutdown unwires); `vision_enabled=false` → the Phase-10 runtime byte for byte.
- **Repository Round 8** — bytedance/UI-TARS **582f3a7 REFERENCE/BENCHMARK** (the plan's explicit ruling — never the primary model; the single adoption is the action-space parse tolerance) · xlang-ai/OpenCUA **dfc91ba RESEARCH** (studied, shelved) · simular-ai/Agent-S **3aa272d RESEARCH** (a bookmark for Plan §15) — zero imports, `nexus/vision/` is 100% stdlib-owned.
- **Bugs the proofs caught**: the discovery stage refused every vision op on Linux because the capability probe folded the surface into the GDI gate (fixed: per-family honesty — any serving family makes the tool available, a refused family fails at execute as data); the Phase-4 GenerateRequest field-set equality and the Phase-10 13/12 record counts relaxed to floors — now a house law: exact-set assertions belong to the owning phase.
- **Exit criteria** — `tests/phase11/verify_exit_criteria.py`: **118/118** (A=20 · B=30 · C=21 · D=9 · E=31 · F=17) + Phases 1–10 green as subprocesses; **+ live proofs on real pixels**: the corpus rendered (Pillow), the real tesseract race **CER 0.0** across all four categories, a full §8.2-router `ocr` roundtrip — `live_vision_ci.py` **PASS 11/11** locally and as the new CI **vision-live** job; the **device §12.5 decision run** is staged (`live_proof_device.py` + `deploy_phase11_bearer.py`) behind the bridge's trust gate (the Task-55 R4<R3 quarantine — documented, waiting, not silently skipped).
- **Version** — `nexus-core` 0.11.0, `NEXUS_PHASE = 11`, CI job "Phases 1–11" + **vision-live**.

### Added — 2026-09-07 (PHASE 10 — Browser Runtime, Plan §11)

The platform gains its **browser capability**: Playwright behind the §8.2 router (the thirteenth §8.1 record), user/agent sessions isolated by construction, and secrets that never cross the tool interface.

- **§11.1 Playwright — MODE A «USE»** (`[browser]` extra, lazy): **navigation · DOM · forms · upload · download · tabs · browser states · automation** as 26 operations through the full pipeline; the **channel ladder** (chromium → chrome → msedge) drives the operator's installed Chrome with the agent's own profile — capability with zero download tax; transfers are path-scoped; the sync API serialized behind one lock.
- **§11.2 browser-use — ADAPT, zero imports** (Round 7): the two-layer BrowserSession split, BrowserProfile → `launch_persistent_context` (persistent workflows — cookies/localStorage survive in the isolated agent profile), and the action-registry surface; the pinned-dependency audit (aiohttp · pydantic · posthog …) is the documented reason MODE A was refused.
- **§11.3 browser-harness — ADAPT** (Round 5 continued): `selfheal.py` — the selector fallback ladder (css → role → text → test_id), every attempt in a ledger, all-fail raises `SelfHealError` **carrying the ledger**, bounded retries; the editable-helpers seam maps onto the Phase-6 skills.
- **§11.4 Browser Sessions** — isolation by construction: the agent profile root is fixed and **user-profile paths are refused structurally** (the §55 guard); the user session is CDP attach behind **explicit consent + explicit URL** — no discovery, no default, never mixed; session ids ride calls and events.
- **§11.5 Authentication — the never-crossing secret**: `BrowserVault` (DPAPI `CryptProtectData` via **pure ctypes** — off win32 storing *refuses*, no plaintext downgrade); secrets enter via a **file path or env name** (the path rides events, the content never does); forms are typed via `vault_ref` — the plaintext goes into the page **only**; every output passes the vault scrubber (defense in depth).
- **The §9.5 chain gains its dom_a11y rung** — `BrowserDomLayer` (the third of five layers): click · type · set_value · inspect with a selector now resolve through the browser before vision/input; the chain stays router clients — no second gate.
- **Integration** — `tools.browser_enabled/browser_channel/browser_headless` (validated, headless default **false** — the operator sees the agent browser in parallel); the runtime wires the façade + the rung + engine shutdown; `browser_enabled=false` → Phase-9 byte for byte; the phase-8 "12 records" assertion re-expressed as forward-tolerant (nine + three present).
- **Bugs the proofs caught**: the §8.2 Verify stage flipped our own successes (contracts named keys the handler never emitted — now bound to always-present keys and exercised live); `download` file:// (request API is http-only — honest local copy + a real local-http download in the proof); a leading-/ strip broke absolute file paths; the §55 consent flag was unreachable from wiring (`set_engine_defaults(user_consent=…)`, still default false).
- **Exit criteria** — `tests/phase10/verify_exit_criteria.py`: **70/70** with Phases 1–9 as subprocesses (98 · 143 · 104 · 106 · 116 · 88 · 88 · 80 · 84); **+ `live_browser_ci.py` PASS 15/15 on a real Chromium** (navigate · DOM · fill · click · effect readback · upload · download file://+http · tabs · new/select/close · snapshot · screenshot · close — all through the router); **+ the device proof PASS**: channel=chrome, real internet navigation, two isolated sessions over CDP, the DPAPI round-trip, **14 events scanned secret-free**, and the agent Chrome window claimed as NEXUS (`win-29034352 · "NEXUS Agent Session"`).
- **Repository Round 7** — playwright USE (dist 1.62.0) · browser-use ADAPT (e25ab65) · browser-harness ADAPT (eba1021) — full §0.2 cycle in `docs/REPOSITORY-INTEGRATION.md`.
- **Version** — `nexus-core` 0.10.0, `NEXUS_PHASE = 10`, CI jobs "Phases 1–10" + **browser-live**.

### Added — 2026-09-07 (PHASE 9 — Window Manager + Human Parallelism, Plan §10)

The platform gains its **human-parallelism**: you use your machine while NEXUS works somewhere else on it. Ownership is per window — never per mouse-move (Spec §62) — and a transparent overlay with real Pause/Resume buttons watches every Computer Use.

- **§10.1 Window Registry** — `nexus.windows.registry`: the **nine fields verbatim** (`window_id · application · task_id · workspace · agent · position · size · visibility · input_owner` + documented bridge fields `hwnd · title`); `ingest()` reconciles the live `windows.list_windows` rows (now carrying **pid · process · rect · minimized** — process names via QueryFullProcessImageNameW, pure ctypes) — open/update/close diffing; **NEXUS decisions survive geometry refreshes** while machine-owned fields refuse direct writes; **the canonical `window.opened` / `window.closed` events get their first real publisher** (they have sat in the 28-event §2.2 registry since Phase 1 — still zero invented names).
- **§10.2 Window Ownership** — `nexus.windows.ownership`: **USER · NEXUS · SHARED**; assignment → best rule (process/title, priority-ordered) → **default USER** (an unclaimed window is the human's — NEXUS never assumes input it was not given); the Spec §61 example ships as the demo ruleset (War Thunder → USER · Chrome A → USER · Chrome B → NEXUS · PowerPoint → NEXUS); `claim()` stakes a window with the full task binding (`task_id · workspace · agent`).
- **§10.3 Human/AI Input Arbitration** — `nexus.windows.arbitration`: per-window verdicts with reasons (USER → **deny**, NEXUS → allow, SHARED → allow+coordinated, unknown → **deny by default**, relaxable `unknown_policy`); `as_hook()` installs the arbitrator on the Phase-6 `pre_tool_call` veto seam (only input tools: mouse · keyboard · uia · windows; target from `hwnd` else `x`/`y` via `WindowFromPoint`); the runtime wires it automatically when the harness runs — the §8.2 router stays the only gate for effects.
- **§10.4 Multiple Monitors** — `nexus.windows.monitors` + additive tool ops: `screen.monitors` (EnumDisplayMonitors + GetMonitorInfoW/MONITORINFOEXW — **risk 1, read-only**) and `windows.geometry/move` (GetWindowRect · MonitorFromWindow · IsIconic · SetWindowPos with SWP_NOZORDER — `move` is a mutating op for the §8.2 Scope stage); `MonitorLayout`: `snapshot() · monitor_for_window() · place()` with **pure placement math** (center/top-left/bottom-right, work-area clamping, never the taskbar — CI-testable anywhere); negative virtual-desktop coordinates honored (a portrait monitor left/right of primary).
- **§10.5 Overlay** — `nexus.windows.overlay`: the Spec §63/§154 box verbatim — "NEXUS is working" + `[Pause] [Resume]`, **شفاف وبسيط**: a real Win32 window in **pure ctypes** (`CreateWindowExW`, WS_EX_LAYERED|WS_EX_TOPMOST|WS_EX_TOOLWINDOW, alpha 235, GDI paint with a state bar, two real BUTTON children); message loop in a daemon thread, cross-thread pokes via `PostMessage`; the controller is the platform-neutral machine **IDLE → WORKING ⇄ PAUSED** (illegal transitions raise `OverlayError`), audits every transition (from/to/origin) and fires `on_pause/on_resume` **only on the human button path** (the §155 emergency surface); honest headless backend off win32; a dismissed overlay can be born again (thread handle reset).
- **Two real bugs the device caught** (the Phase-8 pointer lesson repeated): (1) `DefWindowProcW` without `argtypes` overflows on pointer-sized LPARAM (WM_NCCREATE's CREATESTRUCT*) → the swallowed exception returns 0 → **the window dies at birth silently** — fixed with explicit argtypes/restype for DefWindowProcW · PostMessageW · CreateWindowExW · FindWindowW; (2) `place()` read the geometry rect's (right, bottom) as (w, h) and resized instead of moving — `_current_geometry()` now returns computed (l, t, w, h).
- **Integration seams (real, proven)** — `ToolsConfig.windows_enabled` (additive, default true; `false` or computer off → the Phase-8 runtime **byte for byte**); `NexusRuntime.window_manager` built over the live ComputerRuntime at wiring time (§0.4 lazy import); the §10.3 veto registered on the harness hooks; shutdown dismisses the overlay first; **no 13th tool record** — the manager is policy, the `windows`/`screen` records grew *operations* additively (12 records still).
- **Repository Round 6 — NEXUS-native by plan**: §10 names no external repositories (user32/GDI/messaging are OS-native); the hook seam (Round 3) and input-transport lessons (Round 5) were already absorbed — zero imports, zero staging clones.
- **Exit criteria** — `tests/phase09/verify_exit_criteria.py`: **84/84 checks** (A=17 · B=12 · C=15 · D=13 · E=13 · F=14) with Phases 1–8 re-run as subprocesses (98 · 143 · 104 · 106 · 116 · 88 · 88 · 80); **+ live proofs on the operator's box** (`tests/phase09/live_proof.py` — **PASS**): 16–17 real windows with real process names (War Thunder itself on screen), both arbitration verdicts + a live hook veto, **two real monitors** (1680×1050 primary + 1050×1680 portrait at (1680,−379)), a real SetWindowPos placement verified inside the work area, and the native overlay **appearing, repainting on pause, and dismissing** — evidence PNGs + JSON under `M:\NEXUS\proofs\`.
- **Version** — `nexus-core` 0.9.0, `NEXUS_PHASE = 9`, CI job "Phases 1–9".

### Added — 2026-09-07 (PHASE 8 — Windows Computer Runtime, Plan §9)

The platform gains its **computer hands**: the §9.1 Computer API (eight domains, every one a thin router client — the §8.2 pipeline is the only choke point), the §9.5 fallback hierarchy (Application API → UIA → DOM/a11y → Vision → Mouse/Keyboard, every attempt recorded), and three mechanics tools (mouse · keyboard · uia) registered additively beside the §8.3 nine.

- **§9.1 Computer API** — `nexus.computer.api.ComputerRuntime`: **screens · windows · focus · mouse · keyboard · clipboard · uia · processes** verbatim; each domain method routes through `ToolRouter.route(...)` (policy → confirmation → scope → resources → execute → normalise → verify) — **no second choke point, zero new event names**; `capability_report()` probes all eight domains + the hierarchy; the convenience `act("invoke:131074")` string form parses or refuses.
- **§9.5 Fallback Hierarchy** — `nexus.computer.hierarchy`: the five layers **verbatim and ordered**; unregistered layers degrade honestly (that *is* the design); `None` = unsupported → fall through; `LayerError` = tried-and-failed → fall through; first success wins and is stamped with its layer; all-fail → `HierarchyError` carrying the **full attempt ledger**; DOM/a11y and Vision honestly unavailable until their phases ship.
- **§9.4 Native UIA client** — `nexus.computer.uia_native`: pure **ctypes COM** (no comtypes, no pywin32): `IUIAutomation` root/ElementFromHandle/GetFocusedElement/CreateTrueCondition→FindAll (bounded BFS: depth ≤ 8, nodes ≤ 500); element properties (ProcessId · ControlType · Name · IsEnabled · ClassName · BoundingRectangle via VARIANT r8 SAFEARRAY); **Invoke** and **Value** patterns; every HRESULT checked and raised in hex; BSTRs freed, SAFEARRAYs destroyed, AddRefs Released, COM apartment inits **owned-paired** per thread; off win32 every probe refuses honestly.
- **§9.2 Input transports (ADAPT from windows-harness 46a37cf, MIT, zero imports)** — `nexus.computer.input_engine`: the **foreground** transport (SetForegroundWindow + AttachThreadInput assist + input nudge, then real SendInput) and the **background** message transport (`WM_CHAR` per UTF-16 unit, never activates); **message-transport mouse refused by design** (Chromium/WPF/UWP discard posted clicks — no silent no-ops); `ForegroundError` ≠ `TransportRefusedError` — the error never lies about which failure happened.
- **SendInput packing leaf** — `nexus.tools.native._sendinput`: INPUT/MOUSEINPUT/KEYBDINPUT with **explicit-width fields** (`c_int32`/`c_uint32`/`c_size_t` — a real bug caught on linux: naive `c_long` gives sizeof(INPUT)=56, the winuser truth is 40); absolute mickey normalisation over the **virtual** screen (injectable for purity); hotkey combos (down…up, modifiers released reversed); unicode typing with surrogate pairs as *adjacent downs then ups*; wheel data = units×120; honest `InputError` bounds everywhere (4096 chars, ±1000 units, 256 drag steps).
- **§9.1 mechanics tools** — `nexus.tools.native.mouse` (move · click · double/right/middle · drag · scroll — **risk 3**, `input.inject` permission), `keyboard` (press combo · type unicode — **risk 3**), `uia` (inspect · element · focused · invoke · set_value · focus — **risk 2**, `uia.read`/`uia.control`); platform-honest probes; strict `ToolArgError` coercion.
- **§9.3 pywinauto backend — MODE A «USE»** — `nexus.computer.adapters.pywinauto_backend` (BSD-3-Clause, pinned 18d2a95, optional **`[computer]` extra**): deep UIA control matching, `type_keys` into a specific control, window listing — imported **lazily per method** (the harness source-verifies no module-level pywinauto import in `nexus/`), honest probe, every failure wrapped in `BackendError`.
- **Integration seams (real, proven)** — `build_tool_system(computer=True)` registers the three records **additively** (default stays Phase-7 nine-only for direct callers); `NexusRuntime` wires `ComputerRuntime` over the live router when `tools.computer_enabled` (new additive key, default true; `false` → the Phase-7 runtime byte for byte); the §7.1 `pre_tool_call` veto still guards every computer effect.
- **Repository Round 5** — `browser-use/windows-harness` (ADAPT, 46a37cf — the transport contract + honest-refusal policy rewritten, zero imports) · `pywinauto/pywinauto` (MODE A, 18d2a95) — full §0.2 cycle in `docs/REPOSITORY-INTEGRATION.md`.
- **Exit criteria** — `tests/phase08/verify_exit_criteria.py`: **80/80 checks** (A=14 · B=12 · C=12 · D=17 · E=5 · F=20), crash-injection fallback, platform-honesty sweeps, structure byte-exactness, and Phases 1–7 re-run as subprocesses (98 · 143 · 104 · 106 · 116 · 88 · 88); **+ live Windows proofs on the operator's box** (focused element via the native client, the full harness run ON the device, live domain evidence) — see `docs/PHASE-8-REPORT.md`.
- **Version** — `nexus-core` 0.8.0, `NEXUS_PHASE = 8`, CI job "Phases 1–8" (installs `pywinauto` for pyright).

### Added — 2026-09-07 (PHASE 7 — Tool System, Plan §8 / Spec §71)

The platform gains its **tool spine**: every capability — native or MCP — enters as one §8.1 record behind one §8.2 choke point: gated, scoped, resourced, executed, normalized and **verified**. The Phase-5 `ToolSink` aperture is finally filled; the Phase-6 `pre_tool_call` veto still guards it.

- **§8.1 Tool Registry** — `nexus.tools.registry` + `nexus.tools.models`: the **nine fields verbatim** (id · name · description · input_schema · output_schema · permissions · scope_requirements · risk · verification · version); risk rides the 0..4 danger scale and **level 4 is refused at registration**; strict `X.Y.Z` versions with upgrade-only replacement (no silent replaces); freezable; discovery filters (permission tag · scope dimension · capability availability); honest `CapabilityReport` probes per platform.
- **§8.2 Tool Router** — `nexus.tools.router`: the **verbatim seven-stage pipeline** (discovery → permission → scope → resource → execute → normalize → verify) with an **ordered proof trace on every call**; the §8.1 risk gate is config-level (policy-independent: above `tools.confirm_danger_above` a human confirms, always); all gate confirmations fold into ONE request (approve/deny/no-hook — a missing hook refuses honestly); the Phase-2 PolicyEngine composes permission+scope (blocked tools · OBSERVE/SUGGEST autonomy · §3.4 escalate-never-wall on out-of-scope paths · network host gates); the Phase-3 ResourceManager supplies the concurrency resource gate (released in `finally`, exhausted → honest refusal); the **Verify stage runs the §8.1 contract and flips lying outcomes** (path_exists · path_size · output_nonempty · exit_zero · text_contains · json_field · none); canonical `tool.called/completed/failed` events on direct routes while the §6.2 loop keeps ownership on its path — **zero duplicates, zero new event names**.
- **§8.3 Native Tools (nine, stdlib)** — `nexus.tools.native`: **filesystem** (10 ops, per-op verification, 2 MiB read bound, workspace-root resolution) · **terminal** (list-argv only — never a shell string; hard timeout 1..300s; honest 124/127; risk 3) · **process** (list/info/kill with the psutil→/proc degradation ladder) · **hardware** (snapshot/cpu/disk — ctypes GlobalMemoryStatusEx on Windows, /proc on Linux; risk 0) · **windows** (user32 window control via ctypes — no pywin32) · **clipboard** (win32 ctypes / xclip / wl-clipboard ladder) · **screen** (GDI capture + a **stdlib PNG encoder** — zlib+struct IHDR/IDAT/IEND) · **git** (six list-argv ops over a scope-checked repo) · **github** (REST via urllib; offline-provable `build_request`; token from `NEXUS_GITHUB_TOKEN`, never echoed). Platform-honest everywhere: unavailable ≠ faked.
- **§8.4 MCP — the official SDK, USE'd behind the router** — `nexus.tools.mcp.adapter`: the **official Python SDK v2 stable line** (`mcp>=2.0,<3` @ 2.1.1, MIT, MODE A optional extra `[mcp]`): one session thread per server (asyncio loop + `run_coroutine_threadsafe` bridging, per-server call timeout), `initialize` → `tools/list` → each MCP tool registered as a §8.1 record (`mcp.<server>.<tool>`) with the server's risk-ceiling clamp and verification `none` (§71: an external server's claim is not evidence); `tools/call` normalized; **honest failure & recovery** — a crashed session fails that call (no silent retry that could double-apply a mutation) and the *next* call respawns the transport. v2 API deltas recorded: `FastMCP`→`MCPServer`, `isError`→`is_error`.
- **§8.5 MCP Servers — five, gated before any stdio byte** — `config/tools/mcp.toml`: filesystem · git · fetch · memory · database (sqlite), each with `risk_ceiling`, `allowed_tools`/`blocked_tools` (a blocked tool **never even registers**) and `scope_paths` (path arguments the Scope stage checks); all disabled by default (per-machine opt-in — "clone only what the task needs"); per-server honest failure (a broken server never breaks the boot). **Bonus proof: the official TypeScript filesystem server via npx — write through MCP → read back through the native tool (cross-SDK roundtrip).**
- **Integration seams (real, proven)** — `RoutedToolSink(ToolRouter)` fills the §6.2 `ToolSink` aperture (the loop dispatches `call_tool` decisions through the full pipeline; the verification note rides the output); `NexusRuntime` wires registry + router + sink into the Master Agent (`tools.native_enabled/mcp_enabled` additive config keys; disabled → the Phase-6 runtime byte for byte); shutdown closes MCP sessions before models/repository.
- **Repository Round 4** — `modelcontextprotocol/python-sdk` (MODE A, dist 2.1.1 + clone 08a3bc8) · `modelcontextprotocol/servers` (d73f99e — MIT→Apache-2.0 transition documented per-file) · `modelcontextprotocol/servers-archived` (9be4674, the sqlite server) — full §0.2 cycle in `docs/REPOSITORY-INTEGRATION.md`.
- **Exit criteria** — `tests/phase07/verify_exit_criteria.py`: **88/88 checks** (A=16 · B=20 · C=22 · D=16 · E=8 · F=6) **+1 bonus**, including crash-injection recovery, blocked-before-stdio gates, the cross-SDK roundtrip, the loop/veto integration, and Phases 1–6 re-run as subprocesses (98 · 143 · 104 · 106 · 116 · 88). Fixture: `tests/phase07/mcp_echo_server.py` (a real v2 `MCPServer` with echo/add/boom/die tools).
- **Version** — `nexus-core` 0.7.0, `NEXUS_PHASE = 7`, CI job "Phases 1–7" (installs `mcp>=2.0,<3` for the Phase-7 step).

### Added — 2026-09-07 (PHASE 6 — Harness Integration, Plan §7 / Spec §41)

The platform gains its **harness layer** — the §41 contract that gives the model context, tools, memory, task state, rules, skills and observations and reads back action, tool_call, delegation, decision. Five ecosystems studied, **zero imports** (the §275 Super-Harness rule), stdlib-only, and **no new event names** (`checkpoint.created` was already canonical).

- **§7.1 Skills (ECC pattern, MODE B)** — `nexus.harness.skills`: the `Skill` record (6 fields) + `SkillLibrary` loading SKILL.md files from `<root>/skills` (directory + flat forms, YAML-ish frontmatter: name/description/origin/enabled + instruction body); keyword matching curates candidates per directive; malformed files skip with a warning (a bad skill never breaks boot).
- **§7.1 Rules (ECC pattern, MODE B)** — `nexus.harness.rules`: the `Rule` record (priority 0–100 clamped, scope tags, enabled) + `RuleSet` compiling the binding section ordered by priority; the `security` scope subset is the curation hook; rules load from `<root>/rules`.
- **§7.1/§7.2 Hooks (ECC + Cline pattern, MODE B)** — `nexus.harness.hooks`: the **eight-point registry** (session_start/end · task_start/end · agent_start/end · pre/post_tool_call); handlers fire synchronously, **only `pre_tool_call` may veto** (a `False` return blocks the tool — the sink never sees it); bus-driven points bind to canonical §2.2 events; a raising handler is logged (or propagates under `hooks_strict`).
- **§7.2 Sessions (Cline pattern, MODE B)** — `nexus.harness.session`: the five-state machine CREATED→ACTIVE⇄PAUSED→RESUMED→CLOSED (CLOSED terminal; illegal transitions raise), atomic `harness/sessions.json` ledger with sequence-seeded ids, `latest_open` as the resume target; the master fires session_start/session_end around `handle()`.
- **§7.3 Checkpoints (LangGraph pattern, MODE B — USE rejected on the record)** — `nexus.harness.checkpoint`: `Durability` NONE/MEMORY/DISK; the `Checkpoint` record (6 fields); per-task retention pruning; atomic JSONL append; **event-driven auto-checkpoint on every task lifecycle transition**, publishing the canonical `checkpoint.created`; `resume(task)` answers the last state (None → cold start). A literal langgraph USE would break stdlib-only + §0.5 — documented decision.
- **§7.4 Goals + Heartbeats (Prime pattern, MODE D+B)** — `nexus.harness.goals`: the `Goal` record (4-state lifecycle + append-only progress log) + `GoalStore` (atomic, reboot-persistent, goals outlive tasks and ride the context) + `Heartbeat` (record/last/stalled — unknown ≠ stalled). The full heartbeat system stays Plan §23.
- **§41 Contract** — `nexus.harness.context`: `HarnessInputs` (**seven fields verbatim**: context tools memory task_state rules skills observations) · `HarnessOutputs` (**four verbatim**: action tool_call delegation decision) · the `Harness` assembler (rules always bind; skills match; goals ride; the memory snapshot is the honest §6.1 policy view) + `parse_outputs` mapping the §6.2 decision into the §41 outputs.
- **Integration seams (real, proven)** — `AgentLoop` takes an optional `harness` (context section in the CONTEXT phase; pre/post tool hooks at the dispatch seam) — the harness section is **in the recorded model prompt**; `MasterAgent` passes the harness to every worker loop and fires the session lifecycle; `NexusRuntime` wires the full stack (7 accessors) and `harness_enabled=false` unwires everything — the Phase-5 runtime, byte for byte.
- **Config** — `AgentsConfig` additive keys `harness_enabled` / `checkpoint_retention` (1..4096) / `hooks_strict`, documented in `config/agents/agents.toml`; §2.1/§6 trees fully backward compatible.
- **Repository Round 3** — five fresh pins in `vendor-staging/` (ecc e04ea0b · cline c21b172 · langgraph 81bf17b · prime-agent 2ce4431 · deepagents 07d2952), each with the full §0.2 cycle in `docs/REPOSITORY-INTEGRATION.md`; `rg "from (ecc|cline|langgraph|prime|deepagents)" nexus/` → zero hits.
- **Governance** — `CONTRIBUTING.md` now carries the **mandatory 18-step sub-phase cycle** (operator directive, effective Phase 6+).
- **Exit criteria** — `tests/phase06/verify_exit_criteria.py`: **88/88 checks** (A=11, B=7, C=12, D=14, E=11, F=33) including the veto proof, the prompt-reach proof, the event-driven checkpoint proof, the disabled-runtime proof, the event-name guard (⊆ 28), and Phases 1–5 re-run as subprocesses (**98/98 · 143/143 · 104/104 · 106/106 · 116/116**).
- **Version** — `nexus-core` 0.6.0, `NEXUS_PHASE = 6`.


### Added — 2026-09-07 (PHASE 5 — Agent Runtime, Plan §6)

The model becomes an agent — **stdlib-only, the Master Agent and Agent Registry wholly NEXUS-owned (§0.5), and no new event names** (agent/tool/verification/task events all come from the §2.2 registry of 28).

- **§6.1 Agent Abstraction** — `nexus.agents.agent`: the `Agent` record with the **eight fields verbatim** (`id role instructions capabilities tools memory_policy model_policy verification`) + the three typed policies NEXUS owns: `MemoryPolicy` (read/write namespaces, retention on the §2.3 ladder task/conversation/user), `ModelPolicy` (explicit registry id or §5.7 routing inputs + generation limits), `VerificationPolicy` (required flag, named criteria, bounded repairs). Fixed master identity `ag_master0000` + `ag_`+12hex ids.
- **§6.2 Agent Loop** — `nexus.agents.loop`: the cycle **verbatim, seven phases, traced per turn** (`LOOP_PHASES`: observe → context → decide → act → observe → verify → continue — a `LoopStep` audit trail proves the order). Strict decision contract (`parse_decision`, pure): one balanced JSON object, action enum `respond/call_tool/delegate/done/failed`, per-action required keys, confidence clamped 0..1 — a violation gets **one corrective retry**, then honest failure. `ToolSink`/`InlineToolSink` is the seam the Tool-Router phases plug into; tool acts are bounded by the agent's own tool list; the verify gate runs every turn (act integrity) and in full (verifier callable or structural policy check) when the agent decides `done`, with bounded repairs. Events: `agent.started/completed/failed` + `tool.called/completed/failed`.
- **§6.3 Master Agent** — `nexus.agents.master`: the **seven behaviors verbatim** (user-facing entry · understand · distribute · follow · receive · decide continuation · decide reaching Verification), driving the §2.4 machine through the injected `TaskEngine`: CREATED→ANALYZING→PLANNING→EXECUTING→VERIFYING→COMPLETED with bounded REPAIRING; subtasks land on the §2.5 `task.plan.steps` (PlanStep records); the model verdict lands on `task.verification` (VerificationCheck list); `task.agents` records everyone who worked; agent slots honor `agents.max_parallel` via the Phase-3 ResourceManager. Three strict model contracts (understanding/plan/verdict) with the same one-retry discipline. Honest failure everywhere: early model failure → legal CANCELLED + recorded error (`master.understanding_failure` / `master.planning_failure`); exhausted verification repairs → COMPLETED with `success=False` — never a fake pass.
- **§6.4 Agent Registry** — `nexus.agents.registry`: the **four verbs verbatim** (registerAgent/unregisterAgent/discoverAgents/getCapabilities, snake_case per codebase convention), atomic persistence (`agents.registry.json` under `NexusPaths.data`, temp+`os.replace`+`fsync`), reboot reload, **open roster** (register/drop freely), master record seeded idempotently and protected from unregistration, corrupt files degrade to an empty start (never a dead boot).
- **§6.5 Agent Communication** — `nexus.agents.messages`: the `AgentMessage` record with the **eight fields verbatim** (`task_id sender receiver type status data evidence confidence`) + closed type vocabulary (task/progress/result/question/coordination/error), delivery lifecycle sent→delivered→read, per-agent mailboxes, broadcast `*`, `Evidence` items (kind/source/detail), confidence clamped 0..1, a structured per-task log, and an append-only JSONL transcript (`tasks/<task_id>.messages.jsonl`) next to the task record when `agents.message_log_enabled`.
- **§6.6 Agent Ownership** — `nexus.agents.ownership`: the record is **`resource` + `owner`, verbatim**; `acquire` is idempotent per owner and raises `ResourceOwnedError` carrying the current holder for anyone else — the loop converts that into a `coordination` message and a re-decide (bounded by the turn budget): **coordination instead of collision, never a silent overwrite**. `release_owner` at loop teardown, `clear()` at runtime shutdown. In-process by documented scope (the engine is single-threaded by Phase-1 design); cross-process locking joins the tool phases on the same §6.6 contract.
- **Integration** — `NexusRuntime` wires `agent_registry` / `communicator` / `ownership` / `master_agent` (None when `agents.master_agent_enabled=false`); boot payload `phase: 5`; shutdown releases every ownership entry before unloading models; `AgentsConfig` gains the additive keys `loop_max_turns` (1..256) / `master_repair_limit` (0..16) / `message_log_enabled` (defaults — §2.1 tree backward compatible, 98/98 proves it). Import-order safety documented in `master.py` (lazy core vocabulary — no partially-initialized-module cycle when `nexus.agents` imports first).
- **Repository Round 2 (MODE D references)** — `vendor-staging/` gains the Phase-5 reference clones (langchain-ai/langgraph · microsoft/autogen · langchain-ai/deepagents) studied for the loop/registry/delegation **patterns**; zero imports from their code (§0.4/§0.5 + the pre-written watchlist). Pins and the §0.2 cycle records in `docs/REPOSITORY-INTEGRATION.md`.
- **Exit criteria** — `tests/phase05/verify_exit_criteria.py`: **116/116 checks** (A=13, B=29, C=24, D=12, E=16, F=22) — trace-order proof of the seven phases, the strict parsers, the conflict→coordination path, the full master choreography + repair ladder + honest failures, registry persistence/reboot, the message lifecycle + transcript, ownership semantics, the runtime wiring, the event-name guard (⊆ the 28), and Phases 1–4 re-run as subprocesses (**98/98 · 143/143 · 104/104 · 106/106**).
- **Fixed** — `.github/workflows/ci.yml` carried a byte-level corruption since PHASE 0 (`branches: ain, develop]` instead of `[main, develop]` in both triggers); repaired, and the python-quality job now runs the Phase-5 harness ("Phases 1–5").
- **Version** — `nexus-core` 0.5.0, `NEXUS_PHASE = 5`.

### Added — 2026-09-07 (Repository Integration Round 1 — Plan §0.2/§0.3)

The «الباقي من المستودعات» principle gets its first full §0.2 intake cycle: battle-tested engines enter **under NEXUS-owned interfaces** (§0.4), with licenses audited, versions pinned, and a live proof against the real thing. Permanent record: `docs/REPOSITORY-INTEGRATION.md`.

- **ggml-org/llama.cpp — MODE B (ADAPT), pinned b10829 / commit 5fdfa628** — the audited shallow clone lives in `vendor-staging/` (gitignored); MIT license recorded. The adapter's wire contract was verified against the **real llama-server binary** (official release asset, ubuntu-x64): `/health` → `{"status":"ok"}`, `/completion` → `content` + `timings` (`prompt_n/prompt_ms/predicted_n/predicted_ms`), SSE `data:{json}` deltas ending in a `stop:true` event with empty `content`. Windows deployment path documented (win-cpu / win-vulkan / win-cuda release assets).
- **Live integration proof** — `tests/phase04/integration_llama_server.py` (opt-in; CI keeps the fake chain): **26/26 checks** against the real server with **Qwen3-0.6B-Q8_0.gguf** (first-pool member, Apache-2.0, 639 MB) — load/health/generate/stream/benchmark/manager-cycle/unload, with a measured profile (147.5 tok/s prompt · 29.7 tok/s generation · **1588 MB real RSS** · stability 1.0).
- **Fixed (live-proof catch): the port disagreement bug** — `load()` built the argv with `--port 0` while `LlamaServerProcess` polled a different self-chosen port: the real server bound an unknowable ephemeral port and the adapter waited forever (alive-but-unreachable). `LlamaServerProcess._resolve_port()` now guarantees argv and endpoint agree (explicit `--port>0` wins; otherwise the chosen port is written back into the argv). Fake-server tests structurally cannot catch this — the live proof can, and did.
- **giampaolo/psutil — MODE A (DIRECT USE), pinned 7.2.2 / commit 9eea97d** — BSD-3-Clause, optional dependency `nexus-core[hardware]` (`psutil>=7.2,<8`), lazily imported, stdlib floor preserved (CI runs without it):
  - `resident_memory_mb()` — new concrete-base member on `ModelProvider` (like `loaded_ids`, not one of the §5.1 seven): the llama-server process's real RSS, duck-typed so fakes report honest `None`;
  - **§5.4 load now corrects estimate → observed reality** (Spec §135 «نتائج الجهاز الحقيقي بدل التخمين»): the budget gate still runs on the registry estimate (§91/§92), and the `LoadedModel` record + ResourceManager accounting carry the real footprint after load — proven live (1588 MB vs the 700 MB estimate);
  - `process_rss_mb()` cross-platform (Windows previously returned `None`); POSIX scanner `max_clock_mhz` no longer `None`.
- **Windows companions documented** — `pyproject.toml [project.optional-dependencies].windows` with platform markers: `pywin32` / `wmi` / `pynvml` (installable and testable only on the user's box).
- **vendor-staging/README.md** — the staging dir's intake rules + exact re-clone commands for every pin.
- **Gates** — ruff clean · pyright 0 errors · **98/98 · 143/143 · 104/104 · 106/106** regressions · **26/26 live**.

### Added — 2026-09-06 (PHASE 4 — Local Model Runtime, Plan §5)

Local intelligence enters the machine — **stdlib-only, the manager independent of any backend, and no new event names** (only the four §2.2 model events are published; the 28 registry stays the single authority).

- **§5.1 Model Abstraction** — `nexus.models.provider`: the `ModelProvider` interface with the **seven members verbatim** (`load unload generate stream health capabilities benchmark`) plus the NEXUS Model API contracts: `GenerateRequest` (system · prompt · sampling · stop · seed · auto-load), `GenerateResult` (text + prompt/generation token & second accounting), `StreamChunk` (deltas; the final chunk carries the stats), `ProviderHealth`, `LoadInfo`, and the `ProviderError` hierarchy. Spec §137's chain is literal: NEXUS Model API → llama.cpp Adapter → llama-server → Model.
- **§5.2 Model Registry** — `nexus.models.registry`: the `Model` record with the **twelve fields verbatim** (`id name format backend size context capabilities ram vram language benchmark status` + RAM/VRAM in MB · size in bytes) and two documented auxiliary fields (`path`, bounded `benchmark_history`); `ModelRegistry` with atomic persistence (`models.registry.json` under `NexusPaths.models`), the `ModelStatus` lifecycle, and an **open pool** — register and drop freely.
- **§5.3 llama.cpp Integration** — `nexus.models.llamacpp`: the Adapter over **ggml-org/llama.cpp** `llama-server`: argv builder (`-m -c --host --port -ngl -t` + KV-Q4 `-ctk/-ctv` from the §88 device learnings + explicit extras), process driver (Windows `CREATE_NO_WINDOW`, OS free-port pick, `/health` ready-poll, terminate→wait→kill), stdlib HTTP (`/completion` + SSE), pure encode/parse functions, and a clear `ProviderError` when the binary is absent — the core imports and boots without llama.cpp.
- **§5.4 Dynamic Loading** — `nexus.models.manager`: the five verbs verbatim — `select` (router with live budgets) · `load` (predictive budget gate → LRU idle eviction → provider load → allocation → events; refusal only when hosting is impossible — Spec §91/§92) · `run` (`generate`/`stream` with auto-load) · `keep_warm` (per-model TTL + `unload_idle`) · `unload` (provider + allocation release). `apply_pressure` reacts to the §92 ladder; `shutdown` releases everything.
- **§5.5 Model Benchmarking** — `nexus.models.benchmark`: the **seven fields verbatim** (`warmup prompt_speed generation_speed context ram vram stability`) + provenance; `run_benchmark` follows the **Spec §135 order verbatim** (Load → Warm-up → Prompt → Generation → Context → Memory → Stability → Register profile), and the manager wraps it in the §5.4 resource discipline.
- **§5.6 MiMo Edge Profile** — `nexus.models.mimo`: the five models verbatim (Qwen2.5-Coder-1.5B · LFM2.5-1.2B · Qwen3-0.6B · DS-Coder-1.3B · Yi-Coder-1.5B) seeded with **the user's measured results** (9.57 · 7.54 · 11.66 · 29.14 tok/s @ ctx 8192 — Spec §88; Yi honestly awaits its on-device run). Idempotent seeding, never fixed: «هي أول Model Pool فقط».
- **§5.7 Model Router** — `nexus.models.router`: the **six inputs verbatim** (task type · complexity · required capability · RAM · VRAM · current workload) → **selected model id**; Spec §87 filters then the **Spec §178 score verbatim** (task fit + capabilities + RAM + VRAM + latency + context + observed reliability); complexity blends depth-over-cheapness; unbenchmarked models never outrank measured ones (Spec §135's «بدل التخمين»); §136 examples proven; no vision/speech model → honest `None` + reason.
- **Reference backend** — `nexus.models.simulated.SimulatedProvider`: deterministic in-process provider — the whole §5 stack runs CI-green without llama.cpp.
- **Integration** — `NexusRuntime.boot(model_provider=…)` wires the ModelManager (llama-server only ever starts on an explicit load); first boot seeds the §5.6 pool once and the registry persists across reboots; shutdown unloads every resident model; payload `phase: 4`; `ModelsConfig` gains the additive keys `llama_server` / `llama_host` / `llama_port` / `keep_warm_seconds` (defaults — the §2.1 six-section tree stays backward compatible, 98/98 regression proves it).
- **Exit criteria** — `tests/phase04/verify_exit_criteria.py`: **106/106 checks** (A=12, B=17, C=16, D=22, E=8, F=31) including the full fake-llama-server chain, the §135 order audit, the §92 pressure reactions, two-boot persistence, the event-name guard, and Phases 1–3 re-run as subprocesses (**98/98 · 143/143 · 104/104**).
- **Version** — `nexus-core` 0.4.0, `NEXUS_PHASE = 4`.

### Added — 2026-09-06 (PHASE 3 — Hardware Intelligence + Resource Manager, Plan §4)

The machine now knows itself: **stdlib-only, Windows system libraries per §4.6, no agent framework, and no new event names** (the §2.2 registry of 28 stays the single authority).

- **§4.1 Hardware Scanner** — `nexus.resources.scanner`: the twelve detection targets verbatim (`CPU GPU VRAM RAM Storage Displays Resolution Windows Network Devices Installed software Processes`). `WindowsScanner` via ctypes (GlobalMemoryStatusEx · GetLogicalDrives/GetDriveTypeW · screen metrics), winreg (CPU name · 64-bit GPU VRAM `qwMemorySize` · edition · uninstall hives ×3), PowerShell CIM (processor/GPU+current resolutions/network adapters/PnP devices) and `tasklist` processes; `PosixScanner` (procfs/sysfs); `StaticScanner` for harnesses; `default_scanner()` platform pick. Every probe best-effort — a failing category degrades to empty, never an exception.
- **§4.2 Hardware Profile** — `nexus.resources.profile`: typed profile + 10 entry models, persisted as `hardware_profile.json` under `NexusPaths.data` with the §2.5 atomic discipline (temp + `os.replace` + `fsync`), envelope `nexus.hardware.profile` v1. **System data — never model memory.**
- **§4.3 Change Detection** — `nexus.resources.changes`: previous-vs-current diff (RAM/GPU/Storage/display major · drivers/OS-release/software-set minor, "where detectable"), hardware fingerprint that deliberately excludes volatile categories.
- **§4.4 Resource Manager** — `nexus.resources.manager`: tracks the **eight §4.4 items verbatim** (cpu · ram · gpu · vram · disk · concurrency · model_memory · agent_count) — capacities from the profile, exact allocations (per-model memory/VRAM, agents, concurrency slots, background units), injectable best-effort utilization samplers, budgets (75% RAM · 90% VRAM · cores · 4096 MB disk floor · `agents.max_parallel` from the §2.1 config), pressure thresholds LOW 0.70 / MEDIUM 0.85 / HIGH 0.95 / CRITICAL >1.0, JSON snapshots.
- **§4.5 Resource Policies** — `nexus.resources.policies`: the plan's mappings verbatim (RAM → reduce concurrency · VRAM → unload/switch · CPU → reduce background) running on the **Spec §92 ladder verbatim**: reduce concurrency → unload idle model → switch smaller model → reduce context → **continue**. One deduped recommendation per action; no abort action exists — نُبطئ، لا نُفقد المهمة.
- **Integration** — `NexusRuntime.boot(hardware_scanner=…)` wires the ResourceManager; boot loads the persisted profile but never scans (explicit `refresh_profile()` = scan → diff → persist); payload `phase: 3`; `agents.max_parallel` honored as `max_agents`.
- **Exit criteria** — `tests/phase03/verify_exit_criteria.py`: **104/104 checks** (A=14, B=14, C=14, D=33, E=17, F=12) including a **real platform scan** (six live WindowsScanner proofs activate on the Windows box) and the Phase 1–2 harnesses re-run as subprocesses (**98/98 · 143/143**).
- **Version** — `nexus-core` 0.3.0, `NEXUS_PHASE = 3`.

### Added — 2026-09-06 (PHASE 2 — Workspace + Scope + Policy, Plan §3)

The concept is locked: **Full Control within Task Scope** — stdlib-only, zero new dependencies, and **no new event names** (the §2.2 registry of 28 stays the single authority).

- **§3.1 Workspace Manager** — `nexus.core.workspace`: `Workspace` with the seven fields verbatim (`id name path project memory_namespace git_repository settings`), `wsp_` identities, unique names, atomic JSON registry (`nexus.workspaces.registry` v1 under `NexusPaths.workspaces`, temp + `os.replace` + `fsync`), longest-root path resolution, synthetic default honoring `config.workspaces.default_workspace`.
- **§3.2 Scope Engine** — `nexus.core.scope.models`: `Scope` with the six dimensions verbatim (`filesystem_paths applications browser_sessions network_permissions tools repositories`), coverage checks (paths, wildcard hosts, tools/apps/sessions/repos), merge algebra, and the `Task.scope` mapping bridge (`to_scope_map`/`from_scope_map`).
- **§3.3 Scope Resolution** — `nexus.core.scope.engine`: natural-language resolution with recorded confidence — path token (1.0) → workspace name, word-boundary matched (0.8) → project label (0.7) → default (0.3). The plan example **"اشتغل على M:\Client" → workspace Client, filesystem scope M:\Client** is proven verbatim in the harness.
- **§3.4 Cross-workspace Access** — never an absolute block: `request_cross_workspace` grants access by design, carves a keyword-matched sub-scope (with or without a path lister), returns an audit `CrossWorkspaceAccess`, never merges histories (Spec §21); unregistered targets are nonexistence, not denial.
- **§3.5 Policy Engine** — `nexus.core.policy`: `TaskPolicy` with the nine components verbatim (`autonomy_level time_policy network_policy tool_policy workspace_scope app_scope git_policy external_ai_policy resource_policy`), `AutonomyLevel` OBSERVE/SUGGEST/ACT_CONFIRMED/FULL, dotted-path overrides, workspace-seeded policies, full serialization; `PolicyEngine.decide` → allow / confirm / deny with explicit-negative-only denials (blocked tools/hosts, offline, git/external-AI/app-launch disabled, OBSERVE mutations) and confirmation — never a wall — for out-of-scope and cross-workspace work.
- **Integration** — `NexusRuntime.boot()` wires workspace manager + scope engine + policy engine (payload `phase: 2`); the registry persists across NEXUS restarts; `Task.scope` now carries the six §3.2 canonical keys.
- **Exit criteria** — `tests/phase02/verify_exit_criteria.py`: **143/143 checks** (A=32, B=19, C=14, D=15, E=21, F=42), including the full decision matrix, restart persistence, the §2.3 bridge, and the **Phase 1 harness re-run as a subprocess — still 98/98**.
- **Version** — `nexus-core` 0.2.0, `NEXUS_PHASE = 2`.

### Fixed — 2026-09-06 (Phase 1 audit corrections)

- **§2.2 documentation drift** — the canonical event count is **28, not 27**: the `EventName` enum and the harness's `PLAN_EVENTS` reference list were always correct (28/28, verbatim); six docstrings, one harness label and four report rows carried a stale “27” from an early draft — all corrected.
- **Harness §D regression guards (95 → 98 checks)** — added: `completed_at` must be populated on completion; a cancel issued **from PAUSED** must land `CANCELLED` and publish `task.updated` — never `task.resumed` (permanently guards the post-review engine fix).
- **Report numbers realigned** — per-section counts in `docs/PHASE-1-REPORT.md` now match the real harness output (A=15, B=14, C=14, D=18, E=19, F=18).

### Added — 2026-09-06 (PHASE 1 — NEXUS Core Foundation, Plan §2)

The Core is alive — **stdlib-only, zero external dependencies** (no agent framework, Plan §2 goal; adapters only from §0.4 onward).

- **§2.1 Core Configuration** — `config/` six typed TOML sections (`system/ models/ tools/ agents/ workspaces/ security/`) + `nexus.core.config`: typed dataclass schema with validation & provenance, environment resolution (`NEXUS_<SECTION>__<KEY>` wins over files, files win over defaults), local paths (Spec §245 layout, per-dir env overrides, `NEXUS_HOME`), runtime configuration (`NexusRuntime.boot()` → publishes `system.started`).
- **§2.2 Event Bus** — `nexus.events`: central thread-safe pub/sub, the 28 canonical events verbatim, exact/`prefix.*`/`*` patterns, handler isolation (raising subscribers never break dispatch), bounded history + strict-names mode.
- **§2.3 Session System** — `nexus.core.session`: strict `User → Conversation → Task → Session` hierarchy, distinct `usr_/conv_/task_/sess_` identities, one active session per task, no overlap, restored-task registration.
- **§2.4 Task Engine** — `nexus.core.engine`: the 13-state machine verbatim (`CREATED…CANCELLED`), documented transition table, completion only via `VERIFYING` (verification-first), pause/resume with pre-pause memory, audit trail + canonical transition events.
- **§2.5 Task Persistence** — `nexus.core.persistence`: atomic JSON records (`temp + os.replace + fsync`) with envelope/version, exactly the 11 fields, self-healing index, strict id validation (no path traversal).
- **§2.6 Exit Criteria** — `tests/phase01/verify_exit_criteria.py`: **98/98 checks**, including the full lifecycle **create → save → close NEXUS → open NEXUS → retrieve → continue state** across two restart cycles.
- **Packaging** — `pyproject.toml` (`nexus-core` 0.1.0, requires-python ≥ 3.11, `py.typed`); CI: Python quality gate activated (ruff + pyright, pinned) **and** runs the §2.6 harness on every push; packaging job now builds the wheel and verifies the Phase 1 modules ship.

### Added — 2026-09-06 (PHASE 0 — Machine & Repository Preparation, Plan §1)
- **Governance pack**: `LICENSE` (MIT), `CONTRIBUTING.md`, `SECURITY.md`, `ARCHITECTURE.md`, this `CHANGELOG.md`.
- **Branch model**: `main` (protected baseline) + `develop` (integration branch) *(Plan §1.1)*.
- **CI pipeline** (`.github/workflows/ci.yml`): docs & governance integrity, §0.5 ownership-skeleton validation, conditional Python lint/type jobs, packaging placeholder *(Plan §1.4)*.
- **Code skeleton** `nexus/` with all 28 modules *(Plan §1.3)* mapped to the 24 NEXUS-owned components *(Plan §0.5)* — see `nexus/README.md`.
- **Workspace staging layout** in `.gitignore` for `vendor-staging/`, `external/`, `runtime/` *(Plan §1.2 / §45)*.
- Fixed `.gitignore` path scoping so `nexus/models/` **source code** can never be shadowed by the root `models/` binary-dir rule.

### Previously
- `6017d87` — **NEXUS Final Build Plan v1.0** (109 sections) archived as the second canonical document.
- `48d5dec` — Legendary bilingual (AR/EN) engineering README.
- `a98a4fe` — **NEXUS Master Technical Specification v1.0** (375 sections) + initial engineering README + `.gitignore`.

[Unreleased]: https://github.com/PS-COMMUNITY/NEXUS/compare/main...develop
