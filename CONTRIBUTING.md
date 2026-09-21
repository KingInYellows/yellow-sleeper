# Contributing

This is a personal dynasty MCP server. Current installable code is on `main`. Open draft PRs from `agent/` branches; do not push to `main`.

## Setup

```bash
uv sync --extra dev
uv run ruff check src tests scripts
uv run python -m pytest tests/ -v
uv run yellow-sleeper --help
```

Python 3.11 is the declared minimum; 3.12 is the primary CI image. Keep `uv.lock` in sync with `uv lock --check`. Do not upgrade the lock without a reason.

## Tests

Tests use hand-crafted fixtures and `respx`. They must not call live Sleeper, FantasyCalc, or paid models. Seed scoped cache files when a test needs league data.

## Docs and identity

- Canonical contracts: `PRD.md`, `TOOL_CONTRACTS.md`, `TECHNICAL_SPEC.md`, `DECISIONS.md`. Append amendments; do not silently rewrite historical decisions.
- Copy `.yellow-sleeper.yaml.example` locally. Never commit `.yellow-sleeper.yaml`, `.env`, caches, or logs.
- Examples in public files must be synthetic (`casey` / league `1234567890`). Keep authorship notices.
- MIT (`LICENSE`) covers code and synthetic fixtures only. Do not paste live league data. See `NOTICE`.

## Pull requests

Open **draft** PRs from `agent/` branches. Graphite CLI is not required and must not be used if it would mark a PR ready. Do not enable auto-merge.

## Security

See `SECURITY.md`. There is no private reporting inbox published for this repo.
