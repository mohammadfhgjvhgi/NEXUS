# PHASE 20 — Verification Engine — Delivery Report

**Date:** 2026-09-09 · **Version:** `nexus-core 0.20.0` · **NEXUS_PHASE:** 20
**Plan:** New Plan v3 §20 (the 75-section plan — the binding reference)
**Status:** ✅ Implemented · Integrated · Tested · Verified · Documented · Committed

---

## 1. The claim this phase closes

> **لا يكفي أن NEXUS يعمل. يجب أن يثبت أنه يعمل.**
> It is not enough that NEXUS works. It must prove that it works.

PHASE 20 turns that sentence into runtime machinery: any claim about
NEXUS — its code, its host, its memory, its git state, its models —
becomes a `Criterion`, is judged by a `Verifier`, and lands as
`Evidence` with five fields and a sealed artifact. When a criterion
fails, the §20.4 loop diagnoses, fixes, retests and verifies — with
evidence on every stage.

## 2. What was delivered (§20.1–§20.4)

### §20.1 Verification Framework — `nexus/verification/contracts.py`

The four nouns, verbatim from the plan:

| Noun | Shape | Law |
|---|---|---|
| `Criterion` | `id · domain (one of the nine) · description · check` | a claim with a real executable — never checked-by-name |
| `Verifier` | ABC: `criteria()` + `verify(criterion) -> Result` | declares what it can judge; judges honestly |
| `Result` | `criterion_id · status · evidence · duration · message` | statuses: `PASS · FAIL · ERROR · SKIP` |
| `Evidence` | `method · output · timestamp · artifact · result` | §20.3's five fields, verbatim |

The judging law in `BaseVerifier.verify`: a check returning a string is
**PASS** with that observation; an `AssertionError` is **FAIL** (the
claim did not hold); a `CriterionSkipped` raise is **SKIP** (this host
honestly cannot judge it); anything else is **ERROR** (the probe itself
broke — never disguised as FAIL or SKIP).

### §20.2 Verification Domains — `nexus/verification/domains.py`

Nine verifiers, in the plan's order, with **real probes**:

1. **Software** — core + phase package imports; `__version__` semver at
   the phase floor; §20 vocabularies verbatim; pyproject↔package
   agreement and the stdlib-only core.
2. **Windows** — package vocabulary (everywhere); platform probe,
   `M:\NEXUS` checkpoint probe and PowerShell probe — **judged on the
   real box; honest SKIP elsewhere**.
3. **Browser** — §11 vocabulary; playwright availability probed via
   `find_spec`, never assumed.
4. **Documents** — §18 kinds/stages/verification contract; docling
   MODE A/B probe with the native-floors law in its skip message.
5. **Research** — §17 engine/evidence/finding contracts, the authority
   map, the three declared providers.
6. **Git** — a real binary on PATH; the repo root found by walking up,
   HEAD sha read straight from `.git` with stdlib; §16 engine vocabulary.
7. **Memory** — an **actual §12 roundtrip**: `SQLiteMemoryStore` →
   `MemoryEngine` → remember → retrieve → `close()` **before** the temp
   dir is removed (the Windows handle lesson).
8. **Models** — §5 vocabulary; llama.cpp binary probed honestly
   (SKIP when absent); the measured-vs-documented provenance law.
9. **System** — python ≥ 3.11; a real temp write/read-back; real disk
   free; CPU count and architecture observed.

### §20.3 Evidence — `nexus/verification/evidence.py`

- Every observation carries `method · output · timestamp · artifact ·
  result` — the plan's five fields, verbatim.
- `EvidenceStore.record` seals each observation as a JSON artifact with
  its own **sha256**; `read_back` re-verifies the digest — **tampering
  is detected**, not assumed away.
- An evidence without `output` is refused: *an unlabelled observation is
  no observation*. Identical observations share one artifact (content-
  addressed).
- The whole report persists as `report.json` under the same seal.

### §20.4 Repair Loop — `nexus/verification/repair.py`

`Fail → Diagnose → Fix → Retest → Verify` — verbatim and ordered:

- **Diagnose** — `RuleDiagnostician` names the failure class from the
  real message: `missing-directory · locked-handle (WinError 32) ·
  transient · missing-file · unknown`.
- **Fix** — declared strategies: `CreateDirectoryStrategy`,
  `UnlockRetryStrategy` (gc + backoff — the generalised Windows handle
  lesson), `TransientRetryStrategy`, and the honest `NoOpStrategy`
  floor. A fix that claims to be applied must list what it changed.
- **Retest** — the same verifier runs the same criterion again.
- **Verify** — only a holding retest becomes the final PASS, and it is
  **labelled**: `repaired after N attempt(s)` — a repaired PASS is never
  mistaken for a first-try PASS. An unrepairable failure stops honestly
  after `max_attempts` with the full chain preserved.
- Every stage leaves sealed evidence — fail, diagnose, fix:\<sig\>,
  retest, verify — so the loop's own behaviour is verifiable.

### The engine — `nexus/verification/engine.py`

One `VerificationEngine` over the nine verifiers → one
`VerificationReport` with per-domain tallies and an honest overall:

- **PASS** — nothing failed/errored and something really passed;
- **DEGRADED** — nothing failed but parts of the truth live elsewhere
  (the Windows facts SKIP on non-Windows hosts);
- **FAIL** — any failure, any error, or *nothing proven* (all-SKIP is
  not a pass).

## 3. Verification of the phase (eating our own cooking)

| Layer | Result |
|---|---|
| Sandbox pytest (phase 20) | **55/55** (contracts 11 · evidence 8 · domains 13 · engine 5 · repair 13 — plus gate) |
| Live proof `live_verification_ci.py` (sandbox) | **10/10 rungs — VERDICT: PASS** |
| Exit gate `verify_exit_criteria.py` A–F | **26/26** with 15–19 regression green |
| Regression: phases 15–19 | 73 + 64 + 74 + 81 + 104 = **396/396** |
| Ruff (`nexus/`) | clean |
| Pyright (`nexus/verification/`) | 0 errors |
| Device deployment | 51/51 files sha-verified via tunnel |
| Device pytest (phase 20) | 55/55 on Windows 10 · python 3.14.5 |
| Live proof on the real box | **10/10 rungs — VERDICT: PASS** (`M:\NEXUS\proofs\phase20_live.json`) |
| CI | 14/14 jobs green incl. `verification-live` |

On the device the strictness flips: the Windows-domain probes must
really **PASS** (platform · checkpoint `M:\NEXUS` · PowerShell) — the
off-Windows honest SKIP is not allowed to stand in for the facts there.

## 4. Honesty statement

- SKIP is a refusal with a written reason in its evidence — never a
  fake PASS; all-SKIP is a FAIL overall, not a pass.
- ERROR (a broken probe) is never smuggled through as SKIP or FAIL.
- A repaired PASS is labelled as repaired; its full chain rides in the
  outcome.
- No capability row above claims anything the rungs did not show.

## 5. Files

```
nexus/verification/__init__.py      exports — the plan's vocabulary
nexus/verification/contracts.py     §20.1 + §20.2/§20.3/§20.4 vocabularies
nexus/verification/evidence.py      §20.3 EvidenceStore (sha256-sealed)
nexus/verification/domains.py       §20.2 nine verifiers + BaseVerifier
nexus/verification/engine.py        VerificationEngine + VerificationReport
nexus/verification/repair.py        §20.4 RepairLoop + strategies
tests/phase20/conftest.py           path setup
tests/phase20/test_contracts.py     §20.1 laws (11)
tests/phase20/test_evidence.py      §20.3 store laws (8)
tests/phase20/test_domains.py       §20.2 verifier laws (13)
tests/phase20/test_engine.py        report/tally laws (5)
tests/phase20/test_repair.py        §20.4 loop laws (13)
tests/phase20/live_verification_ci.py  10-rung live proof
tests/phase20/test_device_proof.py  the tunnel execution path
tests/phase20/verify_exit_criteria.py  the A–F gate
```

Plus: version bump (`0.20.0`/`NEXUS_PHASE=20`), pyproject description,
CI workflow (Phase 20 gate step + `verification-live` job), README
matrix row + AR/EN summaries, this report.
