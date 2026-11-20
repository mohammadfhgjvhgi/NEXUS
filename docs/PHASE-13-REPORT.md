# PHASE 13 REPORT — Learning System (New Plan §13)

> **الهدف**: التمييز بين «يتذكر» و«يتعلم».
> Memory (PHASE 12) persists *what happened*. Learning turns what
> happened into lessons, decisions and skills — **future tasks
> already know them**.

Status: **COMPLETE** — implemented, integrated, tested, verified on
the real Windows box, documented, committed. `nexus-core 0.13.0` ·
`NEXUS_PHASE = 13`.

---

## 1. ما بُني (What landed)

| Component | Plan | Module | What it is |
|---|---|---|---|
| Experience kinds + Extractor | §13.1 | `nexus/learning/extractor.py` | one finished TaskResult → the six kinds (success · failure · decision · pattern · lesson · skill_candidate), audit-grade: task id + honest summary + §12.1 evidence + §12.2 containers |
| Learning Record | §13.2 | `nexus/learning/contracts.py` | `experience_id · lesson · source_task · evidence · confidence · scope` verbatim + seams (status/occurrences/signature/memory_id); confidence ≤ 0.95 — corrigible by design |
| Learning Pipeline | §13.3 | `nexus/learning/pipeline.py` | the six stages end-to-end; promotion into the §12 MemoryEngine; recall; stats; events |
| SQLite learning index | §13.3 (Store) | `nexus/learning/store.py` | four tables in one `learning.db` (experiences audit · learning_records · task_sequences · skill_candidates), WAL, merge by signature, restart-proof |
| Skill Candidate + WorkflowMiner | §13.4 | `nexus/learning/skills.py` | Task A + B + C → ONE pattern → candidate (occurrences 3, per-task evidence); maximal windows only |
| Confidence rule | §13.3 stage 4 | `nexus/learning/contracts.py` | pure: kind prior + distinct capture methods + repeats, clamped [0.05, 0.95] |
| References | §13.5–§13.7 | `vendor-staging/phase-13/` + docs | letta-code `e073938` · prime-agent `bf8894a` · dspy `f70d08a` — **MODE D, zero imports** |

## 2. المسار — §13.3 (the six stages, verbatim)

```
Experience            extractor.extract(task_result) — the six kinds
   ↓
Candidate lesson      kind → lesson text + §12.2 scope
                       (SUCCESS→LESSON · FAILURE→ERROR · DECISION→DECISION
                        · PATTERN→KNOWLEDGE · LESSON→LESSON · SKILL→SKILL)
   ↓
Evidence check        < 1 evidence → REFUSED («an opinion, not a
                       lesson») — refused, counted, kept in the
                       experiences audit (never silently dropped)
   ↓
Confidence            confidence_for(kind, methods, occurrences)
                       pure rule — never 1.0
   ↓
Store                 learning.db upsert by signature: the same
                       lesson re-learned MERGES (occurrences +1,
                       confidence rises — repetition is signal)
   ↓
Future retrieval      ≥ LEARN_PROMOTE_THRESHOLD (0.65) → written to
                       the §12 MemoryEngine: source="learning",
                       conflict_key=lsig_… — every future task's §12.7
                       context already knows it; recall() additionally
                       surfaces still-pending lessons (honest)
```

The §12.8 conflict ladder stays in force untouched: an old lesson
loses to a current prompt/task/workspace rule/project decision/user
preference (proven: gate J — a USER rule outranks a learned lesson).

## 3. المهارات — §13.4

```
Task A (open_tunnel > health_check > auth_probe)
Task B (open_tunnel > health_check > auth_probe)
Task C (open_tunnel > health_check > auth_probe)
   ↓  WorkflowMiner (maximal windows only)
Pattern (wsig_…)  →  SkillCandidate (occurrences 3, evidence per task)
   ↓  confidence 0.67 ≥ 0.65
promoted → §12 engine SKILL record (source="learning")
```

Two repeats are noise (§13.4 needs three); sub-windows of a kept
workflow never spawn duplicate candidates; a window that itself
repeats survives even when a longer non-repeating workflow contains
it; a 4th run strengthens the candidate (occurrences 4, still one);
a rejected candidate re-opens when new evidence arrives.

## 4. المراجع — §13.5/§13.6/§13.7 (MODE D, Round 10)

* **letta-code** (Apache-2.0, `e073938`) — studied for persistent
  identity, memory, skills, continual agent state. Its state lives in
  the Letta *server* — exactly what Plan §61 forbids for NEXUS; the
  idea (agent state outliving sessions) is implemented NEXUS-native
  in SQLite (`learning.db` + the §12 engine link).
* **prime-agent** (MIT, `bf8894a`) — studied for the continual
  harness, persistent goals, subagents, heartbeat. The heartbeat→
  learning trigger maps to the future §23; the pipeline is already
  absorb-on-task-completion shaped.
* **dspy** (MIT, `f70d08a`) — prompt/workflow optimization,
  evaluation-driven refinement. The plan says «مرحلة لاحقة» —
  **deferred** (DW-5) with an open seam: §13.3 stage 4 is a pure,
  swappable function.

Zero imports from any of them; `pyproject.toml` core dependencies
remain `[]`.

## 5. الاختبار والإثبات (What proves it)

| Proof | Where | Result |
|---|---|---|
| Exit gate — 11 sections A–K | `tests/phase13/verify_exit_criteria.py` | **60/60 PASS** (incl. Phases 1–12 regression green) |
| Live CI proof | `tests/phase13/live_learning_ci.py` | **14/14 PASS** — bilingual AR+EN lessons, promotion into a real §12 engine, §13.4 folding, **fresh child-process restart**, recall |
| Device live proof | `tests/phase13/live_proof_device.py` | run on the real Windows box via the tunnel → `proofs/phase13_live.json` |
| Lint/types | ruff + pyright | clean (nexus/ + tests/phase13/) |

The exit gate lines and where each is proven:

```
Experience extraction ✅   (B — all six kinds, evidence attached)
Learning records ✅        (A + C — §13.2 fields verbatim, upsert/merge)
Evidence check ✅          (D — opinion refused, audited)
Confidence + store ✅      (A + D — pure rule, merge by signature)
Skill candidate ✅         (E — A+B+C → one candidate, promoted)
Future retrieval ✅        (F — recall + §12.7 future-task context)
Restart persistence ✅     (C + G — new store/process, same files)
Existing tests ✅          (K — Phases 1–12 harnesses green)
```

## 6. التكامل والبوابات (Integration & gates)

* `nexus/__init__.py` — Phase 13 block, `__version__ 0.13.0`,
  `NEXUS_PHASE = 13`; `pyproject.toml` bumped, description extended.
* CI — `python-quality` runs the phase13 gate (`--no-regression`;
  phases 1–12 run as their own steps); new `learning-live` job runs
  the live proof on every push.
* Events — `learning.record.created/promoted/refused` +
  `learning.skill.found` on the §2.2 bus (defensively emitted, the
  bus never breaks learning).
* Deploy — `tools/deploy_phase13_bearer.py` (the house pattern:
  write the file set over the tunnel, SHA-256 verify each file,
  run the device live proof, read the verdict, write the marker).

## 7. الأخطاء التي كشفها الإثبات (Bugs the proofs caught)

1. Sub-window mining spawned three candidates for one skill — the
   maximal-window rule (a fragment of a kept workflow is noise, and
   only a *qualifying* window may shadow) fixed it; the harness
   caught it before any deploy.
2. Single-evidence lessons promoted at the 0.60 threshold — raised
   to **0.65**: a lesson needs a second capture method or a repeat
   before it claims future context (the live proof's "weak lesson
   stays pending" check encodes it).
3. Container-scoped lessons were invisible to container-less recall
   — that is the §12.2 law *working* (a lesson learned inside a
   project is at least project-scoped); the live proofs now recall
   with the honest container.
4. Raw dict evidence was silently dropped by the extractor (it only
   keeps §12.1 `MemoryEvidence` objects) — caught while porting the
   device proof; all proofs now pass real evidence objects.

## 8. المؤجل (Deferred)

See `docs/DEFERRED-WORK.md` — DW-5 (DSPy optimization, §13.7 «مرحلة
لاحقة», seam open) and DW-6 (absorb wiring into the live §2.4 task
end — the input shape is the documented TaskResult).
