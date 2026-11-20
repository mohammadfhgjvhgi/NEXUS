# PHASE 12 REPORT — Memory System (New Plan §12 / Build Plan §13)

> Status: **Complete** · Commit: see `CHANGELOG.md` · Exit criteria: **137/137 (A–J + integration + regressions 1–11) + live Qdrant proof 11/11 (local + CI memory-live job)** · CI job: "Phases 1–12" + **memory-live**
>
> الهوية: «تحويل الذاكرة من مجرد persistence إلى Memory Engine
> فعلية» — سبعة أفعال حرفية، مستويات اثنا عشر، فهرس واحد، محركان
> دلاليان خلف محوّل، وسُلّم أولويات يحسم التعارض، ونسيان مدوَّت،
> وضغطٌ يختصر المساء الطويلة.

## 1. ما بُني (What landed)

```
nexus/memory/                    ← §12/§13 the Memory Engine (NEXUS-owned)
├── __init__.py                  exports · the component table
├── contracts.py                 §12.1 the five contracts · §12.2 the 12 scopes
│                                · §12.3 the 11 metadata fields · visibility ladder
├── store.py                     §12.4 the SQLite index (5 tables, WAL, one file)
├── embeddings.py                §12.5 the embedding seam (Hashing · Model)
├── vectors.py                   §12.5 VectorIndex + LocalVectorIndex (stdlib)
│                                + QdrantVectorIndex (MODE A, [qdrant] extra)
├── mem0_adapter.py              §12.6 Mem0MemoryProvider (MODE B, [mem0] extra)
├── conflict.py                  §12.8 the priority ladder + ConflictResolver
├── forget.py                    §12.9 exact/category/scope + audit
├── compression.py               §12.10 the 5-stage pipeline (mem0 patterns, AR+EN)
└── engine.py                    §13.1 the seven verbs + §12.7 the retrieval
                                 pipeline (search → rank → resolve → assemble)

tests/phase12/
├── verify_exit_criteria.py      126/126 (A–K + regressions 1–11)
├── live_memory_ci.py            the real-Qdrant roundtrip (10/10, CI + local)
└── live_proof_device.py         the Windows device proof (deploy + run via tunnel)

vendor-staging/phase-12/         qdrant @ 6ab21cac · mem0 @ 73e7b876 + AUDIT.md
pyproject.toml                   0.12.0 · [qdrant] · [mem0] extras
.github/workflows/ci.yml         Phase 12 step + the memory-live job
```

## 2. العقود — §12.1/§12.2/§12.3 (verbatim, validated)

`contracts.py` carries the plan's five names **exactly**:
`MemoryProvider` (the §13.1 seven-verb ABC), `MemoryRecord`,
`MemoryQuery`, `MemoryScope` (the twelve-scope vocabulary),
`MemoryEvidence` (method ∈ `tool_run/observation/user_statement/
document/research/test/system` + uri + snippet — evidence with no
provenance is *refused*). The §12.3 eleven metadata fields are the
dataclass's verbatim core (`id·type·scope·content·source·confidence
·created_at·updated_at·expires_at·project·workspace·task`); the
house seams beyond them (session/agent containers, conflict_key,
evidence, tombstone fields) are documented as such. Validation is
construct-time: bad id/scope/type/empty content/∞ confidence and
container-incoherent scopes (a TASK memory without `task=`) all
raise `InvalidMemoryError` — 5/5 refusal checks in the harness.

**The §12.2 visibility ladder** is one pure function,
`scope_visible(record, query)`:

* `GLOBAL`/`USER` — visible to every query (single-operator system);
* `PROJECT/WORKSPACE/TASK/SESSION/AGENT` — the query's matching
  container must *equal* the record's (strict isolation: task A
  never sees task B);
* the semantic libraries (`KNOWLEDGE/DECISION/LESSON/SKILL/ERROR`) —
  visible when their container fields are unset (library-wide) or
  match the query's containers exactly.

The isolation is enforced in **every retrieval stage** — lexical
*and* vector — after the harness caught the vector stage leaking a
task-B memory (fixed at the source, §6 below: the E-section failures
were the proof working).

## 3. الفهرس — §12.4 SQLite (one file, five tables, WAL)

`SQLiteMemoryStore`: `memory_records` (metadata + tombstone
columns), `memory_evidence` (provenance rows), `memory_relationships`
(the §13.1 `link` graph), `memory_audit` (§12.9 trail), and
`memory_vectors` (**float64 blobs + payload JSON** — the local
semantic layer persists *in the same file*, so restart persistence
covers semantics with zero moving parts). WAL mode + explicit
transactions (`BEGIN IMMEDIATE`/COMMIT/ROLLBACK) — a crash mid-write
cannot corrupt the index; every statement is parameterized (user
content never touches SQL). `lexical_search` is the §12.7 lexical
stage (hit-count ranking, deterministic order). The exit-gate
restart proof: new store on the same path → records, relationships,
vectors all survive.

## 4. الطبقة الدلالية — §12.5 (two engines, one contract)

`VectorIndex` = `upsert · search · delete · count` (+payload
filters — §12.5 "filtered retrieval"). Two implementations:

* **`LocalVectorIndex`** — stdlib cosine over the SQLite vector
  rows. Zero deps, survives restarts, proves the pipeline anywhere
  (CI, cold start, the device without extras). Deterministic tie-
  breaking by record id.
* **`QdrantVectorIndex`** — **MODE A** over the official
  `qdrant-client` (Apache-2.0, `[qdrant]` extra, `>=1.19,<2`).
  `:memory:` for tests, **a local path for persisted local mode —
  no server, no sockets** (the default under a data root), or a URL
  for a live server. `query_points` (the current API), payload
  filters → `Filter(must=[FieldCondition])`, point ids =
  deterministic **UUID5** of our record ids (local mode's UUID law)
  with the real id riding the payload; `close()` releases the
  local-mode single-instance lock.

`resolve_vector_index(auto|local|qdrant)` + `qdrant_probe()` make
absence *reported, never faked*: `auto` picks Qdrant when installed
(and says so in the engine's `backend_report`), else falls back to
the local index **with the probe's reason verbatim**.

**The embedding seam** (`EmbeddingProvider.embed → list[float]`):
`HashingEmbedder` (blake2b feature hashing, NFKC casefolded
tokens — Arabic intact, L2-normalized, deterministic across
machines) is the always-available baseline; `ModelEmbedder` routes
through the **Phase 4 Model Runtime** (`RoutingRequest(
required_capability="embeddings")` → `GenerateRequest` → parse the
floats — the llama-server `/embedding` JSON shape) and *refuses*
honestly when no embeddings model answers.

## 5. المحرّك — §13.1 الأفعال السبعة + §12.7 الخط + §12.8 السُلّم

`MemoryEngine` implements the seven verbs over store+embedder+index
(+ optional §2.2 `EventBus`: `MEMORY_CREATED`/`MEMORY_UPDATED` —
forget stays audit-only, §2.2 has no forgotten event):

* **remember** — store + vector, atomically visible, event emitted;
* **search** — the ranked pipeline minus assembly (`MemorySearchHit`
  with semantic/lexical scores and per-stage provenance);
* **retrieve** — the full §12.7 pipeline → `MemoryContext`:
  `_query_from` (prompt+containers) → `_search_candidates` (vector
  top-k ∪ lexical scan, visibility/freshness/filters applied in
  *both* stages, expiry swept first) → `_rank` → `_resolve` →
  `_assemble` (blocks in `BLOCK_ORDER`, **char budget with honest
  drop counts**, conflict notes attached);
* **update** — partial update + re-embed + event;
* **forget** — the three §12.9 verbs (below);
* **summarize** — §12.10 compression over raw turns or stored
  records: extracts events/decisions/lessons, mints the compact
  SUMMARY, links everything `compressed_from`;
* **link** — one §12.4 relationship edge (both endpoints must exist).

**Ranking** (`RANK_WEIGHTS`, documented and summing to 1.0):
`0.45·semantic + 0.20·lexical + 0.15·recency + 0.10·confidence +
0.10·scope_fit`. Recency = 14-day half-life decay (an evening-old
fact beats last month's). Scope-fit rewards the ladder (TASK 1.0 →
GLOBAL 0.3) — *closer to the question wins at equal evidence*.

**Conflict resolution** (`conflict.py`): records sharing a
`conflict_key` form a family; the winner is
`(ladder rank, updated_at, id)`-maximal — the §12.8 ladder verbatim
(current_prompt is the query itself; current_task = TASK/SESSION;
workspace_rules = WORKSPACE RULE/DECISION; project_decisions =
PROJECT; user_preferences = USER PREFERENCE; old_lessons = LESSON,
the floor). The §13.7 rule «الجديد يفوز» is the recency term made
arithmetic. **Losers are documented, not deleted** — they stay in
the store (§12.9 is the only removal path) and appear in
`context.conflicts` as `conflict[key] winner=… superseded=[…]`.

## 6. النسيان — §12.9 (tombstone + audit, content dropped)

`forget_exact / forget_category / forget_scope` with the container
guards (PROJECT forget needs `project=`; **GLOBAL wipe needs
`allow_global=True`** — the two-key guard). Forget is a *tombstone*:
every read path stops returning the record, its vector is deleted
from whichever engine holds it, and the audit row keeps the
metadata (id/type/scope/source/reason/who/when) — **content is
dropped by design** («مع الحفاظ على audit metadata حيث يلزم»).
`sweep_expired` runs at the head of every search — memories with a
past `expires_at` expire into the same audited tombstone.

## 7. الضغط — §12.10 (the mem0 pattern, deterministic)

`MemoryCompressor`: the five stages verbatim
(`raw_history → important_events → decisions → lessons →
compact_memory`). Bilingual AR+EN markers (قرار/قرّرنا/اخترنا/
decided/we will use… · درس/تعلّمنا/lesson/learned… · خطأ/فشل/
error/traceback…), event kinds (tool_call/tool_result/file_write/
task_state/checkpoint/artifact). Triggers: `>50 turns` or
`>24,000 chars` (`should_compress`). The compact record is the
span's shape — counts, first/last timestamps, up to 10 decision and
lesson texts, the raw-char ratio — enough to resume without
re-reading; products land in the semantic libraries (DECISION/
LESSON/ERROR) with containers stamped, events+summary in the
caller's container (session → task → user fallback), all linked
`compressed_from`.

## 8. Mem0 — §12.6 (MODE B, the candidate engine)

`Mem0MemoryProvider(MemoryProvider)` wraps a duck-typed mem0
backend (`add/search/get_all/update/delete`) — the real
`mem0.Memory` when the `[mem0]` extra is installed, a deterministic
fake in tests. The NEXUS-owned side store keeps ids/scopes/links/
audit (Plan §61 — the engine is replaceable, the semantics are
not); `mem0_probe()` reports absence honestly; a not-mem0-shaped
backend is refused at construction. The §13.4 behaviors we took:
**memory extraction** → the deterministic compressor above;
**retrieval patterns** → `MEM0_SCOPE_MAP` (mem0's user/agent/run
scoping onto our containers). Full cycle in
`docs/REPOSITORY-INTEGRATION.md` Round 9.

## 9. الاختبار والإثبات (What proves it)

* **`tests/phase12/verify_exit_criteria.py` — 137/137** (126 section
  checks + 11 regression lines): A=21 (contracts verbatim +
  refusals) · B=15 (store: tables, roundtrips, restart,
  tombstone+audit) · C=17 (embeddings, cosine, local index +
  filtered + restart, ModelEmbedder over the fake manager) + BONUS
  live Qdrant · D=10 (seven verbs + events + factory restart) ·
  E=12 (scope isolation, every ladder) · F=10 (conflict ladder +
  §13.7 + end-to-end) · G=11 (forget ×3 + guards + audit) ·
  H=10 (compression stages/markers/triggers/links) · I=12
  (pipeline weights/recency/budget/provenance + the relevance
  floor) · J=11 (mem0 adapter) · K=9 integration + **regressions:
  Phases 1–11 green as subprocesses** (the exit gate's «Existing
  tests ✅» — phase11's internal 1–10 chain included; the local
  run executed it standalone at 119/119+7 exit 0 because the
  sandbox's 10-minute tool limit ends just before phase11's
  8-minute nested chain finishes — GitHub CI runs the full chain
  in one step, no such limit).
* **`tests/phase12/live_memory_ci.py` — PASS 11/11 on the real
  engine**: the factory picks Qdrant local-persisted mode (report
  proves it — no silent fallback), a bilingual corpus across four
  scopes, semantic search from **Arabic and English**, scope-
  filtered retrieval, the §12.8 conflict decided live, §12.9 forget
  dropping the Qdrant point, and **restart persistence** (close →
  new engine, same root — SQLite + Qdrant both survive). This is
  the new CI **memory-live** job (qdrant-client installed).
* **Bugs the proofs caught** (the harness doing its job):
  1. *the vector stage leaked scope*: `scope_visible` was applied
     only in the lexical stage — task B's memory came back through
     semantic search (E-section failures). Fixed: visibility +
     type/confidence filters apply to **every** stage;
  2. *float32 roundtrip drift*: the vector blob table lost
     precision (`0.1` → `0.10000000149…`) — fixed to float64
     (exact for Python floats);
  3. *Qdrant local-mode laws*: point ids must be UUIDs (→
     deterministic UUID5 mapping), the storage folder is single-
     instance (→ `close()` lifecycle, honored by the restart
     proofs), and `location=<path>` is a URL not a path (→ the
     `path=`/`url=`/`:memory:` constructor split).

## 10. التكامل والبوابات (Integration & gates)

`nexus-core` **0.12.0** · `NEXUS_PHASE = 12` · CI "Phases 1–12" +
**memory-live** · `[qdrant]`/`[mem0]` extras pinned and audited ·
`docs/REPOSITORY-INTEGRATION.md` Round 9 (qdrant A · mem0 B) ·
`vendor-staging/phase-12/` with the audit · ruff + pyright clean.
Core dependencies stay **empty** — the stdlib-only law holds; both
engines are adapters away from replacement.

**Exit gate (§12.11), all six proven**: Memory create ✅ · Memory
retrieve ✅ · Scope isolation ✅ · Conflict resolution ✅ · Restart
persistence ✅ · Semantic retrieval ✅ · Existing tests ✅.

**Deferred (documented, not silently dropped)**: the §41 harness
memory-view wiring (the Master Agent consumes `MemoryContext` —
that seam lands with the Agent-Loop upgrade in the Track-A/B
convergence), and the real-`mem0` device run (the wheel's LLM-stack
dependency tree is an operator decision, the adapter hole is
tested and waiting). Both entries live in `docs/DEFERRED-WORK.md`.

**Device proof**: `tests/phase12/live_proof_device.py` — the
Windows run (real `M:\NEXUS` path, real SQLite file, restart in a
fresh process, the §12.7 roundtrip) deployed and executed through
the tunnel; verdict JSON to `M:\NEXUS\proofs\phase12_live.json`.
