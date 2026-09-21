from __future__ import annotations

import re

CONDITIONAL_RE = re.compile(
    r"\b(if|unless|when|whenever|conditional)\b",
    re.IGNORECASE,
)
SWAP_RE = re.compile(r"\b(pick\s*swap|swap)\b", re.IGNORECASE)
OR_SPLIT_RE = re.compile(r"\s+\bor\b\s+", re.IGNORECASE)
_ORDINAL_PLURAL_RE = re.compile(r"\b(1st|2nd|3rd|4th|5th)s\b", re.IGNORECASE)


def is_conditional(asset: str) -> bool:
    return bool(CONDITIONAL_RE.search(asset))


def is_swap(asset: str) -> bool:
    return bool(SWAP_RE.search(asset))


def or_choice_parts(asset: str) -> list[str]:
    parts = [part.strip() for part in OR_SPLIT_RE.split(asset) if part.strip()]
    if len(parts) >= 2:
        return parts
    return []


def is_or_choice(asset: str) -> bool:
    return bool(or_choice_parts(asset))


def is_open_ended_asset(asset: str) -> bool:
    return is_conditional(asset) or is_swap(asset) or is_or_choice(asset)


def is_open_ended_trade(assets: list[str]) -> bool:
    return any(is_open_ended_asset(asset) for asset in assets)


def strip_conditional_clause(asset: str) -> str:
    """Return the base asset name with trailing if/unless/when clauses removed."""
    base = CONDITIONAL_RE.split(asset, maxsplit=1)[0].strip()
    base = re.sub(r"[\s(\[{]+$", "", base).strip()
    return base or asset


def normalize_trade_asset(asset: str) -> str:
    """Strip conditional/swap phrasing so the remaining token can resolve."""
    text = strip_conditional_clause(asset)
    text = SWAP_RE.sub(" ", text)
    text = _ORDINAL_PLURAL_RE.sub(r"\1", text)
    text = " ".join(text.split())
    return text or asset
