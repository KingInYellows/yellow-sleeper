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

Decision: default FantasyCalc requests use `tep=te+` for this league’s **0.5 TEP**. Config `tep_tier` supports `off` | `te+` | `te++`. Never send `tep=0.5` (API 404). Empty `tep=` is also invalid — omit the key when off.

Alternatives considered: keep non-TEP forever; hard-code a local ~15% TE multiplier; use `te++`.

Why this one: live probes confirmed discrete TE+ / TE++ tiers; KTC maps +.5 PPR TEP to TE+. See `docs/research/accurate-stage-2-value-modeling.md`.

## 2026-08-20 — Stage 2 Accuracy Build Order

Decision: implement accuracy work as (1) FantasyCalc TEP, (2) FantasyCalc pick ladder with static fallback, (3) sleeper_id CSV overlay under contract source name `xlsx`, (4) conditional/pick-swap scenario ranges via `delta_min`/`delta_max` + `CONDITIONAL_OR_SWAP_TRADE` flag.

Alternatives considered: xlsx-first; pick-swap first; add openpyxl.

Why this one: research ranked TE format mismatch and static picks as the largest accuracy gaps; CSV avoids a new heavy dependency while satisfying the existing `xlsx` source literal.
