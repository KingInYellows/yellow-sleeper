from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from typing import Any

from ..clients.fantasycalc import PICK_TABLE_EXPLANATION, FCRecord, TepTier, tep_source_explanation
from ..models import SourceDisagreement, ValueSourceBreakdown

PICK_VALUE_BY_ROUND = {
    1: 3000.0,
    2: 1200.0,
    3: 600.0,
    4: 300.0,
    5: 100.0,
}

CONTRACT_DISAGREEMENT_PCT = 25.0


def parse_value_records(records: Iterable[FCRecord | Mapping[str, Any]]) -> list[FCRecord]:
    return [
        record if isinstance(record, FCRecord) else FCRecord.model_validate(record)
        for record in records
    ]


def values_by_sleeper_id(records: Iterable[FCRecord | Mapping[str, Any]]) -> dict[str, FCRecord]:
    parsed = parse_value_records(records)
    return {
        record.player.sleeperId: record
        for record in parsed
        if record.player.sleeperId and record.player.position != "PICK"
    }


def value_source(
    source: str,
    value: float | None,
    *,
    timestamp: datetime | None = None,
    enabled: bool = True,
) -> ValueSourceBreakdown:
    return ValueSourceBreakdown(
        source=source,  # type: ignore[arg-type]
        value=value,
        timestamp=timestamp or datetime.now(UTC),
        enabled=enabled,
    )


def player_value_source(
    sleeper_id: str,
    value_index: dict[str, FCRecord],
    *,
    timestamp: datetime | None = None,
) -> ValueSourceBreakdown:
    record = value_index.get(sleeper_id)
    return value_source(
        "fantasycalc",
        record.value if record is not None else None,
        timestamp=timestamp,
        enabled=True,
    )


def pick_value_source(
    round_number: int,
    *,
    timestamp: datetime | None = None,
) -> ValueSourceBreakdown:
    return value_source(
        "config_pick_table",
        PICK_VALUE_BY_ROUND.get(round_number),
        timestamp=timestamp,
        enabled=True,
    )


def source_disagreement(
    sources: list[ValueSourceBreakdown],
    *,
    threshold_pct: float = CONTRACT_DISAGREEMENT_PCT,
) -> SourceDisagreement | None:
    enabled_values = [source for source in sources if source.enabled and source.value is not None]
    if len(enabled_values) < 2:
        return None
    values = [float(source.value) for source in enabled_values]
    low = min(values)
    high = max(values)
    if low <= 0:
        return None
    spread = (high - low) / low * 100
    if spread <= threshold_pct:
        return None
    return SourceDisagreement(max_delta_pct=round(spread, 2), sources=enabled_values)


def valuation_explanation(
    tep_tier: TepTier,
    *,
    league_format: str | None = None,
    cache_error: str | None = None,
) -> str:
    parts = [tep_source_explanation(tep_tier, league_format=league_format), PICK_TABLE_EXPLANATION]
    if cache_error:
        parts.insert(0, cache_error)
    return " ".join(parts)
