# Yellow Sleeper MCP MVP Decisions

## 2026-05-11 — Smoke Scenario Source

Decision: implement six smoke tests from the canonical behaviors implied by `TOOL_CONTRACTS.md` and `TECHNICAL_SPEC.md` because `PRD.md` v0.4.4 does not contain a section literally named `Success Metrics`.

Alternatives considered: pause for human clarification; create no smoke tests until the PRD is amended; use the examples embedded in `TOOL_CONTRACTS.md` plus the smoke example in `TECHNICAL_SPEC.md`.

Why this one: `goal.md` says the three source documents are frozen and to proceed with documented behavior while recording drift. The contracts/spec define enough canonical scenarios to build the required smoke suite.

## 2026-05-11 — MVP Pick Value Table

Decision: use an internal static MVP pick table by round: R1=3000, R2=1200, R3=600, R4=300, R5=100.

Alternatives considered: leave picks valueless; add YAML configuration; add an external dynasty pick-value source.

Why this one: the PRD names static table/config as the MVP pick-value source, while Stage 2 defers richer overlays. A small internal table keeps trade math complete for fixtures without adding a dependency or undocumented API.

## 2026-08-19 — Stage 2 TEP is computed locally

Decision: apply TE premium as `value * (1 + tep * 0.35)` after fetching raw FantasyCalc. Mifflin Doty uses `tep=0.5` (1.175x TEs). Surface the TEP-adjusted book as the `xlsx` source; keep raw FantasyCalc as a second source. User xlsx/csv rows replace the book for that sleeper_id. Flag `source_disagreement` only when enabled sources differ by more than 25%.

Alternatives considered: pass `tep` to FantasyCalc (404s); leave TEs unadjusted; invent a new source literal (frozen contract only allows fantasycalc/xlsx/config_pick_table).

Why this one: FantasyCalc's public `/values/current` endpoint rejects TEP query params. The frozen `ValueSourceBreakdown.source` literal cannot grow a `tep_book` name.

## 2026-08-19 — Live Mifflin Doty league

Decision: default live config is league `1312121399602581504`, username `BradSchwarzkopf`. Roster match is case-insensitive across username, display_name, team_name, and user_id because this league's `/users` payload has `username: null`.

Alternatives considered: keep default `brad`; require Sleeper username only.

Why this one: a default of `brad` misses the live roster.

## 2026-08-19 — HTTP desk + streamable MCP

Decision: `yellow-sleeper` with no args stays stdio MCP. `serve-http` is a Starlette JSON dispatcher on 8091 for the desk. `serve-mcp-http` is FastMCP streamable-http on 8092. Docker, OAuth, and live Sleeper notifications stay deferred.

Why this one: the desk and Claude/Cursor clients need a live process; public OAuth/Docker is Stage 2 remainder, not required for a working local MCP.
