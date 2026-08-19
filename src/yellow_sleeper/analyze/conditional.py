"""Detect conditional / OR / swap trade language and refuse to resolve it."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ..models import AssetResolution, Candidate, FlagSeverity, FlagType, PolicyFlag
from ..resolve import resolve_player

_CONDITIONAL_RE = re.compile(
    r"\b(or|swap|if|unless|only if|conditional|contingent)\b",
    re.IGNORECASE,
)
_OR_SPLIT_RE = re.compile(r"\s+or\s+", re.IGNORECASE)


def is_conditional_or_swap(text: str) -> bool:
    return bool(_CONDITIONAL_RE.search(text or ""))


def inspect_trade_assets(assets: list[str]) -> list[str]:
    return [asset for asset in assets if is_conditional_or_swap(asset)]


def unresolved_or_resolution(
    asset: str,
    *,
    side: str,
    players: Mapping[str, Any],
) -> AssetResolution:
    del side
    parts = [part.strip() for part in _OR_SPLIT_RE.split(asset) if part.strip()]
    candidates: list[Candidate] = []
    for part in parts:
        if is_conditional_or_swap(part) and part.lower() == asset.lower():
            continue
        resolution = resolve_player(part, players)
        if resolution.resolved_id:
            candidates.append(
                Candidate(
                    sleeper_id=resolution.resolved_id,
                    name=part,
                    match_confidence=resolution.match_confidence,
                )
            )
        else:
            candidates.extend(resolution.candidates[: 5 - len(candidates)])
        if len(candidates) >= 5:
            break
    return AssetResolution(
        input=asset,
        asset_type="player",
        resolved_id=None,
        match_confidence=0,
        candidates=candidates[:5],
        manual_review=True,
    )


def conditional_flag(asset: str) -> PolicyFlag:
    clipped = asset if len(asset) <= 100 else asset[:97] + "..."
    return PolicyFlag(
        type=FlagType.CONDITIONAL_OR_SWAP_TRADE,
        asset=clipped,
        rule_source="computed",
        severity=FlagSeverity.WARNING,
        reason=(
            "Conditional, swap, or OR packages are not auto-resolved. "
            "Name one player or pick per slot."
        ),
    )
