# Accurate Stage 2 Value Modeling for Yellow Sleeper MCP

**Date:** 2026-08-20 **Sources:** FantasyCalc live API probe (2026-08-20), go-fantasycalc, fantasydatapros, KeepTradeCut, DynastyProcess/ffscrapr, Exa web search/fetch, Tavily search, Ceramic (partial), GitHub code search, project TECHNICAL_SPEC.md; Parallel Task still running (incomplete); Perplexity research, Tavily research, EXA deep_researcher skipped (unavailable)

## Summary

Yellow Sleeper’s TECHNICAL_SPEC assumption that FantasyCalc has **no TEP parameter is outdated**. Live probes of `api.fantasycalc.com` on 2026-08-20 confirm a `tep` query param with discrete values `te+` and `te++` that raise TE values by ~15% and ~29% respectively while leaving non-TE assets unchanged. For a **14-team SF PPR 0.5 TEP** league, Stage 2 accuracy is best served by enabling FantasyCalc `tep=te+` (aligned with KTC’s TE+ guidance for +.5 PPR), then optionally layering a sleeper_id-keyed xlsx overlay and FantasyCalc’s already-included early/mid/late pick ladder—before investing in pick-swap/conditional parsing.

## Key Findings

### FantasyCalc / API reality

**Confirmed endpoint (community + official tutorial):**

```http
GET https://api.fantasycalc.com/values/current
```

**Documented / widely used query params:**

| Param | Values | Role |
| --- | --- | --- |
| `isDynasty` | `true` / `false` | Dynasty vs redraft |
| `numQbs` | `1` / `2` | 1QB vs Superflex |
| `numTeams` | commonly 8–16; Yellow uses `14` | League size |
| `ppr` | `0`, `0.5`, `1` | Reception scoring |
| `includeAdp` | bool | Optional ADP on entries |
| `includeRosterPercent` | bool | Optional roster % (go-fantasycalc) |
| `tep` | omit, `te+`, `te++` | TE premium (see below) |
| `includePicksAsPlayers` | used by some clients | Pick inclusion (see live note) |

**Join key:** each player object includes `sleeperId` (nullable for some fringe players)—the correct primary join for Sleeper, as already designed in Yellow Sleeper.

**Canonical tutorial:** Josh Cordell’s Fantasy Data Pros post (2023) documents the endpoint and sample JSON shape (`value`, `overallRank`, `positionRank`, `trend30Day`, nested `player` with platform IDs).

**Community clients (GitHub, 2024–2026):** `dsheehan167/go-fantasycalc`, `gtonic/nfl_mcp`, `HandHanley/fantasy-delta`, `320james/ready-trade`, `zachcopen/tradedesk`, and others all hit the same `/values/current` shape. Parse.bot’s Marketplace wrapper documents `ppr` / `num_qbs` / `num_teams` / `is_dynasty` / `include_adp` but **incorrectly claims TE-premium is not exposed**—contradicted by both go-fantasycalc and live probes.

**Live probe results (2026-08-20, 14-team SF PPR dynasty):**

| Request | HTTP | TE example (Brock Bowers value) | Notes |
| --- | --- | --- | --- |
| base (no `tep`) | 200 | 7929 (overall #8) | 475 assets; **76 already `position=PICK`** |
| `tep=te+` | 200 | 9110 (overall #5) | ~**+14.9%** on TEs; non-TEs unchanged |
| `tep=te++` | 200 | 10228 (overall #2) | ~**+29%** on TEs |
| `tep=0.5` | **404** | — | Numeric TEP not accepted |
| `includePicksAsPlayers=true` | 200 | same as base | No size change vs base for this format (picks already present) |

Across 66 TEs, `te+` uplift was nearly uniform (**median ≈ 1.149×**, mean ≈ 1.149×). That implies FantasyCalc’s TEP is largely a **position-wide multiplicative premium**, not a sparse “stud TE only” re-rank—useful for local approximation if the param were ever unavailable.

**Pick assets in FantasyCalc dynasty responses** (already valuable for Yellow Sleeper’s static pick table replacement):

- Slot-specific current class: e.g. `2026 Pick 1.01` with synthetic id `DP_0_0` (value 7128 in this probe)
- Generic / early-mid-late future: e.g. `2027 1st (Early)` → `FP_2027_early_0`, `2027 1st (Mid)`, `2027 1st` → `FP_2027_1`
- go-fantasycalc documents the `FP_*` / `DP_*` synthetic Sleeper ID conventions

**Implication for Yellow Sleeper TECHNICAL_SPEC §4:** update QUERY_PARAMS to include `"tep": "te+"` for 0.5 TEP, and treat FantasyCalc pick rows as a first-class pick-value source rather than only a static round table.

**Stale / conflicting secondary claims:** Parse.bot FAQ and `fantasy-delta`’s fetch script comments still say FantasyCalc “cannot represent TE-premium.” Treat those as **wrong as of Aug 2026** relative to live API + go-fantasycalc.

--- begin (reference only) ---
go-fantasycalc ValuesRequest: TEP vocabulary is `te+` / `te++`; empty means omit param entirely (API errors on `tep=` with no value).  
KTC: TE+ ≈ mild/moderate bonus such as +.5PPR/.75PPR boost.  
--- end (reference only) ---

### TEP methodologies

**KeepTradeCut (primary community standard for TEP UX):**

- Crowdsourced base values assume vanilla **12-team .5 PPR, no TEP**.
- TEP is applied **algorithmically post hoc** via four tiers: Off / TE+ / TE++ / TE+++.
- Official mapping guidance ([keeptradecut.com/about/tight-end-premium](https://keeptradecut.com/about/tight-end-premium)):
  - **TE+** → 1 starting TE + mild/moderate scoring bonus (e.g. **+.5 / +.75 PPR**, or ~1.5–2× WR PPR)
  - **TE++** → 2TE **or** large/extreme bonus (>1 PPR)
  - **TE+++** → 2TE **and** additional bonuses
- League Power Rankings auto-detect TEP from league scoring; trade calculator uses a stepper.
- Voters answering K/T/C prompts should **not** bake TEP into answers—premium is applied on top.

**For Yellow Sleeper’s 0.5 TEP (single TE starter, +0.5 PPR to TEs):** KTC’s **TE+** tier is the intended match. FantasyCalc’s `tep=te+` is the analogous discrete setting.

**FantasyCalc:** discrete `te+` / `te++` only—no continuous `0.5` / `1.0` float. Perfect 0.5 vs 1.0 interpolation is not exposed; closest market-aligned choice for 0.5 TEP is `te+`. Optional local hybrid if the league “feels” between Off and TE+:  
`value_adj = value_base + α * (value_te+ − value_base)` with α≈0.5–1.0, TE-only—but prefer API `te+` first for market consistency.

**Dynasty Process:** values from FantasyPros ECR via exponential decay (`Value ≈ 10500 * e^(ECR * -0.0235)`), with 1QB/2QB columns and valuation-factor knobs in the web calculator. **No first-class TEP toggle** in the public CSV; TEP would be a custom ECR transform or separate sheet. CSV columns include `fp_id`, `value_1qb`, `value_2qb`—join to Sleeper via `dp_playerids()` (`sleeper_id` ↔ `fantasypros_id`).

**Draft Sharks / FantasyPros:** publish separate TE-premium rankings/charts (productized TEP boards), useful as calibration targets, not as free APIs.

**“Accurate enough” for trade analysis (not perfect market pricing):**

1. Same format lens for both sides (SF + TEP tier).
2. Absolute TE levels within ~10–15% of peer calculators on elite TEs.
3. Relative TE-vs-WR/RB ordering that matches league intuition (Bowers/McBride clearly above mid WR2s in 0.5 TEP).
4. Explicit `source_notes` / `source_disagreement` when a second source exists—LLM advisory, not false precision.

A uniform ~15% TE bump (`te+`) is “accurate enough” for fairness checks; obsessing over mid-TE decimal precision is lower ROI than fixing pick slot granularity and human overrides.

### Spreadsheet overlay practices

**Common schemas in the wild:**

| Pattern | Keys | Pros | Cons |
| --- | --- | --- | --- |
| DynastyProcess CSV | `fp_id` → map to `sleeper_id` | Public, MIT-ish community data, weekly-ish updates | Extra ID map; no TEP |
| FantasyCalc JSON | `sleeperId` native | Best for Sleeper MCP | Discrete TEP only |
| Human xlsx | Prefer `sleeper_id` column; name+pos fallback | League-specific overrides | Drift, typos, maintenance |
| Stats Guy Fantasy API | Sleeper `id` native; pick IDs `pick:YYYY:R` / early-mid-late | Real Sleeper-trade derived; slot-aware picks | Separate SF/non-SF formats; **no TEP format** documented |

**Recommended Yellow Sleeper xlsx schema (minimal):**

- Required: `sleeper_id`, `value`
- Optional: `name`, `position`, `notes`, `as_of`, `priority` (override strength)
- Forbidden as sole key: bare display name (collisions: Jr/III, rookies)

**Merge / precedence (activates existing `source: xlsx` + `source_disagreement` contracts):**

1. Load FantasyCalc (with `tep=te+`) as base `source=fantasycalc`.
2. For each xlsx row with valid `sleeper_id`: if `|xlsx − fc| / max(fc, ε) > threshold` (e.g. 8–12%), set `source_disagreement` and choose policy:
   - **overlay_wins** (default for Stage 2 human goal): use xlsx value, keep both in notes
   - **blend**: weighted average
   - **fc_wins**: xlsx advisory only
3. Missing FantasyCalc `sleeperId`: try name fallback; else `missing_value`.
4. Never silently drop disagreement—surface to the LLM in trade analysis.

**Open-source / MCP precedents:**

- `gtonic/nfl_mcp`: FantasyCalc → Sleeper-id index with TTL cache (closest MCP analogue; **no TEP param yet**).
- DynastyProcess + ffscrapr: CSV overlay onto Sleeper rosters via id maps.
- `zachcopen/tradedesk`: merges FantasyCalc (1QB+SF) with DynastyProcess player/pick CSVs.
- Community issue templates (e.g. dynastiest-league #59): FantasyCalc first, DynastyProcess second, KTC last (no official API / name match pain).

**Xlsx remains valuable even with FantasyCalc TEP** for: leaguehouse “house values,” protected pets, and players FantasyCalc underweights relative to this specific 14-team market.

### Pick & conditional trade accuracy

**Static round tables are weak for 14-team SF.** Hit-rate and value falloff differ sharply early vs late firsts; SF classes with QB depth keep late 1sts richer than 1QB (Footballguys Aug 2026 SF pick charts; FantasyPros early/mid/late buckets; Dynasty Nerds hit-rate tiers).

**Better than static rounds (ordered):**

1. **FantasyCalc pick ladder already in `/values/current`** — early/mid/late + slot-specific current year. Map Yellow `pick_token` / season_round to FC names or `FP_*`/`DP_*` ids.
2. **Stats Guy Fantasy `/picks`** — explicit `pick:2027:1:early` style IDs from real Sleeper trades; good secondary for SF dynasty (no TEP).
3. **Analyst charts** (FantasyPros / Footballguys) as sanity checks, not primary machine sources.

**14-team nuance:** a “mid 1st” in 14-team is later in absolute draft capital than in 12-team; prefer **slot-aware or early/mid/late** over “any 1st = same value.” FantasyCalc’s 14-team format param helps the **player** board; pick naming still needs careful mapping (1.01–1.14 slots when known).

**Conditional / pick-swap representation (read-only, no write-actions):**

- Model as **scenario bundles**, not a single net value:
  - Base assets (unconditional players/picks)
  - Conditional clauses: `{trigger, if_true_assets, if_false_assets}`
  - Pick swaps: `{give: pick_A, receive: pick_B}` as two-sided inventory deltas
- Analyzer outputs: value range (min/expected/max), probability notes if known, and `UNRESOLVED` / `CONDITIONAL` flags when trigger cannot be evaluated.
- Do **not** auto-propose Sleeper trade writes; stay advisory (fits Stage 2 deferred “beyond UNRESOLVED” scope without shipping packaging/auth).

### Recommended Stage 2 build order for Yellow Sleeper

Ranked by **accuracy impact for this exact league** (14-team SF PPR 0.5 TEP), highest first:

| Priority | Work item | Why | Risk |
| --- | --- | --- | --- |
| **1** | **FantasyCalc `tep=te+` (+ document 0.5 TEP mapping)** | One-line param; TE market moves ~15%; matches KTC TE+ guidance; non-TEs unchanged | Discrete tiers ≠ continuous 0.5; if league “feels” lighter, allow α-blend config |
| **2** | **Richer pick values from FantasyCalc pick rows** | Already in API response; kills largest blind spot vs static round table; SF early/mid/late matters | Synthetic pick IDs need robust mapper; 14-team slot edges |
| **3** | **xlsx overlay (sleeper_id, overlay_wins + source_disagreement)** | Human league accuracy / house rules; contracts already reserved | Maintenance burden; name-key footguns |
| **4** | **Pick-swap / conditional parsing (scenario ranges)** | Improves edge cases; lower frequency than TE/pick mispricing | Complexity; ambiguity; keep UNRESOLVED-first |

**Implementation options:**

1. **API-only (recommended first slice):**  
   `isDynasty=true&numQbs=2&numTeams=14&ppr=1&tep=te+`  
   Use FC players + FC picks. Fastest path to “accurate enough.” Update TECHNICAL_SPEC §4.

2. **Sheet overlay:**  
   Human xlsx as override layer; FantasyCalc remains freshness backbone. Best when Brad maintains league-specific values.

3. **Hybrid (target end-state):**  
   FC(+TEP) → pick ladder → xlsx overrides → optional Stats Guy / DynastyProcess as disagreement peers → scenario engine for conditionals.  
   Precedence: `xlsx > fantasycalc_tep > fantasycalc_base`; always emit `source_disagreement` when peers diverge past threshold.

**Explicitly deprioritize for Stage 2 accuracy goal:** multi-user, HTTP, Docker, OAuth, live notifications (already deferred in TECHNICAL_SPEC §13)—they do not improve trade math.

### Open risks / unknowns

- Exact FantasyCalc algorithm behind `te+` vs `te++` (uniform ~15% TE multiplier observed; may change without notice).
- Whether FantasyCalc UI and API TEP tiers stay in sync long-term; schema drift remains a real ops concern (Yellow’s fail-open cache + probe is correct).
- Continuous 0.5 vs 1.0 TEP: no official float; α-blend is heuristic.
- `includePicksAsPlayers` behavior across formats is under-documented; dynasty SF 14 already returned picks without it.
- Parse.bot and some OSS comments still deny TEP—do not trust secondary wrappers over live probes.
- Stats Guy and DynastyProcess lack TEP formats—good peers for SF/picks, weak for TE premium alone.
- Parallel deep-research task (`trun_6ae53d1e637f41f88330fadca5af3776`) was still active at write time (423 sources considered / 36 read); its final markdown was not available for this synthesis.
- Ceramic lexical search returned little on-topic FantasyCalc/TEP content for the keyword rewrites (mostly noise / off-topic).
- Perplexity research, Tavily research (plugin-yellow-research-tavily), and EXA `deep_researcher_*` were unavailable (auth 401 / 410); substituted Exa search/fetch, Tavily search (plugin-tavily-tavily), GitHub, and live API.

## Sources

- [FantasyCalc live API](https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=2&numTeams=14&ppr=1) — live 2026-08-20 probe; confirmed `tep=te+` / `te++`, 404 on `tep=0.5`, pick ladder present
- [go-fantasycalc values.go / README](https://github.com/dsheehan167/go-fantasycalc) — documents `tep` vocabulary, pick ID conventions, ValuesRequest fields
- [FantasyCalc API Intro (fantasydatapros)](https://www.fantasydatapros.com/fantasyfootball/blog/fantasycalc/1) — official-adjacent tutorial for `/values/current` and response shape
- [KeepTradeCut Tight End Premium](https://keeptradecut.com/about/tight-end-premium) — TE+/TE++/TE+++ mapping; +.5 PPR → TE+
- [KeepTradeCut FAQ](https://keeptradecut.com/frequently-asked-questions) — TEP algorithmic overlay on base .5PPR values
- [DynastyProcess values methodology](https://dynastyprocess.com/values/) — ECR exponential decay; valuation factor
- [DynastyProcess values-players.csv](https://github.com/dynastyprocess/data/blob/master/files/values-players.csv) — public value sheet schema
- [ffscrapr sleeper + dp_values](https://ffscrapr.ffverse.com/articles/sleeper_basics.html) — sleeper_id join overlay pattern
- [Parse.bot FantasyCalc API page](https://parse.bot/marketplace/fc0e447d-6f7d-4c87-aaa1-0f7b86797302/fantasycalc-com-api) — param list (TEP claim outdated vs live API)
- [Stats Guy Fantasy API docs](https://statsguyfantasy.com/developers/docs) — Sleeper-id values + structured pick IDs; no TEP format
- [FantasyPros dynasty trade value chart](https://www.fantasypros.com/2026/05/fantasy-football-rankings-dynasty-trade-value-chart-may-2026-update) — early/mid/late pick buckets; TE premium charts referenced
- [Footballguys Aug 2026 dynasty pick chart](https://www.footballguys.com/article/2026-dynasty-trade-value-chart-august) — SF vs 1QB pick falloff
- [Dynasty Nerds pick values](https://www.dynastynerds.com/trades/dynasty-trade-secrets-understanding-draft-pick-values) — hit rates by pick tier
- [nfl_mcp player_values.py](https://github.com/gtonic/nfl_mcp) — MCP FantasyCalc→Sleeper pattern (no TEP yet)
- [fantasy-delta fetch-market-values.js](https://github.com/HandHanley/fantasy-delta) — format grid + includePicksAsPlayers (stale “no TEP” comment)
- [dynastiest-league #59](https://github.com/jason-shprintz/dynastiest-league/issues/59) — FantasyCalc-first integration design notes
- [Draft Sharks TE Premium chart](https://www.draftsharks.com/trade-value-chart/te-premium) — commercial TEP board reference
- Yellow Sleeper `TECHNICAL_SPEC.md` §4 / §13 — current MVP FantasyCalc params; Stage 2 deferrals (TEP claim superseded by live probe)

### Research conductor source annotations

- Ceramic — used (weak/on-topic sparse; 1–5 results depending on query)
- Exa web_search / web_fetch — used
- Tavily search — used
- GitHub search_code — used
- FantasyCalc live curl probe — used
- Parallel createDeepResearch — started (`trun_6ae53d1e637f41f88330fadca5af3776`), **incomplete at synthesis time** (still running)
- [research-conductor] Source skipped: Perplexity research — unavailable (401 invalid API key)
- [research-conductor] Source skipped: Tavily research (plugin-yellow-research-tavily) — unavailable (invalid API key)
- [research-conductor] Source skipped: EXA deep_researcher_start — unavailable (HTTP 410)
