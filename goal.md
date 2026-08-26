> **Historical MVP prompt.** This file is the completed Milestone 0–4 execution prompt. Do not treat the Stage 2 prohibition below as current work. **Stage 2 value accuracy is governed by `STAGE2_PLAN.md`** (and the four-PR Graphite stack from `main`). Packaging, HTTP, Docker, OAuth, multi-user, and notifications remain out of Stage 2 scope.

/goal Build the Yellow Sleeper MCP server MVP to the spec frozen in PRD.md, TOOL_CONTRACTS.md, and TECHNICAL_SPEC.md at the repository root. Do not stop until every smoke-test scenario in PRD §"Success Metrics" passes on a real Sleeper+FantasyCalc fixture set and `uv tool install .` succeeds locally.

## Source of truth — read these first, every loop

These three documents are the contract. They are frozen. Do not modify them. If you believe one is wrong, write a note in DECISIONS.md and proceed with the documented behavior anyway — humans reconcile during review.

- `PRD.md` — what to build and why (v0.4.4 Polished Canonical)
- `TOOL_CONTRACTS.md` — exact Pydantic shapes, validators, JSON examples, fuzzy thresholds (v1.0 Final)
- `TECHNICAL_SPEC.md` — module layout, cache pattern, client implementations, pipeline order, testing approach (v1.0)

Re-read these at the start of every milestone. Treat them as the single source of truth over your own memory.

## Durable project memory — create and maintain these

Before writing any code, create three markdown files in the repo root and keep them current:

- `PLAN.md` — Milestone-based execution plan generated from the three spec docs. Each milestone has: a name, the spec sections it implements, acceptance criteria, validation commands, and "stop-and-fix" rule (if validation fails, repair before advancing). Order milestones so each one is independently testable.
- `STATUS.md` — Living status log. After every milestone update: current milestone, what was just completed, what was verified (commands run + results), what's next, any blockers. This is how a human reviewer understands the run without reading the diff.
- `DECISIONS.md` — Architectural decision log. Every time you make a non-obvious choice (e.g., resolving a spec ambiguity, picking a library version, handling an undocumented API edge case), record: the decision, the alternatives considered, why this one. One entry per decision, ~5 lines.

## Starting state

Empty repository. PRD.md, TOOL_CONTRACTS.md, TECHNICAL_SPEC.md exist at the root. Nothing else.

## Target state

A working Python 3.11+ MCP server at `src/yellow_sleeper/` that:
1. Installs cleanly via `uv tool install .` and exposes the `yellow-sleeper` command
2. Implements all 11 `dynasty_*` tools per TOOL_CONTRACTS.md §2 with exact Pydantic shapes
3. Enforces the three guardrails from PRD §"Guardrail Policy" (hard untouchable block, asset resolution, no write actions)
4. Returns `schema_version`, `policy_status`, `resolution_status`, `data_status`, `source_notes[]`, and `policy_flags[]` on every tool response
5. Passes all six smoke-test scenarios from PRD §"Success Metrics" via the `tests/smoke/` suite
6. Caches Sleeper and FantasyCalc data per TECHNICAL_SPEC §2 with atomic writes and per-key asyncio locks
7. Logs to `.cache/logs/server.log` with JSON format and redaction filter — never to stdio

## Execution loop — follow this every milestone

1. **Plan**: Read PLAN.md. Confirm the next milestone scope. If it's larger than ~300 LOC of new code, split it before starting.
2. **Act**: Implement the milestone. Keep diffs scoped to the files PLAN.md says belong to this milestone. Do not refactor adjacent code.
3. **Test**: Run validation commands listed in PLAN.md for this milestone. At minimum:
   - `ruff check src/ tests/`
   - `python -m pytest tests/unit/ -x -q` for unit milestones
   - `python -m pytest tests/integration/ -x -q` after adding clients
   - `python -m pytest tests/smoke/ -x -q` once the relevant tool is wired
4. **Review**: If validation fails, repair before advancing. Do not move to the next milestone with red tests. Record the failure and fix in STATUS.md.
5. **Iterate**: Update STATUS.md with what shipped and what's next. Update DECISIONS.md if anything non-obvious came up. Move to the next milestone.

## Allowed actions

- Create and modify files under `src/`, `tests/`, and root config files (`pyproject.toml`, `README.md`, `.yellow-sleeper.yaml.example`, `.gitignore`)
- Add dependencies listed in TECHNICAL_SPEC §11 to `pyproject.toml`
- Run `uv`, `python`, `pytest`, `ruff`, and shell commands needed for validation
- Create test fixtures under `tests/fixtures/sleeper/` and `tests/fixtures/fantasycalc/` by hand-crafting representative JSON based on the response shapes in TECHNICAL_SPEC §3 and §4. Do NOT call live APIs to generate fixtures.

## Forbidden actions

- Do NOT modify PRD.md, TOOL_CONTRACTS.md, or TECHNICAL_SPEC.md
- Do NOT call live Sleeper or FantasyCalc APIs from tests — use respx mocks against pinned fixtures only
- Do NOT add dependencies beyond what TECHNICAL_SPEC §11 specifies without recording the decision in DECISIONS.md
- Do NOT copy code from any repository whose license you have not verified as MIT/Apache/BSD (this includes tokenbowl-mcp per PRD)
- Do NOT implement Stage 2 items listed in TECHNICAL_SPEC §13 (xlsx overlay, TEP adjustment, conditional trades, multi-user, HTTP transport, Docker, OAuth)
- Do NOT push to git, deploy, or run any destructive command
- Do NOT add verdicts, recommendations, context scores, or roster_mode anywhere — the server returns data and flags only, never judgment (per PRD)
- Do NOT log `league_id`, `username`, or `user_id` in plain text — the redaction filter in TECHNICAL_SPEC §9 is mandatory

## Stop conditions — pause and write to STATUS.md when

- A spec ambiguity cannot be resolved by re-reading the three source documents
- Two valid implementation paths exist where TECHNICAL_SPEC does not pick a winner and the choice affects more than one module
- The same test has failed three times across repair attempts
- A required dependency cannot be installed or has a hard version conflict
- An external API response shape differs from what TECHNICAL_SPEC §3 or §4 documents (record the actual shape in DECISIONS.md and adapt the parser)
- Token budget is exhausted (the runtime will signal this — wrap up gracefully: write STATUS.md, commit nothing, leave the next milestone clearly named)

## Verifiable end state — the goal is complete when ALL of these hold

1. `uv tool install .` succeeds from a clean checkout
2. `yellow-sleeper --help` runs and exits 0
3. `python -m pytest tests/ -v` shows 100% pass on unit, integration, and smoke tiers
4. `ruff check src/ tests/` returns no errors
5. All six smoke-test scenarios from PRD §"Success Metrics" have a corresponding test in `tests/smoke/test_smoke_questions.py` and each passes
6. Every Pydantic model from TOOL_CONTRACTS.md §1 and §2 exists in `src/yellow_sleeper/models/` with the exact field names, types, and validators specified
7. The three cross-cutting validators from TOOL_CONTRACTS.md §3 (blocking consistency, stale explanation, blocked trade shape) are implemented and tested
8. STATUS.md final entry reads "MVP complete — all smoke tests passing, ready for human review"

## Reporting cadence

After each milestone:
- Update STATUS.md with: milestone name, files touched, validation commands run + results, what's next
- Output a one-line summary in the run log: ✅ Milestone N: [name] — [N tests passing] — next: [milestone N+1]

At final completion, generate a `HANDOFF.md` containing:
- Inventory of every file created with one-line purpose
- The exact commands a reviewer should run to verify the build
- Known gaps, deferred items, and TODOs (categorized: spec deferrals vs implementation shortcuts vs unresolved questions)
- Any spec drift discovered during the build, with pointers to DECISIONS.md