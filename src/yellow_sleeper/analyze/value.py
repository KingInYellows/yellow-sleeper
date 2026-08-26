from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from ..clients.fantasycalc import FCRecord, TepTier, tep_source_explanation
from ..models import SourceDisagreement, ValueSourceBreakdown

PICK_VALUE_BY_ROUND = {
    1: 3000.0,
    2: 1200.0,
    3: 600.0,
    4: 300.0,
    5: 100.0,
}

# TOOL_CONTRACTS.md §1.6: emit source_disagreement only when spread is strictly >25%.
CONTRACT_DISAGREEMENT_PCT = 25.0
OVERLAY_NOT_CONFIGURED = "CSV overlay is not configured (contract source name xlsx)."


@dataclass(frozen=True)
class PlayerValueResolution:
    value: float | None
    sources: tuple[ValueSourceBreakdown, ...]
    disagreement: SourceDisagreement | None
    missing: tuple[str, ...]
    diagnostics: tuple[str, ...]
    effective_source: Literal["fantasycalc", "xlsx"]
    provenance_explanation: str


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


def resolve_player_value(
    sleeper_id: str,
    value_index: Mapping[str, FCRecord],
    *,
    overlay: Mapping[str, float] | None = None,
    overlay_diagnostics: tuple[str, ...] = (),
    valuation_source: str = "auto",
    overlay_precedence: str = "overlay_wins",
    tep_tier: TepTier = "te+",
    timestamp: datetime | None = None,
) -> PlayerValueResolution:
    """Shared player-value resolver used by all value-bearing tools.

    Overlay merge lands in S2-3. This stub always returns FantasyCalc for
    ``auto`` / ``fantasycalc`` and a missing overlay for ``xlsx``.
    ``overlay`` / ``overlay_precedence`` are accepted so later PRs can plug in
    without forking call sites.
    """
    del overlay, overlay_precedence
    now = timestamp or datetime.now(UTC)
    if valuation_source == "xlsx":
        diagnostics = overlay_diagnostics or (OVERLAY_NOT_CONFIGURED,)
        return PlayerValueResolution(
            value=None,
            sources=(value_source("xlsx", None, timestamp=now, enabled=False),),
            disagreement=None,
            missing=("xlsx",),
            diagnostics=diagnostics,
            effective_source="xlsx",
            provenance_explanation=diagnostics[0],
        )

    fc = player_value_source(sleeper_id, dict(value_index), timestamp=now)
    missing = () if fc.value is not None else ("fantasycalc",)
    explanation = tep_source_explanation(tep_tier)
    return PlayerValueResolution(
        value=fc.value,
        sources=(fc,),
        disagreement=None,
        missing=missing,
        diagnostics=overlay_diagnostics,
        effective_source="fantasycalc",
        provenance_explanation=explanation,
    )
