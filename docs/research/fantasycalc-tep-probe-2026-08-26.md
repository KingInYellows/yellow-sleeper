# FantasyCalc live probe (sanitized)

**Date:** 2026-08-26  
**Method:** `curl` against `api.fantasycalc.com` (not used in automated tests).  
**Note:** `tep=te+` must be sent as `tep=te%2B`. A raw `+` in some URL encoders is treated as a space and 404s.

## Requests

| Query | HTTP | Assets | `position=PICK` rows |
| --- | --- | --- | --- |
| `isDynasty=true&numQbs=2&numTeams=14&ppr=1` | 200 | 475 | 76 |
| same + `tep=te+` | 200 | 475 | 76 |

## Representative values

| Player | Position | Base value | `tep=te+` value |
| --- | --- | --- | --- |
| Brock Bowers | TE | 7700 (overall #8) | 8847 (overall #6), ~1.149× |
| Drake London | WR | 5472 | 5472 (unchanged) |

No full payload is committed. This confirms the 2026-08-20 finding: discrete `tep=te+` lifts TEs and leaves non-TEs unchanged; dynasty SF 14 already returns pick rows.
