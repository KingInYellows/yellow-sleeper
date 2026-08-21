from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from ..clients.fantasycalc import FCRecord
from ..models import Pick, SourceDisagreement, ValueSourceBreakdown

PICK_VALUE_BY_ROUND = {
    1: 3000.0,
    2: 1200.0,
    3: 600.0,
    4: 300.0,
    5: 100.0,
}

_ROUND_ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th"}
PickBand = Literal["Early", "Mid", "Late"]


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


def roster_pick_band(original_owner_roster_id: int, *, num_teams: int = 14) -> PickBand:
    """Map original owner roster id into early/mid/late terciles for num_teams."""
    slot = max(1, min(int(original_owner_roster_id), num_teams))
    third = max(1, num_teams // 3)
    if slot <= third:
        return "Early"
    if slot <= 2 * third:
        return "Mid"
    return "Late"


def match_fantasycalc_pick(
    pick: Pick,
    pick_index: Mapping[str, FCRecord],
    *,
    num_teams: int = 14,
) -> FCRecord | None:
    """Resolve a Yellow pick to a FantasyCalc PICK row by name conventions."""
    ordinal = _ROUND_ORDINAL.get(pick.round)
    if ordinal is None:
        return None
    band = roster_pick_band(pick.original_owner_roster_id, num_teams=num_teams)
    candidates = [
        f"{pick.season} {ordinal} ({band})",
        f"{pick.season} {ordinal}",
    ]
    for name in candidates:
        record = pick_index.get(name.lower())
        if record is not None:
            return record
    return None


def pick_value_source(
    round_number: int,
    *,
    pick: Pick | None = None,
    pick_index: Mapping[str, FCRecord] | None = None,
    timestamp: datetime | None = None,
) -> ValueSourceBreakdown:
    if pick is not None and pick_index:
        matched = match_fantasycalc_pick(pick, pick_index)
        if matched is not None:
            return value_source(
                "fantasycalc",
                matched.value,
                timestamp=timestamp,
                enabled=True,
            )
    return value_source(
        "config_pick_table",
        PICK_VALUE_BY_ROUND.get(round_number),
        timestamp=timestamp,
        enabled=True,
    )


def pick_value_range(
    pick: Pick,
    pick_index: Mapping[str, FCRecord],
) -> tuple[float | None, float | None, float | None]:
    """Return (point, min, max) using early/mid/late FC ladder when available."""
    ordinal = _ROUND_ORDINAL.get(pick.round)
    if ordinal is None:
        fallback = PICK_VALUE_BY_ROUND.get(pick.round)
        return fallback, fallback, fallback
    band_values: list[float] = []
    for band in ("Early", "Mid", "Late"):
        record = pick_index.get(f"{pick.season} {ordinal} ({band})".lower())
        if record is not None:
            band_values.append(float(record.value))
    generic = pick_index.get(f"{pick.season} {ordinal}".lower())
    matched = match_fantasycalc_pick(pick, pick_index)
    point = float(matched.value) if matched is not None else (
        float(generic.value) if generic is not None else PICK_VALUE_BY_ROUND.get(pick.round)
    )
    if band_values:
        return point, min(band_values), max(band_values)
    return point, point, point


def source_disagreement(
    sources: list[ValueSourceBreakdown],
    *,
    threshold_pct: float = 25.0,
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


def load_overlay_values(path: Path | None) -> dict[str, float]:
    """Load sleeper_id,value CSV overlay. Missing/invalid path → empty map."""
    if path is None:
        return {}
    overlay_path = Path(path)
    if not overlay_path.exists():
        return {}
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
    return values


def merge_player_value(
    sleeper_id: str,
    value_index: dict[str, FCRecord],
    overlay: Mapping[str, float],
    *,
    valuation_source: str = "auto",
    overlay_precedence: Literal["overlay_wins", "blend", "fc_wins"] = "overlay_wins",
    disagreement_pct: float = 10.0,
    timestamp: datetime | None = None,
) -> tuple[float | None, list[ValueSourceBreakdown], SourceDisagreement | None, list[str]]:
    """Merge FantasyCalc + CSV overlay for one player.

    Contract source name ``xlsx`` means the local overlay file (CSV in Stage 2).
    """
    now = timestamp or datetime.now(UTC)
    fc_enabled = valuation_source != "xlsx"
    overlay_enabled = valuation_source != "fantasycalc"
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
    if overlay_enabled:
        if sleeper_id in overlay:
            overlay_value = float(overlay[sleeper_id])
            sources.append(value_source("xlsx", overlay_value, timestamp=now, enabled=True))
        else:
            sources.append(value_source("xlsx", None, timestamp=now, enabled=overlay_enabled))
            if valuation_source == "xlsx":
                missing.append("xlsx")

    disagreement = source_disagreement(sources, threshold_pct=disagreement_pct)

    if valuation_source == "xlsx":
        chosen = overlay_value
    elif valuation_source == "fantasycalc":
        chosen = fc_value
    elif overlay_value is None:
        chosen = fc_value
    elif fc_value is None:
        chosen = overlay_value
    elif overlay_precedence == "fc_wins":
        chosen = fc_value
    elif overlay_precedence == "blend":
        chosen = (fc_value + overlay_value) / 2.0
    else:
        chosen = overlay_value

    if chosen is None and "fantasycalc" not in missing and fc_enabled:
        missing.append("fantasycalc")
    if chosen is None and valuation_source == "xlsx" and "xlsx" not in missing:
        missing.append("xlsx")

    return chosen, sources, disagreement, missing
