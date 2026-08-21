# Yellow Sleeper Stage 2 Plan — Value Accuracy

**Date:** 2026-08-20  
**Research:** `docs/research/accurate-stage-2-value-modeling.md`  
**Goal:** Make dynasty trade/player values accurate for this league (**14-team SF PPR 0.5 TEP**).

## Priority order

1. **S2-1** FantasyCalc `tep=te+`
2. **S2-2** FantasyCalc pick ladder (static table fallback)
3. **S2-3** CSV overlay (`source=xlsx`) + `source_disagreement`
4. **S2-4** Conditional / pick-swap scenario ranges (`delta_min`/`delta_max`)

Deferred: multi-user, HTTP, Docker, OAuth, live notifications.
