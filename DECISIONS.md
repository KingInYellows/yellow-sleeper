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

## 2026-09-20 — LICENSE granted as MIT; data-rights limitation recorded

Decision: add MIT License, with the owner's named 2026 copyright as recorded in `LICENSE`, and matching `pyproject.toml` `license` / `license-files` metadata. MIT covers this repository's **code and synthetic fixtures only**. It does not relicense Sleeper or FantasyCalc APIs, datasets, or caches. This preview ships code plus synthetic examples, not live provider dumps or personal workbooks. Unresolved commercial and redistribution rights for provider payloads remain an explicit limitation (`NOTICE`), not a grant.

Sleeper's public API is documented as free for non-commercial use; commercial use requires contacting Sleeper ([docs.sleeper.com](https://docs.sleeper.com/)). Sleeper Terms of Use prohibit third-party commercial access to league/roster data without written consent ([sleeper.com/terms](https://sleeper.com/terms)). FantasyCalc data is copyrighted; documented API use is non-commercial with attribution; commercial use needs written permission ([terms-of-usage](https://fantasycalc.com/terms-of-usage), [api-docs](https://fantasycalc.com/api-docs)). Keep existing authorship notices.

Also: `format_looks_supported` requires an explicit `0.5` TEP token (so `14-team SF PPR` is unsupported), bounds team-count `14` so `214-team` does not match, and rejects `1QB` while the pinned query is `numQbs=2`. Default `14-team SF PPR 0.5 TEP` remains supported.

This supersedes the same-day "LICENSE withheld from this published branch" entry for this candidate.

Alternatives considered: keep the withheld LICENSE; treat MIT as a grant over live API payloads.

Why this one: the copyright holder named the grant; data-rights research showed provider terms still restrict commercial/redistribution use of their datasets.

Sources consulted 2026-09-20 (public pages only; no live league data): [Sleeper API](https://docs.sleeper.com/), [Sleeper Terms of Use](https://sleeper.com/terms), [legacy support ToS URL](https://support.sleeper.com/en/articles/5432002-general-terms-of-service) (404), [FantasyCalc Terms of Usage](https://fantasycalc.com/terms-of-usage), [FantasyCalc API Docs](https://fantasycalc.com/api-docs), [FantasyCalc /terms SPA](https://fantasycalc.com/terms).

## 2026-09-21 — League-true FantasyCalc query and provider-backed picks

Decision: derive FantasyCalc `/values/current` params from configured `league_format` when every field maps to a value documented on the public [FantasyCalc API Docs](https://fantasycalc.com/api-docs) (consulted 2026-09-21): `isDynasty=true`, `numQbs` `"1"` or `"2"`, `numTeams` `8|10|12|14`, `ppr` `0|0.5|1`, `tep` omitted / `te+` / `te++`. Do not send `tep=none` (docs default is none; empty `tep=` has historically errored; this repo omits the key). Do not invent multipliers, extra TEP tiers, or undocumented team/PPR values. The default `14-team SF PPR 0.5 TEP` path still sends `tep=te+`.

Unsupported combinations (unparseable format, `16`-team, `1.5 TEP`, SF+1QB conflict, missing PPR, and similar) do **not** reuse another board. They stay explicit missing/partial with reasons. Cache files stay isolated by schema version `v1` plus the normalized query that was actually sent.

When the active values payload includes FantasyCalc `position=PICK` rows, pick assets use the generic `{season} {ordinal}` row (e.g. `2027 1st`) and provenance says so. Early/mid/late banded rows and Sleeper `roster_id`-as-slot are out of scope. The static round table (R1=3000…R5=100) remains fallback only, labeled `config_pick_table`, never presented as freshly fetched provider data.

This re-implements the reviewed generic-row pick match from PR #15 (`cursor/stage2-value-accuracy-be01`, head `5139502`) with attribution. It does not merge #15 (no CSV overlay, no conditionals, no banded ladder).

Alternatives considered: keep the pinned 14-team SF PPR `te+` query for every format and label approximations; merge #15’s overlay/banded/conditional stack; send `tep=none` instead of omitting.

Why this one: smallest honest step that makes the query follow settings the public API actually documents, and that uses provider pick rows when they are in the payload.

## 2026-09-21 — `tep=none` and Early/Mid/Late pick ranges

Decision: for a resolved **supported** non-TEP FantasyCalc query, send the documented literal `tep=none`. Keep `tep=te+` on the default 14-team Superflex full-PPR 0.5 TEP path and `tep=te++` where that discrete tier is already supported. Do not invent multipliers. Official FantasyCalc API docs list `tep` as `none` / `te+` / `te++`. A bare `tep=` has historically errored; omitting the key matched the documented default until now, but `none` is the valid explicit value, so send `none`. Internal config still uses `tep_tier=off`; only the HTTP param is `none`. Cache variants follow the params actually sent (`tep-none`).

When a generic `{season} {ordinal}` PICK row exists (e.g. `2027 1st`), keep using that single value. When it does not, and FantasyCalc Early/Mid/Late band rows exist for that pick, do **not** pick a band or a slot. Leave the single-number field empty, set `data_status=PARTIAL`, and put the low/high range plus band labels in provenance (`source_notes` / `missing_value` reason). The static round table (R1=3000…R5=100) remains labeled `config_pick_table` fallback only when **neither** a generic row nor band rows exist. No `projected_slot`, no CSV/xlsx overlay, no conditional-trade engine. Tests stay respx/fixture-only.

This supersedes the same-day “omit `tep=none` / ignore banded rows” sentences for these two residuals. Generic-row matching from PR #15 stays; #15 is still not merged.

Alternatives considered: keep omitting `tep` as equivalent to none; pick Mid (or Early) as a single number; average the bands; keep using the static table whenever the generic row is missing.

Why this one: the public enum includes `none`, so supported non-TEP queries should send it. Band rows are real provider data but not a known slot; a range plus PARTIAL is honest, a fabricated single slot is not.

## 2026-09-21 — First public tag is v0.2.0

The first public tag is `v0.2.0` (developer prerelease of current `main`), not a silent tag of unpublished `0.1.0`.

## 2026-09-21 — Local CSV value overlay (contract source name `xlsx`)

Decision: optional local CSV keyed by Sleeper player id overrides FantasyCalc when configured (`overlay_wins`). The tool-contract source name stays `xlsx`; the on-disk format is CSV (no openpyxl). A configured path whose file is missing is an explicit status (flag + provenance), not a crash and not a silent FantasyCalc fallback labeled as overlay. Default (no `values_overlay_path`) stays FantasyCalc-only. Disagreement above the existing 25% threshold remains a `source_disagreement` flag. Provenance names which source supplied the chosen number. FantasyCalc cache identity includes whether the overlay is active (`overlay-on`), so a no-overlay board cannot satisfy an overlay query. Tests and the tracked example file are synthetic only.

This re-implements the reviewed CSV overlay idea from closed PR #15 (`cursor/stage2-value-accuracy-be01`, head `5139502`) with attribution. It does not reopen, cherry-pick, or merge that branch (no conditionals, no pick-swap ranges, no personal workbook, no live league export).

Alternatives considered: merge #15; ship real `.xlsx` via openpyxl; treat a missing file as an empty map and keep using FantasyCalc under an overlay label (as in #15); rename the contract literal from `xlsx` to `csv`; put `overlay-off` on the default cache token.

Why this one: smallest honest overlay that keeps the existing contract name, keeps the default cache path unchanged, and refuses to mislabel FantasyCalc as a local sheet.
