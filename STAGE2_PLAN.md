# Yellow Sleeper Stage 2 Plan — Value Accuracy

**Date:** 2026-08-20  
**Research:** `docs/research/accurate-stage-2-value-modeling.md`  
**Goal:** Make dynasty trade/player values accurate for this league (**14-team SF PPR 0.5 TEP**). Packaging, multi-user, HTTP, Docker, OAuth, and live notifications stay deferred.

Source of truth for *what* to build remains `PRD.md` / `TOOL_CONTRACTS.md` / `TECHNICAL_SPEC.md`. Spec drift found in research is recorded in `DECISIONS.md` and should be reconciled in `TECHNICAL_SPEC.md` §4 before or during Milestone S2-1.

---

## Priority order (accuracy impact)

| # | Milestone | Outcome | Why first |
| --- | --- | --- | --- |
| 1 | **S2-1 FantasyCalc TEP** | Call values with `tep=te+` | Live API already supports it; ~15% TE uplift; matches KTC TE+ for +.5 PPR |
| 2 | **S2-2 FantasyCalc pick ladder** | Replace static round table with FC early/mid/late + slot picks | Largest remaining blind spot for SF 14-team capital |
| 3 | **S2-3 xlsx overlay** | Optional human sheet, `sleeper_id` keyed, activates `source_disagreement` | House values / overrides; contracts already reserve `xlsx` |
| 4 | **S2-4 conditionals / pick-swaps** | Scenario ranges beyond UNRESOLVED | Lower frequency than TE/pick mispricing |

Explicitly **out of Stage 2 accuracy scope:** multi-user, public HTTP, Docker, OAuth, live Sleeper notifications.

---

## Milestone S2-1: FantasyCalc `tep=te+`

### Spec / decision work
- Update `TECHNICAL_SPEC.md` §4: document `tep` values `te+` / `te++`; map league **0.5 TEP → `te+`**; note `tep=0.5` returns 404.
- Record decision (done in `DECISIONS.md`): TECHNICAL_SPEC’s “no tep parameter” claim is superseded by 2026-08-20 live probes.

### Implementation
- Extend `FantasyCalcClient.QUERY_PARAMS` with `"tep": "te+"` (config-driven preferred: `tep_tier: off | te+ | te++`).
- Emit `source_notes` that values are FantasyCalc **TE+** (0.5 TEP approximation), not a continuous 0.5 float.
- Optional later: α-blend between base and `te+` for “light TEP” leagues — **not** required for S2-1.

### Tests
- Unit: param builder includes `tep=te+` for default league format.
- Integration (respx): fixture variant with TE uplift vs no-tep fixture; non-TE values unchanged.
- Smoke: elite TE ranks higher under TEP fixture than base (relative assertion).

### Validation
```bash
uv run --extra dev ruff check src/ tests/
uv run --extra dev python -m pytest tests/unit/ tests/integration/ tests/smoke/ -q
```

### Stop-and-fix
Do not start S2-2 while FantasyCalc client still omits `tep` or docs still claim TEP is impossible.

---

## Milestone S2-2: FantasyCalc pick ladder

### Implementation
- Index FantasyCalc rows with `position=PICK` (and/or synthetic ids `FP_*` / `DP_*` per go-fantasycalc).
- Map Yellow pick tokens (season, round, early/mid/late, slot when known) → FC pick values.
- Fallback chain: FC pick match → existing `PICK_VALUE_BY_ROUND` static table → `missing_value`.
- Source label: prefer extending contracts carefully; until contract amend, use `fantasycalc` for pick rows and keep `config_pick_table` as fallback only.

### Tests
- Mapper unit tests for early/mid/late 1sts and current-year slot picks.
- Trade smoke: 1st-for-1st swap uses differentiated early vs late values when fixtures include them.

### Stop-and-fix
Do not remove the static table until mapper coverage + smoke pass.

---

## Milestone S2-3: xlsx value overlay

### Schema (minimal)
| Column | Required | Notes |
| --- | --- | --- |
| `sleeper_id` | yes | Primary key |
| `value` | yes | Numeric |
| `name`, `position`, `notes`, `as_of` | no | Diagnostics only |

Config: path to csv, enable flag, precedence `overlay_wins | blend | fc_wins` (default `overlay_wins`). Contract `source_disagreement` remains strictly `>25%`. Precedence alone selects the displayed value.

### Merge
1. FantasyCalc (+TEP) base.  
2. Overlay by `sleeper_id`.  
3. Apply precedence to the displayed value. Populate `source_disagreement` only when enabled sources differ by **>25%**.  
4. Never key solely on display name.

### Tests
- Overlay wins / FC wins / disagreement emission.
- Missing sleeper_id rows ignored with note.

### Dependencies
Add an explicit spreadsheet library only if needed; prefer CSV first to avoid heavy deps (record in `DECISIONS.md` if CSV-only).

---

## Milestone S2-4: Conditional / pick-swap scenarios

- Represent conditionals as scenario bundles (base + if_true / if_false), not a single net.
- Outputs: `conditional_or_swap_trade` flag, `data_status=PARTIAL`, and min/max on existing `per_asset` dicts. Do **not** add public `delta_min` / `delta_max` fields. Expected value only when the user supplied an explicit probability.
- **No** Sleeper write actions. Schema stays `1.0`.
- Defer until S2-1–S2-3 are live and trusted.

---

## Target architecture (end of Stage 2 accuracy)

```text
FantasyCalc (SF 14 PPR + tep=te+)
    → player values + pick ladder
    → optional xlsx/csv overlay (sleeper_id)
    → source_disagreement when peers diverge
    → trade tools remain facts/flags only (no verdicts)
```

Precedence (hybrid end-state): `xlsx > fantasycalc(+tep) > config_pick_table`.

---

## Non-goals this stage

- Perfect continuous 0.5 vs 1.0 TEP interpolation (API has discrete tiers only).
- Replacing FantasyCalc with KeepTradeCut (no official API; name-match pain).
- Shipping Docker / OAuth / multi-user “because Stage 2.”

---

## Suggested first PR

**S2-1 only:** config + `tep=te+` + fixture updates + TECHNICAL_SPEC §4 / DECISIONS note. Small, high accuracy ROI, low risk.
