# Yellow Sleeper MCP Status

## 2026-08-19 — Stage 2 live MCP

Current milestone: Stage 2 (TEP, xlsx overlay, conditionals, as_user, HTTP).

What was just completed:
- Restored the package after the sandbox wipe and re-applied Stage 2 on top of `bdc471b6`.
- Added TEP book (`1 + tep*0.35`), user xlsx/csv overlay, conditional/OR/swap detection, case-insensitive roster match, `as_user`, Starlette `/health` + `/tools/{name}` on 8091, streamable HTTP MCP on 8092.
- Live config points at Mifflin Doty Dynasty `1312121399602581504` / `BradSchwarzkopf`.
- Intentionally deferred: Docker, OAuth, live Sleeper notifications.

Files touched:
- `src/yellow_sleeper/analyze/tep.py`
- `src/yellow_sleeper/analyze/overlay.py`
- `src/yellow_sleeper/analyze/conditional.py`
- `src/yellow_sleeper/clients/xlsx.py`
- `src/yellow_sleeper/web.py`
- `src/yellow_sleeper/__main__.py`
- `src/yellow_sleeper/config.py`
- `src/yellow_sleeper/runtime.py`
- `src/yellow_sleeper/analyze/pipelines.py`
- `src/yellow_sleeper/analyze/roster.py`
- `src/yellow_sleeper/tools/*`
- `tests/unit/test_tep.py`
- `tests/unit/test_conditional.py`
- `tests/unit/test_web_dispatcher.py`
- `tests/unit/test_roster_username.py`
- `tests/fixtures/sleeper/users_14team.json`

What's next:
- Prove stdio MCP handshake + live roster against Mifflin Doty.
- Keep 8080/8091 up for the desk.

Blockers:
- None.

## MVP complete — all smoke tests passing, ready for human review

See prior entries for Milestones 0–4. Frozen contracts were not edited.
