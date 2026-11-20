# PHASE 25 — Long-Horizon Execution — Build Report

> **الهدف: «خذ المهمة واشتغل لحد ما تخلص.»**
> (Goal: take the task and work until it's done.)

**Status:** Implemented · Integrated · Tested · Verified · Documented · Committed
**Version:** 0.24.0 → **0.25.0** · `NEXUS_PHASE = 25`
**Tests:** sandbox 54/54 · device 54/54 · exit gate 21/21 (regression 15–24 green) · live proof **11/11**

---

## What was built — `nexus/horizon/` (4 files, stdlib only)

### `contracts.py` — the verbatim vocabulary

| Constant | Value |
|---|---|
| `DEADLINES` | the §25.7 four, in plan order: `30_minutes` · `2_hours` · `8_hours` · `until_completion` |
| `DEADLINE_SECONDS` | the honest windows: 1800.0 · 7200.0 · 28800.0 · **None** (unbounded = no deadline exists) |
| `GOAL_STATES` | the §25.3 ladder: `pending → running → paused/completed/failed/deadline_hit` |
| `TRANSITIONS` | the transition law — `completed` is terminal (no exits) |
| `RESUMABLE_STATES` | `paused · failed · deadline_hit · running` (a running state is resumable because its process may be dead) |

Records (frozen, round-trips): `GoalRecord` (statement · deadline ·
state · progress_seq · last_checkpoint_id · **generation** (the durable
run lease) · **deadline_at** (epoch — a wall deadline survives a
reboot; a monotonic one does not)), `ProgressNote`, `StepOutcome`.
Error family: `HorizonError` → `UnknownDeadlineError` ·
`UnknownGoalError` · `IllegalTransitionError` · `BlindResumeError`.

### `goals.py` — §25.1 + §25.3

`GoalStore`: one directory per goal — `goal.json` written atomically
(temp + `os.replace` + `fsync`, the §6.4/§22 house pattern) plus an
append-only `progress.jsonl` journal. A fresh store over the same
directory is the reboot: every goal found exactly as the dying process
left it. The ladder is enforced (`IllegalTransitionError`); a corrupt
file is refused (`HorizonError`), never silently forgotten. The store
is thread-safe (one lock around read-modify-write).

### `runner.py` — §25.2 + §25.4 + §25.5 + §25.7

`HorizonRunner.start()` opens a run and spawns **one real thread**;
`HorizonHandle` returns immediately (`state()`/`record()`/`progress()`
read the disk, `wait()` joins, `pause()` walks the ladder). The loop,
every step:

1. re-reads `goal.json` — the disk decides, not memory;
2. **the generation lease**: a superseded worker retires itself —
   including *mid-step*, re-checked before every write (a ghost never
   clobbers the record of its successor);
3. **§25.7**: a bounded wall (epoch, persisted) stops the run with
   `deadline_hit` — never a fake completion; `until_completion` has
   `deadline_at is None`;
4. the step runs (exceptions → `failed` with the true reason on the
   journal; a wrong return shape fails too — the shape police);
5. **§25.4**: the §23 monitor is beaten (`agent` per step, `task` at
   the milestones);
6. **§25.5**: every N steps a real §22 `CheckpointManager` `PERIODIC`
   capture — the id persisted with the goal.

### `resume.py` — §25.6

`ResumeInspector` re-reads the persisted evidence before a single step
runs: raw JSON readable · the §25.7 deadline vocabulary intact (read
from the raw file so a corrupt value is *named*, not hidden) · the
record structurally parseable · the state resumable (terminal
`completed` refuses) · the recorded checkpoint really in the §22 store
(drift refuses). **Every refusal is collected** — `BlindResumeError`
carries the full list. `resume()` opens a fresh run: a new generation,
a fresh bounded window (a deadline bounds ONE RUN — documented
decision), and — when the crash left the state `running` — a
`RESUMED after interrupted run` note on the journal, so the takeover
is on the record.

## Laws proven (not claimed)

- **the reboot finds the goal** — fresh store, same directory, same
  statement, same seq;
- **the caller is not blocked** — the worker parks mid-step while the
  main thread observes `running` from disk;
- **the wall is honest** — 1800s window burned at 400s/step → exactly
  five steps, then `deadline_hit`; the journal shows no fake finish;
- **the ghost writes nothing** — a parked worker wakes after its goal
  was resumed and retires at the write-guard, journal untouched;
- **resume continues the count** — seq 1..N with no gaps across both
  lives of the goal;
- **§23 rides along** — ALIVE while stepping, SILENT from the real
  clock after the worker stops.

## Verification

| Stage | Result |
|---|---|
| Sandbox pytest (`tests/phase25/`) | **54/54** |
| Sandbox live proof (`live_horizon_ci.py`) | **11/11** |
| Exit gate (`verify_exit_criteria.py`) | **21/21** — A contracts · B persistence+state · C workers+deadline · D heartbeat+checkpoints · E resume · F identity+stdlib+regression |
| Regression 15–24 | **green** (10 suites, zero failures) |
| ruff (whole `nexus/` + new tests) | **0 findings** |
| Device tests (Windows, py 3.14.5) | **54/54** |
| Device live proof | **11/11** — `M:\NEXUS\proofs\phase25_live.json` PASS, read back verified |

## Identity & docs updated

`nexus/__init__.py` (0.25.0 / NEXUS_PHASE 25 / Phase-25 docstring) ·
`pyproject.toml` · `README.md` (comparison row + roadmap row + both
narratives) · `CHANGELOG.md` · `ci.yml` (phase-25 gate step +
`horizon-live` job) · this report.

## Position

**PHASE 25 — Long-Horizon Execution — مكتملة ومثبتة على القرص الحقيقي.**
CI run pending the same external billing wall recorded for 21/22/23/24;
per the CI law, the marker joins the queue and writes the moment a
rerun turns green.
