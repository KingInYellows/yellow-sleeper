from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

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

OverlayStatus = Literal["disabled", "loaded", "missing", "error"]

XLSX_OVERLAY_NOTE = (
    "Local CSV overlay (contract source name xlsx); overlay wins over FantasyCalc "
    "when configured."
)


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


@dataclass(frozen=True)
class OverlayResult:
    """Local CSV overlay keyed by Sleeper player id (contract source name xlsx)."""

    status: OverlayStatus
    values: dict[str, float] = field(default_factory=dict)
    path: Path | None = None
    message: str | None = None

    @property
    def active(self) -> bool:
        return self.status == "loaded"


DISABLED_OVERLAY = OverlayResult(status="disabled")


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


def load_overlay_values(path: Path | None) -> OverlayResult:
    """Load a sleeper_id,value CSV overlay.

    Missing/unreadable configured paths are explicit statuses, not an empty
    map silently labeled as overlay. Unset path stays disabled.
    Re-implements the reviewed CSV overlay idea from PR #15 with attribution.
    """
    if path is None:
        return OverlayResult(status="disabled")
    overlay_path = Path(path)
    if not overlay_path.is_file():
        return OverlayResult(
            status="missing",
            path=overlay_path,
            message=(
                f"Configured CSV overlay path does not exist: {overlay_path}. "
                "FantasyCalc was not labeled as overlay."
            ),
        )
    try:
        values: dict[str, float] = {}
        with overlay_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                sleeper_id = (row.get("sleeper_id") or "").strip()
                raw_value = (row.get("value") or "").strip()
                if not sleeper_id or not raw_value:
                    continue
                try:
                    values[sleeper_id] = float(raw_value)
                except ValueError:
                    continue
        return OverlayResult(status="loaded", values=values, path=overlay_path)
    except OSError as exc:
        return OverlayResult(
            status="error",
            path=overlay_path,
            message=(
                f"Configured CSV overlay could not be read: {overlay_path} ({exc}). "
                "FantasyCalc was not labeled as overlay."
            ),
        )


def overlay_status_explanation(overlay: OverlayResult) -> str | None:
    status = overlay.status
    if status == "disabled":
        return None
    if status == "loaded":
        count = len(overlay.values)
        return (
            f"CSV overlay active for {count} sleeper_id(s) "
            "(contract source name xlsx); overlay wins over FantasyCalc."
        )
    if status == "missing" or status == "error":
        return overlay.message
    never: OverlayStatus = status
    raise RuntimeError(f"unhandled overlay status: {never}")


def merge_player_value(
    sleeper_id: str,
    value_index: dict[str, FCRecord],
    overlay: OverlayResult | Mapping[str, float],
    *,
    valuation_source: str = "auto",
    timestamp: datetime | None = None,
    disagreement_pct: float = CONTRACT_DISAGREEMENT_PCT,
) -> tuple[float | None, list[ValueSourceBreakdown], SourceDisagreement | None, list[str]]:
    """Merge FantasyCalc and CSV overlay for one player.

    Contract source name ``xlsx`` means the local overlay file (CSV). Overlay
    wins when both sources have a number. Re-implements the reviewed merge
    from PR #15 with attribution; blend/fc_wins are not implemented.
    """
    now = timestamp or datetime.now(UTC)
    overlay_state = (
        overlay
        if isinstance(overlay, OverlayResult)
        else OverlayResult(status="loaded", values=dict(overlay))
    )
    overlay_map = dict(overlay_state.values)
    fc_enabled = valuation_source != "xlsx"
    overlay_requested = valuation_source != "fantasycalc"
    overlay_usable = overlay_requested and overlay_state.status == "loaded"
    overlay_failed = overlay_requested and overlay_state.status in {"missing", "error"}

    sources: list[ValueSourceBreakdown] = []
    missing: list[str] = []

    fc_value = None
    if fc_enabled:
        fc_source = player_value_source(sleeper_id, value_index, timestamp=now)
        sources.append(fc_source)
        fc_value = fc_source.value
        if fc_value is None:
            missing.append("fantasycalc")

    overlay_value = None
    if overlay_usable:
        if sleeper_id in overlay_map:
            overlay_value = float(overlay_map[sleeper_id])
            sources.append(value_source("xlsx", overlay_value, timestamp=now, enabled=True))
        else:
            sources.append(value_source("xlsx", None, timestamp=now, enabled=True))
            if valuation_source == "xlsx":
                missing.append("xlsx")
    elif overlay_failed or valuation_source == "xlsx":
        sources.append(value_source("xlsx", None, timestamp=now, enabled=False))
        if valuation_source == "xlsx":
            missing.append("xlsx")

    disagreement = source_disagreement(sources, threshold_pct=disagreement_pct)

    if valuation_source == "xlsx":
        chosen = overlay_value
    elif valuation_source == "fantasycalc" or overlay_value is None:
        chosen = fc_value
    else:
        chosen = overlay_value

    return chosen, sources, disagreement, missing


def chosen_value_source(
    chosen: float | None,
    sources: list[ValueSourceBreakdown],
) -> str:
    """Name the source that supplied the chosen number."""
    if chosen is None:
        for source in sources:
            if source.enabled:
                return source.source
        return sources[0].source if sources else "fantasycalc"
    matching = [
        source
        for source in sources
        if source.enabled and source.value is not None and float(source.value) == float(chosen)
    ]
    for source in matching:
        if source.source == "xlsx":
            return "xlsx"
    if matching:
        return matching[0].source
    return sources[0].source if sources else "fantasycalc"
