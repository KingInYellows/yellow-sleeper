# Yellow Sleeper MCP MVP Status

## 2026-05-11 01:30 CDT — Milestone 0: Project Memory And Spec Map

Current milestone: Milestone 0.

What was just completed:
- Read `goal.md`, `PRD.md`, `TOOL_CONTRACTS.md`, and `TECHNICAL_SPEC.md`.
- Created the durable project-memory files required before code work.
- Mapped the MVP into independently testable milestones.

Files touched:
- `PLAN.md`
- `STATUS.md`
- `DECISIONS.md`

Validation commands run:
- `test -f PLAN.md && test -f STATUS.md && test -f DECISIONS.md` — passed.

What's next:
- Milestone 1: packaging, Pydantic models, config, logging, and cache.

Blockers:
- None. The missing PRD `Success Metrics` heading is recorded in `DECISIONS.md` and will be handled by implementing six smoke scenarios implied by the frozen contracts/spec.

## 2026-05-11 01:45 CDT — Milestone 1: Packaging, Models, Config, Logging, Cache

Current milestone: Milestone 1.

What was just completed:
- Added Python package metadata, command entry point, package skeleton, README, gitignore, and example YAML config.
- Implemented all shared and tool-specific Pydantic contract models under `src/yellow_sleeper/models/`.
- Implemented cross-cutting response validators, blocked-trade validation, and find-roster narrow-margin validation.
- Implemented config loading/merging/hot-reload behavior for env, `.yellow-sleeper.yaml`, defaults, and tool override.
- Implemented file cache with atomic writes, gzip support, per-key asyncio locks, TTL status helpers, and stale fallback.
- Implemented JSON file logging with recursive redaction for `league_id`, `username`, and `user_id`.

Files touched:
- `.gitignore`
- `.yellow-sleeper.yaml.example`
- `README.md`
- `pyproject.toml`
- `uv.lock`
- `src/yellow_sleeper/__init__.py`
- `src/yellow_sleeper/__main__.py`
- `src/yellow_sleeper/server.py`
- `src/yellow_sleeper/config.py`
- `src/yellow_sleeper/models/*`
- `src/yellow_sleeper/store/*`
- `src/yellow_sleeper/obs/*`
- `tests/unit/*`

Validation commands run:
- `uv run --extra dev ruff check src/ tests/` — passed.
- `uv run --extra dev python -m pytest tests/unit/ -x -q` — passed, 15 tests.

What's next:
- Milestone 2: clients, pinned fixtures, fuzzy resolution, pick parser, and pick inventory.

Blockers:
- None. The host shell does not expose a bare `python` command, so validation is being run through `uv run python` until final install verification.

## 2026-05-11 02:05 CDT — Milestone 2: Clients, Fixtures, Resolution, Pick Inventory

Current milestone: Milestone 2.

What was just completed:
- Added shared HTTP client factory plus Sleeper and FantasyCalc clients with explicit timeouts, retry behavior, probes, and cache-ready fetch methods.
- Added hand-crafted Sleeper and FantasyCalc fixture files covering a 14-team league, Brad's roster, users, traded picks, draft state, players, and values.
- Implemented RapidFuzz player and roster resolution, including the find-roster narrow-margin behavior.
- Implemented regex/lexicon pick parsing and pick resolution using 100/50/0 scoring.
- Implemented native-grid plus traded-overlay pick inventory with enriched traded-pick attribution.

Files touched:
- `src/yellow_sleeper/clients/*`
- `src/yellow_sleeper/resolve/*`
- `src/yellow_sleeper/analyze/*`
- `tests/conftest.py`
- `tests/fixtures/sleeper/*`
- `tests/fixtures/fantasycalc/*`
- `tests/unit/test_pick_parser.py`
- `tests/unit/test_player_resolver.py`
- `tests/unit/test_roster_resolver.py`
- `tests/unit/test_pick_inventory.py`
- `tests/integration/test_sleeper_client.py`
- `tests/integration/test_fantasycalc_client.py`

Validation commands run:
- `uv run --extra dev ruff check src/ tests/` — passed.
- `uv run --extra dev python -m pytest tests/unit/ -x -q` — passed, 35 tests.
- `uv run --extra dev python -m pytest tests/integration/ -x -q` — passed, 4 tests.

What's next:
- Milestone 3: implement all eleven tool pipelines and register FastMCP tools.

Blockers:
- None.

## 2026-05-11 02:30 CDT — Milestone 3: Tool Pipelines And MCP Registration

Current milestone: Milestone 3.

What was just completed:
- Implemented typed pipeline builders for all eleven `dynasty_*` tool outputs.
- Added runtime wiring for config, cache, Sleeper client, FantasyCalc client, and shared HTTP client.
- Registered all eleven FastMCP tools under `src/yellow_sleeper/tools/`.
- Added six fixture-backed smoke scenarios in `tests/smoke/test_smoke_questions.py`.
- Recorded the static MVP pick-value table in `DECISIONS.md`.

Files touched:
- `DECISIONS.md`
- `src/yellow_sleeper/analyze/pipelines.py`
- `src/yellow_sleeper/analyze/value.py`
- `src/yellow_sleeper/runtime.py`
- `src/yellow_sleeper/server.py`
- `src/yellow_sleeper/tools/*`
- `tests/smoke/test_smoke_questions.py`

Validation commands run:
- `uv run --extra dev ruff check src/ tests/` — passed.
- `uv run --extra dev python -m pytest tests/unit/ -x -q` — passed, 35 tests.
- `uv run --extra dev python -m pytest tests/integration/ -x -q` — passed, 4 tests.
- `uv run --extra dev python -m pytest tests/smoke/ -x -q` — passed, 6 tests.

What's next:
- Milestone 4: full verification, local tool install, final audit, and `HANDOFF.md`.

Blockers:
- None.

## MVP complete — all smoke tests passing, ready for human review

Current milestone: Milestone 4.

What was just completed:
- Installed the package as a uv tool and verified the `yellow-sleeper` command.
- Re-ran the full unit, integration, and smoke suite.
- Re-ran ruff on all source and test files.
- Wrote `HANDOFF.md`.
- Audited tool count, smoke count, frozen source-doc integrity, and forbidden judgment/write terms.

Files touched:
- `HANDOFF.md`
- `STATUS.md`
- `src/yellow_sleeper/tools/league_power_map.py`

Validation commands run:
- `uv tool install .` — passed.
- `uv tool install --force .` — passed after final source touch.
- `yellow-sleeper --help` — passed.
- `PATH="$PWD/.venv/bin:$PATH" ruff check src/ tests/` — passed.
- `PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/ -v` — passed, 45 tests.
- `rg -n "^async def dynasty_" src/yellow_sleeper/tools` — found all 11 tools.
- `rg -n "^def test_smoke_" tests/smoke/test_smoke_questions.py` — found all 6 smoke scenarios.
- `git diff --name-only -- PRD.md TOOL_CONTRACTS.md TECHNICAL_SPEC.md` — no output; frozen docs unchanged.
- `rg -n "verdict|recommendations?|context_scores|roster_mode|tokenbowl|write_action|write-action" src tests` — no matches.

What's next:
- Human review.

Blockers:
- None.

## 2026-09-20 — Public developer-preview candidate (contract recorded)

Current milestone: public developer-preview candidate on `agent/public-developer-preview`.

What was just completed:
- Recorded preview contract amendments in `DECISIONS.md`, `TOOL_CONTRACTS.md` §9, `TECHNICAL_SPEC.md` §15, and `PRD.md` (append-only). Historical MVP decisions were not rewritten.

What's next:
- Implement identity, cache isolation, FantasyCalc `tep=te+` (re-implementing PR #16 ideas with attribution), log redaction, traded-picks roster helper, CI, and public README.

Blockers:
- LICENSE grant is an owner decision (not included on this branch).
- Sleeper/FantasyCalc data-rights remain an explicit README blocker pending owner review of current public terms.

## 2026-09-20 — Public developer-preview candidate implemented

Current milestone: public developer-preview candidate on `agent/public-developer-preview` (draft PR).

What was just completed:
- Explicit identity; scoped cache isolation; FantasyCalc `tep=te+`; log redaction; traded-picks username helper; CI; public README/CONTRIBUTING/SECURITY.
- Synthetic examples (`casey` / `1234567890`); `.yellow-sleeper.yaml.example` fictional policy; no LICENSE file.

Validation commands run:
- `uv lock --check` — passed (exit 0). Lock was not stale; not upgraded.
- `uv sync --frozen --extra dev` — passed (exit 0).
- `uv run ruff check src tests scripts` — passed (exit 0).
- `uv run python -m pytest tests/ -q` — passed, **88 tests** at that run (later **101** at `6e344a5`; current recount **108** after owner-decision tests). No live Sleeper/FantasyCalc HTTP.
- `uv build && uv run python scripts/inspect_dist.py` — passed (exit 0).
- `uv run pip-audit` — passed, no known vulnerabilities (pip-audit installed in the disposable venv only; not added to `uv.lock`).
- `uv run yellow-sleeper --help` — passed without identity.

What's next:
- Owner review of draft PR, LICENSE grant, and Sleeper/FantasyCalc data-rights.

Blockers:
- LICENSE grant is an owner decision (not included on this branch).
- Sleeper/FantasyCalc data-rights remain an explicit README blocker.

## 2026-09-20 — Owner decisions: MIT, data-rights, format heuristic

Current milestone: owner decisions landed on `agent/public-developer-preview` (draft PR #19).

What was just completed:
- MIT License (`LICENSE`) with the owner's named 2026 copyright and `pyproject.toml` `license = "MIT"` / `license-files = ["LICENSE", "NOTICE"]`.
- `NOTICE` + README data-rights: MIT covers code and synthetic fixtures only; Sleeper/FantasyCalc terms govern their APIs/datasets; we ship code + synthetic examples, not live dumps or workbooks; commercial/redistribution rights stay a limitation, not a grant.
- `format_looks_supported` requires an explicit `0.5` TEP token, bounds team-count 14 (`214-team` does not match), and rejects `1QB` while the query is `numQbs=2`. Default `14-team SF PPR 0.5 TEP` stays supported.

Validation commands run:
- `uv lock --check` — passed (exit 0).
- `uv sync --frozen --extra dev` — passed (exit 0).
- `uv run ruff check src tests scripts` — passed (exit 0).
- `uv run python -m pytest tests/ -q` — passed, **108 tests** collected and passed (exit 0). No live Sleeper/FantasyCalc HTTP.
- `uv build && uv run python scripts/inspect_dist.py` — passed (exit 0). Wheel METADATA `License-Expression: MIT`; LICENSE and NOTICE packed.
- `uv run yellow-sleeper --help` — passed without identity.

What's next:
- Coordinator/owner review of draft PR #19. Stay draft.

Blockers:
- Commercial/redistribution rights for Sleeper and FantasyCalc payloads remain an explicit limitation (`NOTICE`), not a grant.

## 2026-09-21 — League-true valuations (provider picks + settings-matched query)

Current milestone: league-true valuations on `agent/league-true-valuations` (draft PR).

What was just completed:
- FantasyCalc `/values/current` params derived from `league_format` when they map to documented `numTeams` / `numQbs` / `ppr` / `tep`. Default `14-team SF PPR 0.5 TEP` still sends `tep=te+`. Unsupported combinations skip the fetch.
- Provider-backed generic PICK rows when present; static R1=3000 table labeled as fallback only (PR #15 generic-row idea re-implemented with attribution; overlay/conditionals/bands not merged).
- README supported set and limitations updated.

Validation commands run:
- `uv lock --check` — passed (exit 0).
- `uv sync --frozen --extra dev` — passed (exit 0).
- `uv run ruff check src tests scripts` — passed (exit 0).
- `uv run python -m pytest tests/ -q` — passed, **120 tests** collected and passed (exit 0). No live Sleeper/FantasyCalc HTTP.
- `uv build && uv run python scripts/inspect_dist.py` — passed (exit 0).
- `uv run yellow-sleeper --help` — passed without identity (exit 0).
- `uv tool install --force .` into a disposable `UV_TOOL_DIR` / `UV_TOOL_BIN_DIR`; `yellow-sleeper --help` from a non-repo cwd — passed (exit 0).

What's next:
- Coordinator/owner review of draft PR. Stay draft.

Blockers:
- Commercial/redistribution rights for Sleeper and FantasyCalc payloads remain an explicit limitation (`NOTICE`), not a grant.
- Banded FantasyCalc pick rows and projected slots remain unused.

## 2026-09-21 — Valuation residuals (`tep=none` + pick-band range)

Current milestone: valuation residuals on `agent/valuation-residuals` (draft PR).

What was just completed:
- Supported non-TEP FantasyCalc queries send documented `tep=none` instead of omitting the key. Default 14-team SF full-PPR 0.5 TEP still sends `tep=te+`; `te++` unchanged.
- When a generic `{season} {ordinal}` PICK row is missing but Early/Mid/Late band rows exist, provenance reports low/high plus band labels and `data_status=PARTIAL`; the single-number field is not a fabricated slot. Static R1=3000 remains labeled fallback only when neither generic nor band rows exist.

Validation commands run:
- `uv lock --check` — passed (exit 0).
- `uv sync --frozen --extra dev` — passed (exit 0).
- `uv run ruff check src tests scripts` — passed (exit 0).
- `uv run python -m pytest tests/ -q` — passed, **124 tests** collected and passed (exit 0). No live Sleeper/FantasyCalc HTTP (also 124 passed with HTTP(S)_PROXY blackhole).
- `uv build && uv run python scripts/inspect_dist.py` — passed (exit 0).
- `uv run yellow-sleeper --help` — passed without identity (exit 0).

What's next:
- Coordinator/owner review of draft PR. Stay draft.

Blockers:
- Commercial/redistribution rights for Sleeper and FantasyCalc payloads remain an explicit limitation (`NOTICE`), not a grant.

## 2026-09-21 — Local CSV value overlay

Current milestone: CSV overlay on `cursor/csv-value-overlay-90b8` (draft PR).

What was just completed:
- Optional `values_overlay_path` CSV keyed by Sleeper player id. Contract source name stays `xlsx`. Overlay wins over FantasyCalc when the file loads.
- Missing configured file is an explicit status, not a crash and not a silent FantasyCalc fallback labeled as overlay.
- Cache identity includes `overlay-on` only when the overlay is active. Default unset path is unchanged.
- Re-implements the reviewed overlay idea from closed PR #15 with attribution; does not merge that branch.

Validation commands run:
- `uv lock --check` — passed (exit 0).
- `uv run ruff check src tests scripts` — passed (exit 0).
- `uv run python -m pytest tests/ -q` — passed, **139 tests** collected and passed (exit 0). No live Sleeper/FantasyCalc HTTP.
- `HTTP(S)_PROXY=http://127.0.0.1:1 uv run python -m pytest tests/ -q` — passed, **139 tests** (exit 0).
- `uv build && uv run python scripts/inspect_dist.py` — passed (exit 0).
- `uv run yellow-sleeper --help` — passed without identity (exit 0).

What's next:
- Coordinator/owner review of draft PR. Stay draft.

Blockers:
- Commercial/redistribution rights for Sleeper and FantasyCalc payloads remain an explicit limitation (`NOTICE`), not a grant.

## 2026-09-21 — Conditional, OR, and pick-swap ranges

Current milestone: conditional/swap ranges on `cursor/conditional-swap-ranges-f829` (draft PR).

What was just completed:
- Conditional (`if` / `unless` / `when` / `whenever` / `conditional`), exclusive-OR (`or`), and pick-swap (`swap` / `pick swap`) language does not get one invented `delta`.
- `dynasty_analyze_trade` returns `PARTIAL` + `NEEDS_CLARIFICATION` with `conditional_or_swap_trade`, plus `candidates` and/or `delta_min` / `delta_max`.
- A normal trade still returns one `delta`. No write tools or trade submission.
- Re-implements the reviewed range idea from closed PR #15 with attribution; does not merge that branch. Base is overlay merge `68d3ddef`. Tag `v0.2.0` stays on `617427ff`.

Validation commands run:
- `uv lock --check` — passed (exit 0).
- `uv run ruff check src tests scripts` — passed (exit 0).
- `uv run python -m pytest tests/ -q` — passed, **147 tests** collected and passed (exit 0). No live Sleeper/FantasyCalc HTTP.
- `HTTP(S)_PROXY=http://127.0.0.1:1 HTTPS_PROXY=http://127.0.0.1:1 uv run python -m pytest tests/ -q` — passed, **147 tests** (exit 0).
- `uv build && uv run python scripts/inspect_dist.py` — passed (exit 0).
- `uv run yellow-sleeper --help` — passed without identity (exit 0).

What's next:
- Coordinator/owner review of draft PR. Stay draft.

Blockers:
- Commercial/redistribution rights for Sleeper and FantasyCalc payloads remain an explicit limitation (`NOTICE`), not a grant.

