# PHASE 23 — Heartbeat + Health — Delivery Report

> **منع التوقف الصامت.**
> (Prevent the silent stall.)
> New Plan §23 · delivered on NEXUS `0.23.0` · `NEXUS_PHASE = 23`

## What was built

`nexus/health/` — five stdlib-only modules:

| Module | Section | Content |
| --- | --- | --- |
| `contracts.py` | §23.1–§23.3 | The verbatim vocabulary — `MONITORED_COMPONENTS` (core · agent · model · tool · browser · computer · task) · `STALL_SIGNALS` (same_action · same_error · same_state · no_progress) · `RECOVERY_LADDER` (detect → diagnose → retry → alternate_method → replan) — plus `Heartbeat`, `HealthReport`, `Observation`, `StallFinding` (component-tagged), `Diagnosis`, `LadderOutcome` (every rung observable), `SupervisorReport` and the error family (`HealthError` · `UnknownComponentError`) |
| `heartbeat.py` | §23.1 | `HeartbeatMonitor` — the seven watch targets, one honest clock; status *derived* per check: alive inside the fresh window · degraded when late or self-reported · stalled when a finding named it · silent past the stale window (التوقف الصامت). A fresh beat is the only stall-clearer — recovery is proven by the component, never granted by the monitor. Insertion order preserved so the §23.1 verbatim order survives snapshots |
| `stall.py` | §23.2 | `StallDetector` — one sliding window of `Observation`s, the four loop shapes fired from real trailing runs; empty fields never judged; one fire per evidence (no spam while the loop keeps looping); `reset()` re-arms after a recovery; a changed loop shape re-arms by itself |
| `engine.py` | §23.3 | `RecoveryLadder` — the walk with every rung on the record: a refuted finding ends honestly at detect (`NOT_CONFIRMED`), absent rungs climb past honestly, a raising rung escalates without dying, replan hands the problem upward; `before_rung` announces every world-mutating rung (retry · alternate method) and **a failed announcement refuses the rung**. Plus `HealthSupervisor` — one poll: §23.1 snapshot + per-component private detectors + the ladder; silence becomes a `no_progress` finding with the truth in its detail; every confirmed finding marks its component STALLED until it beats again; silence reported once per silence era (a new beat seq is a new era) |
| `__init__.py` | — | The house package surface (30 exports) |

## The §22 law rides along, structurally

```
before_rung("retry", finding):            # a world-mutating rung
    manager.on_event(BEFORE_RISKY_CHANGE)  # §22.2 announces it
    # if the checkpoint cannot be captured → the rung is REFUSED
```

A recovery that mutates the world without a checkpoint is just a
second accident. The live proof wires the hook to a real
`CheckpointManager` and the store lists the captured
`before_risky_change` manifests back from disk.

## Evidence

* **Sandbox tests:** 55/55 (`tests/phase23/` — contracts 11 · heartbeat 10 · stall 13 · ladder 12 · supervisor 9)
* **Live proof (sandbox):** `live_heartbeat_ci.py` — **11/11 rungs**: a real thread beats and really stops (silence caught by the clock — التوقف الصامت), a real action really fails three times (`same_error`), a real frozen loop traces its shapes, the ladder climbs through all three resolutions, and a real CheckpointManager captures the §22 announcements
* **Exit gate:** `tests/phase23/verify_exit_criteria.py` — **17/17** with the 15–22 regression suite green · ruff clean
* **Device proof:** `tests/phase23/test_device_proof.py` seals `M:\NEXUS\proofs\phase23_live.json` on the real Windows box

## Lessons recorded this phase

1. **A pinned fixture can lie by inheritance** — a constant action/state/progress triple trips three signals at once; each test plants exactly the loop it isolates (unpinned fields vary).
2. **Silence eras need sequence numbers** — a component that beat and went silent *between two polls* was hidden by set-based dedupe; the beat seq distinguishes silence eras (a new seq is a new era).
3. **The snapshot and the mark are ordered** — `poll()` takes the health snapshot before handling findings, so a confirmed stall appears in the *next* report; the honest order, documented and tested.

## Status

Implemented · Integrated · Tested (55/55 sandbox) · Verified (live 11/11 sandbox · gate 17/17 with regression · device proof runs on the box) · Documented (README · CHANGELOG · this report) · Committed — CI green pending the external billing wall (documented in the worklog; the moment billing clears, a rerun judges it).
