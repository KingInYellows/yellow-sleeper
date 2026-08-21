# Accurate Stage 2 Value Modeling for Yellow Sleeper MCP

**Date:** 2026-08-20 **Sources:** FantasyCalc live API probe, go-fantasycalc, KeepTradeCut, DynastyProcess, Exa/Tavily/GitHub

## Summary

FantasyCalc accepts discrete `tep=te+` / `te++` (not `tep=0.5`). For 14-team SF PPR **0.5 TEP**, use `tep=te+`. Dynasty responses include pick ladder rows. Prefer FC picks over static round tables; CSV overlay activates `source_disagreement`.

## Recommended build order

1. FantasyCalc `tep=te+`
2. FantasyCalc pick ladder
3. sleeper_id CSV overlay
4. Conditional / pick-swap scenario ranges

Full synthesis captured during Stage 2 planning; see `STAGE2_PLAN.md` and `DECISIONS.md`.
