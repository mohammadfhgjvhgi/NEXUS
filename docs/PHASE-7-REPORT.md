# PHASE 7 REPORT — Tool System (Final Build Plan §8)

**Status:** COMPLETE · **Exit criteria:** 88/88 (A=16 · B=20 · C=22 · D=16 · E=8 · F=6) **+1 bonus proof**
**Regressions inside §F:** 98/98 · 143/143 · 104/104 · 106/106 · 116/116 · 88/88 — all green.
**Quality gates:** ruff clean (nexus + tests) · pyright 0 errors · stdlib-only core (`dependencies = []`) · zero new event names (⊆ 28 canonical).
**Scope:** Plan §8.1–§8.5 + Spec §71 (كل MCP tool يمر بـ NEXUS gate) + the 18-step sub-phase cycle (operator directive, Phase 6+).

---

## 1. What the plan asked, and what landed

| Plan § | Ask | Delivered | Proof |
|---|---|---|---|
| 8.1 Tool Registry | Every tool: `id · name · description · input_schema · output_schema · permissions · scope_requirements · risk · verification · version` | `nexus/tools/models.py` (the §8.1 records, nine fields verbatim; risk 0..4 — level 4 refused; verification strategies; the RouterTrace) + `nexus/tools/registry.py` (validated registration, upgrade-only replacement, freeze, discovery filters, honest capability probes) | A (16) |
| 8.2 Tool Router | Agent → discovery → permission → scope → resource → execute → normalize → verify | `nexus/tools/router.py` — the verbatim seven-stage pipeline with an **ordered proof trace on every call**; the §8.1 risk gate (config-level, policy-independent); confirmation fold (approve/deny/no-hook); Phase-2 policy+scope composition (blocked tools, OBSERVE/SUGGEST autonomy, §3.4 escalate-never-wall); the Phase-3 concurrency resource gate (released in `finally`); the Verify stage **flips lying outcomes**; canonical `tool.called/completed/failed` events on direct routes (the §6.2 loop keeps ownership on its path — no duplicates) | B (20) |
| 8.3 Native Tools | filesystem · terminal · process · hardware · windows · clipboard · screen · git · github | `nexus/tools/native/` — the nine, verbatim. All stdlib (even the PNG encoder — zlib+struct IHDR/IDAT/IEND). Platform-honest: windows/clipboard/screen report unavailability instead of faking; terminal is list-argv only (never a shell string) with a hard timeout; git is list-argv subprocess over a scope-checked repo; github is REST over `urllib` with **offline-provable request construction** and token hygiene | C (22) |
| 8.4 MCP | modelcontextprotocol — interoperability layer, **USE the official SDK behind the NEXUS Tool Router** | `nexus/tools/mcp/adapter.py` — the official Python SDK **v2 stable line** (`mcp>=2.0,<3`, MODE A pinned optional extra `[mcp]`, MIT): one session thread per server (asyncio loop + `run_coroutine_threadsafe` bridging), `initialize` → `tools/list` → each MCP tool registered as a §8.1 record (`mcp.<server>.<tool>`), `tools/call` with per-server timeout, **honest failure & recovery** (a crashed session fails that call — no silent retry that could double-apply a mutation; the *next* call respawns the transport) | D (16) |
| 8.5 MCP Servers | Clone only what the task needs: filesystem · git · fetch · memory · database — **every one behind NEXUS permission + NEXUS scope** | `config/tools/mcp.toml` — the five §8.5 names declared with launch commands referencing the **pinned audited clones** (Round 4, `docs/REPOSITORY-INTEGRATION.md`), each with `risk_ceiling` clamp, `allowed_tools`/`blocked_tools` gates (refused **before any stdio byte**), `scope_paths` (path arguments the Scope stage checks), disabled-by-default (per-machine opt-in). The in-repo echo fixture + the **official TypeScript filesystem server via npx** prove the chain end-to-end — including a **cross-SDK roundtrip**: write through MCP → read back through the native tool | D (16) + bonus |

**Module count:** `nexus/tools/` = 15 files (models, registry, router, native×10, mcp×3 + `__init__`), all NEXUS-owned; core stdlib-only, the official MCP SDK behind the `[mcp]` extra.

## 2. The integration seams (real, not cosmetic)

1. **§6.2 loop** — the Phase-5 `ToolSink` aperture is now filled by
   `RoutedToolSink(ToolRouter)`: `AgentLoop(tools=sink)` dispatches
   `call_tool` decisions through the full seven-stage pipeline; the
   loop keeps owning the canonical `tool.*` events (proven: exactly
   one `tool.called` + one `tool.completed` per routed act) and the
   verification note rides the output (`[verify:path_size ok]`).
2. **Phase-6 veto still in front** — `pre_tool_call` fires *before*
   the sink: a vetoed routed tool never executes (proven in §E: the
   file never appears).
3. **Runtime wiring** — `NexusRuntime` builds the registry (native
   nine + MCP servers from `config/tools/mcp.toml`, enabled-only,
   per-server honest failure), the router over the injected
   Phase-2/3 engines, and hands the sink to the Master Agent
   (`master_agent._tools is runtime.tool_sink` — identity-proven).
   `tools.native_enabled=false` + `tools.mcp_enabled=false` unwire
   everything — the Phase-6 runtime, byte for byte (proven).
4. **Shutdown order** — ownership released → MCP sessions closed
   (stdio children exit cleanly) → models unloaded → repository
   closed (§2.6 vocabulary, no invented event names).

## 3. Documented decisions

1. **Official SDK v2 line (operator pin)** — the plan says "use the
   official SDK per NEXUS's settled language"; NEXUS is Python, so
   the **v2 stable line** (`mcp>=2.0,<3` at 2.1.1) is the MODE A
   extra `[mcp]`. Audit finding: the official **Python** servers
   (git/fetch 0.6.x, sqlite) currently pin `mcp>=1.29,<2` on their
   own side — they run under `uvx` with isolated environments on the
   machine, so no conflict with NEXUS's v2 client; protocol-level
   interop is what the stdio wire carries (initialize negotiation).
   The **cross-SDK bonus proof** (official TS filesystem server +
   official Python v2 client) demonstrates exactly that wire-level
   interop.
2. **v2 API deltas caught live** — `FastMCP` → `MCPServer`
   (`mcp.server.MCPServer`), `isError` → `is_error` on
   `CallToolResult`. The adapter accepts both names (v1/v1.29
   interop) and the echo fixture uses the v2 surface.
3. **MCP risk = server ceiling clamp, verification = none** — §71:
   an external server's *claim* is not evidence. The Verify stage
   records "not required" honestly for MCP tools; native tools carry
   real verification contracts (path_size/exit_zero/json_field…).
4. **MCP tools are conservatively mutating** — unknown server
   semantics → every MCP call is treated as a mutation by the Scope
   stage (the strictest reading; in-workspace at FULL autonomy still
   flows, out-of-scope escalates).
5. **Git tool risk = 2, not 3** — the platform's own remote surface
   rates `git_commit` dl 3 (localhost-only there); NEXUS composes
   equivalent protection differently: risk 2 + scope WRITE check +
   §3.5 policy (protected branches, OBSERVE/SUGGEST escalation).
   Documented so the two risk languages stay reconcilable.
6. **Terminal risk = 3** — mirrors the platform's `code_run_cmd`
   dl 3: with the default `confirm_danger_above = 2`, every terminal
   call passes a human confirmation gate (proven in §B).
7. **The five servers disabled by default** — "clone only what the
   task needs": each machine flips `enabled` per capability after
   its runtime (npx/uvx) is present. A missing/broken server is an
   isolated honest report — never a boot failure (proven in §D).

## 4. Failure & recovery (Step 15 of the 18-step cycle)

| Failure injected | Behavior (proven) |
|---|---|
| unknown tool | discovery:fail, honest error, no crash |
| platform-unavailable tool (windows/screen on Linux) | capability report + actionable error |
| risk above threshold, no hook | refused with the exact reason |
| confirmation hook denies | refused, trace records the denial |
| policy-blocked tool / OBSERVE mutation | Phase-2 engine denial |
| out-of-scope mutation | §3.4 escalation (confirm, never wall) |
| exhausted concurrency budget | honest refusal; slot freed in `finally` |
| handler raises | execute:fail + verify:skip, exception name preserved |
| lying handler (exit 128) | **verify flips the outcome to failure** |
| MCP server returns isError | honest McpToolError with the server text |
| MCP server process dies mid-call (in-protocol `die` fixture) | that call fails (no silent retry); the **next** call respawns and recovers |
| broken server at connect | isolated per-server error; natives keep working |
| double registration | RegistryError (no silent replace) |

## 5. Repository Round 4 (the §0.2 cycle, mandatory per phase)

Cloned + audited + pinned (see `docs/REPOSITORY-INTEGRATION.md` Round 4):

| Repo | Pin | License | Mode |
|---|---|---|---|
| `modelcontextprotocol/python-sdk` | clone 08a3bc8 · PyPI **2.1.1** (v2 stable line) | MIT | **A (USE)** — the `[mcp]` extra behind the router |
| `modelcontextprotocol/servers` | d73f99e | MIT→Apache-2.0 transition (per-file) | B (operational clones: filesystem 0.6.3 TS · git 0.6.2 Py · fetch 0.6.3 Py · memory 0.6.3 TS) |
| `modelcontextprotocol/servers-archived` | 9be4674 | MIT | B (sqlite 0.6.2 — the §8.5 "database" server) |

Security notes: filesystem server's path validation (null-byte
rejection, normalize+resolve, allowlist) reviewed; git server's
gitpython surface reviewed (write ops gated by NEXUS scope on our
side); fetch server SSRF surface noted (network policy gates it);
memory server is a local JSON graph; sqlite server exposes
`write_query` (risk ceiling 2 + NEXUS scope on our side).

## 6. Exit criteria detail

`tests/phase07/verify_exit_criteria.py` — **88/88 + 1 bonus**:

* **A (16)** — §8.1: field list verbatim; every tool carries the ten;
  risk scale 0..4 with level-4 refused; strict X.Y.Z; empty name /
  non-object schema / empty permissions / risk-4 / bad version all
  rejected; duplicate refused; upgrade-in-place; freeze; discovery
  filters; typed honest capability reports; native family count;
  serialization roundtrip.
* **B (20)** — §8.2: verbatim pipeline constant; ordered trace;
  path_size proof; unknown tool; unavailable tool; risk gate without
  policy; folded confirmation (approve/deny); policy denial;
  OBSERVE refusal; out-of-scope escalation; in-workspace FULL flow;
  exhausted budget; slot freed after failure; verify flip
  (exit_zero); verify:skip on raised handlers; canonical events;
  the sink contract (ToolResult shape, honest `available()`, the
  verify note).
* **C (22)** — §8.3: nine names verbatim; native ids/versions;
  filesystem full suite (write/append/move/copy/stat/find/list/
  delete + root-relative resolution); terminal (exit 0, 127,
  timeout 124); process (list/info/kill-honest); hardware
  snapshot/cpu/disk; windows/clipboard/screen honest availability;
  the stdlib PNG encoder (chunk-parsed: IHDR dims + IDAT
  decompressed pixel-exact); git on a real repo (status/add/commit/
  log, exit-zero verified); github offline construction + POST body
  + live-or-honest.
* **D (16) + bonus** — §8.4/§8.5: SDK present; **v2 line**; five
  servers declared with gates; blocklist/allowlist semantics;
  config validation; MCP route through the full pipeline; add→42;
  §8.1 record with risk clamp; isError honesty; blocked-before-
  stdio; allowlist bounds; crash honesty + respawn recovery; broken
  server isolation; no-servers degradation; **BONUS: official TS
  filesystem server via npx — cross-SDK roundtrip (write via MCP →
  native read-back)**.
* **E (8)** — runtime wiring + phase-7 boot event + Master-Agent
  sink identity + clean shutdown + disabled runtime byte-for-byte
  + the loop completing a routed tool act (file exists, evidence
  kept) + no duplicate events + the Phase-6 veto still blocking.
* **F (6)** — Phases 1–6 harnesses as subprocesses: 98 · 143 ·
  104 · 106 · 116 · 88 — all exit 0.

## 7. Real-machine evidence (Step 14)

The same capability domains the native tools cover were proven on
the **real Windows box** through the operator's remote surface
(dl 0/1/2 only, Bearer, both tunnels): filesystem read/write with
SHA verification on `M:\NEXUS`, `git_status`/`git_log`, process
listing, system info, screen size + window enumeration — the
deployment section of the phase log records the exact calls. (The
native tools themselves run wherever NEXUS runs; the Windows-native
tools activate there via the same capability ladder proven on
Linux.)

---

**Bottom line:** every capability now enters NEXUS as one §8.1
record behind one §8.2 choke point — native or MCP, local or
external — gated, scoped, resourced, executed, normalized and
**verified**. The Phase-5 aperture and the Phase-6 veto finally
have something real to guard.
