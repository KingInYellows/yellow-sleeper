"""Value overlay: TEP-adjusted FantasyCalc book, then user xlsx rows win."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from ..clients.fantasycalc import FCRecord
from ..models import ValueSourceBreakdown
from .tep import apply_te_premium
from .value import parse_value_records, value_source

UserBook = Mapping[str, Any]


@dataclass
class OverlayBook:
    display: dict[str, float] = field(default_factory=dict)
    raw_fc: dict[str, float] = field(default_factory=dict)
    user_ids: set[str] = field(default_factory=set)
    positions: dict[str, str] = field(default_factory=dict)

    def sources_for(self, sleeper_id: str) -> list[ValueSourceBreakdown]:
        sid = str(sleeper_id)
        sources: list[ValueSourceBreakdown] = []
        book = self.display.get(sid)
        raw = self.raw_fc.get(sid)
        if book is not None:
            sources.append(value_source("xlsx", book))
        if raw is not None:
            sources.append(value_source("fantasycalc", raw))
        return sources

    def display_value(self, sleeper_id: str) -> float | None:
        return self.display.get(str(sleeper_id))


def build_overlay(
    values: Iterable[FCRecord | Mapping[str, Any]],
    players: Mapping[str, Any],
    *,
    tep: float,
    user_book: UserBook | None = None,
) -> OverlayBook:
    book = OverlayBook()
    for record in parse_value_records(values):
        sid = record.player.sleeperId
        if not sid:
            continue
        sid = str(sid)
        raw = players.get(sid)
        position = record.player.position
        if isinstance(raw, Mapping) and raw.get("position"):
            position = str(raw.get("position"))
        book.raw_fc[sid] = float(record.value)
        book.positions[sid] = position or ""
        adjusted = apply_te_premium(record.value, position, tep)
        if adjusted is not None:
            book.display[sid] = round(adjusted, 2)
    if user_book:
        for sid, row in user_book.items():
            value = _row_value(row)
            if value is None:
                continue
            key = str(sid)
            book.display[key] = float(value)
            book.user_ids.add(key)
            position = _row_position(row)
            if position:
                book.positions[key] = position
    return book


def apply_display_values(
    overlay: OverlayBook,
    sleeper_id: str,
    fallback: float | None = None,
) -> float | None:
    book = overlay.display_value(sleeper_id)
    if book is not None:
        return book
    return fallback


def _row_value(row: Any) -> float | None:
    if row is None:
        return None
    if isinstance(row, (int, float)):
        return float(row)
    if isinstance(row, Mapping):
        raw = row.get("value")
        if raw is None:
            return None
        return float(raw)
    value = getattr(row, "value", None)
    return None if value is None else float(value)


def _row_position(row: Any) -> str:
    if isinstance(row, Mapping):
        return str(row.get("position") or "")
    return str(getattr(row, "position", "") or "")
