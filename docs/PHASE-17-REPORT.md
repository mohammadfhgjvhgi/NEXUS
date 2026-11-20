# PHASE 17 — Research Engine · Delivery Report

> **New Plan §17 · v3 plan (75 sections) · status: COMPLETE (sandbox) — device proof via the bridge**
> Identity: `nexus-core 0.17.0` · `NEXUS_PHASE = 17` · stdlib-only · zero new dependencies.

---

## What was delivered — §17 verbatim

### §17.1 Search abstraction — five surfaces, one contract

| Surface | Provider | Backend | Notes |
|---|---|---|---|
| `web` | `WebSearchProvider` | stdlib `urllib` JSON adapter (`result_key` · `field_map` · `uri_template` · `strip_html` · `query_param`) | any keyless engine fits (Wikipedia/DuckDuckGo proven live) |
| `github` | `GitHubSearchProvider` | the §16.2 `GitHubEngine.search` | public credential-free reads (§124 unchanged); repos marked `github_type=repo` |
| `docs` | `DocsSearchProvider` | real corpus walker (md/rst/txt/html) | `file://` hits, snippet = best matching line |
| `forums` | `ForumSearchProvider` | Discourse-style `/search.json` adapter | same mapping machinery, community defaults |
| `local` | `LocalSearchProvider` | any local tree | honest absence for non-matches |

The contract: `SearchProvider.name / kind / search(query, max_results)`.
Empty list = *no results*. A raise = *the surface failed* (`ProviderError`).
The workflow records failures; it never hides them, never guesses.

### §17.2 Research workflow — eight stages, verbatim, verdicts

```
Query → Search → Collect → Deduplicate → Rank → Compare → Verify → Evidence
```

* `StageTrace(name, state, detail)` per stage — `ok/failed/skipped` honestly reported (`report.reached`, `report.ok`).
* One failing surface never sinks a run; every surface failing (or none registered) fails at `search`.
* Dedup: URI-exact, then content fingerprint — best carrier wins (3→2 proven in the gate).
* Compare: term-Jaccard clustering; **contested numbers** (`4 GB` vs `64 GB` on one claim) mark the finding `contested` — contested never verifies.
* Verify: ≥ `min_corroboration` distinct sources AND mean authority ≥ `min_authority` AND not contested.
* Evidence: per-source rows (`uri · title · snippet · source_class · provider · kind · confidence`).

### §17.3 Source Classification — six classes, one ladder

`official · documentation · academic · community · personal · unknown` — a documented
deterministic ladder: explicit `metadata["nexus_class"]` → academic → documentation →
community platforms → official → personal → path-shaped forums → **unknown (honest fallback)**.
GitHub repos = their project's official home; issues/discussions = community; `file://`
under `/docs/` = documentation.

### §17.4 Source Confidence — four dimensions, published math

`authority · relevance · freshness · evidence`, weighted **0.35/0.25/0.20/0.20**:

* authority = per-class prior (official 0.95 → unknown 0.30);
* relevance = query-term overlap over title+snippet;
* freshness = linear decay to zero across 720 days from a **surface-reported** date;
  no reported date → neutral 0.5 (never optimistically fresh — `fetched_at` is
  provenance, not an age claim);
* evidence = 0.0 no snippet · 0.5 snippet · 1.0 snippet contains a query term.

### §17.5 Research Memory — sources ride every record

`ResearchMemory` over the §12 engine: one `FACT` record per finding
(`confidence` = §17.4 score; scope TASK/PROJECT/KNOWLEDGE by container), every backing
hit → `MemoryEvidence(method="research", uri, snippet)`, one `SUMMARY` record per
session; `recall` returns records **with their sources**; the §12.2 ladder keeps Task
memories task-private (proven by test).

---

## Verification chain

| Rung | Result |
|---|---|
| pytest `tests/phase17` | **73/73** (contracts 18 · classify 10 · providers 14 · workflow 18 · memory 8 · engine 7) |
| Exit gate `verify_exit_criteria.py` | **23/23** (A–F) with **zero regression** on phases 14 · 15 · 16 |
| ruff 0.16.6 + pyright 1.1.411 | **0 errors** on `nexus/research/` |
| Live proof `live_research_ci.py` (sandbox) | **6/6**: real GitHub search (api.github.com) · real web search (en.wikipedia.org) · real repo corpus (docs/ + nexus/) · 8-stage workflow · 4 dimensions · remember→recall with sources |
| Device proof (Windows, via bridge) | see `M:\NEXUS\proofs\phase17_live.json` after the tunnel run |
| CI | `python-quality` (Phases 1–17) + new `research-live` job |

## Files

```
nexus/research/__init__.py      — package surface + SCORED_SHAPE cardinalities
nexus/research/contracts.py     — §17.1 kinds · §17.3 classes · §17.4 dimensions + math
nexus/research/classify.py      — §17.3 the ladder
nexus/research/providers.py     — §17.1 the five adapters
nexus/research/workflow.py      — §17.2 the eight stages + report shapes
nexus/research/memory.py        — §17.5 the §12 bridge
nexus/research/engine.py        — the ResearchEngine facade
tests/phase17/*                 — 73 tests + fixtures + gate + live proof + device wrapper
.github/workflows/ci.yml        — Phase 17 step + research-live job
README.md / CHANGELOG.md        — §17 narrative + map rows re-aligned to plan v3
```

## Design decisions (the honest ones)

1. **Freshness never lies** — a hit with no surface-reported date is graded 0.5, not
   1.0; the fetch timestamp is provenance, not an age claim.
2. **Contested beats corroboration** — three sources agreeing on "4 GB" cannot rescue a
   claim one source pins at "64 GB": the whole cluster is contested and unverified.
3. **Provider identity is explicit** — classification prefers the provider's own
   `nexus_class`/`github_type` metadata over any URL rule, then the documented ladder,
   then honest `unknown`.
4. **Query text never rides the bus** — tool events carry term *counts* and verdict
   counts only (test-enforced).
5. **The web rung tries keyless engines in order** (Wikipedia → DuckDuckGo) and fails
   honestly when neither answers — sandbox network policy may block them; CI and the
   real machine decide.
