# Yellow Sleeper MCP MVP Decisions

## 2026-05-11 — Smoke Scenario Source

Decision: implement six smoke tests from the canonical behaviors implied by `TOOL_CONTRACTS.md` and `TECHNICAL_SPEC.md` because `PRD.md` v0.4.4 does not contain a section literally named `Success Metrics`.

Alternatives considered: pause for human clarification; create no smoke tests until the PRD is amended; use the examples embedded in `TOOL_CONTRACTS.md` plus the smoke example in `TECHNICAL_SPEC.md`.

Why this one: `goal.md` says the three source documents are frozen and to proceed with documented behavior while recording drift. The contracts/spec define enough canonical scenarios to build the required smoke suite.

## 2026-05-11 — MVP Pick Value Table

Decision: use an internal static MVP pick table by round: R1=3000, R2=1200, R3=600, R4=300, R5=100.

Alternatives considered: leave picks valueless; add YAML configuration; add an external dynasty pick-value source.

Why this one: the PRD names static table/config as the MVP pick-value source, while Stage 2 defers richer overlays. A small internal table keeps trade math complete for fixtures without adding a dependency or undocumented API.

## 2026-08-20 — FantasyCalc TEP Parameter Exists

Decision: treat FantasyCalc query param `tep=te+` as the Stage 2 mapping for this league’s **0.5 TEP** (KTC TE+ guidance). Do **not** send `tep=0.5` (live probe → HTTP 404). Prefer API TEP over inventing a local TE multiplier, unless config later opts into an α-blend.

Alternatives considered: keep MVP non-TEP forever; apply a hard-coded ~15% TE multiplier locally; use `te++`; wait for a continuous TEP float that does not exist on the API.

Why this one: live probes of `api.fantasycalc.com` on 2026-08-20 confirmed `tep=te+` / `te++` (~15% / ~29% TE uplift, non-TEs unchanged). This supersedes `TECHNICAL_SPEC.md` §4’s claim that no `tep` parameter exists. Full write-up: `docs/research/accurate-stage-2-value-modeling.md`. Execution plan: `STAGE2_PLAN.md`.

## 2026-08-20 — Stage 2 Accuracy Build Order

Decision: Stage 2 accuracy work order is (1) FantasyCalc `tep=te+`, (2) FantasyCalc pick ladder replacing the static round table as primary, (3) sleeper_id-keyed xlsx/csv overlay with `source_disagreement`, (4) conditional/pick-swap scenario ranges. Deprioritize multi-user/HTTP/Docker/OAuth/notifications for this goal.

Alternatives considered: xlsx-first; pick-swap parsing first; hybrid Stats Guy / DynastyProcess as primary value source.

Why this one: research ranked TE format mismatch and static pick tables as the largest accuracy gaps for 14-team SF 0.5 TEP; FantasyCalc already returns both TEP-adjusted players and pick rows.

## 2026-08-26 — Stage 2 replacement stack; frozen ValueMath; 25% disagreement

Decision: implement Stage 2 as four Graphite PRs from `main`. Treat PR #15 as reference only (do not merge). Keep `schema_version="1.0"` and the public `ValueMath` field set (`send_total`, `receive_total`, `delta`, `delta_pct`, `per_asset`, `source_disagreement`). Scenario ranges go in `per_asset` dicts. Contract disagreement is strictly `>25%`; overlay precedence (`overlay_wins` / `fc_wins` / `blend`) selects the displayed value. Physical overlay format is CSV; contract source label stays `xlsx`.

Alternatives considered: merge PR #15; add `delta_min`/`delta_max`; use a 10% disagreement threshold; infer pick bands from Sleeper `roster_id`.

Why this one: PR #15 bundled the four milestones and added public range fields plus a 10% threshold that contradict TOOL_CONTRACTS.md. A replacement stack keeps each milestone independently green and schema-stable.
