# PHASE 2 — Workspace + Scope + Policy · Completion Report

> Final Build Plan §3 · Concept locked: **Full Control within Task Scope**
> المصدر الحاكم: `docs/reference/NEXUS-Final-Build-Plan-v1.0.md` (§3.1–§3.5) + `NEXUS-Master-Technical-Specification-v1.0.md` (§18–§22)

## الملخص التنفيذي

<div dir="rtl">

المرحلة الثانية تُثبّت مفهوم **التحكم الكامل داخل نطاق المهمة**: مساحة عمل لكل سياق مستقل (§3.1)، نطاق من ستة أبعاد يُحلّ من اللغة الطبيعية (§3.2–§3.3)، وصول عبر المساحات **بلا منع مطلق** — مقصوص على الجزء المطلوب فقط ومُدوَّن للتدقيق (§3.4)، وسياسة مهمة من تسعة مكونات تحوّل المفهوم إلى قرارات allow/confirm/deny لكل فعل مقترح (§3.5). كل ذلك بلا أسماء أحداث جديدة — سجل §2.2 المعياري (28) يبقى مصدرًا وحيدًا ملزمًا، كما تنص وثيقة المرحلة الأولى.

</div>

Phase 2 anchors **Full Control within Task Scope**: one registry-backed workspace per independent context (§3.1), a six-dimension scope resolved from natural language (§3.2–§3.3), cross-workspace access that is **never an absolute block** — carved to the requested part only and audit-logged (§3.4), and a nine-component task policy that turns the concept into allow/confirm/deny decisions per proposed action (§3.5). No new event names were invented — the §2.2 canonical registry (28) remains the single authority, exactly as Phase 1 documented.

---

## 1 · Deliverables vs. Plan (مقابل الخطة)

| Plan section | Spec support | Delivered | Location |
|---|---|---|---|
| §3.1 Workspace Manager | Spec §20, §22 | `Workspace` — the **seven fields verbatim** (`id name path project memory_namespace git_repository settings`), `wsp_` identities, unique names, atomic JSON registry under `NexusPaths.workspaces`, longest-root path resolution, synthetic default (`config.workspaces.default_workspace`) | `nexus/core/workspace/` |
| §3.2 Scope Engine | Spec §18, §19 | `Scope` — the **six dimensions verbatim** (`filesystem_paths applications browser_sessions network_permissions tools repositories`), coverage checks, merge, `Task.scope` mapping bridge | `nexus/core/scope/models.py` |
| §3.3 Scope Resolution | Spec §18 | `ScopeEngine.resolve` — path token (1.0) → name (0.8) → project (0.7) → default (0.3); the plan example **"اشتغل على M:\Client" → workspace Client, filesystem scope M:\Client** proven verbatim | `nexus/core/scope/engine.py` |
| §3.4 Cross-workspace Access | Spec §21 | `request_cross_workspace` — **never an absolute block**: access granted by design, carved to keyword-matched sub-scopes only (with or without a path lister), `CrossWorkspaceAccess` audit records, histories never merged; unregistered target = nonexistence, not denial | `nexus/core/scope/engine.py` |
| §3.5 Policy Engine | — | `TaskPolicy` — the **nine components verbatim**, `AutonomyLevel` (OBSERVE/SUGGEST/ACT_CONFIRMED/FULL), dotted overrides, workspace-seeded policies, serialization; `PolicyEngine.decide` — explicit-negative deny · within-scope allow · outside-scope escalate/confirm, reads never walled | `nexus/core/policy/` |
| Integration | Plan §3 | `NexusRuntime.boot` wires workspace manager + scope engine + policy engine; `boot` payload reports phase 2; registry persists across restarts; `Task.scope` carries the six canonical keys | `nexus/core/config/runtime.py` |

## 2 · Exit criteria proof (إثبات معايير الخروج) — `tests/phase02/verify_exit_criteria.py`

**143/143 checks passed (0 failed), exit code 0.** Sections:

| Section | Scope | Checks |
|---|---|---|
| A — Workspace Manager | §3.1 | **32** |
| B — Scope Model | §3.2 | **19** |
| C — Scope Resolution | §3.3 | **14** |
| D — Cross-workspace Access | §3.4 | **15** |
| E — Task Policy | §3.5 | **21** |
| F — Policy Engine · Integration · Regression | §3.1–§3.5 | **42** |
| **Total** | | **143** |

Key proofs inside F: the §3.3 example resolved through the booted runtime; cross-workspace READ allowed / WRITE escalated / `allow_cross_workspace=False` → human approval **not a wall**; OBSERVE denies mutations, SUGGEST confirms them, FULL allows within scope; protected-branch pushes confirm even at FULL; workspace registry reloads after NEXUS restart; `Task.scope` holds the six §3.2 keys; and the **Phase 1 harness is executed as a subprocess and still green (98/98)** — Phase 2 broke nothing.

## 3 · Quality gates (بوابات الجودة)

- `ruff check nexus tests` — **All checks passed** (line length 100, E/F/W/I/N/UP/B).
- `pyright` (standard, 3.11) — **0 errors, 0 warnings, 0 informations**.
- `tests/phase01/verify_exit_criteria.py` — **98/98** (regression, run twice: standalone + inside §F).
- `tests/phase02/verify_exit_criteria.py` — **143/143**.

## 4 · Documented design decisions (قرارات موثقة)

1. **No new event names.** The §2.2 registry of 28 canonical events is authoritative; inventing names is forbidden (Phase 1 runtime docstring). Workspace/scope/policy components publish nothing; their audit trail is their own records + the registry file.
2. **Scope is not a sandbox (Spec §19).** Coverage checks are placement logic for *decisions*, not OS-level isolation. NEXUS can reach the whole machine; the scope is the logical/policy boundary of the task relation.
3. **Never an absolute block (Plan §3.4).** The only hard denials are *explicit negative policy* (blocked tools/hosts, offline, git disabled, external AI disabled, app launch disabled, OBSERVE mutations). Outside-scope work is scoped + audited + (below FULL autonomy) confirmed — `allow_cross_workspace=False` routes to a human, it never walls. Reads in other workspaces stay allowed (Spec §21 retrieval flow). An unregistered target is nonexistence, not denial.
4. **Workspace registry is write-explicit.** `default()` returns a synthetic reserved-id workspace when the configured default name isn't registered; nothing is auto-persisted at boot.
5. **Path semantics.** Normalization: separators → `/`, case-insensitive comparison (pragmatic for Windows roots), longest-root resolution; name/project matching uses **word boundaries** — `ClientWebsite` must not match the name `Client`.
6. **Policy defaults encode the goal.** Autonomy FULL, allow-lists `["*"]`, cross-workspace allowed, git on with `main` protected — full control *within* the declared policy, never above it.
7. **`Task.scope` bridge.** The Phase 1 `ScopeMap` placeholder is now produced by `Scope.to_scope_map()` with the six §3.2 keys verbatim; persistence stays mapping-shaped (no schema change, §2.5 records unchanged).

## 5 · Inventory (الجرد)

- **Package** — `nexus/core/workspace/` (models · manager · init) · `nexus/core/scope/` (models · engine · init) · `nexus/core/policy/` (models · engine · init)
- **Modified** — `nexus/core/config/runtime.py` (wiring + phase payload 2) · `nexus/core/__init__.py` (exports) · `nexus/__init__.py` (0.2.0, NEXUS_PHASE=2) · `nexus/core/session/models.py` (ScopeMap docstring) · `pyproject.toml` (0.2.0)
- **Tests** — `tests/phase02/verify_exit_criteria.py` (sections A–F, 143 checks, runs Phase 1 as subprocess)
- **Docs** — README roadmap & structure, CHANGELOG, this report
- **Registry format** — `nexus.workspaces.registry` v1, `workspaces.json` under `NexusPaths.workspaces`, atomic writes (temp + `os.replace` + `fsync`)

## 6 · Reproduce (إعادة الإثبات)

```bash
python tests/phase02/verify_exit_criteria.py     # 143/143 + phase01 98/98, exit code 0
python tests/phase01/verify_exit_criteria.py     # 98/98 (standalone regression)
ruff check nexus tests && pyright                # clean
```

---

<div dir="rtl">

**الحكم:** استُوفت أقسام الخطة §3.1–§3.5 حرفيًا (الحقول والأبعاد والمكونات كما وردت نصًّا)، والمثال المرجعي «اشتغل على M:\Client» مُثبت بحرفيته، وقاعدة «لا منع مطلقًا» محكومة باختبارات. الانتقال إلى **PHASE 3 — Hardware Intelligence + Resource Manager** (الخطة §4) مُصرَّح به وفق قاعدة الترتيب الإجباري.

</div>

**Verdict:** Plan §3.1–§3.5 satisfied literally (fields, dimensions and components verbatim), the reference example "اشتغل على M:\Client" proven verbatim, and the never-block rule guarded by tests. Transition to **PHASE 3 — Hardware Intelligence + Resource Manager** (Plan §4) is authorized under the mandatory build order.
