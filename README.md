# Yellow Sleeper

Local, single-user, read-only stdio MCP server for one Sleeper dynasty league. It answers roster, pick, value, and trade-guardrail questions for a configured owner. It does not place waivers, send trades, host HTTP, or talk to paid models.

This README describes the **v0.2.0 developer prerelease** (current `main`). Settings-matched FantasyCalc valuations and provider-backed picks are in that tag. Unmerged feature PRs are not.

## What this is vs what it is not

| Surface | Status |
| --- | --- |
| `main` | Current installable tree: 11 `dynasty_*` tools, explicit league/user, cache isolation, settings-matched FantasyCalc queries, provider-backed generic PICK rows with labeled static fallback, log redaction, CI |
| Unmerged PRs `#2` `#3` `#13` `#15` `#16` `#18` | Not on `main`. `#16` ideas (TEP query + cache-by-query-shape + CI skeleton) were **re-implemented here with attribution**, not merged. Closed `#15` CSV overlay and conditional-range ideas are this tree, re-implemented with attribution, not merged |
| Future | FantasyCalc early/mid/late slot picking, transactions, HTTP/OAuth/Docker, multi-user |

**Non-goals:** HTTP hosting, OAuth, Docker, transaction tools, workbook import, trade submission, multi-user, live API tests, Graphite submit.

## Data rights (read before install)

**MIT covers this repository's code and synthetic fixtures only.** See `LICENSE` and `NOTICE`. It does **not** relicense Sleeper or FantasyCalc APIs, datasets, or caches.

- **What we ship:** code plus synthetic examples (`casey` / league `1234567890`). We do **not** ship live provider dumps or personal workbooks.
- **Sleeper:** The public API is documented as free for **non-commercial** use; commercial use requires contacting Sleeper about licensing ([Sleeper API](https://docs.sleeper.com/)). Sleeper's [General Terms of Use](https://sleeper.com/terms) grant a limited personal, non-commercial license and prohibit connecting a third-party product that accesses, syncs, retrieves, aggregates, stores, or displays Sleeper data (including league, roster, transaction, scoring, and account data) for that third party's commercial or business purposes without Sleeper's express written consent. The older support-center ToS URL currently 404s; use the live terms page.
- **FantasyCalc:** Data is copyrighted by FantasyCalc. Documented API use is **non-commercial**, requires attribution and a link to fantasycalc.com, and commercial use needs express written permission. Public-facing apps should email FantasyCalc before launch. Binding text: [Terms of Usage](https://fantasycalc.com/terms-of-usage) and [API Docs](https://fantasycalc.com/api-docs). [`/terms`](https://fantasycalc.com/terms) is a marketing SPA, not the terms text.
- **Limitation, not a grant:** unresolved commercial and redistribution rights for Sleeper/FantasyCalc payloads remain an explicit limitation. MIT does not grant those rights. Tests never hit live APIs.

## Supported valuation profile

FantasyCalc `/values/current` params are derived from configured `league_format` when every field maps to a value documented on the public [FantasyCalc API Docs](https://fantasycalc.com/api-docs):

| Param | Documented values | Default `14-team SF PPR 0.5 TEP` |
| --- | --- | --- |
| `isDynasty` | `true` (this product is dynasty-only) | `true` |
| `numQbs` | `"1"` (1QB) or `"2"` (Superflex/2QB) | `2` |
| `numTeams` | `8`, `10`, `12`, `14` | `14` |
| `ppr` | `0`, `0.5`, `1` | `1` |
| `tep` | `none`, `te+`, `te++` | `te+` |

Default query: `isDynasty=true&numQbs=2&numTeams=14&ppr=1&tep=te+`

- `tep=te+` is the documented discrete TE+ tier for 0.5 TEP (not a local `0.5` multiplier). Supported non-TEP queries send literal `tep=none` (documented enum; empty `tep=` errors).
- `tep_tier=off` sends `tep=none` when the format does not request TEP. `te++` is the documented heavy-TEP discrete tier.
- Supported examples include `12-team 1QB PPR`, `10-team Superflex 0.5 PPR`, `8-team SF non-PPR`, and `14-team SF PPR` (no TEP → `tep=none`).
- Unsupported combinations (`16`-team, `214-team`, SF+1QB together, missing PPR, `1.5 TEP`, empty format) **do not** reuse another board. Tools return missing/partial values with reasons. Cache files stay isolated by schema version `v1` plus the normalized query that was actually sent.
- **Pick values:** when a generic `{season} {ordinal}` FantasyCalc `PICK` row exists (e.g. `2027 1st`), that single value is used and provenance says `fantasycalc`. When it does not, and Early/Mid/Late band rows exist, the single-number field stays empty and provenance reports the low/high range plus band labels (`PARTIAL`). Sleeper `roster_id` is never a draft slot. The static round table (R1=3000, R2=1200, R3=600, R4=300, R5=100) is **fallback only** when neither generic nor band rows exist, labeled `config_pick_table`, never presented as freshly fetched provider data.
- Missing/partial player values stay on the roster or pick list with `data_status` partial/unavailable. The server does not invent numbers.

## Install

**v0.2.0 is a developer prerelease.** It is not on PyPI. Install from that tag.

Python 3.11+ (3.12 is the primary CI image). [`uv`](https://docs.astral.sh/uv/) is the package manager.

```bash
git clone https://github.com/KingInYellows/yellow-sleeper.git
cd yellow-sleeper
git checkout v0.2.0
uv sync --extra dev
uv run yellow-sleeper --help
```

Equivalent: `uv tool install git+https://github.com/KingInYellows/yellow-sleeper.git@v0.2.0` then `yellow-sleeper --help`. Help works with no league configured.

Copy the synthetic example (tracked) and fill **your** identity:

```bash
cp .yellow-sleeper.yaml.example .yellow-sleeper.yaml
```

`.yellow-sleeper.yaml` is gitignored. Do not commit a live league id or username.

## Config and precedence

Required before any league-scoped Sleeper request:

- `sleeper_league_id` (not empty, not `0` / `your_league_id` / `changeme`)
- `sleeper_username` (not empty, not `your_username` / `changeme`)

There is **no** silent first-roster or username fallback.

**Static keys** (league id, username, format, cache dir, tep tier, overlay path): YAML > environment.

**Policy lists** (untouchables / protected players / pick patterns): tool override > YAML > environment.

| YAML | Environment |
| --- | --- |
| `sleeper_league_id` | `SLEEPER_LEAGUE_ID` |
| `sleeper_username` | `SLEEPER_USERNAME` |
| `league_format` | `LEAGUE_FORMAT` |
| `cache_dir` | `CACHE_DIR` |
| `tep_tier` | `YELLOW_SLEEPER_TEP_TIER` (`off` / `te+` / `te++`) |
| `values_overlay_path` | `YELLOW_SLEEPER_VALUES_OVERLAY_PATH` (CSV keyed by `sleeper_id`; contract source name `xlsx`) |
| `hard_untouchables` | `YELLOW_SLEEPER_HARD_UNTOUCHABLES` (comma-separated) |
| config path | `YELLOW_SLEEPER_CONFIG` (default `.yellow-sleeper.yaml`) |

`dynasty_health_check` (without `force_probe`) works when identity is missing and reports the error in `errors`.

## Cursor stdio MCP setup

Official Cursor docs (https://cursor.com/docs/mcp) describe project `.cursor/mcp.json`, user `~/.cursor/mcp.json`, stdio `type` / `command` / `args` / `env` / `envFile`, and `${env:NAME}` interpolation.

**Docs-only:** Cursor Settings → MCP UI, `envFile`, and interpolation were read from those official docs and were **not** clicked in this preview environment.

**Exercised in this repo:** local stdio JSON-RPC `initialize`, `tools/list`, and representative `tools/call` against synthetic fixtures (`tests/smoke/test_mcp_stdio.py`). No live Sleeper or FantasyCalc HTTP in tests.

Example (put **your** ids in env or a gitignored `.env`; do not commit them):

```json
{
  "mcpServers": {
    "yellow-sleeper": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "yellow-sleeper"],
      "env": {
        "SLEEPER_LEAGUE_ID": "${env:SLEEPER_LEAGUE_ID}",
        "SLEEPER_USERNAME": "${env:SLEEPER_USERNAME}"
      },
      "envFile": "${workspaceFolder}/.env"
    }
  }
}
```

If `yellow-sleeper` is on `PATH` via `uv tool install .`, `command` can be `yellow-sleeper` with no `args`.

## Tools (11)

Derived from `src/yellow_sleeper/tools/` on this branch:

1. `dynasty_health_check` — config, cache freshness, optional live probes
2. `dynasty_get_my_roster` — configured owner's roster, values, policy flags
3. `dynasty_find_roster` — fuzzy roster search
4. `dynasty_list_traded_picks` — league traded-pick market (owner roster via username helper)
5. `dynasty_list_my_picks` — native + traded-in (optional traded-away)
6. `dynasty_get_player_value` — FantasyCalc lookup; optional CSV overlay (`xlsx`) wins when configured
7. `dynasty_analyze_trade` — resolution, guardrails, value math, roster context; conditional/OR/swap language returns a range or candidates plus clarification
8. `dynasty_league_power_map` — per-team rollups
9. `dynasty_whats_on_the_clock` — draft clock / recent picks
10. `dynasty_best_player_available` — rookie BPA board
11. `dynasty_refresh_cache` — refresh players/values/snapshot/draft using the same cache keys

## Example questions

- "Health-check the yellow-sleeper server and tell me if identity is configured."
- "Show my roster with FantasyCalc values and which assets are protected."
- "Which 2027 firsts have been traded, and who currently owns them?"
- "What is Drake London's cached value, and which TEP query was used?"
- "If I send Example Franchise Quarterback for Bijan Robinson, which guardrails fire?" (replace names with yours)

## Cache and privacy

Cache files live under `cache_dir` (default `.cache/`):

- `sleeper_players_nfl.json.gz` — global player dictionary
- `league_snapshot__<league_id>.json` — one file per league
- `draft_state__<draft_id>__league-<league_id>.json` — draft + league scope
- `fantasycalc_values__v1__<sorted-query>.json` — one board per query shape (no overlay)
- `fantasycalc_values__v1__<sorted-query>__overlay-on.json` — same query with overlay active; a no-overlay board cannot satisfy an overlay query
- `logs/server.log` — JSON logs (gitignored)

Legacy unscoped `league_snapshot.json` / `fantasycalc_values.json` / `draft_state.json` are **never** reused for scoped reads. Switching leagues or TEP tiers in one cache directory cannot satisfy the other identity.

Do not commit `.env`, `.yellow-sleeper.yaml`, `.yellow-sleeper-values.csv`, caches, or logs. The example YAML and CSV are synthetic.

**Logging:** the `yellow_sleeper` logger redacts configured league id / username (length ≥ 4), matching extra keys, formatted messages, args, exception text, and `/league/<id>` URL path segments. Residual limits: root/`httpx` loggers, process listings, Cursor MCP UI, and MCP **tool JSON** (league data is the product and is not redacted).

## Troubleshooting

| Symptom | What to do |
| --- | --- |
| "Missing or invalid sleeper_league_id" | Set YAML or `SLEEPER_LEAGUE_ID` / `SLEEPER_USERNAME`; `0` and `changeme` are rejected |
| `dynasty_health_check` shows `unconfigured` | Expected until identity is set; help still works |
| Username did not map to a roster | Live Sleeper users often omit `username`; try display name; the helper never invents roster `0` |
| Values look like non-TEP | Confirm `tep_tier: te+` and delete old unscoped `fantasycalc_values.json` |
| Stale values after an outage | Scoped stale fallback is within that identity only; `dynasty_refresh_cache` |
| Cursor does not list tools | Stdio only; check MCP logs; stdout must stay JSON-RPC (`propagate=False` on app logs) |
| Tests failed in CI | Tests are fixture/respx only; they must not call live Sleeper or FantasyCalc |

## Limitations

- When a generic `{season} {ordinal}` FantasyCalc PICK row is missing but Early/Mid/Late band rows exist, the single-number field stays empty and provenance reports the low/high range plus band labels (`PARTIAL`). Static R1=3000 is fallback only when neither generic nor band rows exist. No projected_slot.
- Optional local CSV overlay (`values_overlay_path`) is keyed by Sleeper player id. Contract source name stays `xlsx`. Overlay wins over FantasyCalc when the file loads. A missing configured file is an explicit status, not a silent FantasyCalc fallback labeled as overlay. Unset path keeps FantasyCalc-only.
- Conditional, exclusive-OR, and pick-swap trade language does not get one invented delta. `dynasty_analyze_trade` returns `PARTIAL` + `NEEDS_CLARIFICATION` with candidates and/or `delta_min` / `delta_max`. A normal trade still returns one value. No write tools or trade submission.
- Transactions, HTTP MCP, OAuth, Docker: out of scope.
- MIT covers code and synthetic fixtures only; Sleeper/FantasyCalc commercial and redistribution rights stay a limitation (`NOTICE`).
- GitHub org `KingInYellows` does not currently enable private vulnerability reporting.

## Maintainer expectations

- `uv lock --check` before bumping dependencies; no indiscriminate upgrades.
- `uv run ruff check src tests scripts` and `uv run python -m pytest tests/ -v`.
- GitHub Actions on this branch: Python 3.11 and 3.12, `contents: read`, SHA-pinned actions, no secrets, no self-hosted runners.
- Submit preview work as a **draft** PR (`agent/` prefix). Do not `gt submit` (repo `.graphite.yml` defaults `submit.draft: false`).
- Canonical product docs remain `PRD.md`, `TOOL_CONTRACTS.md`, `TECHNICAL_SPEC.md`, `DECISIONS.md`. Extend them; do not start a second spec tree.
- Frozen MVP wording that says "Brad's roster" means the configured owner. Authorship notices stay.

See `CONTRIBUTING.md` and `SECURITY.md`.
