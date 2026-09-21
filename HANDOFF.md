# Yellow Sleeper MCP MVP Handoff

## Inventory

| File | Purpose |
| --- | --- |
| `.gitignore` | Ignores caches, virtualenvs, build output, and Python bytecode. |
| `.yellow-sleeper.yaml.example` | Example local policy config for hard untouchables and protected assets. |
| `DECISIONS.md` | Durable architectural decision log. |
| `PLAN.md` | Milestone plan generated from the frozen PRD/contracts/spec. |
| `README.md` | Minimal project overview and source-of-truth pointer. |
| `STATUS.md` | Living implementation and verification log. |
| `HANDOFF.md` | Reviewer handoff, verification commands, gaps, and drift notes. |
| `pyproject.toml` | Package metadata, dependencies, script entry point, pytest, and ruff config. |
| `uv.lock` | Resolved dependency lock created by `uv`. |
| `src/yellow_sleeper/__init__.py` | Package marker and version. |
| `src/yellow_sleeper/__main__.py` | CLI entry point and `--help` handling. |
| `src/yellow_sleeper/server.py` | Single FastMCP instance with lifespan-managed runtime. |
| `src/yellow_sleeper/runtime.py` | Config/cache/client runtime wiring and cache refresh orchestration. |
| `src/yellow_sleeper/config.py` | Env/YAML/default config and hot-reload policy merge logic. |
| `src/yellow_sleeper/models/__init__.py` | Public exports for all Pydantic contract models. |
| `src/yellow_sleeper/models/envelope.py` | Status enums, response envelope, transport error, and envelope validators. |
| `src/yellow_sleeper/models/shared.py` | Source notes, policy flags, blocking rules, candidates, and asset resolution models. |
| `src/yellow_sleeper/models/trade.py` | Trade input/output, value math, roster context, and blocked-trade validator. |
| `src/yellow_sleeper/models/roster.py` | Roster, find-roster, and league power map models. |
| `src/yellow_sleeper/models/picks.py` | Traded-pick and pick inventory models. |
| `src/yellow_sleeper/models/values.py` | FantasyCalc value lookup models. |
| `src/yellow_sleeper/models/bpa.py` | Best-player-available input/output models. |
| `src/yellow_sleeper/models/draft.py` | Draft state and on-the-clock models. |
| `src/yellow_sleeper/models/health.py` | Health-check models and cache-state literal. |
| `src/yellow_sleeper/models/refresh.py` | Cache refresh input/output models. |
| `src/yellow_sleeper/clients/__init__.py` | Client exports. |
| `src/yellow_sleeper/clients/http.py` | Shared `httpx.AsyncClient` factory with explicit timeouts. |
| `src/yellow_sleeper/clients/sleeper.py` | Sleeper API client, retry policy, probes, and cached fetch helpers. |
| `src/yellow_sleeper/clients/fantasycalc.py` | FantasyCalc client, schema adapter, indexing, probes, and cached values. |
| `src/yellow_sleeper/store/__init__.py` | Cache exports. |
| `src/yellow_sleeper/store/cache.py` | Atomic JSON/gzip file cache with per-key asyncio locks and stale fallback. |
| `src/yellow_sleeper/store/paths.py` | Cache key, path, gzip, and TTL definitions. |
| `src/yellow_sleeper/resolve/__init__.py` | Resolver exports. |
| `src/yellow_sleeper/resolve/players.py` | RapidFuzz player resolution with 88/70 thresholds. |
| `src/yellow_sleeper/resolve/rosters.py` | Fuzzy roster resolution with narrow-margin rule. |
| `src/yellow_sleeper/resolve/picks.py` | Pick description parser and 100/50/0 pick resolution. |
| `src/yellow_sleeper/analyze/__init__.py` | Analysis exports. |
| `src/yellow_sleeper/analyze/roster.py` | Pick inventory native grid, traded overlay, and roster helpers. |
| `src/yellow_sleeper/analyze/value.py` | FantasyCalc value parsing, provider pick rows, and static pick-table fallback. |
| `src/yellow_sleeper/analyze/pipelines.py` | Typed output builders for all eleven `dynasty_*` tools. |
| `src/yellow_sleeper/obs/__init__.py` | Observability utility exports. |
| `src/yellow_sleeper/obs/caps.py` | String and array cap utilities. |
| `src/yellow_sleeper/obs/logging.py` | JSON file logging and recursive redaction filter. |
| `src/yellow_sleeper/tools/__init__.py` | Imports all FastMCP tool modules for registration. |
| `src/yellow_sleeper/tools/health_check.py` | `dynasty_health_check` MCP wrapper. |
| `src/yellow_sleeper/tools/get_my_roster.py` | `dynasty_get_my_roster` MCP wrapper. |
| `src/yellow_sleeper/tools/find_roster.py` | `dynasty_find_roster` MCP wrapper. |
| `src/yellow_sleeper/tools/list_traded_picks.py` | `dynasty_list_traded_picks` MCP wrapper. |
| `src/yellow_sleeper/tools/list_my_picks.py` | `dynasty_list_my_picks` MCP wrapper. |
| `src/yellow_sleeper/tools/get_player_value.py` | `dynasty_get_player_value` MCP wrapper. |
| `src/yellow_sleeper/tools/analyze_trade.py` | `dynasty_analyze_trade` MCP wrapper. |
| `src/yellow_sleeper/tools/league_power_map.py` | `dynasty_league_power_map` MCP wrapper. |
| `src/yellow_sleeper/tools/whats_on_the_clock.py` | `dynasty_whats_on_the_clock` MCP wrapper. |
| `src/yellow_sleeper/tools/best_player_available.py` | `dynasty_best_player_available` MCP wrapper. |
| `src/yellow_sleeper/tools/refresh_cache.py` | `dynasty_refresh_cache` MCP wrapper. |
| `tests/__init__.py` | Test package marker. |
| `tests/conftest.py` | Fixture loader and joined Sleeper snapshot fixture. |
| `tests/fixtures/sleeper/league.json` | Hand-crafted Sleeper league fixture. |
| `tests/fixtures/sleeper/rosters_14team.json` | Hand-crafted 14-team Sleeper roster fixture. |
| `tests/fixtures/sleeper/users_14team.json` | Hand-crafted Sleeper users fixture. |
| `tests/fixtures/sleeper/traded_picks.json` | Hand-crafted Sleeper traded-picks fixture. |
| `tests/fixtures/sleeper/drafts.json` | Hand-crafted Sleeper league drafts fixture. |
| `tests/fixtures/sleeper/draft.json` | Hand-crafted current draft fixture. |
| `tests/fixtures/sleeper/draft_picks.json` | Hand-crafted recent draft picks fixture. |
| `tests/fixtures/sleeper/players_nfl.json` | Hand-crafted Sleeper player cache fixture. |
| `tests/fixtures/fantasycalc/values_current.json` | Hand-crafted FantasyCalc current values fixture. |
| `tests/unit/test_envelope_validators.py` | Cross-cutting envelope and trade validators. |
| `tests/unit/test_models_contract.py` | Contract model export coverage. |
| `tests/unit/test_config.py` | Config precedence, validation, and reload behavior. |
| `tests/unit/test_cache.py` | Atomic cache writes, gzip reads, and stale fallback. |
| `tests/unit/test_logging.py` | JSON log output and redaction behavior. |
| `tests/unit/test_caps.py` | Field cap helper behavior. |
| `tests/unit/test_pick_parser.py` | Pick parsing and pick resolution thresholds. |
| `tests/unit/test_player_resolver.py` | Player fuzzy resolution thresholds. |
| `tests/unit/test_roster_resolver.py` | Roster fuzzy resolution and narrow-margin rule. |
| `tests/unit/test_pick_inventory.py` | Pick inventory native grid and traded overlay. |
| `tests/integration/test_sleeper_client.py` | Sleeper client with respx and pinned fixtures. |
| `tests/integration/test_fantasycalc_client.py` | FantasyCalc adapter/indexing with respx and pinned fixtures. |
| `tests/smoke/test_smoke_questions.py` | Six end-to-end MVP smoke scenarios against real fixtures. |

## Verification Commands

Run from the repository root:

```bash
uv tool install .
yellow-sleeper --help
uv sync --extra dev
PATH="$PWD/.venv/bin:$PATH" ruff check src/ tests/
PATH="$PWD/.venv/bin:$PATH" python -m pytest tests/ -v
```

The final run in this workspace passed with 50 tests: 39 unit, 5 integration, and 6 smoke.

Preview candidate verification on `agent/public-developer-preview`: `uv run python -m pytest tests/ -q` passed with **108 tests** (recount after owner-decision tests; was 101 at `6e344a5`, previously documented as 88).

League-true valuations on `agent/league-true-valuations`: `uv run python -m pytest tests/ -q` passed with **120 tests**.

Preview candidate verification is recorded in the section below; re-run those commands on `agent/public-developer-preview`.

## Known Gaps

Spec deferrals:
- Optional CSV value overlay (`source=xlsx`) is implemented; a missing configured file is explicit, default unset path is FantasyCalc-only.
- TEP-aware value adjustment is not implemented as a local multiplier; FantasyCalc discrete `tep` enums are used when the format maps.
- Conditional trades and pick swaps return a range or candidates plus clarification; they do not invent one delta. A normal trade still returns one value. No write/submit tools.
- Multi-user support, public HTTP transport, Docker packaging, OAuth, and live Sleeper notifications are not implemented.

Implementation shortcuts:
- Pick values use FantasyCalc generic PICK rows when present; otherwise the internal static round table recorded in `DECISIONS.md` (labeled fallback, not provider data).
- Smoke scenarios are derived from the frozen contracts/spec because the PRD has no literal `Success Metrics` section.
- Tests use hand-crafted fixtures only; no fixture was generated from live APIs.

Unresolved questions:
- None blocking for MVP review.

## Spec Drift

- `goal.md` references PRD `Success Metrics`, but `PRD.md` v0.4.4 does not contain that heading. See `DECISIONS.md` entry "Smoke Scenario Source".
- MVP pick values required a concrete static table not numerically specified in the frozen docs. See `DECISIONS.md` entry "MVP Pick Value Table".

## Public developer-preview candidate (2026-09-20)

Branch: `agent/public-developer-preview` (not `main`). Draft PR only.

What this candidate adds on top of the MVP handoff above:

- Explicit `sleeper_league_id` / `sleeper_username`; no silent first-roster fallback.
- Cache files namespaced by league id, draft id+league, and FantasyCalc query shape (`v1` + sorted params). Legacy unscoped files are never trusted.
- FantasyCalc `tep=te+` for the supported 14-team SF PPR 0.5 TEP profile (re-implemented from PR `#16` ideas; `#16` was not merged). Static pick table unchanged and stated in provenance.
- Log redaction for messages, args, exceptions, and `/league/<id>` URLs on the `yellow_sleeper` logger.
- `dynasty_list_traded_picks` uses `find_roster_id_for_username` instead of roster `0`.
- Public README, CONTRIBUTING, SECURITY (no invented contact; org private reporting is off).
- GitHub Actions `test.yml` on GitHub-hosted runners, Python 3.11/3.12, `contents: read`, SHA-pinned actions.
- MIT License (`LICENSE`) with matching `pyproject.toml` license metadata. MIT covers code and synthetic fixtures only; see `NOTICE`.

Verification (preview):

```bash
uv lock --check
uv sync --frozen --extra dev
uv run ruff check src tests scripts
uv run python -m pytest tests/ -v
uv build && uv run python scripts/inspect_dist.py
uv run yellow-sleeper --help
```

Known preview gaps:

- Sleeper/FantasyCalc commercial and redistribution rights remain an explicit limitation (`NOTICE`), not a grant.
- Cursor MCP `mcp.json` fields were checked against https://cursor.com/docs/mcp (docs-only). Stdio initialize/tools/list/tools/call is exercised in `tests/smoke/test_mcp_stdio.py`.
- Unmerged PRs `#2` `#3` `#13` `#15` `#16` `#18` stay out of this branch.

## League-true valuations (2026-09-21)

Branch: `agent/league-true-valuations`. Draft PR only. Does not merge `#15`.

What this adds on top of the preview candidate:

- FantasyCalc query follows documented settings parsed from `league_format` (`numTeams` 8/10/12/14, `numQbs` 1/2, `ppr` 0/0.5/1, `tep` omitted/`te+`/`te++`). Default 14-team SF full-PPR 0.5 TEP still sends `tep=te+`.
- Unsupported formats do not reuse another board; tools return missing/partial with reasons.
- Provider generic PICK rows when present; static round table is labeled fallback only.

Verification:

```bash
uv lock --check
uv sync --frozen --extra dev
uv run ruff check src tests scripts
uv run python -m pytest tests/ -q
uv build && uv run python scripts/inspect_dist.py
uv run yellow-sleeper --help
```

The run on this head passed with **120 tests** (exit 0 on every command above). Stdio MCP smoke remains in `tests/smoke/test_mcp_stdio.py`.

## Valuation residuals (2026-09-21)

Branch: `agent/valuation-residuals`. Draft PR only. Does not merge `#13` `#15` `#16` `#18` `#2` `#3`.

- Supported non-TEP FantasyCalc queries send documented `tep=none` (bare `tep=` errors; the key is not omitted). Default 14-team SF full-PPR 0.5 TEP still sends `tep=te+`; `te++` stays as already supported.
- Generic `{season} {ordinal}` PICK rows remain a single value. Early/Mid/Late-only rows are an explicit low/high range plus `PARTIAL`, not a fabricated slot. Static R1=3000 is fallback only when neither generic nor band rows exist.

The run on this head passed with **124 tests** (exit 0 on every command above). Stdio MCP smoke remains in `tests/smoke/test_mcp_stdio.py`.

