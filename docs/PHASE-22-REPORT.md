# PHASE 22 — Recovery + Checkpoints — Delivery Report

> **أي Task كبيرة يجب أن تكون قابلة للاستعادة.**
> (Any large Task must be recoverable.)
> New Plan §22 · delivered on NEXUS `0.22.0` · `NEXUS_PHASE = 22`

## What was built

`nexus/recovery/` — six stdlib-only modules:

| Module | Section | Content |
| --- | --- | --- |
| `contracts.py` | §22.1–§22.4 | The verbatim vocabulary — `CHECKPOINT_SCOPES` (task · project · git · state) · `TRIGGER_EVENTS` (task start · phase complete · major change · critical test · before risky change · periodic) · `VERIFICATION_SURFACES` (files · git · processes · windows · browser · task state) · `RECOVERY_CHAIN` (crash → checkpoint → actual_environment → reconciliation → resume) — plus `CheckpointManifest` (frozen, round-tripping), `EnvironmentFacts`, `Drift`, `ReconciliationReport`, `RecoveryOutcome` and the error family (`RecoveryError` · `CheckpointNotFoundError` · `CorruptCheckpointError` · `NoBlindResumeError`) |
| `store.py` | §22.1 | `DiskCheckpointStore` — one directory per checkpoint (`manifest.json` + `files/` blobs), atomic writes (tmp + `os.replace`), per-scope retention, id-validated and escape-proof blob paths, `restore()` re-applying blobs |
| `probes.py` | §22.4 | The six live probes — `FilesProbe` (tree → sha256, noise-skipping) · `GitProbe` (binary when present, stdlib `.git` fallback, honest not-a-repo vs unreadable) · `ProcessProbe` (tasklist CSV / ps, honest empty on failure) · `WindowProbe` (PowerShell titles / wmctrl, documented injection seams) · `browser_markers` · `TaskStateProbe` (missing/corrupt reads as `{}` → surfaces as drift) — composed by `CompositeProbe` into `EnvironmentFacts` |
| `checkpoint.py` | §22.1–§22.2 | `CheckpointManager` (four scopes; PROJECT/GIT inventory + blobs; TASK/STATE state payloads; environment expectations captured into every manifest) and `TriggerPolicy` (periodic gated by an interval, everything else immediate) with `on_event` as the one §22.2 entry |
| `engine.py` | §22.3–§22.4 | `RecoveryEngine` — `reconcile()` (live probe → six-surface diff), `resume()` (the only door; verdict AND error list both checked), `recover()` (the full chain; repair re-applies digest-checked blobs then re-reconciles; missing/corrupt checkpoint → UNRECOVERABLE + ABORT), plus the standalone `verify_tree()` |
| `__init__.py` | — | The house package surface (40 exports) |

## The §22.4 law, structurally

```
resume(report):
    if not report.ok() or report.errors():      # verdict AND errors
        raise NoBlindResumeError(§22.4 …)       # even a forged verdict dies here
```

There is no code path in the package that yields `resume` unless all
six surfaces passed against a live probe. The test suite proves it one
surface at a time (`test_no_blind_resume.py` — files · git · processes
· windows · browser · task_state) and the forged-verdict test proves
the belt-and-braces check.

## Evidence

* **Sandbox tests:** 67/67 (`tests/phase22/` — contracts 11 · store 8 · triggers 5 · checkpoint manager 8 · probes 11 · recovery 12 · no-blind-resume 11 · wait: 66 + the gate's own pytest layer = 67)
* **Live proof (sandbox):** `live_recovery_ci.py` — **10/10 rungs**, including a *real* process started → captured from the real process table → killed → `process_dead` blocks the resume, and a *real* git divergence holding the wall
* **Exit gate:** `tests/phase22/verify_exit_criteria.py` — sections A–F with the 15–21 regression suite
* **Device proof:** `tests/phase22/test_device_proof.py` seals `M:\NEXUS\proofs\phase22_live.json` on the real Windows box

## Lessons recorded this phase

1. **The phase-20 verifier caught the pending pyproject bump** (`pyproject 0.21.0 != package 0.22.0`) — the verification engine works; the regression layer is a real judge.
2. **A too-eager guard swallows drift** — `_check_windows/_check_browser` originally skipped when the *live* side was empty, which silenced exactly the "it closed" case. Guards must ask "was anything expected?", never "did the live side answer?".
3. **A lying verdict header needs a second lock** — `resume()` originally trusted `verdict` alone; the forged-report test forced the verdict-AND-errors check.

## Status

Implemented · Integrated · Tested (67/67 sandbox) · Verified (live 10/10 sandbox · device proof runs on the box) · Documented (README · CHANGELOG · this report) · Committed — CI green pending the external billing wall (documented in the worklog; the moment billing clears, a rerun judges it).
