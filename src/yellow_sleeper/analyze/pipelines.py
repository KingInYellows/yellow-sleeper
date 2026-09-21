from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from statistics import mean, median
from typing import Any

from rapidfuzz import fuzz

from ..clients.fantasycalc import FCRecord, TepTier, format_looks_supported
from ..config import DynamicPolicy
from ..models import (
    TRADED_PICKS_CAP,
    AgeStats,
    AnalyzeTradeOutput,
    AssetResolution,
    BestPlayerAvailableOutput,
    BlockingRule,
    BPACandidate,
    CacheRefreshResult,
    Candidate,
    DataStatus,
    FindRosterOutput,
    FlagSeverity,
    FlagType,
    GetMyRosterOutput,
    GetPlayerValueOutput,
    GroupedRoster,
    HealthCheckOutput,
    LeaguePowerMapOutput,
    ListMyPicksOutput,
    ListTradedPicksOutput,
    Pick,
    PickContext,
    PickInventorySummary,
    PolicyFlag,
    PolicyStatus,
    PositionalDepth,
    RecentPick,
    RefreshCacheOutput,
    ResolutionStatus,
    RosterContext,
    RosterPlayer,
    SourceDisagreement,
    SourceNote,
    TeamRollup,
    ValueMath,
    ValueSourceBreakdown,
    WhatsOnTheClockOutput,
)
from ..resolve import resolve_pick_description, resolve_player, resolve_roster
from ..resolve.picks import parse_pick_description
from .roster import (
    PickInventory,
    build_pick_inventory,
    build_roster_lineup,
    current_season,
    find_roster_id_for_username,
)
from .trade_phrases import (
    is_conditional,
    is_open_ended_asset,
    is_open_ended_trade,
    is_or_choice,
    is_swap,
    normalize_trade_asset,
    or_choice_parts,
)
from .value import (
    CONTRACT_DISAGREEMENT_PCT,
    DISABLED_OVERLAY,
    XLSX_OVERLAY_NOTE,
    OverlayResult,
    OverlayStatus,
    chosen_value_source,
    merge_player_value,
    overlay_status_explanation,
    parse_value_records,
    pick_records,
    pick_records_by_name,
    player_value_source,
    resolve_pick_value,
    valuation_explanation,
    value_source,
    values_by_sleeper_id,
)

POSITIONS = ("QB", "RB", "WR", "TE")

# Cache-status sentinels — mirror SourceNote.cache_status Literal in models/shared.py.
# Use these constants at comparison sites so a typo fails at import rather than silently.
CACHE_STATUS_FRESH = "fresh"
CACHE_STATUS_CACHED = "cached"
CACHE_STATUS_STALE = "stale"


def _values_for_query(
    values: Iterable[FCRecord | Mapping[str, Any]],
    league_format: str | None,
    tep_tier: TepTier,
) -> Iterable[FCRecord | Mapping[str, Any]]:
    if league_format and not format_looks_supported(league_format, tep_tier=tep_tier):
        return []
    return values


def health_check_output(
    *,
    cache_status: dict[str, str],
    league_id: str,
    user: str,
    config_sources: list[str],
    errors: list[str] | None = None,
    live_probe_results: list[Any] | None = None,
) -> HealthCheckOutput:
    errors = errors or []
    degraded_states = {CACHE_STATUS_STALE, "missing"}
    all_unavailable = all(status in degraded_states for status in cache_status.values())
    any_partial = any(status in degraded_states for status in cache_status.values()) or errors
    if all_unavailable:
        data_status = DataStatus.UNAVAILABLE
    elif any_partial:
        data_status = DataStatus.PARTIAL
    else:
        data_status = DataStatus.COMPLETE
    flags = [
        PolicyFlag(
            type=FlagType.STALE_DATA,
            asset=key,
            rule_source="computed",
            severity=FlagSeverity.WARNING,
            reason=f"{key} cache status is {status}.",
        )
        for key, status in cache_status.items()
        if status in degraded_states
    ]
    return HealthCheckOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=data_status,
        policy_flags=flags,
        source_notes=[_source_note("league_id", "local_config")],
        config_sources=config_sources,
        status_msgs=[_health_msg(cache_status)],
        cache_status=cache_status,  # type: ignore[arg-type]
        league_id=league_id,
        user=user,
        errors=errors,
        live_probe_results=live_probe_results,
    )


def get_my_roster_output(
    *,
    snapshot: dict[str, Any],
    players: Mapping[str, Any],
    values: Iterable[FCRecord | Mapping[str, Any]],
    sleeper_username: str,
    policy: DynamicPolicy,
    config_sources: list[str],
    values_cache_status: str = "cached",
    values_cache_error: str | None = None,
    tep_tier: TepTier = "te+",
    league_format: str | None = None,
    values_timestamp: datetime | None = None,
    overlay: OverlayResult | None = None,
) -> GetMyRosterOutput:
    roster_id = find_roster_id_for_username(snapshot, sleeper_username)
    if roster_id is None:
        return GetMyRosterOutput(
            policy_status=PolicyStatus.OK,
            resolution_status=ResolutionStatus.NEEDS_CLARIFICATION,
            data_status=DataStatus.UNAVAILABLE,
            policy_flags=[
                PolicyFlag(
                    type=FlagType.AMBIGUOUS_RESOLUTION,
                    asset=sleeper_username,
                    rule_source="computed",
                    severity=FlagSeverity.WARNING,
                    reason=(
                        f"Username '{sleeper_username}' did not resolve to a roster "
                        "in the league snapshot."
                    ),
                )
            ],
            source_notes=[_source_note("grouped_roster", "sleeper")],
            config_sources=config_sources,
            grouped_roster=[],
            positional_depth=_positional_depth([]),
            age_stats=_age_stats([], []),
        )
    roster = _roster_by_id(snapshot, roster_id)
    overlay_state = overlay or DISABLED_OVERLAY
    usable_values = _values_for_query(values, league_format, tep_tier)
    value_index = values_by_sleeper_id(usable_values)
    player_ids = roster.get("players") or []
    roster_players = [
        _roster_player(
            player_id,
            players,
            value_index,
            timestamp=values_timestamp,
            overlay=overlay_state,
        )
        for player_id in player_ids
        if _player_record(str(player_id), players) is not None
    ]
    league = snapshot.get("league") or {}
    roster_positions = [str(pos) for pos in (league.get("roster_positions") or []) if pos]
    lineup = build_roster_lineup(roster, roster_positions, players)
    missing_values = [player.sleeper_id for player in roster_players if player.value is None]
    grouped = [
        GroupedRoster(
            position=position,  # type: ignore[arg-type]
            players=[player for player in roster_players if player.position == position],
        )
        for position in POSITIONS
    ]
    flags = _protected_player_flags(roster_players, policy, ".yellow-sleeper.yaml")
    flags.extend(_value_cache_flags(values_cache_status, values_cache_error))
    overlay_notes, overlay_flags = _overlay_notes_and_flags(
        overlay_state, field="grouped_roster[].value", timestamp=values_timestamp
    )
    flags.extend(overlay_flags)
    data_status = _with_stale_data_status(
        DataStatus.PARTIAL if missing_values else DataStatus.COMPLETE,
        values_cache_status,
    )
    source_notes = [
        _source_note("grouped_roster", "sleeper"),
        _source_note(
            "grouped_roster[].value",
            "fantasycalc",
            cache_status=values_cache_status,
            explanation=valuation_explanation(
                tep_tier,
                league_format=league_format,
                cache_error=values_cache_error,
                pick_rows_present=bool(pick_records(usable_values)),
            ),
            timestamp=values_timestamp,
        ),
    ]
    source_notes.extend(overlay_notes)
    return GetMyRosterOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=data_status,
        policy_flags=flags,
        source_notes=source_notes,
        config_sources=config_sources,
        grouped_roster=grouped,
        positional_depth=_positional_depth(roster_players),
        age_stats=_age_stats(roster_players, roster_players),
        missing_values=missing_values,
        starters=lineup.starters,
        reserve=lineup.reserve,
        taxi=lineup.taxi,
        player_count=lineup.player_count,
        roster_spots=lineup.roster_spots,
        over_capacity=lineup.over_capacity,
    )


def find_roster_output(search_term: str, snapshot: dict[str, Any]) -> FindRosterOutput:
    resolution = resolve_roster(search_term, snapshot["rosters"], snapshot["users"])
    needs = resolution.matched is None
    flags = []
    if needs:
        flags.append(
            PolicyFlag(
                type=FlagType.AMBIGUOUS_RESOLUTION,
                asset=search_term,
                rule_source="computed",
                severity=FlagSeverity.WARNING,
                reason=(
                    "Search term matched zero or multiple rosters under the resolver thresholds."
                ),
            )
        )
    return FindRosterOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.NEEDS_CLARIFICATION if needs else ResolutionStatus.OK,
        data_status=DataStatus.COMPLETE,
        policy_flags=flags,
        source_notes=[_source_note("alternatives" if needs else "matched", "sleeper")],
        matched=resolution.matched,
        alternatives=resolution.alternatives,
    )


def list_traded_picks_output(
    *,
    snapshot: dict[str, Any],
    my_roster_id: int,
    seasons: list[int] | None = None,
) -> ListTradedPicksOutput:
    inventory = build_pick_inventory(snapshot, my_roster_id=my_roster_id, seasons=seasons)
    all_picks = inventory.traded_picks
    truncated = len(all_picks) > TRADED_PICKS_CAP
    source_notes = [_source_note("picks", "sleeper")]
    if truncated:
        source_notes.append(
            _source_note(
                "picks",
                "sleeper",
                explanation=(
                    f"Returned {TRADED_PICKS_CAP} of {len(all_picks)} traded picks; "
                    "remainder omitted by output cap."
                ),
            )
        )
    return ListTradedPicksOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=DataStatus.PARTIAL if truncated else DataStatus.COMPLETE,
        source_notes=source_notes,
        picks=all_picks[:TRADED_PICKS_CAP],
        truncated=truncated,
        total_count=len(all_picks),
    )


def list_my_picks_output(
    *,
    snapshot: dict[str, Any],
    my_roster_id: int,
    seasons: list[int] | None = None,
    include_traded_away: bool = False,
) -> ListMyPicksOutput:
    inventory = build_pick_inventory(
        snapshot,
        my_roster_id=my_roster_id,
        seasons=seasons,
        include_traded_away=include_traded_away,
    )
    data_status = DataStatus.PARTIAL if inventory.unresolved else DataStatus.COMPLETE
    return ListMyPicksOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=data_status,
        source_notes=[_source_note("owned_picks", "sleeper")],
        owned_picks=inventory.owned_picks[:25],
        traded_away_picks=inventory.traded_away_picks[:25],
        unresolved=inventory.unresolved[:10],
    )


def get_player_value_output(
    *,
    player: str,
    players: Mapping[str, Any],
    values: Iterable[FCRecord | Mapping[str, Any]],
    valuation_source: str = "auto",
    values_cache_status: str = "cached",
    values_cache_error: str | None = None,
    tep_tier: TepTier = "te+",
    league_format: str | None = None,
    values_timestamp: datetime | None = None,
    overlay: OverlayResult | None = None,
) -> GetPlayerValueOutput:
    overlay_state = overlay or DISABLED_OVERLAY
    resolution = resolve_player(player, players)
    fantasycalc_enabled = valuation_source != "xlsx"
    usable_values = (
        _values_for_query(values, league_format, tep_tier) if fantasycalc_enabled else []
    )
    value_index = values_by_sleeper_id(usable_values) if fantasycalc_enabled else {}
    flags: list[PolicyFlag] = []
    candidates = resolution.candidates if resolution.manual_review else []
    value = None
    sources: list = []
    missing: list[str] = []
    disagreement = None
    if resolution.resolved_id:
        value, sources, disagreement, missing = merge_player_value(
            resolution.resolved_id,
            value_index,
            overlay_state,
            valuation_source=valuation_source,
            timestamp=values_timestamp,
        )
        if value is None:
            flags.append(_missing_value_flag(player))
        if disagreement is not None:
            flags.append(
                PolicyFlag(
                    type=FlagType.SOURCE_DISAGREEMENT,
                    asset=player,
                    rule_source="computed",
                    severity=FlagSeverity.INFO,
                    reason=(
                        f"Value sources disagree by {disagreement.max_delta_pct}% "
                        f"(threshold {CONTRACT_DISAGREEMENT_PCT}%)."
                    ),
                )
            )
    overlay_notes, overlay_flags = _overlay_notes_and_flags(
        overlay_state, field="value", timestamp=values_timestamp
    )
    flags.extend(overlay_flags)
    if fantasycalc_enabled:
        flags.extend(_value_cache_flags(values_cache_status, values_cache_error))
    cache_status = values_cache_status if fantasycalc_enabled else CACHE_STATUS_FRESH
    primary_source, source_note_explanation = _player_value_provenance(
        value,
        sources,
        overlay=overlay_state,
        fantasycalc_enabled=fantasycalc_enabled,
        tep_tier=tep_tier,
        league_format=league_format,
        values_cache_error=values_cache_error,
        pick_rows_present=bool(pick_records(usable_values)) if fantasycalc_enabled else False,
    )
    data_status = _with_stale_data_status(
        _value_data_status(bool(resolution.resolved_id), value is not None),
        cache_status,
    )
    source_notes = [
        _source_note(
            "value",
            primary_source,
            cache_status=cache_status,
            explanation=source_note_explanation,
            timestamp=values_timestamp,
        )
    ]
    if primary_source != "xlsx":
        source_notes.extend(overlay_notes)
    return GetPlayerValueOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=_resolution_status([resolution]),
        data_status=data_status,
        policy_flags=flags,
        source_notes=source_notes,
        sleeper_id=resolution.resolved_id,
        name=_resolved_player_name(resolution.resolved_id, players),
        value=value,
        value_sources=sources,
        source_disagreement=disagreement,
        missing_values=missing,
        candidates=candidates,
    )


def analyze_trade_pipeline(
    *,
    my_send: list[str],
    my_receive: list[str],
    policy: DynamicPolicy,
    snapshot: dict[str, Any],
    players: Mapping[str, Any],
    values: Iterable[FCRecord | Mapping[str, Any]],
    sleeper_username: str,
    config_sources: list[str] | None = None,
    values_cache_status: str = "cached",
    values_cache_error: str | None = None,
    tep_tier: TepTier = "te+",
    league_format: str | None = None,
    values_timestamp: datetime | None = None,
    overlay: OverlayResult | None = None,
) -> AnalyzeTradeOutput:
    overlay_state = overlay or DISABLED_OVERLAY
    value_records = parse_value_records(_values_for_query(values, league_format, tep_tier))
    value_index = values_by_sleeper_id(value_records)
    pick_index = pick_records_by_name(value_records)
    my_roster_id = find_roster_id_for_username(snapshot, sleeper_username)
    if my_roster_id is None:
        return AnalyzeTradeOutput(
            policy_status=PolicyStatus.OK,
            resolution_status=ResolutionStatus.NEEDS_CLARIFICATION,
            data_status=DataStatus.UNAVAILABLE,
            policy_flags=[
                PolicyFlag(
                    type=FlagType.AMBIGUOUS_RESOLUTION,
                    asset=sleeper_username,
                    rule_source="computed",
                    severity=FlagSeverity.WARNING,
                    reason=(
                        f"Username '{sleeper_username}' did not resolve to a roster "
                        "in the league snapshot."
                    ),
                )
            ],
            source_notes=[_source_note("asset_resolution", "sleeper")],
            config_sources=config_sources or [],
            asset_resolution=[],
            value_math=None,
            roster_context=None,
        )
    inventory = build_pick_inventory(
        snapshot,
        my_roster_id=my_roster_id,
        include_traded_away=True,
    )
    send_resolutions = [
        _resolve_asset(asset, "send", inventory, players, current_season(snapshot))
        for asset in my_send
    ]
    receive_resolutions = [
        _resolve_asset(asset, "receive", inventory, players, current_season(snapshot))
        for asset in my_receive
    ]
    asset_resolutions = send_resolutions + receive_resolutions
    blocking_rules = _blocking_rules(my_send, send_resolutions, players, policy)
    resolution_status = _resolution_status(asset_resolutions)
    flags = _trade_policy_flags(asset_resolutions, policy, players, current_season(snapshot))
    open_ended = is_open_ended_trade(my_send + my_receive)
    if open_ended:
        flags.append(_conditional_or_swap_flag())
        resolution_status = ResolutionStatus.NEEDS_CLARIFICATION

    if blocking_rules:
        return AnalyzeTradeOutput(
            policy_status=PolicyStatus.BLOCKED,
            resolution_status=resolution_status,
            data_status=DataStatus.UNAVAILABLE,
            blocking_rules=blocking_rules,
            policy_flags=[],
            source_notes=[_source_note("asset_resolution", "sleeper")],
            config_sources=config_sources or [],
            asset_resolution=asset_resolutions,
            value_math=None,
            roster_context=None,
        )

    if resolution_status == ResolutionStatus.NEEDS_CLARIFICATION and not open_ended:
        flags.extend(_ambiguous_flags(asset_resolutions))
        return AnalyzeTradeOutput(
            policy_status=PolicyStatus.OK,
            resolution_status=resolution_status,
            data_status=DataStatus.PARTIAL,
            policy_flags=flags,
            source_notes=[_source_note("asset_resolution", "sleeper")],
            config_sources=config_sources or [],
            asset_resolution=asset_resolutions,
            value_math=None,
            roster_context=None,
        )

    if open_ended:
        flags.extend(
            _ambiguous_flags(
                [
                    resolution
                    for resolution in asset_resolutions
                    if not is_open_ended_asset(resolution.input)
                ]
            )
        )

    value_math, missing_assets, band_notes = _trade_value_math(
        send_resolutions,
        receive_resolutions,
        inventory,
        value_index,
        pick_index,
        timestamp=values_timestamp,
        overlay=overlay_state,
        open_ended=open_ended,
    )
    flags.extend(_missing_value_flags(missing_assets, band_notes))
    flags.extend(_value_cache_flags(values_cache_status, values_cache_error))
    data_status = _trade_data_status(
        value_math, missing_assets, band_range_assets=list(band_notes)
    )
    if open_ended:
        data_status = DataStatus.PARTIAL
    data_status = _with_stale_data_status(data_status, values_cache_status)
    roster_context = None
    if not open_ended:
        roster_context = _roster_context(
            snapshot,
            players,
            my_roster_id,
            send_resolutions,
            receive_resolutions,
            inventory,
        )
    overlay_notes, overlay_flags = _overlay_notes_and_flags(
        overlay_state, field="value_math", timestamp=values_timestamp
    )
    flags.extend(overlay_flags)
    source_notes = [
        _source_note("asset_resolution", "sleeper"),
        _source_note(
            "value_math",
            "fantasycalc",
            cache_status=values_cache_status,
            explanation=valuation_explanation(
                tep_tier,
                league_format=league_format,
                cache_error=values_cache_error,
                pick_rows_present=bool(pick_index),
            ),
            timestamp=values_timestamp,
        ),
    ]
    if roster_context is not None:
        source_notes.append(
            _source_note(
                "roster_context.age_stats",
                "computed",
                explanation="Pick ages are treated as 0 for pick-conversion context.",
            )
        )
    if open_ended:
        source_notes.append(
            _source_note(
                "value_math.delta",
                "computed",
                explanation=(
                    "Conditional, OR, or pick-swap language does not get one invented "
                    "delta. See candidates and/or value_math.delta_min/delta_max."
                ),
            )
        )
    source_notes.extend(_pick_band_range_notes(band_notes, values_timestamp))
    source_notes.extend(overlay_notes)
    return AnalyzeTradeOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=resolution_status,
        data_status=data_status,
        policy_flags=flags,
        source_notes=source_notes,
        config_sources=config_sources or [],
        asset_resolution=asset_resolutions,
        value_math=value_math,
        roster_context=roster_context,
    )


def league_power_map_output(
    *,
    snapshot: dict[str, Any],
    players: Mapping[str, Any],
    values: Iterable[FCRecord | Mapping[str, Any]],
    include_pick_value: bool = False,
    values_cache_status: str = "cached",
    values_cache_error: str | None = None,
    tep_tier: TepTier = "te+",
    league_format: str | None = None,
    values_timestamp: datetime | None = None,
    overlay: OverlayResult | None = None,
) -> LeaguePowerMapOutput:
    overlay_state = overlay or DISABLED_OVERLAY
    usable_values = _values_for_query(values, league_format, tep_tier)
    value_index = values_by_sleeper_id(usable_values)
    pick_index = pick_records_by_name(usable_values)
    names = _user_by_owner(snapshot)
    teams: list[TeamRollup] = []
    missing_any = False
    band_notes: dict[str, str] = {}
    for roster in snapshot["rosters"]:
        roster_players = [
            _roster_player(
                player_id,
                players,
                value_index,
                timestamp=values_timestamp,
                overlay=overlay_state,
            )
            for player_id in roster.get("players", [])
            if _player_record(player_id, players) is not None
        ]
        rollups = {position: 0.0 for position in POSITIONS}
        missing = []
        for player in roster_players:
            if player.value is None:
                missing.append(player.name)
                missing_any = True
            else:
                if player.position in rollups:
                    rollups[player.position] += player.value
        roster_total = round(sum(rollups.values()), 2)
        pick_total = None
        if include_pick_value:
            pick_total, roster_band_notes = _pick_total(
                snapshot,
                int(roster["roster_id"]),
                pick_index,
                timestamp=values_timestamp,
            )
            band_notes.update(roster_band_notes)
        teams.append(
            TeamRollup(
                roster_id=int(roster["roster_id"]),
                owner_name=names[int(roster["roster_id"])]["owner_name"],
                username=names[int(roster["roster_id"])]["username"],
                positional_rollups=rollups,  # type: ignore[arg-type]
                roster_total=roster_total,
                pick_total=pick_total,
                roster_age=_age_stats(roster_players, roster_players),
                missing_flags=missing[:10],
                context_summary=_context_summary(rollups, roster_players),
            )
        )
    source_notes = [
        _source_note("teams", "sleeper"),
        _source_note(
            "teams[].roster_total",
            "fantasycalc",
            cache_status=values_cache_status,
            explanation=valuation_explanation(
                tep_tier,
                league_format=league_format,
                cache_error=values_cache_error,
                pick_rows_present=bool(pick_index),
            ),
            timestamp=values_timestamp,
        ),
    ]
    source_notes.extend(_pick_band_range_notes(band_notes, values_timestamp))
    overlay_notes, overlay_flags = _overlay_notes_and_flags(
        overlay_state, field="teams[].roster_total", timestamp=values_timestamp
    )
    source_notes.extend(overlay_notes)
    flags = _value_cache_flags(values_cache_status, values_cache_error)
    flags.extend(overlay_flags)
    return LeaguePowerMapOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=_with_stale_data_status(
            DataStatus.PARTIAL if missing_any or band_notes else DataStatus.COMPLETE,
            values_cache_status,
        ),
        policy_flags=flags,
        source_notes=source_notes,
        teams=teams,
    )


def whats_on_the_clock_output(
    *,
    draft_state: dict[str, Any],
    snapshot: dict[str, Any],
    players: Mapping[str, Any],
    pool: str = "rookies_only",
) -> WhatsOnTheClockOutput:
    draft = draft_state.get("draft", {})
    picks = draft_state.get("picks", [])
    status = _draft_status(draft.get("status", "complete"))
    recent = [_recent_pick(raw, players, snapshot) for raw in picks[-10:]]
    pick_context = None
    if status == "drafting":
        next_pick_no = len(picks) + 1
        teams = int(draft.get("settings", {}).get("teams", 14))
        round_number = (next_pick_no - 1) // teams + 1
        slot = (next_pick_no - 1) % teams + 1
        owner = _owner_for_draft_slot(draft, snapshot, slot)
        pick_context = PickContext(
            round=round_number,
            slot=slot,
            on_the_clock_owner=owner["owner_name"],
            on_the_clock_team=owner["team_name"],
        )
    pool_not_implemented = pool == "all"
    source_notes = [_source_note("draft_status", "sleeper")]
    if pool_not_implemented:
        source_notes.append(
            _source_note(
                "recent_picks",
                "sleeper",
                explanation=(
                    "pool='all' is not yet implemented; returning rookies_only view. "
                    "Set pool='rookies_only' to suppress this notice."
                ),
            )
        )
    return WhatsOnTheClockOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=DataStatus.PARTIAL if pool_not_implemented else DataStatus.COMPLETE,
        source_notes=source_notes,
        draft_status=status,
        pick_context=pick_context,
        recent_picks=recent,
    )


def best_player_available_output(
    *,
    players: Mapping[str, Any],
    values: Iterable[FCRecord | Mapping[str, Any]],
    draft_state: dict[str, Any],
    position: str | None = None,
    limit: int = 10,
    board_source: str = "fantasycalc",
    values_cache_status: str = "cached",
    values_cache_error: str | None = None,
    tep_tier: TepTier = "te+",
    league_format: str | None = None,
    values_timestamp: datetime | None = None,
    overlay: OverlayResult | None = None,
) -> BestPlayerAvailableOutput:
    overlay_state = overlay or DISABLED_OVERLAY
    drafted = {str(pick.get("player_id")) for pick in draft_state.get("picks", [])}
    usable_values = _values_for_query(values, league_format, tep_tier)
    value_index = values_by_sleeper_id(usable_values)
    valuation_source = "xlsx" if board_source == "xlsx" else "auto"
    candidates = []
    excluded = 0
    for player_id, raw in players.items():
        if not isinstance(raw, Mapping):
            continue
        player_position = raw.get("position")
        rookie = int(raw.get("years_exp") or 0) == 0
        prior_drafted = str(player_id) in drafted
        if (
            player_position not in POSITIONS
            or not rookie
            or prior_drafted
            or (position and player_position != position)
        ):
            excluded += 1
            continue
        chosen, _sources, _disagreement, _missing = merge_player_value(
            str(player_id),
            value_index,
            overlay_state,
            valuation_source=valuation_source,
            timestamp=values_timestamp,
        )
        candidates.append(
            BPACandidate(
                sleeper_id=str(player_id),
                name=str(raw.get("full_name") or raw.get("search_full_name")),
                position=player_position,  # type: ignore[arg-type]
                value=chosen,
                rookie_status=rookie,
                prior_drafted=prior_drafted,
                inclusion_reasons=_bpa_reasons(
                    player_position,
                    rookie,
                    prior_drafted,
                    board_source,
                ),
            )
        )
    candidates.sort(key=lambda candidate: candidate.value or 0, reverse=True)
    overlay_notes, overlay_flags = _overlay_notes_and_flags(
        overlay_state, field="candidates", timestamp=values_timestamp
    )
    flags = _value_cache_flags(values_cache_status, values_cache_error)
    flags.extend(overlay_flags)
    source_notes = [
        _source_note(
            "candidates",
            "fantasycalc" if board_source != "xlsx" else "xlsx",
            cache_status=values_cache_status,
            explanation=valuation_explanation(
                tep_tier,
                league_format=league_format,
                cache_error=values_cache_error,
                pick_rows_present=bool(pick_records(usable_values)),
            )
            if board_source != "xlsx"
            else overlay_status_explanation(overlay_state)
            or "CSV overlay (contract source name xlsx) is not configured.",
            timestamp=values_timestamp,
        )
    ]
    if board_source != "xlsx":
        source_notes.extend(overlay_notes)
    return BestPlayerAvailableOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=_with_stale_data_status(DataStatus.COMPLETE, values_cache_status),
        policy_flags=flags,
        source_notes=source_notes,
        candidates=candidates[:limit],
        excluded_count=excluded,
        board_source=board_source,  # type: ignore[arg-type]
    )


def refresh_cache_output(
    *,
    prior_status: dict[str, str],
    post_status: dict[str, str],
    refreshed: list[str],
    failures: dict[str, str] | None = None,
) -> RefreshCacheOutput:
    failures = failures or {}
    return RefreshCacheOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=DataStatus.PARTIAL if failures else DataStatus.COMPLETE,
        source_notes=[_source_note("refreshed", "computed")],
        refreshed=[
            CacheRefreshResult(cache_key=key, success=True)  # type: ignore[arg-type]
            for key in refreshed
        ],
        failures=[
            CacheRefreshResult(cache_key=key, success=False, error=error)  # type: ignore[arg-type]
            for key, error in failures.items()
        ],
        prior_status=prior_status,  # type: ignore[arg-type]
        post_status=post_status,  # type: ignore[arg-type]
    )


def _health_msg(cache_status: dict[str, str]) -> str:
    if all(status in {CACHE_STATUS_FRESH, CACHE_STATUS_CACHED} for status in cache_status.values()):
        return "all caches within TTL"
    return "one or more caches are stale or missing"


def _with_stale_data_status(data_status: DataStatus, cache_status: str) -> DataStatus:
    if cache_status == CACHE_STATUS_STALE and data_status == DataStatus.COMPLETE:
        return DataStatus.PARTIAL
    return data_status


def _value_cache_flags(cache_status: str, error: str | None = None) -> list[PolicyFlag]:
    if cache_status != CACHE_STATUS_STALE:
        return []
    reason = "FantasyCalc values were served from stale cache after refresh failed."
    if error:
        reason = _truncate(f"{reason} {error}")
    return [
        PolicyFlag(
            type=FlagType.STALE_DATA,
            asset="fantasycalc_values",
            rule_source="computed",
            severity=FlagSeverity.WARNING,
            reason=reason,
        )
    ]


def _truncate(value: str, limit: int = 500) -> str:
    return value[:limit]


def _source_note(
    field: str,
    source: str,
    *,
    cache_status: str = "fresh",
    explanation: str | None = None,
    timestamp: datetime | None = None,
) -> SourceNote:
    stale = cache_status == CACHE_STATUS_STALE
    note_explanation = (
        explanation if explanation or not stale else "stale cache served after refresh failed"
    )
    return SourceNote(
        field=field,
        source=source,  # type: ignore[arg-type]
        timestamp=timestamp or datetime.now(UTC),
        cache_status=cache_status,  # type: ignore[arg-type]
        stale=stale,
        explanation=_truncate(note_explanation) if note_explanation else None,
    )


def _overlay_notes_and_flags(
    overlay: OverlayResult,
    *,
    field: str,
    timestamp: datetime | None = None,
) -> tuple[list[SourceNote], list[PolicyFlag]]:
    explanation = overlay_status_explanation(overlay)
    if overlay.status == "disabled" or not explanation:
        return [], []
    notes = [
        _source_note(
            f"{field}.xlsx" if overlay.status == "loaded" else field,
            "xlsx",
            explanation=explanation,
            timestamp=timestamp,
        )
    ]
    flags: list[PolicyFlag] = []
    if overlay.status in {"missing", "error"}:
        flags.append(
            PolicyFlag(
                type=FlagType.MISSING_VALUE,
                asset="xlsx",
                rule_source="computed",
                severity=FlagSeverity.WARNING,
                reason=_truncate(explanation),
            )
        )
    return notes, flags


def _player_value_provenance(
    value: float | None,
    sources: list[Any],
    *,
    overlay: OverlayResult,
    fantasycalc_enabled: bool,
    tep_tier: TepTier,
    league_format: str | None,
    values_cache_error: str | None,
    pick_rows_present: bool,
) -> tuple[str, str]:
    fc_note = valuation_explanation(
        tep_tier,
        league_format=league_format,
        cache_error=values_cache_error,
        pick_rows_present=pick_rows_present,
    )
    overlay_note = overlay_status_explanation(overlay) or XLSX_OVERLAY_NOTE
    if not fantasycalc_enabled:
        status = overlay.status
        if status == "loaded":
            return "xlsx", overlay_note
        if status == "missing" or status == "error":
            return "xlsx", overlay.message or overlay_note
        if status == "disabled":
            return "xlsx", "CSV overlay (contract source name xlsx) is not configured."
        never: OverlayStatus = status
        raise RuntimeError(f"unhandled overlay status: {never}")
    primary = chosen_value_source(value, sources)
    if primary == "xlsx":
        return "xlsx", overlay_note
    return "fantasycalc", fc_note


def _player_record(player_id: str, players: Mapping[str, Any]) -> Mapping[str, Any] | None:
    raw = players.get(str(player_id))
    return raw if isinstance(raw, Mapping) else None


def _roster_by_id(snapshot: dict[str, Any], roster_id: int | None) -> dict[str, Any]:
    for roster in snapshot.get("rosters", []):
        if roster_id is not None and int(roster["roster_id"]) == roster_id:
            return roster
    return {}


def _roster_player(
    player_id: str,
    players: Mapping[str, Any],
    value_index: dict[str, FCRecord],
    *,
    timestamp: datetime | None = None,
    overlay: OverlayResult | None = None,
) -> RosterPlayer:
    raw = _player_record(player_id, players) or {}
    overlay_state = overlay or DISABLED_OVERLAY
    if overlay_state.status == "disabled":
        source = player_value_source(str(player_id), value_index, timestamp=timestamp)
        sources = [source]
        value = source.value
    else:
        value, sources, _disagreement, _missing = merge_player_value(
            str(player_id),
            value_index,
            overlay_state,
            valuation_source="auto",
            timestamp=timestamp,
        )
    return RosterPlayer(
        sleeper_id=str(player_id),
        name=str(raw.get("full_name") or raw.get("search_full_name") or player_id),
        position=raw.get("position"),  # type: ignore[arg-type]
        team=raw.get("team"),
        age=raw.get("age"),
        value=value,
        rookie_status=int(raw.get("years_exp") or 0) == 0,
        value_sources=sources,
    )


def _positional_depth(players: list[RosterPlayer]) -> list[PositionalDepth]:
    counts = {position: 0 for position in POSITIONS}
    for player in players:
        if player.position in counts:
            counts[player.position] += 1
    starter_defaults = {"QB": 2, "RB": 2, "WR": 3, "TE": 1}
    return [
        PositionalDepth(
            position=position,  # type: ignore[arg-type]
            count=counts[position],
            starters_required=starter_defaults[position],
        )
        for position in POSITIONS
    ]


def _age_stats(pre_players: list[RosterPlayer], post_players: list[RosterPlayer]) -> AgeStats:
    pre_ages = [player.age for player in pre_players if player.age is not None]
    post_ages = [player.age for player in post_players if player.age is not None]
    return AgeStats(
        pre_avg=round(mean(pre_ages), 2) if pre_ages else 0.0,
        pre_median=round(median(pre_ages), 2) if pre_ages else 0.0,
        post_avg=round(mean(post_ages), 2) if post_ages else 0.0,
        post_median=round(median(post_ages), 2) if post_ages else 0.0,
        by_position={},
    )


def _protected_player_flags(
    players: list[RosterPlayer],
    policy: DynamicPolicy,
    source: str,
) -> list[PolicyFlag]:
    protected = {name.lower(): name for name in policy.protected_players}
    return [
        PolicyFlag(
            type=FlagType.PROTECTED_PLAYER,
            asset=player.name,
            rule_source=source,  # type: ignore[arg-type]
            severity=FlagSeverity.INFO,
            reason=f"{player.name} is on protected_players list.",
        )
        for player in players
        if player.name.lower() in protected
    ]


def _resolve_asset(
    asset: str,
    side: str,
    inventory: PickInventory,
    players: Mapping[str, Any],
    season: int,
) -> AssetResolution:
    lookup = normalize_trade_asset(asset)
    parts = or_choice_parts(lookup)
    if len(parts) >= 2:
        return _resolve_or_asset(asset, parts, side, inventory, players, season)
    resolution = _resolve_plain_asset(lookup, side, inventory, players, season)
    if is_swap(asset) and not resolution.candidates:
        resolution = _swap_candidates(resolution, side, inventory)
    return resolution.model_copy(update={"input": asset})


def _resolve_plain_asset(
    asset: str,
    side: str,
    inventory: PickInventory,
    players: Mapping[str, Any],
    season: int,
) -> AssetResolution:
    parsed = parse_pick_description(asset, current_season=season, draft_active=False)
    pickish = parsed.round is not None or any(
        token in asset.lower() for token in ["pick", "1st", "2nd"]
    )
    if pickish:
        return resolve_pick_description(
            asset,
            owned_picks=inventory.owned_picks,
            league_picks=inventory.league_picks,
            current_season=season,
            side=side,
        )
    return resolve_player(asset, players)


def _resolve_or_asset(
    original: str,
    parts: list[str],
    side: str,
    inventory: PickInventory,
    players: Mapping[str, Any],
    season: int,
) -> AssetResolution:
    candidates: list[Candidate] = []
    saw_player = False
    saw_pick = False
    seen: set[str] = set()
    for part in parts[:5]:
        resolution = _resolve_plain_asset(part, side, inventory, players, season)
        if resolution.asset_type == "pick":
            saw_pick = True
        else:
            saw_player = True
        for candidate in _candidates_from_resolution(resolution, players):
            key = candidate.sleeper_id or candidate.pick_token or candidate.name
            if key in seen:
                continue
            seen.add(key)
            candidates.append(candidate)
    asset_type = "player" if saw_player or not saw_pick else "pick"
    return AssetResolution(
        input=original,
        asset_type=asset_type,  # type: ignore[arg-type]
        resolved_id=None,
        match_confidence=50,
        candidates=candidates[:5],
        manual_review=True,
    )


def _candidates_from_resolution(
    resolution: AssetResolution,
    players: Mapping[str, Any] | None = None,
) -> list[Candidate]:
    if resolution.candidates:
        return list(resolution.candidates)
    if resolution.resolved_id is None:
        return []
    if resolution.asset_type == "player":
        raw = _player_record(resolution.resolved_id, players or {}) or {}
        name = _resolved_player_name(resolution.resolved_id, players or {}) or resolution.input
        return [
            Candidate(
                sleeper_id=resolution.resolved_id,
                name=name,
                position=raw.get("position"),
                team=raw.get("team"),
                match_confidence=resolution.match_confidence,
            )
        ]
    return [
        Candidate(
            pick_token=resolution.resolved_id,
            name=resolution.input,
            match_confidence=resolution.match_confidence,
        )
    ]


def _swap_candidates(
    resolution: AssetResolution,
    side: str,
    inventory: PickInventory,
) -> AssetResolution:
    pool = inventory.owned_picks if side == "send" else inventory.league_picks
    token = resolution.resolved_id
    if token:
        match = _PICK_TOKEN_RE.match(token)
        if match:
            season = int(match.group(1))
            round_number = int(match.group(2))
            siblings = [
                pick for pick in pool if pick.season == season and pick.round == round_number
            ]
            if len(siblings) > 1:
                return AssetResolution(
                    input=resolution.input,
                    asset_type="pick",
                    resolved_id=None,
                    match_confidence=50,
                    candidates=[
                        Candidate(
                            pick_token=pick.pick_token,
                            name=pick.display_name,
                            match_confidence=50,
                        )
                        for pick in siblings[:5]
                    ],
                    manual_review=True,
                )
    if resolution.resolved_id and not resolution.candidates:
        return resolution.model_copy(
            update={
                "candidates": _candidates_from_resolution(resolution)[:5],
                "manual_review": True,
            }
        )
    return resolution


def _resolution_status(resolutions: list[AssetResolution]) -> ResolutionStatus:
    return (
        ResolutionStatus.NEEDS_CLARIFICATION
        if any(
            resolution.manual_review or resolution.resolved_id is None for resolution in resolutions
        )
        else ResolutionStatus.OK
    )


def _blocking_rules(
    send_assets: list[str],
    send_resolutions: list[AssetResolution],
    players: Mapping[str, Any],
    policy: DynamicPolicy,
) -> list[BlockingRule]:
    rules: list[BlockingRule] = []
    for raw, resolution in zip(send_assets, send_resolutions, strict=True):
        names: list[str] = []
        if resolution.asset_type == "player":
            resolved_name = _resolved_player_name(resolution.resolved_id, players)
            if resolved_name:
                names.append(resolved_name)
            else:
                names.append(raw)
        names.extend(
            candidate.name
            for candidate in resolution.candidates
            if candidate.name and candidate.sleeper_id
        )
        for display in names:
            for untouchable in policy.hard_untouchables:
                score = int(round(fuzz.WRatio(display, untouchable)))
                if score >= 88:
                    rules.append(
                        BlockingRule(
                            rule="hard_untouchable",
                            asset=display,
                            matched_against=untouchable,
                            match_confidence=score,
                            rule_source=".yellow-sleeper.yaml",
                        )
                    )
    return rules


def _resolved_player_name(resolved_id: str | None, players: Mapping[str, Any]) -> str | None:
    if resolved_id is None:
        return None
    raw = _player_record(resolved_id, players)
    if raw is None:
        return None
    return str(raw.get("full_name") or raw.get("search_full_name") or resolved_id)


_PICK_TOKEN_RE = re.compile(r"^pick_(\d+)_r(\d+)_orig\d+$")


def _trade_policy_flags(
    resolutions: list[AssetResolution],
    policy: DynamicPolicy,
    players: Mapping[str, Any],
    season: int,
) -> list[PolicyFlag]:
    flags: list[PolicyFlag] = []
    protected_players = {name.lower() for name in policy.protected_players}
    for resolution in resolutions:
        if resolution.asset_type == "player":
            canonical = _resolved_player_name(resolution.resolved_id, players)
            match_name = (canonical or resolution.resolved_id or "").lower()
            if match_name and match_name in protected_players:
                display = canonical or resolution.resolved_id or resolution.input
                flags.append(
                    PolicyFlag(
                        type=FlagType.PROTECTED_PLAYER,
                        asset=display,
                        rule_source=".yellow-sleeper.yaml",
                        severity=FlagSeverity.INFO,
                        reason=f"{display} is on protected_players list.",
                    )
                )
        if resolution.asset_type == "pick" and resolution.resolved_id:
            token_match = _PICK_TOKEN_RE.match(resolution.resolved_id)
            if token_match:
                token_season = int(token_match.group(1))
                token_round = int(token_match.group(2))
                for pattern in policy.protected_pick_patterns:
                    parsed = parse_pick_description(
                        pattern, current_season=season, draft_active=False
                    )
                    if (
                        parsed.parsed
                        and parsed.season == token_season
                        and parsed.round == token_round
                    ):
                        flags.append(
                            PolicyFlag(
                                type=FlagType.PROTECTED_PICK_PATTERN,
                                asset=resolution.resolved_id,
                                rule_source=".yellow-sleeper.yaml",
                                severity=FlagSeverity.WARNING,
                                reason=f"{resolution.resolved_id} matches protected_pick_patterns.",
                            )
                        )
    return flags[:25]


def _ambiguous_flags(resolutions: list[AssetResolution]) -> list[PolicyFlag]:
    return [
        PolicyFlag(
            type=FlagType.AMBIGUOUS_RESOLUTION,
            asset=resolution.input,
            rule_source="computed",
            severity=FlagSeverity.WARNING,
            reason="Asset did not resolve exactly under the configured thresholds.",
        )
        for resolution in resolutions
        if resolution.manual_review or resolution.resolved_id is None
    ]


def _trade_value_math(
    send: list[AssetResolution],
    receive: list[AssetResolution],
    inventory: PickInventory,
    value_index: dict[str, FCRecord],
    pick_index: Mapping[str, FCRecord],
    *,
    timestamp: datetime | None = None,
    overlay: OverlayResult | None = None,
    open_ended: bool = False,
) -> tuple[ValueMath, list[str], dict[str, str]]:
    overlay_state = overlay or DISABLED_OVERLAY
    per_asset = []
    send_total = 0.0
    receive_total = 0.0
    missing_assets = []
    disagreements = []
    band_notes: dict[str, str] = {}
    send_options: list[list[float]] = []
    receive_options: list[list[float]] = []
    for side, resolutions, option_lists in (
        ("send", send, send_options),
        ("receive", receive, receive_options),
    ):
        for resolution in resolutions:
            asset_source, band_note, merged_sources, disagreement = _asset_value_source(
                resolution,
                inventory,
                value_index,
                pick_index,
                timestamp=timestamp,
                overlay=overlay_state,
            )
            value = asset_source.value
            entry: dict[str, Any] = {
                "asset": resolution.resolved_id,
                "side": side,
                "value": value,
                "sources": merged_sources,
            }
            alternatives = _alternative_asset_values(
                resolution,
                inventory,
                value_index,
                pick_index,
                timestamp=timestamp,
                overlay=overlay_state,
            )
            if alternatives:
                entry["alternatives"] = alternatives
            if is_conditional(resolution.input):
                entry["conditional"] = True
            per_asset.append(entry)
            if band_note:
                band_notes[resolution.input] = band_note
            option_lists.append(
                _scenario_option_values(
                    resolution,
                    value,
                    alternatives,
                )
            )
            if value is None and not alternatives:
                missing_assets.append(resolution.input)
                continue
            if not open_ended and value is not None:
                if side == "send":
                    send_total += value
                else:
                    receive_total += value
            if disagreement is not None:
                disagreements.append(disagreement)
    delta = receive_total - send_total
    delta_min: float | None = None
    delta_max: float | None = None
    if open_ended:
        bounds = _scenario_delta_bounds(send_options, receive_options)
        if bounds is not None and bounds[0] != bounds[1]:
            delta_min, delta_max = bounds
        return (
            ValueMath(
                send_total=None,
                receive_total=None,
                delta=None,
                delta_pct=None,
                delta_min=round(delta_min, 2) if delta_min is not None else None,
                delta_max=round(delta_max, 2) if delta_max is not None else None,
                per_asset=per_asset,
                source_disagreement=disagreements[0] if disagreements else None,
            ),
            missing_assets,
            band_notes,
        )
    return (
        ValueMath(
            send_total=round(send_total, 2),
            receive_total=round(receive_total, 2),
            delta=round(delta, 2),
            delta_pct=round(delta / send_total * 100, 2) if send_total else None,
            per_asset=per_asset,
            source_disagreement=disagreements[0] if disagreements else None,
        ),
        missing_assets,
        band_notes,
    )


def _conditional_or_swap_flag() -> PolicyFlag:
    return PolicyFlag(
        type=FlagType.CONDITIONAL_OR_SWAP_TRADE,
        asset=None,
        rule_source="computed",
        severity=FlagSeverity.WARNING,
        reason=(
            "Trade input includes conditional, OR, or pick-swap language. "
            "The server did not invent one delta; see candidates and/or "
            "value_math.delta_min/delta_max."
        ),
    )


def _alternative_asset_values(
    resolution: AssetResolution,
    inventory: PickInventory,
    value_index: dict[str, FCRecord],
    pick_index: Mapping[str, FCRecord],
    *,
    timestamp: datetime | None = None,
    overlay: OverlayResult | None = None,
) -> list[dict[str, Any]]:
    alternatives: list[dict[str, Any]] = []
    seen: set[str] = set()
    if resolution.resolved_id:
        seen.add(resolution.resolved_id)
    for candidate in resolution.candidates:
        resolved_id = candidate.sleeper_id or candidate.pick_token
        if not resolved_id or resolved_id in seen:
            continue
        seen.add(resolved_id)
        fake = AssetResolution(
            input=candidate.name,
            asset_type="player" if candidate.sleeper_id else "pick",
            resolved_id=resolved_id,
            match_confidence=candidate.match_confidence,
        )
        source, _band, sources, _disagreement = _asset_value_source(
            fake,
            inventory,
            value_index,
            pick_index,
            timestamp=timestamp,
            overlay=overlay,
        )
        alternatives.append(
            {
                "asset": resolved_id,
                "value": source.value,
                "name": candidate.name,
                "sources": sources,
            }
        )
    return alternatives


def _scenario_option_values(
    resolution: AssetResolution,
    value: float | None,
    alternatives: list[dict[str, Any]],
) -> list[float]:
    numbers: list[float] = []
    if value is not None:
        numbers.append(float(value))
    for alternative in alternatives:
        alt_value = alternative.get("value")
        if alt_value is not None:
            numbers.append(float(alt_value))
    unique: list[float] = []
    for number in numbers:
        if number not in unique:
            unique.append(number)
    if is_conditional(resolution.input):
        if 0.0 not in unique:
            unique.append(0.0)
        return unique
    if is_or_choice(resolution.input) or is_swap(resolution.input):
        return unique
    return unique[:1] if unique else []


def _scenario_delta_bounds(
    send_options: list[list[float]],
    receive_options: list[list[float]],
) -> tuple[float, float] | None:
    if not send_options or not receive_options:
        return None
    if any(not options for options in send_options + receive_options):
        return None
    # Independent linear sums: extrema are per-asset min/max, not a Cartesian product.
    send_min = sum(min(options) for options in send_options)
    send_max = sum(max(options) for options in send_options)
    receive_min = sum(min(options) for options in receive_options)
    receive_max = sum(max(options) for options in receive_options)
    return receive_min - send_max, receive_max - send_min


def _asset_value_source(
    resolution: AssetResolution,
    inventory: PickInventory,
    value_index: dict[str, FCRecord],
    pick_index: Mapping[str, FCRecord],
    *,
    timestamp: datetime | None = None,
    overlay: OverlayResult | None = None,
) -> tuple[ValueSourceBreakdown, str | None, list[ValueSourceBreakdown], SourceDisagreement | None]:
    overlay_state = overlay or DISABLED_OVERLAY
    if resolution.resolved_id is None:
        empty = value_source("fantasycalc", None, timestamp=timestamp, enabled=True)
        return empty, None, [empty], None
    if resolution.asset_type == "player" and resolution.resolved_id:
        chosen, sources, disagreement, _missing = merge_player_value(
            resolution.resolved_id,
            value_index,
            overlay_state,
            valuation_source="auto",
            timestamp=timestamp,
        )
        if not sources:
            sources = [
                player_value_source(
                    resolution.resolved_id, value_index, timestamp=timestamp
                )
            ]
        primary_name = chosen_value_source(chosen, sources)
        primary = next(
            (source for source in sources if source.source == primary_name),
            sources[0],
        )
        if chosen is not None and primary.value != chosen:
            primary = value_source(
                primary_name, chosen, timestamp=primary.timestamp, enabled=True
            )
        return primary, None, sources, disagreement
    pick = next(
        (pick for pick in inventory.league_picks if pick.pick_token == resolution.resolved_id),
        None,
    )
    resolved = resolve_pick_value(
        pick.round if pick else 0,
        pick=pick,
        pick_index=pick_index,
        timestamp=timestamp,
    )
    band_note = resolved.band_range.explanation(pick) if resolved.band_range and pick else None
    return resolved.source, band_note, [resolved.source], None


def _trade_data_status(
    value_math: ValueMath,
    missing_assets: list[str],
    *,
    band_range_assets: list[str] | None = None,
) -> DataStatus:
    if not value_math.per_asset:
        return DataStatus.UNAVAILABLE
    has_number = any(asset["value"] is not None for asset in value_math.per_asset)
    has_band = bool(band_range_assets)
    if has_number and not missing_assets:
        return DataStatus.COMPLETE
    if has_number or has_band:
        return DataStatus.PARTIAL
    return DataStatus.UNAVAILABLE


def _value_data_status(resolved: bool, has_value: bool) -> DataStatus:
    if not resolved:
        return DataStatus.UNAVAILABLE
    return DataStatus.COMPLETE if has_value else DataStatus.PARTIAL


def _missing_value_flag(asset: str, reason: str | None = None) -> PolicyFlag:
    return PolicyFlag(
        type=FlagType.MISSING_VALUE,
        asset=asset,
        rule_source="computed",
        severity=FlagSeverity.WARNING,
        reason=reason or "No enabled value source returned a value for this asset.",
    )


def _missing_value_flags(
    assets: list[str],
    band_notes: Mapping[str, str] | None = None,
) -> list[PolicyFlag]:
    notes = band_notes or {}
    return [_missing_value_flag(asset, notes.get(asset)) for asset in assets]


def _pick_band_range_notes(
    band_notes: Mapping[str, str],
    timestamp: datetime | None = None,
) -> list[SourceNote]:
    if not band_notes:
        return []
    unique = list(dict.fromkeys(band_notes.values()))
    return [
        _source_note(
            "pick_band_range",
            "fantasycalc",
            explanation="; ".join(unique),
            timestamp=timestamp,
        )
    ]


def _roster_context(
    snapshot: dict[str, Any],
    players: Mapping[str, Any],
    my_roster_id: int,
    send: list[AssetResolution],
    receive: list[AssetResolution],
    inventory: PickInventory,
) -> RosterContext:
    roster = _roster_by_id(snapshot, my_roster_id)
    current_ids = [str(player_id) for player_id in roster.get("players", [])]
    send_ids = {resolution.resolved_id for resolution in send if resolution.asset_type == "player"}
    receive_ids = [
        resolution.resolved_id for resolution in receive if resolution.asset_type == "player"
    ]
    post_ids = [player_id for player_id in current_ids if player_id not in send_ids]
    post_ids.extend(player_id for player_id in receive_ids if player_id)
    dummy_values: dict[str, FCRecord] = {}
    pre_players = [
        _roster_player(player_id, players, dummy_values)
        for player_id in current_ids
        if _player_record(player_id, players) is not None
    ]
    post_players = [
        _roster_player(player_id, players, dummy_values)
        for player_id in post_ids
        if _player_record(player_id, players) is not None
    ]
    pre_counts = _position_counts(pre_players)
    post_counts = _position_counts(post_players)
    return RosterContext(
        position_depth_change=[
            {
                "position": position,
                "pre": pre_counts[position],
                "post": post_counts[position],
                "delta": post_counts[position] - pre_counts[position],
            }
            for position in POSITIONS
        ],
        age_stats=_age_stats(pre_players, post_players),
        pick_inventory_summary=_pick_inventory_summary(send, receive, inventory),
    )


def _position_counts(players: list[RosterPlayer]) -> dict[str, int]:
    counts = {position: 0 for position in POSITIONS}
    for player in players:
        if player.position in counts:
            counts[player.position] += 1
    return counts


def _pick_inventory_summary(
    send: list[AssetResolution],
    receive: list[AssetResolution],
    inventory: PickInventory,
) -> PickInventorySummary:
    pre = _pick_counts(inventory.owned_picks)
    post = dict(pre)
    for resolution in send:
        if resolution.asset_type == "pick" and resolution.resolved_id:
            _adjust_pick_count(post, resolution.resolved_id, inventory, -1)
    for resolution in receive:
        if resolution.asset_type == "pick" and resolution.resolved_id:
            _adjust_pick_count(post, resolution.resolved_id, inventory, 1)
    keys = set(pre) | set(post)
    return PickInventorySummary(
        pre=pre,
        post=post,
        delta={key: post.get(key, 0) - pre.get(key, 0) for key in keys},
    )


def _pick_counts(picks: list[Pick]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for pick in picks:
        counts[f"{pick.season}_R{pick.round}"] += 1
    return dict(counts)


def _adjust_pick_count(
    counts: dict[str, int],
    pick_token: str,
    inventory: PickInventory,
    delta: int,
) -> None:
    pick = next((item for item in inventory.league_picks if item.pick_token == pick_token), None)
    if pick is None:
        return
    key = f"{pick.season}_R{pick.round}"
    counts[key] = counts.get(key, 0) + delta


def _user_by_owner(snapshot: dict[str, Any]) -> dict[int, dict[str, str]]:
    users = {user.get("user_id"): user for user in snapshot.get("users", [])}
    result = {}
    for roster in snapshot.get("rosters", []):
        roster_id = int(roster["roster_id"])
        user = users.get(roster.get("owner_id"), {})
        metadata = user.get("metadata") if isinstance(user.get("metadata"), dict) else {}
        result[roster_id] = {
            "owner_name": str(user.get("display_name") or user.get("username") or roster_id),
            "username": str(user.get("username") or user.get("display_name") or roster_id),
            "team_name": str(metadata.get("team_name") or user.get("display_name") or roster_id),
        }
    return result


def _pick_total(
    snapshot: dict[str, Any],
    roster_id: int,
    pick_index: Mapping[str, FCRecord],
    *,
    timestamp: datetime | None = None,
) -> tuple[float, dict[str, str]]:
    inventory = build_pick_inventory(snapshot, my_roster_id=roster_id)
    total = 0.0
    band_notes: dict[str, str] = {}
    for pick in inventory.owned_picks:
        resolved = resolve_pick_value(
            pick.round, pick=pick, pick_index=pick_index, timestamp=timestamp
        )
        if resolved.band_range is not None:
            band_notes[pick.pick_token] = resolved.band_range.explanation(pick)
            continue
        if resolved.source.value is not None:
            total += float(resolved.source.value)
    return total, band_notes


def _context_summary(rollups: dict[str, float], players: list[RosterPlayer]) -> str:
    strongest = max(rollups, key=rollups.get)
    thinnest = min(rollups, key=rollups.get)
    ages = [player.age for player in players if player.age is not None]
    avg_age = round(mean(ages), 1) if ages else 0.0
    return f"strongest at {strongest}, thinnest at {thinnest}, average age {avg_age}"


def _draft_status(status: str) -> str:
    if status == "drafting":
        return "drafting"
    if status in {"pre_draft", "paused"}:
        return "not_started"
    return "complete"


def _recent_pick(
    raw: dict[str, Any],
    players: Mapping[str, Any],
    snapshot: dict[str, Any],
) -> RecentPick:
    player = _player_record(str(raw.get("player_id")), players) or {}
    owners = _user_by_owner(snapshot)
    roster_id = int(raw.get("roster_id") or 0)
    return RecentPick(
        round=int(raw.get("round") or 0),
        slot=int(raw.get("pick_no") or 0),
        sleeper_id=str(raw.get("player_id")),
        name=str(player.get("full_name") or raw.get("player_id")),
        position=str(player.get("position") or ""),
        drafted_by_owner=owners.get(roster_id, {}).get("owner_name", f"Roster {roster_id}"),
    )


def _owner_for_draft_slot(
    draft: dict[str, Any],
    snapshot: dict[str, Any],
    slot: int,
) -> dict[str, str]:
    draft_order = draft.get("draft_order", {})
    owner_id = next(
        (user_id for user_id, draft_slot in draft_order.items() if draft_slot == slot),
        None,
    )
    user_by_id = {user.get("user_id"): user for user in snapshot.get("users", [])}
    user = user_by_id.get(owner_id, {})
    metadata = user.get("metadata") if isinstance(user.get("metadata"), dict) else {}
    return {
        "owner_name": str(user.get("display_name") or user.get("username") or "unknown"),
        "team_name": str(metadata.get("team_name") or user.get("display_name") or "unknown"),
    }


def _bpa_reasons(
    position: str,
    rookie: bool,
    prior_drafted: bool,
    board_source: str,
) -> list[str]:
    return [
        f"rookie_status:{str(rookie).lower()}",
        f"position:{position}",
        f"not_already_drafted:{str(not prior_drafted).lower()}",
        f"value_source:{board_source}",
    ]
