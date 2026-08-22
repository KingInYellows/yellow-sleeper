from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from statistics import mean, median
from typing import Any

from rapidfuzz import fuzz

from ..clients.fantasycalc import FCRecord, tep_source_explanation
from ..config import DynamicPolicy
from ..models import (
    AgeStats,
    AnalyzeTradeOutput,
    AssetResolution,
    BestPlayerAvailableOutput,
    BlockingRule,
    BPACandidate,
    CacheRefreshResult,
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
    SourceNote,
    TeamRollup,
    ValueMath,
    WhatsOnTheClockOutput,
)
from ..resolve import resolve_pick_description, resolve_player, resolve_roster
from ..resolve.picks import parse_pick_description
from .roster import (
    PickInventory,
    build_pick_inventory,
    current_season,
    find_roster_id_for_username,
)
from .value import (
    merge_player_value,
    parse_value_records,
    pick_records_by_name,
    pick_value_range,
    pick_value_source,
    player_value_source,
    source_disagreement,
    value_source,
    values_by_sleeper_id,
)

POSITIONS = ("QB", "RB", "WR", "TE")

# Cache-status sentinels — mirror SourceNote.cache_status Literal in models/shared.py.
# Use these constants at comparison sites so a typo fails at import rather than silently.
CACHE_STATUS_FRESH = "fresh"
CACHE_STATUS_CACHED = "cached"
CACHE_STATUS_STALE = "stale"


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
    value_index = values_by_sleeper_id(values)
    roster_players = [
        _roster_player(player_id, players, value_index)
        for player_id in roster.get("players", [])
        if _player_record(player_id, players) is not None
    ]
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
    data_status = _with_stale_data_status(
        DataStatus.PARTIAL if missing_values else DataStatus.COMPLETE,
        values_cache_status,
    )
    return GetMyRosterOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=data_status,
        policy_flags=flags,
        source_notes=[
            _source_note("grouped_roster", "sleeper"),
            _source_note(
                "grouped_roster[].value",
                "fantasycalc",
                cache_status=values_cache_status,
                explanation=values_cache_error,
            ),
        ],
        config_sources=config_sources,
        grouped_roster=grouped,
        positional_depth=_positional_depth(roster_players),
        age_stats=_age_stats(roster_players, roster_players),
        missing_values=missing_values,
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
    return ListTradedPicksOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=DataStatus.COMPLETE,
        source_notes=[_source_note("picks", "sleeper")],
        picks=inventory.traded_picks[:25],
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
    overlay: Mapping[str, float] | None = None,
    overlay_precedence: str = "overlay_wins",
    overlay_disagreement_pct: float = 10.0,
    tep_tier: str = "te+",
) -> GetPlayerValueOutput:
    resolution = resolve_player(player, players)
    fantasycalc_enabled = valuation_source != "xlsx"
    value_index = values_by_sleeper_id(values) if fantasycalc_enabled else {}
    overlay_map = dict(overlay or {})
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
            overlay_map,
            valuation_source=valuation_source,
            overlay_precedence=overlay_precedence,  # type: ignore[arg-type]
            disagreement_pct=overlay_disagreement_pct,
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
                        f"(threshold {overlay_disagreement_pct}%)."
                    ),
                )
            )
    if fantasycalc_enabled:
        flags.extend(_value_cache_flags(values_cache_status, values_cache_error))
    cache_status = values_cache_status if fantasycalc_enabled else CACHE_STATUS_FRESH
    if fantasycalc_enabled:
        overlay_selected = (
            value is not None
            and resolution.resolved_id is not None
            and resolution.resolved_id in overlay_map
            and float(value) == float(overlay_map[resolution.resolved_id])
            and overlay_precedence == "overlay_wins"
        )
        if overlay_selected:
            source_note_explanation = "Local CSV/sheet overlay (contract source name xlsx)."
            primary_source = "xlsx"
        else:
            source_note_explanation = values_cache_error or tep_source_explanation(tep_tier)  # type: ignore[arg-type]
            primary_source = "fantasycalc"
    else:
        source_note_explanation = (
            "Local CSV/sheet overlay (contract source name xlsx)."
            if overlay_map
            else "XLSX/CSV overlay path is empty or missing."
        )
        primary_source = "xlsx"
    data_status = _with_stale_data_status(
        _value_data_status(bool(resolution.resolved_id), value is not None),
        cache_status,
    )
    return GetPlayerValueOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=_resolution_status([resolution]),
        data_status=data_status,
        policy_flags=flags,
        source_notes=[
            _source_note(
                "value",
                primary_source,
                cache_status=cache_status,
                explanation=source_note_explanation,
            )
        ],
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
    sleeper_username: str = "brad",
    config_sources: list[str] | None = None,
    values_cache_status: str = "cached",
    values_cache_error: str | None = None,
    overlay: Mapping[str, float] | None = None,
    overlay_precedence: str = "overlay_wins",
    overlay_disagreement_pct: float = 10.0,
    tep_tier: str = "te+",
) -> AnalyzeTradeOutput:
    value_records = parse_value_records(values)
    value_index = values_by_sleeper_id(value_records)
    pick_index = pick_records_by_name(value_records)
    overlay_map = dict(overlay or {})
    my_roster_id = find_roster_id_for_username(snapshot, sleeper_username) or 0
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
    conditional = _detect_conditional_or_swap(my_send + my_receive)
    if conditional:
        flags.append(
            PolicyFlag(
                type=FlagType.CONDITIONAL_OR_SWAP_TRADE,
                asset=None,
                rule_source="computed",
                severity=FlagSeverity.WARNING,
                reason=(
                    "Trade input includes conditional or pick-swap language; "
                    "value_math may include scenario delta_min/delta_max ranges."
                ),
            )
        )
        if _conditional_needs_clarification(my_send + my_receive):
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

    if resolution_status == ResolutionStatus.NEEDS_CLARIFICATION and not conditional:
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

    if resolution_status == ResolutionStatus.NEEDS_CLARIFICATION and conditional:
        flags.extend(_ambiguous_flags(asset_resolutions))
        # Still attempt scenario ranges when assets partially resolve.
        value_math, missing_assets = _trade_value_math(
            send_resolutions,
            receive_resolutions,
            inventory,
            value_index,
            pick_index=pick_index,
            overlay=overlay_map,
            overlay_precedence=overlay_precedence,
            overlay_disagreement_pct=overlay_disagreement_pct,
            include_scenario_range=True,
        )
        flags.extend(_missing_value_flags(missing_assets))
        flags.extend(_value_cache_flags(values_cache_status, values_cache_error))
        conditional_data_status = _trade_data_status(value_math, missing_assets)
        if conditional_data_status == DataStatus.COMPLETE:
            # Conditionals remain PARTIAL even when values resolve: triggers are unverified.
            conditional_data_status = DataStatus.PARTIAL
        return AnalyzeTradeOutput(
            policy_status=PolicyStatus.OK,
            resolution_status=resolution_status,
            data_status=conditional_data_status,
            policy_flags=flags,
            source_notes=[
                _source_note("asset_resolution", "sleeper"),
                *_value_math_source_notes(
                    values_cache_status=values_cache_status,
                    values_cache_error=values_cache_error,
                    tep_tier=tep_tier,
                    overlay=overlay_map,
                    overlay_precedence=overlay_precedence,
                    overlay_disagreement_pct=overlay_disagreement_pct,
                ),
            ],
            config_sources=config_sources or [],
            asset_resolution=asset_resolutions,
            value_math=value_math,
            roster_context=None,
        )

    value_math, missing_assets = _trade_value_math(
        send_resolutions,
        receive_resolutions,
        inventory,
        value_index,
        pick_index=pick_index,
        overlay=overlay_map,
        overlay_precedence=overlay_precedence,
        overlay_disagreement_pct=overlay_disagreement_pct,
        include_scenario_range=conditional or _trade_has_picks(asset_resolutions),
    )
    flags.extend(_missing_value_flags(missing_assets))
    flags.extend(_value_cache_flags(values_cache_status, values_cache_error))
    data_status = _trade_data_status(value_math, missing_assets)
    data_status = _with_stale_data_status(data_status, values_cache_status)
    roster_context = _roster_context(
        snapshot,
        players,
        my_roster_id,
        send_resolutions,
        receive_resolutions,
        inventory,
    )
    return AnalyzeTradeOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=resolution_status,
        data_status=data_status,
        policy_flags=flags,
        source_notes=[
            _source_note("asset_resolution", "sleeper"),
            *_value_math_source_notes(
                values_cache_status=values_cache_status,
                values_cache_error=values_cache_error,
                tep_tier=tep_tier,
                overlay=overlay_map,
                overlay_precedence=overlay_precedence,
                overlay_disagreement_pct=overlay_disagreement_pct,
            ),
            _source_note(
                "roster_context.age_stats",
                "computed",
                explanation="Pick ages are treated as 0 for pick-conversion context.",
            ),
        ],
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
) -> LeaguePowerMapOutput:
    value_records = parse_value_records(values)
    value_index = values_by_sleeper_id(value_records)
    pick_index = pick_records_by_name(value_records) if include_pick_value else {}
    names = _user_by_owner(snapshot)
    teams: list[TeamRollup] = []
    missing_any = False
    for roster in snapshot["rosters"]:
        roster_players = [
            _roster_player(player_id, players, value_index)
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
        teams.append(
            TeamRollup(
                roster_id=int(roster["roster_id"]),
                owner_name=names[int(roster["roster_id"])]["owner_name"],
                username=names[int(roster["roster_id"])]["username"],
                positional_rollups=rollups,  # type: ignore[arg-type]
                roster_total=roster_total,
                pick_total=(
                    _pick_total(snapshot, int(roster["roster_id"]), pick_index=pick_index)
                    if include_pick_value
                    else None
                ),
                roster_age=_age_stats(roster_players, roster_players),
                missing_flags=missing[:10],
                context_summary=_context_summary(rollups, roster_players),
            )
        )
    return LeaguePowerMapOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=_with_stale_data_status(
            DataStatus.PARTIAL if missing_any else DataStatus.COMPLETE,
            values_cache_status,
        ),
        policy_flags=_value_cache_flags(values_cache_status, values_cache_error),
        source_notes=[
            _source_note("teams", "sleeper"),
            _source_note(
                "teams[].roster_total",
                "fantasycalc",
                cache_status=values_cache_status,
                explanation=values_cache_error,
            ),
        ],
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
) -> BestPlayerAvailableOutput:
    drafted = {str(pick.get("player_id")) for pick in draft_state.get("picks", [])}
    value_index = values_by_sleeper_id(values)
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
        value = value_index.get(str(player_id))
        candidates.append(
            BPACandidate(
                sleeper_id=str(player_id),
                name=str(raw.get("full_name") or raw.get("search_full_name")),
                position=player_position,  # type: ignore[arg-type]
                value=value.value if value else None,
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
    return BestPlayerAvailableOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=_with_stale_data_status(DataStatus.COMPLETE, values_cache_status),
        policy_flags=_value_cache_flags(values_cache_status, values_cache_error),
        source_notes=[
            _source_note(
                "candidates",
                "fantasycalc",
                cache_status=values_cache_status,
                explanation=values_cache_error,
            )
        ],
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
) -> SourceNote:
    stale = cache_status == CACHE_STATUS_STALE
    note_explanation = (
        explanation if explanation or not stale else "stale cache served after refresh failed"
    )
    return SourceNote(
        field=field,
        source=source,  # type: ignore[arg-type]
        timestamp=datetime.now(UTC),
        cache_status=cache_status,  # type: ignore[arg-type]
        stale=stale,
        explanation=_truncate(note_explanation) if note_explanation else None,
    )


def _value_math_source_notes(
    *,
    values_cache_status: str,
    values_cache_error: str | None,
    tep_tier: str,
    overlay: Mapping[str, float],
    overlay_precedence: str,
    overlay_disagreement_pct: float,
) -> list[SourceNote]:
    """Provenance for trade value_math: FantasyCalc and/or CSV overlay."""
    notes = [
        _source_note(
            "value_math.fantasycalc",
            "fantasycalc",
            cache_status=values_cache_status,
            explanation=values_cache_error or tep_source_explanation(tep_tier),  # type: ignore[arg-type]
        )
    ]
    if overlay:
        notes.append(
            _source_note(
                "value_math.xlsx",
                "xlsx",
                cache_status=CACHE_STATUS_FRESH,
                explanation=(
                    f"CSV/sheet overlay active for {len(overlay)} sleeper_id(s); "
                    f"precedence={overlay_precedence}; "
                    f"disagreement_threshold_pct={overlay_disagreement_pct}."
                ),
            )
        )
    return notes


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
) -> RosterPlayer:
    raw = _player_record(player_id, players) or {}
    source = player_value_source(str(player_id), value_index)
    return RosterPlayer(
        sleeper_id=str(player_id),
        name=str(raw.get("full_name") or raw.get("search_full_name") or player_id),
        position=raw.get("position"),  # type: ignore[arg-type]
        team=raw.get("team"),
        age=raw.get("age"),
        value=source.value,
        rookie_status=int(raw.get("years_exp") or 0) == 0,
        value_sources=[source],
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
    lookup = _strip_conditional_clause(asset)
    parsed = parse_pick_description(lookup, current_season=season, draft_active=False)
    pickish = parsed.round is not None or any(
        token in lookup.lower() for token in ["pick", "1st", "2nd"]
    )
    if pickish:
        resolution = resolve_pick_description(
            lookup,
            owned_picks=inventory.owned_picks,
            league_picks=inventory.league_picks,
            current_season=season,
            side=side,
        )
    else:
        resolution = resolve_player(lookup, players)
    # Preserve the original trade-input string for flags/provenance.
    return resolution.model_copy(update={"input": asset})


def _strip_conditional_clause(asset: str) -> str:
    """Return the base asset name with trailing if/unless/when clauses removed."""
    base = _CONDITIONAL_RE.split(asset, maxsplit=1)[0].strip()
    # Drop dangling openers left by forms like "2027 1st (if ...)".
    base = re.sub(r"[\s(\[{]+$", "", base).strip()
    return base or asset


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
        if resolution.asset_type != "player":
            continue
        resolved_name = _resolved_player_name(resolution.resolved_id, players) or raw
        for untouchable in policy.hard_untouchables:
            score = int(round(fuzz.WRatio(resolved_name, untouchable)))
            if score >= 88:
                rules.append(
                    BlockingRule(
                        rule="hard_untouchable",
                        asset=resolved_name,
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
    *,
    pick_index: Mapping[str, FCRecord] | None = None,
    overlay: Mapping[str, float] | None = None,
    overlay_precedence: str = "overlay_wins",
    overlay_disagreement_pct: float = 10.0,
    include_scenario_range: bool = False,
) -> tuple[ValueMath, list[str]]:
    pick_map = dict(pick_index or {})
    overlay_map = dict(overlay or {})
    per_asset = []
    send_legs: list[tuple[float, float, float, bool]] = []
    receive_legs: list[tuple[float, float, float, bool]] = []
    missing_assets = []
    disagreements = []
    for side, resolutions in [("send", send), ("receive", receive)]:
        for resolution in resolutions:
            value_src, low, high = _asset_value_bundle(
                resolution,
                inventory,
                value_index,
                pick_map,
                overlay_map,
                overlay_precedence=overlay_precedence,
                overlay_disagreement_pct=overlay_disagreement_pct,
            )
            value = value_src.value
            sources = [value_src]
            if (
                resolution.asset_type == "player"
                and resolution.resolved_id
                and overlay_map
                and resolution.resolved_id in overlay_map
            ):
                _, merged_sources, disagreement, _ = merge_player_value(
                    resolution.resolved_id,
                    value_index,
                    overlay_map,
                    valuation_source="auto",
                    overlay_precedence=overlay_precedence,  # type: ignore[arg-type]
                    disagreement_pct=overlay_disagreement_pct,
                )
                sources = merged_sources
                if disagreement is not None:
                    disagreements.append(disagreement)
            per_asset.append(
                {
                    "asset": resolution.resolved_id,
                    "side": side,
                    "value": value,
                    "value_min": low,
                    "value_max": high,
                    "sources": sources,
                }
            )
            if value is None:
                missing_assets.append(resolution.input)
                continue
            point = float(value)
            low_v = float(low if low is not None else point)
            high_v = float(high if high is not None else point)
            leg = (point, low_v, high_v, _asset_is_conditional(resolution.input))
            if side == "send":
                send_legs.append(leg)
            else:
                receive_legs.append(leg)
            disagreement = source_disagreement(
                sources,
                threshold_pct=overlay_disagreement_pct,
            )
            if disagreement is not None and disagreement not in disagreements:
                disagreements.append(disagreement)

    send_total = sum(point for point, _, _, _ in send_legs)
    receive_total = sum(point for point, _, _, _ in receive_legs)
    delta = receive_total - send_total
    delta_min: float | None = None
    delta_max: float | None = None
    if include_scenario_range:
        delta_min, delta_max = _scenario_delta_bounds(send_legs, receive_legs)
    return (
        ValueMath(
            send_total=round(send_total, 2),
            receive_total=round(receive_total, 2),
            delta=round(delta, 2),
            delta_pct=round(delta / send_total * 100, 2) if send_total else None,
            delta_min=round(delta_min, 2) if delta_min is not None else None,
            delta_max=round(delta_max, 2) if delta_max is not None else None,
            per_asset=per_asset,
            source_disagreement=disagreements[0] if disagreements else None,
        ),
        missing_assets,
    )


def _asset_is_conditional(asset: str) -> bool:
    return bool(_CONDITIONAL_RE.search(asset))


def _scenario_delta_bounds(
    send_legs: list[tuple[float, float, float, bool]],
    receive_legs: list[tuple[float, float, float, bool]],
) -> tuple[float, float]:
    """Expand delta across pick bands and conditional include/exclude outcomes.

    Condition-true keeps conditional assets at their resolved values.
    Condition-false omits those assets (trigger did not fire / asset does not move).
    Within each outcome, pick early/late bands still widen the delta envelope.
    """

    def side_bounds(
        legs: list[tuple[float, float, float, bool]], *, include_conditional: bool
    ) -> tuple[float, float]:
        low = 0.0
        high = 0.0
        for _, leg_low, leg_high, is_conditional in legs:
            if is_conditional and not include_conditional:
                continue
            low += leg_low
            high += leg_high
        return low, high

    has_conditional = any(is_cond for *_, is_cond in send_legs + receive_legs)
    include_flags = (True, False) if has_conditional else (True,)
    deltas: list[float] = []
    for include_conditional in include_flags:
        send_low, send_high = side_bounds(send_legs, include_conditional=include_conditional)
        recv_low, recv_high = side_bounds(receive_legs, include_conditional=include_conditional)
        deltas.append(recv_low - send_high)
        deltas.append(recv_high - send_low)
    return min(deltas), max(deltas)


def _asset_value_bundle(
    resolution: AssetResolution,
    inventory: PickInventory,
    value_index: dict[str, FCRecord],
    pick_index: Mapping[str, FCRecord],
    overlay: Mapping[str, float],
    *,
    overlay_precedence: str,
    overlay_disagreement_pct: float,
) -> tuple[Any, float | None, float | None]:
    if resolution.asset_type == "player" and resolution.resolved_id:
        value, sources, _, _ = merge_player_value(
            resolution.resolved_id,
            value_index,
            overlay,
            valuation_source="auto",
            overlay_precedence=overlay_precedence,  # type: ignore[arg-type]
            disagreement_pct=overlay_disagreement_pct,
        )
        src = sources[0] if sources else player_value_source(resolution.resolved_id, value_index)
        # Prefer chosen merged value on the primary source view.
        if value is not None:
            src = value_source(src.source, value, timestamp=src.timestamp, enabled=True)
        return src, value, value
    pick = next(
        (pick for pick in inventory.league_picks if pick.pick_token == resolution.resolved_id),
        None,
    )
    src = pick_value_source(
        pick.round if pick else 0,
        pick=pick,
        pick_index=pick_index,
    )
    if pick is None:
        return src, src.value, src.value
    point, low, high = pick_value_range(pick, pick_index)
    if src.value is None and point is not None:
        src = value_source("config_pick_table", point, enabled=True)
    return src, low if low is not None else src.value, high if high is not None else src.value


def _asset_value_source(
    resolution: AssetResolution,
    inventory: PickInventory,
    value_index: dict[str, FCRecord],
    pick_index: Mapping[str, FCRecord] | None = None,
):
    src, _, _ = _asset_value_bundle(
        resolution,
        inventory,
        value_index,
        pick_index or {},
        {},
        overlay_precedence="overlay_wins",
        overlay_disagreement_pct=10.0,
    )
    return src


def _trade_has_picks(resolutions: list[AssetResolution]) -> bool:
    return any(resolution.asset_type == "pick" for resolution in resolutions)


_CONDITIONAL_RE = re.compile(
    r"\b(if|unless|when|whenever|conditional)\b",
    re.IGNORECASE,
)
_SWAP_RE = re.compile(r"\b(swap|pick\s*swap)\b", re.IGNORECASE)


def _detect_conditional_or_swap(assets: list[str]) -> bool:
    return any(_CONDITIONAL_RE.search(asset) or _SWAP_RE.search(asset) for asset in assets)


def _conditional_needs_clarification(assets: list[str]) -> bool:
    """Conditionals with unresolved triggers need clarification; pure swap language does not."""
    return any(_CONDITIONAL_RE.search(asset) for asset in assets)


def _trade_data_status(value_math: ValueMath, missing_assets: list[str]) -> DataStatus:
    if not value_math.per_asset or len(missing_assets) == len(value_math.per_asset):
        return DataStatus.UNAVAILABLE
    if missing_assets:
        return DataStatus.PARTIAL
    return DataStatus.COMPLETE


def _value_data_status(resolved: bool, has_value: bool) -> DataStatus:
    if not resolved:
        return DataStatus.UNAVAILABLE
    return DataStatus.COMPLETE if has_value else DataStatus.PARTIAL


def _missing_value_flag(asset: str) -> PolicyFlag:
    return PolicyFlag(
        type=FlagType.MISSING_VALUE,
        asset=asset,
        rule_source="computed",
        severity=FlagSeverity.WARNING,
        reason="No enabled value source returned a value for this asset.",
    )


def _missing_value_flags(assets: list[str]) -> list[PolicyFlag]:
    return [_missing_value_flag(asset) for asset in assets]


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
    *,
    pick_index: Mapping[str, FCRecord] | None = None,
) -> float:
    inventory = build_pick_inventory(snapshot, my_roster_id=roster_id)
    index = dict(pick_index or {})
    total = 0.0
    for pick in inventory.owned_picks:
        src = pick_value_source(pick.round, pick=pick, pick_index=index)
        if src.value is not None:
            total += float(src.value)
    return total


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
