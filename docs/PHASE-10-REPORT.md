# PHASE 10 REPORT — Browser Runtime (Build Plan §11 / Spec §51–§55, §209)

> Status: **Complete** · Commit: see `CHANGELOG.md` · Exit criteria: **70/70 + live browser proofs (local Chromium PASS 15/15 · device PASS)** · CI job: "Phases 1–10" + the browser-live job
>
> الهوية: «إعطاء NEXUS Browser capability كاملة» — Playwright خلف الموجّه،
> والجلستان منفصلتان بنيويًا، والأسرار لا تعبر واجهة الأداة أبدًا.

## 1. ما بُني (What landed)

```
nexus/browser/                   ← §11 the Browser Runtime (NEXUS-owned)
├── __init__.py                  exports · register_browser_tools · the DOM layer
├── models.py                    §11.1 the vocabulary (data, not code)
├── sessions.py                  §11.4 user/agent isolation (ADAPT: browser-use)
├── auth.py                      §11.5 DPAPI vault + redaction (pure ctypes)
├── selfheal.py                  §11.3 selector ladder (ADAPT: browser-harness)
├── engine.py                    §11.1 Playwright adapter (MODE A «USE», lazy)
├── api.py                       the façade over the §8.2 router
└── tools.py                     the §8.1 record + the §9.5 dom_a11y rung

nexus/tools/native/browser.py    the thirteenth §8.1 record (risk 2)
nexus/tools/__init__.py          build_tool_system(browser=…)
nexus/core/config/               browser_enabled · browser_channel · browser_headless
nexus/core/config/runtime.py     browser_runtime + dom_a11y wiring + engine shutdown

tests/phase10/
├── verify_exit_criteria.py      70/70 (A–F + regressions 1–9)
├── live_browser_ci.py           the real-Chromium roundtrip (CI + local)
└── live_proof_device.py         the on-device proof (sessions·CDP·vault·claim)
```

### §11.1 Playwright — MODE A «USE» (the `[browser]` extra)

The §11.1 families verbatim — **navigation · DOM · forms · upload ·
download · tabs · browser states · automation** — as 26 tool
operations behind the §8.2 router (policy → confirmation → scope →
resources → execute → normalise → **verify**). The engine imports
Playwright lazily per method (a missing extra never breaks the
boot), serializes every op behind one lock (the sync API's
contract), and climbs the **channel ladder** — chromium → chrome →
msedge — so a machine with Chrome installed needs **no 150 MB
download**: the operator's system Chrome *is* the engine, launched
with the agent's own profile. Transfers (upload/download/screenshot
and the secret file) are **path-scoped** by the §8.2 stage.

### §11.2 browser-use — ADAPT (Round 7, zero imports)

The pinned-dependency audit (aiohttp · pydantic · posthog ·
google-api-core …) rules out importing; the *patterns* are absorbed:
the two-layer **BrowserSession** split (event-driven for agents ·
direct calls for execution), **BrowserProfile →
launch_persistent_context** (the persistent-workflows semantics —
cookies and localStorage survive across runs in the isolated agent
profile), and the action-registry surface (every action maps 1:1
onto a §8.1 operation — declarative data, not scattered code).

### §11.3 browser-harness — ADAPT (Round 5 continued)

The **self-healing** essence, NEXUS-owned: `SelectorFallbacks` —
one logical element, several finders (css → role → text →
test_id); each miss falls through to the next strategy, every
attempt lands in a ledger, all-fail raises `SelfHealError`
**carrying the full ledger** (the honest-trace discipline).
Bounded retries with a settle wait — healing without an unbounded
loop. The editable-helpers seam maps onto the Phase-6 skill
library (documented, not duplicated).

### §11.4 Browser Sessions — isolation by construction

* **AGENT session** — `launch_persistent_context` rooted at the
  fixed `<data>/browser/agent-profile`; the guard *refuses* any
  profile that points at (or inside) a user Chrome/Edge/Firefox
  profile — structurally, not by convention.
* **USER session** — CDP attach (`connect_over_cdp`) behind the
  **§55 gate**: explicit consent + explicit URL, no discovery, no
  default. Without both, every user-session request refuses
  honestly — the default *never* mixes cookies or contexts.
* Every session carries an id that rides tool calls and events;
  the registry drains cleanly on shutdown.

### §11.5 Authentication — the never-crossing secret

Spec §209 made structural: **secrets never cross the tool
interface.**

* storage — `BrowserVault`: DPAPI (`CryptProtectData` via pure
  ctypes — the Phase-8 pointer discipline, explicit signatures)
  at rest under `vault.bin`; off win32 storing **refuses** (no
  plaintext downgrade, ever);
* injection — the tool takes `vault_ref: "site"`, the engine
  resolves it at the typing seam: the plaintext goes **into the
  page only** — there is nothing to redact in arguments because
  nothing rides them;
* storage paths — a secret enters via a **file path** or an **env
  variable name** (the path rides events; the content never does);
* defense in depth — every browser output passes the vault
  scrubber (a page echoing a password is masked to `[REDACTED]`).

### The §9.5 chain gains its dom_a11y rung

`BrowserDomLayer` registers as the third layer of the §9.5
hierarchy (application_api → uia → **dom_a11y** → vision → input):
chain actions (click · type · set_value · inspect with a
selector) now resolve through the browser before vision or raw
input ever fire. Two rungs of five are live; the chain stays a
chain of router clients — no second gate.

## 2. التوصيل (Integration)

* `ToolsConfig` += `browser_enabled` (default true) ·
  `browser_channel` (validated: chromium/chrome/msedge) ·
  `browser_headless` (default **false** — the operator *sees* the
  agent browser working in parallel, Spec §55);
* `build_tool_system(browser=True)` registers the **thirteenth
  record additively** (the Phase-9 twelve untouched);
* `NexusRuntime.browser_runtime` + the dom_a11y rung registered on
  the Computer Runtime's chain; engine defaults injected at wiring
  time; shutdown closes contexts and stops the driver;
* `browser_enabled=false` → the Phase-9 behavior **byte for byte**
  (façade None · 12 records · no dom_a11y provider).

## 3. الإثباتات (Evidence — five layers)

1. **Local**: `tests/phase10/verify_exit_criteria.py` — **70/70**
   (A=12 · B=12 · C=16 · D=9 · E=18 · F=3 + the 9 regression rows)
   including the §55 gate matrix, the profile-guard refusals, the
   never-crossing-secret schema contract, the healing ladder, the
   façade op mapping, and **Phases 1–9 re-run as subprocesses**
   (98 · 143 · 104 · 106 · 116 · 88 · 88 · 80 · 84).
2. **Local live Chromium**: `live_browser_ci.py` — **PASS 15/15**:
   a real Chromium roundtrip through the router — navigate · DOM
   read · fill · click · the form effect read back · upload ·
   download (file:// + a real local-http download) · tabs ·
   tab_new/select/close · snapshot · screenshot · close.
3. **CI** (GitHub): job "Phases 1–10" (ruff · pyright · the ten
   harnesses, playwright pinned for typing) + the dedicated
   **browser-live** job running the same 15-check roundtrip on a
   real installed Chromium.
4. **The real machine** (DESKTOP-46N9B2S · Python 3.14.5 via the
   t1 bridge) — `live_proof_device.py` **PROOF RESULT: PASS**:
   * §11.1 — **channel=chrome** (the ladder drove the operator's
     system Chrome — zero downloads); a real internet navigation
     (`https://example.org` → "Example Domain"); DOM read; form
     fill; tabs; a **7370-byte screenshot** of the visible agent
     window;
   * §11.4 — a stand-in user Chrome launched with
     `--remote-debugging-port=9223`; the **CDP attach passed the
     §55 gate** (explicit consent + URL); **two sessions lived
     side by side** (`kinds: [agent, user]`,
     `profiles_isolated: true`);
   * §11.5 — the **DPAPI vault round-trip** (store-from-file →
     issue → redact, all true); the form typed via `vault_ref`;
     **14 real tool events scanned — the secret appeared in
     zero outputs and zero events** (`secret_in_events: false`);
   * §10 — `claim_new_windows` relaunched the agent context and
     **claimed the new Chrome window as NEXUS**
     (`win-29034352 · "NEXUS Agent Session - Google Chrome"`) —
     the §10.3 arbitration now guards the human's browser while
     the agent works in its own.
   Evidence: `M:\NEXUS\proofs\phase10_live.json` +
   `phase10_browser.png`.
5. **Deployment**: 24/24 files written + SHA-verified on `M:\NEXUS`
   via the t1 bridge, marker `PHASE10_COMPLETE.txt`.

## 4. جولة المستودعات (Round 7)

| Repository | Mode | Pinned | Imported into NEXUS | Proven by |
|---|---|---|---|---|
| microsoft/playwright | **A (USE)** | dist 1.62.0 · clone 312030cd | the library whole, behind the router (`[browser]` extra) | 70/70 + local Chromium 15/15 + device PASS |
| browser-use/browser-use | **ADAPT** | e25ab65 | **no code** — the session/profile/action-registry patterns, rewritten | 70/70 (B/E) + device sessions proof |
| browser-use/browser-harness | **ADAPT** | eba1021 | **no code** — the self-healing ladder + the §55-style explicit gates | 70/70 (D) + device CDP proof |

The §0.5 iron rule holds: `nexus/browser/` core is **100%
NEXUS-owned stdlib**; playwright is a pinned optional extra the way
pywinauto (Round 5) and the MCP SDK (Round 4) are. Full cycle in
`docs/REPOSITORY-INTEGRATION.md` (Round 7).

## 5. Bugs the proofs caught (the honest ledger)

1. **The Verify-stage flip against ourselves**: the browser ops
   *succeeded* (DOM text, screenshots) while the router marked
   them not-ok — the §8.1 verification contracts named artifact
   keys the handler never emitted (`EXIT_ZERO` with no `exit_code`;
   `json_field` with the op's name instead of a key). The
   contracts now bind to keys the handler **always** emits —
   and every contract is exercised live.
2. `download` over `file://` — Playwright's request API is
   http(s)-only: the engine now handles `file://` as an honest
   local copy (documented), and the CI proof also runs a **real
   http download** through a local server so the network path is
   proven too.
3. A leading-`/` strip broke absolute `file://` paths (the source
   "went missing") — fixed at the root.
4. The §55 consent flag was unreachable from wiring —
   `set_engine_defaults(user_consent=…)` now carries the
   operator's explicit opt-in (still default **false**).
5. Phase-8's strict "12 records" assertion broke forward
   compatibility with the 13th record — re-expressed as
   "nine + three present, count tolerant to later additive
   records" (the Phase-7 wording's spirit).

## 6. Why the architecture is what it is

* **One gate**: the browser tool is the 13th §8.1 record; the
  engine, the façade and the DOM layer are all router clients —
  policy, scope and verification run on browser effects exactly
  as they do on file writes.
* **Isolation by construction**: profile guards + the §55 gate +
  session ids — mixing user and agent data is an *explicit,
  consented exception*, never a default or an accident.
* **Secrets as references**: §11.5 is not a redaction patch —
  it is a data-flow design: the plaintext exists only between
  the vault and the page.
* **The channel ladder**: capability without a download tax —
  the operator's Chrome becomes the engine, visibly working in
  its own NEXUS-owned window (§10 integration closes the loop).
