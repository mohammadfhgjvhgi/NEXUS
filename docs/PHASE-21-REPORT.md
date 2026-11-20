# PHASE 21 — Security System — Delivery Report

> **Full capability + controlled execution.**
> New Plan §21 · Spec §156–§166 (§160 · §161 · §163 · §164 · §165) ·
> Blueprint §79 · v0.1 §57 · version 0.21.0 · `NEXUS_PHASE = 21`

## 1. What was built

`nexus/security/` — eight modules, stdlib-only at top level:

| Module | Section | Content |
|---|---|---|
| `contracts.py` | §21 nouns | `RiskLevel` (§163 verbatim) · `GateVerdict` · `SecurityAction` · `GateDecision` · `Credential` (§160 six fields) · `PROTECTED_SINKS` (§21.10 verbatim) · `SCAN_KINDS` + `TRIVY_REPOSITORY` (§21.9 verbatim) · the error family |
| `permissions.py` | §21.1+§21.2 | `RISK_CLASSIFICATION` (the five §163 examples verbatim) · `classify()` · `ScopeEngineIntegration` (§3.3 consumed, §3.4 carve) · `PermissionEngine.decide` (§163 risk × §3.5 policy) |
| `gates.py` | §21.3–§21.5 | `ToolGate` (registry + confirm-first; ghosts escalate) · `McpGate` (server registry + per-server tool allow-lists) · `PluginGate` (declared permissions; `secrets` never a default) · `GatePipeline` (the §57 walk, every verdict audited) |
| `secrets.py` | §21.6 | `SecretVault` — references out, text never out; `resolve` audited text-free, last-used advanced; `scrub` (exact-match) + `contains`; env provider; thread-safe |
| `redaction.py` | §21.7 | `Redactor` — ten pattern families → `[REDACTED:<kind>]`; sensitive-named JSON keys redacted whole; `findings`/`contains_secret`/`redact_mapping` |
| `audit.py` | §21.8 | `AuditRecord` (Who\|What\|When\|Where\|Result verbatim) · `AuditLog` (guarded at append, JSONL artifacts, filters) · `ActivityFeed` (the §165 split) |
| `trivy.py` | §21.9 | `TrivyScanner` (MODE A — real `trivy fs --format json --scanners …` + JSON parsing) · `BaselineScanner` (MODE B — honest stdlib; vulnerability never invented) · `Finding`/`ScanReport` with redacted snippets |
| `rules.py` | §21.10 | `SecurityRules` — the four doors (memory · normal_chat · logs · activity), two passes (vault-exact → patterns), `SecretLeakError` the hard stop |

## 2. The laws, proven

1. **Blueprint §79 — security is not an obstacle.** An explicit
   policy denial is the only hard stop; everything else flows or
   escalates. `test_blocked_tool_denied_by_explicit_policy`,
   `test_out_of_scope_at_full_is_flagged_not_walled`.
2. **Spec §163's note — L4 executes high risk in-scope.**
   `test_high_risk_in_scope_at_full_autonomy_executes` (delete at
   FULL inside the scope → ALLOW, rule `high-risk-in-scope-at-full-autonomy`);
   below FULL the same action escalates (`high-risk-requires-confirmation`).
3. **Spec §160 — the reference law.** No secret text exists on any
   vault surface (`as_dict`, `repr`, audit trail) — proven for the
   vault, the credential, the environment provider.
4. **Spec §164/§165 — audit ≠ activity.** Five fields verbatim and
   in order; two separate surfaces; the audit JSONL artifact
   round-trips.
5. **§21.10 — structurally enforced.** The audit log and activity
   feed take the guard *at construction*; a planted secret appended
   by a "careless" caller still lands clean on disk. The exact-match
   scrub catches the patternless secret the patterns cannot see.
6. **The honesty law (§20 heritage).** MODE B never invents a
   vulnerability — zero findings plus a reason in `notes`. The
   scanner redacts its own findings before reporting them.

## 3. Verification numbers

| Stage | Result |
|---|---|
| Sandbox unit tests | **82/82** (contracts 10 · redaction 12 · secrets 9 · permissions 12 · gates 14 · audit 7 · trivy 11 · rules 7) |
| Exit gate (A–F) | **19/19** with regression on suites 15–20 |
| Live proof (sandbox) | **10/10** rungs |
| Ruff 0.16.6 | clean (0 errors) |
| Pyright 1.1.411 (standard) | 0 errors on `nexus/security/` |

## 4. Discoveries logged

1. **The toolchain redacts secret-shaped literals on write.** Test
   fixtures with planted secrets came back from the Write tool with
   `[REDACTED:*]` markers — the sandbox itself enforces §21.10. All
   planted values are now built by string concatenation; the test
   suite documents this in its own docstring.
2. **Adjacent string literals inside parentheses collapse to one
   string** when the tuple comma is missing (`notes=("a" "b")` is a
   string, not a tuple) — found by the honest-notes rung failing
   while `inspect.getsource` showed the intended code; confirmed by
   disassembling the code object's constants.
3. **The Tool Gate's promise must match its default.** With a
   wildcard allow-list default, "unregistered escalates" required
   the allow-check to treat *registration* as the flowing condition
   — ghosts escalate even under `allowed=("*",)`.

## 5. Files

```
nexus/security/__init__.py       nexus/security/contracts.py
nexus/security/permissions.py    nexus/security/gates.py
nexus/security/secrets.py        nexus/security/redaction.py
nexus/security/audit.py          nexus/security/trivy.py
nexus/security/rules.py
tests/phase21/conftest.py        tests/phase21/test_contracts.py
tests/phase21/test_redaction.py  tests/phase21/test_secrets.py
tests/phase21/test_permissions.py tests/phase21/test_gates.py
tests/phase21/test_audit.py      tests/phase21/test_trivy.py
tests/phase21/test_rules.py      tests/phase21/live_security_ci.py
tests/phase21/test_device_proof.py tests/phase21/verify_exit_criteria.py
```

Identity: `nexus/__init__.py` (`0.21.0` · `NEXUS_PHASE = 21`) ·
`pyproject.toml` · `.github/workflows/ci.yml` (Phase 21 harness +
`security-live` job installing trivy v0.58.2 with
`NEXUS_REQUIRE_TRIVY=1`).
