# Changelog

## [Unreleased]

- Conditional, exclusive-OR, and pick-swap trade language returns `PARTIAL` + clarification with candidates or `delta_min` / `delta_max`, not one invented delta. A normal trade still returns one value. No write/submit tools.
- Mixed player-or-pick phrases still apply hard-untouchable player rules. Open-ended `delta_min` / `delta_max` uses per-asset extrema, not a Cartesian product of scenarios.

## [0.2.0] — 2026-09-21

Developer prerelease. First public tag of current `main`. Not published to PyPI.

`0.1.0` was the unpublished MVP string. This preview changed identity, cache, and valuations, so the first public tag is `0.2.0`.

### On this tag

- Explicit `sleeper_league_id` / `sleeper_username` before any league-scoped Sleeper request (no silent first-roster or username fallback)
- Cache isolation by league id, draft id+scope, and FantasyCalc query shape (legacy unscoped files are never reused)
- Settings-matched FantasyCalc `/values/current` params: `tep=te+` (default 0.5 TEP), `te++`, and `tep=none` for supported non-TEP boards
- Provider generic PICK rows (`{season} {ordinal}`); labeled `config_pick_table` static fallback when neither a generic row nor band rows exist
- Early/Mid/Late band rows as a low/high range when no generic row exists (`PARTIAL`; no invented slot)
- App-logger redaction of configured league id / username in messages, args, extras, exceptions, and `/league/<id>` URL paths
- GitHub Actions CI (ruff, pytest, dist inspect) on Python 3.11 and 3.12
- MIT license for repository code and synthetic fixtures only (not a grant over Sleeper/FantasyCalc data)

### Not in this tag

CSV overlay, conditionals, HTTP MCP, OAuth, Docker, transaction tools, and PyPI upload are out of scope.
