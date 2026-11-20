"""NEXUS — Local Autonomous Computer Intelligence Platform.

Package root. Phase 1 (Final Build Plan §2) delivered the Core
Foundation:

* ``nexus.core.config``     — typed configuration, environment resolution,
                               local paths, runtime configuration (§2.1)
* ``nexus.events``          — central Event Bus with the 28 canonical
                               events (§2.2)
* ``nexus.core.session``    — User → Conversation → Task → Session (§2.3)
* ``nexus.core.engine``     — Task State Machine, 13 states (§2.4)
* ``nexus.core.persistence``— Task persistence, 11 fields (§2.5)

Phase 2 (Final Build Plan §3) added Workspace + Scope + Policy —
*Full Control within Task Scope*:

* ``nexus.core.workspace``  — workspace registry, seven fields (§3.1)
* ``nexus.core.scope``      — six-dimension scope, natural-language
                               resolution, scoped cross-workspace
                               access (§3.2–§3.4)
* ``nexus.core.policy``     — task policies, nine components, and the
                               decision engine (§3.5)

Phase 3 (Final Build Plan §4) added Hardware Intelligence + the
Resource Manager — *the machine knows itself and works within its
capacities*:

* ``nexus.resources``       — the twelve §4.1 scan targets (Windows
                               system libraries · POSIX · static), the
                               persisted ``hardware_profile`` (§4.2,
                               system data — never model memory),
                               change detection (§4.3), the eight
                               tracked resources (§4.4) and the Spec
                               §92 degradation-ladder policies (§4.5)

Phase 4 (Final Build Plan §5) added the Local Model Runtime —
*the intelligence enters the machine, on its own resources*:

* ``nexus.models``         — the §5.1 ``ModelProvider`` interface
                               (seven members, verbatim), the §5.2
                               Model Registry (thirteen fields), the
                               §5.3 llama.cpp adapter over
                               ``llama-server``, the §5.4 dynamic
                               loading (select · load · run · keep
                               warm · unload — per resources), the §5.5
                               benchmark protocol (Spec §135) and the
                               §5.7 Model Router; seeded with the §5.6
                               MiMo Edge pool (the user's measured
                               baselines, Spec §88)

Phase 5 (Final Build Plan §6) added the Agent Runtime — *the model
becomes an agent*:

* ``nexus.agents``         — the §6.1 Agent abstraction (eight
                               verbatim fields), the §6.2 Agent Loop
                               (Observe → Context → Decide →
                               Tool/Agent call → Observe → Verify →
                               Continue), the §6.3 Master Agent (seven
                               behaviors driving the §2.4 task machine),
                               the §6.4 Agent Registry (four verbs,
                               atomic persistence), the §6.5 structured
                               Agent Communication (eight verbatim
                               message fields) and the §6.6 Agent
                               Ownership (resource → owner, conflicts
                               become coordination)

Phase 7 (Final Build Plan §8) added the Tool System — *every
capability enters as one unified tool*:

* ``nexus.tools``         — the §8.1 Tool Registry (nine fields per
                               tool, validated, version-aware,
                               freezable), the §8.2 Tool Router (the
                               verbatim seven-stage pipeline with a
                               proof trace), the §8.3 nine native
                               tools (stdlib), and the §8.4/§8.5 MCP
                               interop — the official Python SDK
                               (v2, MODE A ``[mcp]`` extra) behind the
                               router, every server behind NEXUS
                               permission + scope

Phase 8/9/10 (Final Build Plan §9/§10/§11) added the Windows
Computer Runtime (the §9.1 façade + the §9.5 fallback hierarchy), the
Window Manager (ownership · arbitration · monitors · overlay) and
the Browser Runtime (Playwright behind the router, isolated
user/agent sessions, the DPAPI vault).

Phase 11 (Final Build Plan §12) added the Vision Runtime — *the eyes
for the applications with no useful UI structure*:

* ``nexus.vision``         — the §12.1 Screen Capture (full · window
                               · region — GDI/PrintWindow/DWM in pure
                               ctypes), the §12.2 VisionProvider
                               (analyze · locate · classify · compare)
                               over the Phase 4 Model Runtime, the
                               §12.5 OCR engine candidates + the
                               device benchmark that decides, and the
                               §9.5 chain's fourth rung — locate by
                               description, then real input

Phase 12 (New Plan §12 / Build Plan §13) added the Memory System —
*from persistence to a Memory Engine*:

* ``nexus.memory``         — the §12.1 contracts (MemoryProvider ·
                               MemoryRecord · MemoryQuery ·
                               MemoryScope · MemoryEvidence), the
                               §12.2 twelve-scope hierarchy, the §12.4
                               SQLite index (records · evidence ·
                               relationships · audit · local vectors in
                               one file), the §12.5 semantic layer
                               (Qdrant MODE A behind the ``[qdrant]``
                               extra, local cosine fallback always),
                               the §12.6 Mem0 adapter (MODE B), the
                               §12.7 retrieval pipeline with the
                               §12.8 conflict ladder, §12.9 audited
                               forget and §12.10 compression — all
                               seven §13.1 verbs on one engine

Phase 13 (New Plan §13) added the Learning System — *«يتذكر» is not
«يتعلم»*:

* ``nexus.learning``       — the §13.1 six experience kinds and the
                               Experience Extractor, the §13.2 Learning
                               Record, the §13.3 pipeline (Experience →
                               Candidate lesson → Evidence check →
                               Confidence → Store → Future retrieval),
                               the §13.4 Skill Candidate + Workflow
                               miner (Task A, B, C → pattern → skill),
                               all stdlib, all NEXUS-native — with
                               letta-code/prime-agent/DSPy as MODE D/B
                               references only, and promoted lessons
                               landing in the §12 Memory Engine so
                               future tasks already know them

Phase 14 (New Plan §14) added the Code-Intelligence Engine — *large
projects, understood without shipping 400k lines to the model*:

* ``nexus.codeintel``  — the §14.1 File Index, §14.2 Symbol Index,
                               §14.3 AST (stdlib-ast + tree-sitter
                               MODE A + regex fallback), §14.4
                               Dependency Graph, §14.5 API Graph,
                               §14.6 Test Graph, §14.7 Architecture
                               Map, §14.8 Repository Map (the Aider
                               PageRank methodology, MODE D/C — zero
                               imports), §14.11 large-project engine
                               (budgeted, incremental, 100k+) and
                               §14.12 live index update (file changed
                               → parse affected region → update
                               symbols → update graph)

Phase 15 (New Plan §15) added the Coding System — *NEXUS becomes
a real Developer Agent*:

* ``nexus.coding``     — the §15.1 Coding Agent Contract (seven
                               operations — analyze · plan · edit ·
                               run · test · debug · review — behind one
                               ``execute`` dispatcher), the §15.2 ten
                               specialists (architect · frontend ·
                               backend · database · devops · debugger ·
                               tester · security · performance ·
                               reviewer) registered into the §6.4 Agent
                               Registry, the §15.6 eight-stage Coding
                               Loop (Understand → Plan → Edit → Build →
                               Test → Debug → Retest → Review) over the
                               §2.4 task machine with a bounded
                               Debug→Retest cycle, and the §15.5-inspired
                               coding session trail (files read, files
                               edited, tool calls, commits) — OpenHands,
                               OpenCode and Cline studied MODE B/D
                               (zero imports, ``vendor-staging/phase-15``)

Phase 16 (New Plan §16) added the Git / GitHub Runtime — *GitHub
becomes part of the runtime, not a storage place*:

* ``nexus.git``      — the §16.1 Git Engine (eight operations —
                            status · diff · branch · worktree · commit ·
                            merge · tag · rollback — over the real git
                            binary, honest absence, conflicts surfacing,
                            rollback that saves what it destroys), the
                            §16.3 Repository Lifecycle (Discover → Clone
                            → Index → Modify → Test → Commit → Review →
                            Push — a verdict per stage, review rejection
                            stops the pipeline) and the §16.4 Parallel
                            strategy (Spec §123 as executable law:
                            direct commit / feature branch / worktree
                            fleet / checkpoint + branch / tag release)
* ``nexus.github``   — the §16.2 GitHub Engine (eight operations —
                            search · clone · pull · push · branch · pr ·
                            issue · release — over a stdlib REST client
                            and the §16.1 engine), with the §124 token
                            law built in: credentials live as
                            *references* (env/file locators), masked in
                            every repr, error and event payload; public
                            reads work without them and every write
                            refuses with ``TokenNotAvailableError`` instead
                            of pretending

Phase 17 (New Plan §17) added the Research Engine — *research becomes
a runtime, not a chat side-effect*:

* ``nexus.research`` — the §17.1 Search abstraction (five surfaces —
                            web · github · docs · forums · local files —
                            one ``SearchProvider`` adapter each, every
                            external engine behind the contract), the
                            §17.2 workflow (query → search → collect →
                            deduplicate → rank → compare → verify →
                            evidence — a verdict per stage, corroboration
                            required, contested numbers never verify),
                            the §17.3 Source Classification (official ·
                            documentation · academic · community ·
                            personal · unknown — a documented ladder with
                            an honest fallback), the §17.4 Source
                            Confidence (authority · relevance ·
                            freshness · evidence — documented weights,
                            explainable math) and the §17.5 Research
                            Memory (findings persist into §12
                            Task/Project memory with their sources riding
                            every record)

Phase 18 (New Plan §18) added Document Intelligence — *real documents
get real support*:

* ``nexus.documents`` — the §18.1 docling integration (MODE A direct
                            use when installed, MODE B through the NEXUS
                            ``ParseBackend`` contract always, honest
                            availability probe, one documented pin), the
                            §18.2 pipeline (Document → Parse → Structure
                            → Extract → Index → Memory — a verdict per
                            stage, an inverted SQLite index that answers
                            *where* a word lives, a §12 memory bridge
                            that keeps provenance), the §18.3 DOCX verbs
                            (read · create · edit · format · save ·
                            verify over real OOXML), the §18.4 PPTX
                            verbs (create · slides · images · layout ·
                            sources · save · verify — a real minimal
                            package PowerPoint opens) and the §18.5 PDF
                            verbs (read · search · extract · summarize ·
                            analyze — a stdlib parser that reports what
                            it could not read); native stdlib floors
                            keep every document flowing when the heavy
                            engine is absent

Phase 19 (New Plan §19) added the Speech System — *local voice control*:

* ``nexus.speech``  — the §19.1 Speech API (``SpeechProvider`` ·
                            ``transcribe`` · ``detect_language``) behind
                            honest probes, the §19.2 sherpa-onnx engine
                            (MODE A when installed + model present, the
                            Windows SAPI dictation floor with zero
                            installs, the honest null refusal — one
                            documented pin), the §19.3 benchmark (six
                            real conditions — Arabic · Arabic technical
                            · English · mixed · fast · noise — over real
                            audio fixtures, WER/CER through the
                            normalizer) and the §19.4 pipeline
                            (Microphone → STT → Normalization → Intent
                            → Task — a verdict per stage, voice tasks
                            remembered into §12 memory with their
                            provenance)

Phase 20 (New Plan §20) added the Verification Engine — *it is not
                            enough that NEXUS works; it must prove that
                            it works*:

* ``nexus.verification`` — the §20.1 framework (``Verifier`` ·
                            ``Evidence`` · ``Criterion`` · ``Result``),
                            the nine §20.2 domains each behind its own
                            honest verifier (Software · Windows ·
                            Browser · Documents · Research · Git ·
                            Memory · Models · System), the §20.3
                            evidence — five fields per observation
                            (method · output · timestamp · artifact ·
                            result) sealed as sha256 JSON artifacts —
                            and the §20.4 repair loop (Fail → Diagnose
                            → Fix → Retest → Verify) whose every stage
                            leaves evidence; a SKIP is an honest
                            refusal, never a fake PASS

Phase 22 (New Plan §22) added the Recovery System — *any large Task
                            must be recoverable*:

* ``nexus.recovery``   — the §22.1 Checkpoint Manager (four capture
                            targets — Task · Project · Git · State —
                            digests + blobs on disk, atomic manifests,
                            per-scope retention), the §22.2 six
                            trigger events (task start · phase
                            complete · major change · critical test ·
                            before risky change · periodic, the last
                            gated by an honest interval policy), the
                            §22.3 recovery chain (Crash → Checkpoint
                            → Actual environment → Reconciliation →
                            Resume — every stage observable in the
                            outcome) and the §22.4 law — No Blind
                            Resume: لا يعتمد على الذاكرة؛ يفحص Files
                            · Git · Processes · Windows · Browser ·
                            Task state — six live surfaces, and
                            ``resume()`` raises rather than trusting
                            a drifted report

Phase 23 (New Plan §23) added the Health System — *prevent the
                            silent stall*:

* ``nexus.health``     — the §23.1 Heartbeat (seven watch targets —
                            Core · Agent · Model · Tool · Browser ·
                            Computer · Task — each owing the monitor a
                            beat; silence past the stale window is
                            derived from the clock, never from an
                            exception, and a fresh beat is the only
                            thing that clears a stall), the §23.2
                            Stall Detection (the four loop shapes —
                            same action · same error · same state ·
                            no progress — one sliding window per
                            component, one fire per evidence, empty
                            fields never judged) and the §23.3 ladder
                            (detect → diagnose → retry → alternate
                            method → replan — every rung observable in
                            the outcome, and every world-mutating rung
                            announced to the §22.2 BEFORE_RISKY_CHANGE
                            trigger first: a recovery that mutates the
                            world without a checkpoint is just a
                            second accident)

Phase 24 (New Plan §24) turned the single agent into an agent
system — *نقل NEXUS من Agent واحد إلى Agent system*:

* ``nexus.orchestration`` — the §24.1 Master Agent law as code (the
                            user channel is walled by identity — a
                            specialist's attempt is refused, the
                            master's single door in is
                            ``submit_user_goal`` and its single voice
                            out is ``report_to_user``), the §24.2
                            thirteen specialists (Planner · Researcher
                            · Architect · Coder · Browser · Computer
                            · Tester · Debugger · Security · Reviewer
                            · Git · Recovery · Learning — each a §6.1
                            record on the §6.4 registry with a
                            deterministic id), the §24.3 three
                            conjunctive gates (Tasks independent ·
                            Files independent · Resources available —
                            all three or no parallelism, every denial
                            explainable, waves planned deterministically
                            and run on real threads) and the §24.4 five
                            ownership fields (task · scope · parent ·
                            children · owned resources — scope refused
                            before work, resources coordinated through
                            the §6.6 manager: a conflict surfaces as a
                            result, never an overwrite)

Phase 25 (New Plan §25) made the goal outlive the session — *«خذ
المهمة واشتغل لحد ما تخلص»*:

* ``nexus.horizon``     — the §25.1 Goal persistence (every goal on
                            disk, atomically, and a reboot finds it),
                            the §25.2 Background workers (one real
                            thread per run, the handle back
                            immediately), the §25.3 Long-running
                            state (the durable ladder written between
                            steps — pending → running →
                            paused/completed/failed/deadline_hit),
                            the §25.4 Heartbeat (the §23 monitor
                            beaten per step; silence derived from the
                            clock), the §25.5 Checkpoints (real §22
                            PERIODIC captures on a cadence, ids
                            persisted with the goal), the §25.6
                            Resume (the §22.4 law again — corrupt
                            state, terminal goals and drifted
                            checkpoints all refuse the resume) and
                            the §25.7 Deadline (30 minutes · 2 hours
                            · 8 hours · Until completion — a bounded
                            wall stops with deadline_hit, never a
                            fake completion; the generation lease
                            retires a superseded worker before it
                            can write)

The Core is stdlib-only by design: NEXUS identity must not depend on any
external agent framework (Plan §2 goal — reinforced by §0.5: the Master
Agent and the Agent Registry are NEXUS-owned). External engines enter
later, behind adapters only (Plan §0.4); the Phase-5 reference
frameworks (langgraph / autogen / deepagents) were studied in
``vendor-staging`` and documented — none of their code is imported.
The Phase-7 MCP layer follows the same law: the official SDK is an
optional MODE A companion behind the NEXUS Tool Router, never a core
dependency. The Phase-12 memory engines (qdrant-client, mem0ai)
follow it too: NEXUS owns Memory semantics (Plan §61) and every
engine is an adapter away from replacement.

Phase 21 (New Plan §21) added the Security System — *full capability
                            + controlled execution* (Spec §156: Scope +
                            Permission + Execution Gate):

* ``nexus.security``       — §21.1 Scope Engine Integration (the §3.3
                            resolution is the first check of every
                            admission), §21.2 Permission Engine (§163
                            risk × §3.5 policy — explicit denial is
                            the only wall), the three §21.3–§21.5
                            gates (Tool · MCP · Plugin), §21.6 Secret
                            Handling (references out — the text never
                            leaves the vault), §21.7 Redaction,
                            §21.8 Audit (Who|What|When|Where|Result
                            with the §165 Activity split), §21.9
                            Trivy (aquasecurity/trivy — dependency ·
                            secret · license · vulnerability, MODE
                            A/B) and §21.10 Security Rules — لا يصل
                            secret إلى: Memory · Normal chat · Logs ·
                            Activity — guarded at the doors,
                            structurally, not by discipline
"""

__version__ = "0.25.0"

NEXUS_PHASE = 25
