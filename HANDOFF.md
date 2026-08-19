# Yellow Sleeper MCP Handoff

## Stage 2 (2026-08-19)

Live local MCP for Mifflin Doty Dynasty.

- League: `1312121399602581504`
- User: `BradSchwarzkopf` (Sleeper `username` is null; match display_name)
- Transports: stdio (`yellow-sleeper`), JSON desk (`serve-http` :8091), streamable HTTP MCP (`serve-mcp-http` :8092)
- TEP: computed `1 + tep*0.35` (0.5 → 1.175x TEs). Raw FantasyCalc stays a second source.
- xlsx/csv overlay: user rows win. Disagreement only if sources differ >25%.
- Conditionals / OR / swap → `CONDITIONAL_OR_SWAP_TRADE` + `NEEDS_CLARIFICATION`
- `as_user` on roster / trade / picks
- Deferred: Docker, OAuth, live Sleeper notifications

### Verify

```sh
uv sync --extra dev
uv run ruff check src/ tests/
uv run python -m pytest tests/ -q
printf '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}\n' | timeout 3 uv run python -m yellow_sleeper || true
```

Install for Claude/Cursor:

```sh
uv tool install git+https://github.com/KingInYellows/yellow-sleeper.git
```

Claude Desktop config:

```json
{
  "mcpServers": {
    "yellow-sleeper": {
      "command": "yellow-sleeper",
      "env": {
        "YELLOW_SLEEPER_CONFIG": "/absolute/path/to/.yellow-sleeper.yaml"
      }
    }
  }
}
```

The desk at preview `/` talks to `/mcp-api` → `127.0.0.1:8091`.

## Inventory (MVP + Stage 2)

See `src/yellow_sleeper/` for the package. Frozen contracts: `PRD.md`, `TOOL_CONTRACTS.md`, `TECHNICAL_SPEC.md` — do not edit.

`tests/fixtures/sleeper/users_14team.json` is required by `tests/conftest.py` (was missing from `main` at `bdc471b6`).
