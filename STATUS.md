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

## 2026-08-20 — Stage 2 research and plan (value accuracy)

Current milestone: Stage 2 planning (not yet implementing).

What was just completed:
- Ran multi-source research on FantasyCalc TEP, spreadsheet overlays, and pick valuation (`docs/research/accurate-stage-2-value-modeling.md`).
- Confirmed live FantasyCalc `tep=te+` / `te++` (TECHNICAL_SPEC §4 “no tep param” is outdated).
- Wrote `STAGE2_PLAN.md` with accuracy-first milestones S2-1 → S2-4.
- Recorded decisions in `DECISIONS.md`.

What's next:
- Implement **S2-1**: FantasyCalc `tep=te+` + config + fixtures + TECHNICAL_SPEC §4 reconcile.
- Then S2-2 pick ladder, S2-3 overlay, S2-4 conditionals.

Blockers:
- None for S2-1.

## 2026-08-26 — S2-1: FantasyCalc `tep=te+`

Current milestone: S2-1.

What was just completed:
- Config `tep_tier` (default `te+`); FantasyCalc client sends `tep=te+` and omits the key when `off`.
- Query-shape cache isolation; health still reports `fantasycalc_values`.
- Shared `resolve_player_value` stub wired through the five value-bearing tools.
- Separate TE+ fixture (original non-TEP board unchanged); GitHub Actions ruff+pytest; `goal.md` historical-MVP banner.
- Live probe note: `docs/research/fantasycalc-tep-probe-2026-08-26.md`.

What's next:
- S2-2 FantasyCalc pick ladder.

Blockers:
- None.
