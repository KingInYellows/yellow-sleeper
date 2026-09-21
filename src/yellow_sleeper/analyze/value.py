from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ..clients.fantasycalc import (
    PICK_PROVIDER_EXPLANATION,
    PICK_TABLE_EXPLANATION,
    FCRecord,
    TepTier,
    tep_source_explanation,
)
from ..models import Pick, SourceDisagreement, ValueSourceBreakdown

PICK_VALUE_BY_ROUND = {
    1: 3000.0,
    2: 1200.0,
    3: 600.0,
    4: 300.0,
    5: 100.0,
}

_ROUND_ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}
_BAND_LABELS = ("Early", "Mid", "Late")

CONTRACT_DISAGREEMENT_PCT = 25.0


@dataclass(frozen=True)
class PickBandRange:
    """Low/high FantasyCalc Early/Mid/Late values for one generic pick name."""

    low: float
    high: float
    bands: tuple[tuple[str, float], ...]

    def explanation(self, pick: Pick) -> str:
        ordinal = _ROUND_ORDINAL.get(pick.round, f"R{pick.round}")
        labeled = ", ".join(f"{label}={value:g}" for label, value in self.bands)
        return (
            f"{pick.season} {ordinal} FantasyCalc band range "
            f"low={self.low:g} high={self.high:g} ({labeled}); "
            "single-number omitted (no generic row, no slot picked)."
        )


@dataclass(frozen=True)
class ResolvedPickValue:
    source: ValueSourceBreakdown
    band_range: PickBandRange | None = None


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


def pick_records(records: Iterable[FCRecord | Mapping[str, Any]]) -> list[FCRecord]:
    return [record for record in parse_value_records(records) if record.player.position == "PICK"]


def pick_records_by_name(
    records: Iterable[FCRecord | Mapping[str, Any]],
) -> dict[str, FCRecord]:
    return {record.player.name.lower(): record for record in pick_records(records)}


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


def match_fantasycalc_pick(
    pick: Pick,
    pick_index: Mapping[str, FCRecord],
) -> FCRecord | None:
    """Resolve a Yellow pick to a FantasyCalc PICK row by generic name.

    Uses only ``{season} {ordinal}`` (e.g. ``2027 1st``). Banded Early/Mid/Late
    rows are not used as a single slot. Sleeper ``roster_id`` is not a draft
    slot. Re-implements the reviewed generic-row idea from PR #15 with attribution.
    """
    ordinal = _ROUND_ORDINAL.get(pick.round)
    if ordinal is None:
        return None
    return pick_index.get(f"{pick.season} {ordinal}".lower())


def match_fantasycalc_pick_bands(
    pick: Pick,
    pick_index: Mapping[str, FCRecord],
) -> PickBandRange | None:
    """Collect Early/Mid/Late rows for a pick when no generic row is used.

    Does not select a band. Returns low/high plus the labels that exist.
    """
    ordinal = _ROUND_ORDINAL.get(pick.round)
    if ordinal is None:
        return None
    found: list[tuple[str, float]] = []
    for label in _BAND_LABELS:
        record = pick_index.get(f"{pick.season} {ordinal} ({label})".lower())
        if record is not None:
            found.append((label, record.value))
    if not found:
        return None
    values = [value for _, value in found]
    return PickBandRange(low=min(values), high=max(values), bands=tuple(found))


def resolve_pick_value(
    round_number: int,
    *,
    pick: Pick | None = None,
    pick_index: Mapping[str, FCRecord] | None = None,
    timestamp: datetime | None = None,
) -> ResolvedPickValue:
    if pick is not None and pick_index:
        matched = match_fantasycalc_pick(pick, pick_index)
        if matched is not None:
            return ResolvedPickValue(
                source=value_source(
                    "fantasycalc",
                    matched.value,
                    timestamp=timestamp,
                    enabled=True,
                )
            )
        bands = match_fantasycalc_pick_bands(pick, pick_index)
        if bands is not None:
            return ResolvedPickValue(
                source=value_source(
                    "fantasycalc",
                    None,
                    timestamp=timestamp,
                    enabled=True,
                ),
                band_range=bands,
            )
    return ResolvedPickValue(
        source=value_source(
            "config_pick_table",
            PICK_VALUE_BY_ROUND.get(round_number),
            timestamp=timestamp,
            enabled=True,
        )
    )


def pick_value_source(
    round_number: int,
    *,
    pick: Pick | None = None,
    pick_index: Mapping[str, FCRecord] | None = None,
    timestamp: datetime | None = None,
) -> ValueSourceBreakdown:
    return resolve_pick_value(
        round_number, pick=pick, pick_index=pick_index, timestamp=timestamp
    ).source


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
    pick_rows_present: bool = False,
) -> str:
    parts = [tep_source_explanation(tep_tier, league_format=league_format)]
    if pick_rows_present:
        parts.append(PICK_PROVIDER_EXPLANATION)
        parts.append(PICK_TABLE_EXPLANATION)
    else:
        parts.append(
            "No FantasyCalc PICK rows matched this query; pick values use the internal "
            "static round table fallback (R1=3000, R2=1200, R3=600, R4=300, R5=100), "
            "not freshly fetched provider data."
        )
    if cache_error:
        parts.insert(0, cache_error)
    return " ".join(parts)
