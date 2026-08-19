"""Tight-end premium applied on top of raw FantasyCalc values.

FantasyCalc's public values API does not accept a TEP query parameter (it 404s).
Stage 2 therefore computes a local book: TE values are multiplied by
``1 + tep * 0.35``. Mifflin Doty is 0.5 TEP, so TEs display at 1.175x.
"""

from __future__ import annotations

TE_PREMIUM_PER_POINT = 0.35


def te_multiplier(tep: float) -> float:
    return 1.0 + float(tep) * TE_PREMIUM_PER_POINT


def apply_te_premium(value: float | None, position: str | None, tep: float) -> float | None:
    if value is None:
        return None
    if (position or "").upper() != "TE":
        return float(value)
    return float(value) * te_multiplier(tep)


def tep_explanation(tep: float) -> str:
    mult = te_multiplier(tep)
    return (
        f"TE values multiplied by {mult:.3f} "
        f"(1 + {tep:g}*{TE_PREMIUM_PER_POINT:g}); FantasyCalc has no TEP param."
    )
