# PHASE 15 REPORT — Coding System (New Plan §15)

**Status: Implemented + Integrated + Tested + Verified + Documented + Committed**

**Identity (the operator's words):** «تحويل NEXUS إلى Developer Agent حقيقي» —
turn NEXUS into a real Developer Agent.

## What landed — `nexus/coding/` (6 modules, stdlib-only)

| Module | Sections | What it does |
|---|---|---|
| `contracts.py` | §15.1/§15.2/§15.6 | The seven operations, ten specialists, eight loop stages — verbatim vocabularies; requests/results; EditAction (Cline-shaped search/replace); ReviewVerdict; session records. |
| `specialists.py` | §15.2 | Ten declarative specs → the §6.4 Agent Registry (the four verbs); every mapped NEXUS module:attribute import-checked; loop-stage affinity. |
| `operations.py` | §15.1 | The CodingAgent contract — one `execute` dispatcher: analyze (via §14 code-intel), plan, edit (digests + diffs), run/test (real subprocess, timeout, capture), debug (findings + hypotheses + §13 lessons), review (re-runs tests, renders the verdict). |
| `loop.py` | §15.6 | The eight-stage loop over the §2.4 task machine, canonical §2.2 events, bounded Debug→Retest cycles, skeleton always eight-wide, latest-verdict honesty. |
| `session.py` | §15.5 | The Cline-inspired trail: files read/edited, tool calls, atomic persistence, revival. |

## Proofs

| Layer | Result |
|---|---|
| Local pytest | 73/73 (`tests/phase15/`) |
| Local exit gate | 32/32 (`verify_exit_criteria.py`, sections A–F) |
| Quality | ruff clean · pyright 0 errors · core stdlib+nexus-only (AST-proven) |
| Device (Windows) | `live_proof_device.py` via `code_run_tests` → `proofs\phase15_live.json` |
| Regression | Phases 1–14 gates green (the house chain) |

## Repository Round 12 (MODE B/D — zero imports)

* **OpenHands** `c9b6cea` (MIT) — coding-agent architecture: event loop, sandbox boundary, delegation. Patterns only.
* **OpenCode** `dff8fbc` (MIT) — workflow/runtime split, session persistence. Patterns only.
* **Cline** `b63c738` (Apache-2.0) — the session trail + edit model (search/replace, propose→apply). The §15.5/§15.1 shapes follow it as MODE D.

Full audit: `docs/REPOSITORY-INTEGRATION.md` (Round 12).

## The CI's catch — stale bytecode (2026-09-09)

The fast GitHub runner caught what the slow sandbox never showed: the
loop's build stage (`compileall`) writes `__pycache__` from the buggy
source; the `* → /` fix preserves file **size**; the edit lands within
the same int-second **mtime** — CPython's two-field `.pyc` validation
calls the stale cache "valid" and serves the OLD module to the retest,
so the loop spiraled to its bound (six loop tests failed only on CI).

Root-cause fix, not a workaround: **the edit operation now purges stale
bytecode for every file it writes** (`_invalidate_bytecode` —
`__pycache__/<stem>.cpython-*.pyc` + legacy `<stem>.pyc`), the purge is
payload evidence (`bytecode_purged`), and the trap is pinned by
`test_edit_invalidates_stale_bytecode` (worst case forced: same mtime,
same size) + a gate check that arms the trap exactly the way the loop's
build stage does.

## The NEXUS-ownership law (unchanged)

The loop, the contract, the specialists and the session are
NEXUS-native (Plan §0.5/§61): the fix proposal is a pluggable hook
(`fixes=` recipes now, the model later) — NEXUS owns the machinery,
models plug in behind it.
