# Yellow Sleeper MCP

Local MCP server for Mifflin Doty Dynasty (Sleeper). Facts and flags only.

The frozen implementation contract is in `PRD.md`, `TOOL_CONTRACTS.md`, and `TECHNICAL_SPEC.md`.

## Install

```sh
uv tool install git+https://github.com/KingInYellows/yellow-sleeper.git
```

Or from a checkout:

```sh
uv sync --extra dev
```

Copy `.yellow-sleeper.yaml.example` to `.yellow-sleeper.yaml` and set `sleeper_league_id` / `sleeper_username`.

## Run

```sh
# stdio MCP (Claude Desktop / Cursor)
yellow-sleeper

# JSON desk API
yellow-sleeper serve-http --host 127.0.0.1 --port 8091

# Streamable HTTP MCP
yellow-sleeper serve-mcp-http --host 127.0.0.1 --port 8092
```

Eleven tools: `dynasty_health_check`, `dynasty_get_my_roster`, `dynasty_find_roster`, `dynasty_list_my_picks`, `dynasty_list_traded_picks`, `dynasty_get_player_value`, `dynasty_analyze_trade`, `dynasty_league_power_map`, `dynasty_whats_on_the_clock`, `dynasty_best_player_available`, `dynasty_refresh_cache`.

Stage 2: 0.5 TEP book, optional xlsx overlay, conditional/OR/swap detection, `as_user` roster switch.
