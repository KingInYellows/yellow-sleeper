# Yellow Sleeper

Local, single-user, read-only stdio MCP server for one Sleeper dynasty league. It answers roster, pick, value, and trade-guardrail questions for a configured owner. It does not place waivers, send trades, host HTTP, or talk to paid models.

This README describes the **public developer-preview candidate** on branch `agent/public-developer-preview`. It is not `main`, and it is not the unmerged feature PRs.

## What this is vs what it is not

| Surface | Status |
| --- | --- |
| `main` (`c6c6564` and later) | Merged MVP: 11 `dynasty_*` tools, static pick table, FantasyCalc **without** `tep`, unscoped cache files, default username leftover removed only on this candidate |
| This candidate | Explicit league/user, cache isolation, `tep=te+`, log redaction, CI, this README |
| Unmerged PRs `#2` `#3` `#13` `#15` `#16` `#18` | Not in this preview. `#16` ideas (TEP query + cache-by-query-shape + CI skeleton) were **re-implemented here with attribution**, not merged |
| Future | XLSX overlay, FantasyCalc pick ladder as primary pick values, transactions, conditionals, HTTP/OAuth/Docker, multi-user |

**Non-goals for this preview:** HTTP hosting, OAuth, Docker, transaction tools, workbook import, conditional-trade engine, multi-user, live API tests, Graphite submit.

## Data rights (read before install)

**MIT covers this repository's code and synthetic fixtures only.** See `LICENSE` and `NOTICE`. It does **not** relicense Sleeper or FantasyCalc APIs, datasets, or caches.

- **What we ship:** code plus synthetic examples (`casey` / league `1234567890`). We do **not** ship live provider dumps or personal workbooks.
- **Sleeper:** The public API is documented as free for **non-commercial** use; commercial use requires contacting Sleeper about licensing ([Sleeper API](https://docs.sleeper.com/)). Sleeper's [General Terms of Use](https://sleeper.com/terms) grant a limited personal, non-commercial license and prohibit connecting a third-party product that accesses, syncs, retrieves, aggregates, stores, or displays Sleeper data (including league, roster, transaction, scoring, and account data) for that third party's commercial or business purposes without Sleeper's express written consent. The older support-center ToS URL currently 404s; use the live terms page.
- **FantasyCalc:** Data is copyrighted by FantasyCalc. Documented API use is **non-commercial**, requires attribution and a link to fantasycalc.com, and commercial use needs express written permission. Public-facing apps should email FantasyCalc before launch. Binding text: [Terms of Usage](https://fantasycalc.com/terms-of-usage) and [API Docs](https://fantasycalc.com/api-docs). [`/terms`](https://fantasycalc.com/terms) is a marketing SPA, not the terms text.
- **Limitation, not a grant:** unresolved commercial and redistribution rights for Sleeper/FantasyCalc payloads remain an explicit limitation. MIT does not grant those rights. Tests never hit live APIs.

## Supported valuation profile

Pinned FantasyCalc `/values/current` query (supported profile: 14-team Superflex PPR, 0.5 TEP):

`isDynasty=true&numQbs=2&numTeams=14&ppr=1&tep=te+`

- `tep=te+` is the documented discrete TE+ tier (see public `dsheehan167/go-fantasycalc`; re-implemented from PR `#16`, not a local `0.5` multiplier).
- `tep_tier=off` omits the `tep` key (empty `tep=` errors on the API).
- `te++` is an explicit heavy-TEP discrete tier.
- Other `league_format` strings still use this pinned query and are labeled **unsupported approximations** (including empty format, `14-team SF PPR` with no TEP token, `214-team`, `1QB` while the query is Superflex/`numQbs=2`, `0.5 PPR` / half-PPR / non-PPR, and `1.5 TEP`). The default `14-team SF PPR 0.5 TEP` string is the supported profile and is not labeled unsupported.
- **Pick values** use the internal static round table (R1=3000, R2=1200, R3=600, R4=300, R5=100), not FantasyCalc pick rows. Valuation `source_notes` include that table and the TEP query; on stale/error paths the cache error is prepended rather than replacing those sentences.
- Missing/partial player values stay on the roster or pick list with `data_status` partial/unavailable. The server does not invent numbers.

## Install

Python 3.11+ (3.12 is the primary CI image). [`uv`](https://docs.astral.sh/uv/) is the package manager.

```bash
git clone https://github.com/KingInYellows/yellow-sleeper.git
cd yellow-sleeper
git checkout agent/public-developer-preview
uv sync --extra dev
uv run yellow-sleeper --help
```

Or `uv tool install .` then `yellow-sleeper --help`. Help works with no league configured.

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

**Static keys** (league id, username, format, cache dir, tep tier): YAML > environment.

**Policy lists** (untouchables / protected players / pick patterns): tool override > YAML > environment.

| YAML | Environment |
| --- | --- |
| `sleeper_league_id` | `SLEEPER_LEAGUE_ID` |
| `sleeper_username` | `SLEEPER_USERNAME` |
| `league_format` | `LEAGUE_FORMAT` |
| `cache_dir` | `CACHE_DIR` |
| `tep_tier` | `YELLOW_SLEEPER_TEP_TIER` (`off` / `te+` / `te++`) |
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
6. `dynasty_get_player_value` — FantasyCalc lookup; xlsx source is unimplemented
7. `dynasty_analyze_trade` — resolution, guardrails, value math, roster context
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
- `fantasycalc_values__v1__<sorted-query>.json` — one board per query shape
- `logs/server.log` — JSON logs (gitignored)

Legacy unscoped `league_snapshot.json` / `fantasycalc_values.json` / `draft_state.json` are **never** reused for scoped reads. Switching leagues or TEP tiers in one cache directory cannot satisfy the other identity.

Do not commit `.env`, `.yellow-sleeper.yaml`, caches, or logs. The example YAML is synthetic.

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

- Static pick table, not a live pick market.
- XLSX overlay, conditionals, transactions, HTTP MCP, OAuth, Docker: out of scope.
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
