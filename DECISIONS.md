# Yellow Sleeper MCP MVP Decisions

## 2026-05-11 — Smoke Scenario Source

Decision: implement six smoke tests from the canonical behaviors implied by `TOOL_CONTRACTS.md` and `TECHNICAL_SPEC.md` because `PRD.md` v0.4.4 does not contain a section literally named `Success Metrics`.

Alternatives considered: pause for human clarification; create no smoke tests until the PRD is amended; use the examples embedded in `TOOL_CONTRACTS.md` plus the smoke example in `TECHNICAL_SPEC.md`.

Why this one: `goal.md` says the three source documents are frozen and to proceed with documented behavior while recording drift. The contracts/spec define enough canonical scenarios to build the required smoke suite.

## 2026-05-11 — MVP Pick Value Table

Decision: use an internal static MVP pick table by round: R1=3000, R2=1200, R3=600, R4=300, R5=100.

Alternatives considered: leave picks valueless; add YAML configuration; add an external dynasty pick-value source.

Why this one: the PRD names static table/config as the MVP pick-value source, while Stage 2 defers richer overlays. A small internal table keeps trade math complete for fixtures without adding a dependency or undocumented API.

## 2026-09-20 — Public developer-preview identity is explicit

Decision: require `sleeper_league_id` and `sleeper_username` from YAML or env before any league-scoped Sleeper request. Missing, blank, or sentinel values (`0`, `your_league_id`, `changeme`) produce an actionable error. Help (`yellow-sleeper --help`) and diagnostics (`dynasty_health_check` without `force_probe`) remain usable. Do not default to username `brad`, league id `0`, the first roster, or any silent fallback.

Alternatives considered: keep MVP built-in defaults; fail MCP process startup when identity is missing; infer the first roster when username lookup fails.

Why this one: a public preview must not query an operator’s league by accident or leak a personal default username. YAML still beats env for static keys; tool override still beats YAML for policy.

## 2026-09-20 — Cache isolation by identity and query shape

Decision: namespace cache files so league snapshots key on league id, draft state keys on draft id plus league scope, and FantasyCalc values key on a schema version plus normalized query params. Health and refresh use those same keys. Legacy unscoped files (`league_snapshot.json`, `fantasycalc_values.json`, `draft_state.json`) must never satisfy a scoped read. Atomic writes, freshness, retries, stale fallback within the same identity, and dynamic draft TTL stay as on main.

Alternatives considered: keep the four unscoped files from MVP; adopt PR #15’s broader overlay/cache stack.

Why this one: one cache directory can hold multiple leagues/drafts/valuation boards without cross-talk. Query-shape isolation reuses the reviewed idea from PR #16 (commit `3a253dd`, not merged).

## 2026-09-20 — FantasyCalc `tep=te+` for the supported 0.5 TEP profile

Decision: for the supported preview profile (14-team Superflex PPR, 0.5 TEP) send FantasyCalc `tep=te+` (URL-encoded `te%2B`). Omit `tep` when `tep_tier=off`. `te++` is allowed as an explicit discrete tier. Do not send `tep=0.5` and do not invent a local TE multiplier. Static pick values remain the MVP round table (R1=3000…R5=100) and must appear in provenance. Other league formats are unsupported approximations (same pinned SF/14/PPR query) and must be labeled as such.

Proof (no live probe in this change): public `dsheehan167/go-fantasycalc` documents TEP vocabulary `te+` / `te++`, rejects other values, and omits the param when empty because the API errors on `tep=` with no value. PR #16 recorded the same mapping; this preview re-implements that scoped idea with attribution rather than merging #16.

Alternatives considered: keep MVP non-TEP forever and mark all TEP as unsupported; apply a hard-coded 15% TE bump; land PR #15’s overlay/pick-ladder stack.

Why this one: smallest honest improvement that matches a documented API enum instead of a made-up multiplier. Historical TECHNICAL_SPEC §4 “no tep parameter” remains as MVP text and is superseded by the 2026-09-20 amendment.

## 2026-09-20 — Log redaction covers messages, args, exceptions, and URLs

Decision: redaction applies to structured extras, formatted log messages, log args, exception text, and request URLs emitted by this app’s `yellow_sleeper` logger. MCP tool JSON responses are not redacted (league data is the product). Residual limits (httpx/root loggers, process listings, Cursor MCP UI) are documented rather than claimed solved.

Alternatives considered: extra-key redaction only (MVP); redact tool payloads.

Why this one: MVP logs interpolated identity in messages; extras-only filtering was incomplete.

## 2026-09-20 — LICENSE withheld from this published branch

Decision: do not add `LICENSE` on the public developer-preview PR. A proposed MIT + copyright patch is stored only in the agent store as an owner decision.

Alternatives considered: ship MIT immediately with a guessed copyright holder.

Why this one: copyright holder and license grant are owner decisions; a silent LICENSE on a published branch would over-claim.
