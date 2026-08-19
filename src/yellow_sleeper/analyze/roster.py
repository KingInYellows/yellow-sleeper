from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from ..models import LineupSlot, Pick, TradedPick
from ..resolve.picks import pick_token, round_label
from ..resolve.rosters import resolve_roster

logger = logging.getLogger("yellow_sleeper.analyze.roster")

_EMPTY_SLOT_IDS = frozenset({"", "0", "none", "null"})
_BENCH_OR_RESERVE_SLOTS = frozenset({"BN", "IR", "TAXI"})
_IR_SLOTS = frozenset({"IR"})
_TAXI_SLOTS = frozenset({"TAXI"})
_COMPACT_QUERY_MIN_LEN = 4


@dataclass(frozen=True)
class PickInventory:
    league_picks: list[Pick]
    owned_picks: list[Pick]
    traded_away_picks: list[Pick]
    traded_picks: list[TradedPick]
    unresolved: list[str]


@dataclass(frozen=True)
class RosterLineup:
    starters: list[LineupSlot]
    reserve: list[LineupSlot]
    taxi: list[LineupSlot]
    player_count: int
    roster_spots: int
    over_capacity: bool


def current_season(snapshot: dict[str, Any], *, fallback: int = 2026) -> int:
    league = snapshot.get("league", {})
    value = league.get("season") or league.get("metadata", {}).get("season")
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.warning(
            "current_season: could not parse league season %r, falling back to %d",
            value,
            fallback,
        )
        return fallback


def default_capital_seasons(snapshot: dict[str, Any], *, count: int = 3) -> list[int]:
    """Seasons that still count as pick capital: current draft + two forward.

    After the current season's rookie draft is complete, those picks are players,
    not capital. Shift the window forward so the native grid starts at season+1.
    """
    start = current_season(snapshot)
    if season_rookie_draft_complete(snapshot, start):
        start += 1
    return [start + offset for offset in range(count)]


def default_market_seasons(snapshot: dict[str, Any], *, count: int = 3) -> list[int]:
    """Default traded-pick market window: current league season + two forward."""
    start = current_season(snapshot)
    return [start + offset for offset in range(count)]


def season_rookie_draft_complete(snapshot: dict[str, Any], season: int) -> bool:
    matching = [
        draft
        for draft in snapshot.get("drafts") or []
        if isinstance(draft, Mapping) and _draft_season(draft) == season
    ]
    if matching:
        return all(_draft_is_complete(draft) for draft in matching)
    if season > current_season(snapshot):
        return False
    league = snapshot.get("league") or {}
    return str(league.get("status") or "").lower() == "in_season"


def find_roster_id_for_username(snapshot: dict[str, Any], username: str) -> int | None:
    """Map a configured owner query to exactly one roster, or None.

    Live Sleeper /users objects often omit `username` entirely. Match
    case-insensitively on username, display_name, and metadata.team_name,
    then a unique compact substring (so "brad" resolves to BradSchwarzkopf),
    then the existing fuzzy roster resolver. Never invent roster 0.
    """
    query = str(username or "").strip()
    if not query:
        return None

    exact = _roster_ids_for_users(snapshot, query, _identity_exact_match)
    if len(exact) == 1:
        return exact[0]
    if len(exact) > 1:
        return None

    compact = _roster_ids_for_users(snapshot, query, _identity_compact_match)
    if len(compact) == 1:
        return compact[0]
    if len(compact) > 1:
        return None

    resolution = resolve_roster(query, snapshot.get("rosters") or [], snapshot.get("users") or [])
    if resolution.matched is None:
        return None
    return int(resolution.matched.roster_id)


def build_roster_lineup(
    roster: Mapping[str, Any],
    roster_positions: list[str],
    players: Mapping[str, Any],
) -> RosterLineup:
    starter_positions = [pos for pos in roster_positions if pos not in _BENCH_OR_RESERVE_SLOTS]
    ir_positions = [pos for pos in roster_positions if pos in _IR_SLOTS]
    taxi_positions = [pos for pos in roster_positions if pos in _TAXI_SLOTS]
    player_ids = [_filled_slot_id(raw) for raw in _as_id_list(roster.get("players"))]
    real_players = [player_id for player_id in player_ids if player_id is not None]
    roster_spots = len(roster_positions)
    return RosterLineup(
        starters=_slots_for(
            _as_id_list(roster.get("starters")),
            starter_positions,
            default_position="FLEX",
            players=players,
        ),
        reserve=_slots_for(
            _as_id_list(roster.get("reserve")),
            ir_positions,
            default_position="IR",
            players=players,
        ),
        taxi=_slots_for(
            _as_id_list(roster.get("taxi")),
            taxi_positions,
            default_position="TAXI",
            players=players,
        ),
        player_count=len(real_players),
        roster_spots=roster_spots,
        over_capacity=roster_spots > 0 and len(real_players) > roster_spots,
    )


def build_pick_inventory(
    snapshot: dict[str, Any],
    *,
    my_roster_id: int,
    seasons: list[int] | None = None,
    include_traded_away: bool = False,
    rounds: int = 5,
) -> PickInventory:
    capital_seasons = [
        season
        for season in (seasons or default_capital_seasons(snapshot))
        if not season_rookie_draft_complete(snapshot, season)
    ]
    market_seasons = seasons or default_market_seasons(snapshot)
    rosters = [int(roster["roster_id"]) for roster in snapshot.get("rosters", [])]
    names = _roster_names(snapshot)
    grid: dict[tuple[int, int, int], int] = {
        (season, round_number, roster_id): roster_id
        for season in capital_seasons
        for round_number in range(1, rounds + 1)
        for roster_id in rosters
    }
    unresolved: list[str] = []

    for traded in snapshot.get("traded_picks", []):
        try:
            season = int(traded["season"])
            round_number = int(traded["round"])
            original = int(traded["roster_id"])
            owner = int(traded["owner_id"])
        except (KeyError, TypeError, ValueError) as exc:
            unresolved.append(f"invalid traded_picks record: {exc}")
            continue
        key = (season, round_number, original)
        if season not in capital_seasons:
            continue
        if key not in grid:
            unresolved.append(f"{season} round {round_number} original roster {original}")
            continue
        grid[key] = owner

    league_picks = [
        _pick_from_grid(
            season=season,
            round_number=round_number,
            original_owner=original,
            current_owner=current_owner,
            my_roster_id=my_roster_id,
            names=names,
        )
        for (season, round_number, original), current_owner in sorted(grid.items())
    ]
    owned = [pick for pick in league_picks if pick.current_owner_roster_id == my_roster_id]
    traded_away = [
        pick
        for pick in league_picks
        if (
            pick.original_owner_roster_id == my_roster_id
            and pick.current_owner_roster_id != my_roster_id
        )
    ]
    traded_picks = _traded_pick_models(snapshot, market_seasons, names, unresolved)
    return PickInventory(
        league_picks=league_picks,
        owned_picks=owned,
        traded_away_picks=traded_away if include_traded_away else [],
        traded_picks=traded_picks,
        unresolved=unresolved,
    )


def _pick_from_grid(
    *,
    season: int,
    round_number: int,
    original_owner: int,
    current_owner: int,
    my_roster_id: int,
    names: dict[int, str],
) -> Pick:
    if original_owner == my_roster_id and current_owner == my_roster_id:
        origin = "native"
        display = f"{season} {round_label(round_number)} (native)"
    elif current_owner == my_roster_id:
        origin = "traded_in"
        original_name = names.get(original_owner, original_owner)
        display = f"{season} {round_label(round_number)} (via {original_name})"
    elif original_owner == my_roster_id:
        origin = "traded_away"
        display = (
            f"{season} {round_label(round_number)} "
            f"(traded away to {names.get(current_owner, current_owner)})"
        )
    else:
        origin = "native" if original_owner == current_owner else "traded_in"
        original_name = names.get(original_owner, original_owner)
        display = f"{season} {round_label(round_number)} (via {original_name})"
    return Pick(
        pick_token=pick_token(season, round_number, original_owner),
        display_name=display,
        season=season,
        round=round_number,
        original_owner_roster_id=original_owner,
        original_owner_name=str(names.get(original_owner, f"Roster {original_owner}")),
        current_owner_roster_id=current_owner,
        origin=origin,
    )


def _traded_pick_models(
    snapshot: dict[str, Any],
    seasons: list[int],
    names: dict[int, str],
    unresolved: list[str],
) -> list[TradedPick]:
    picks: list[TradedPick] = []
    for raw in snapshot.get("traded_picks", []):
        try:
            season = int(raw["season"])
            if season not in seasons:
                continue
            round_number = int(raw["round"])
            original = int(raw["roster_id"])
            current = int(raw["owner_id"])
            previous = raw.get("previous_owner_id")
            previous_owner = int(previous) if previous is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            unresolved.append(f"invalid traded_picks record (model): {exc}")
            continue
        picks.append(
            TradedPick(
                pick_token=pick_token(season, round_number, original),
                display_name=(
                    f"{season} {round_label(round_number)} "
                    f"(via {names.get(original, f'Roster {original}')})"
                ),
                season=season,
                round=round_number,
                original_owner_roster_id=original,
                previous_owner_roster_id=previous_owner,
                current_owner_roster_id=current,
                original_owner_name=str(names.get(original, f"Roster {original}")),
                current_owner_name=str(names.get(current, f"Roster {current}")),
            )
        )
    return picks


def _roster_names(snapshot: dict[str, Any]) -> dict[int, str]:
    users = {user.get("user_id"): user for user in snapshot.get("users", [])}
    names: dict[int, str] = {}
    for roster in snapshot.get("rosters", []):
        roster_id = int(roster["roster_id"])
        user = users.get(roster.get("owner_id"), {})
        names[roster_id] = str(
            user.get("display_name") or user.get("username") or f"Roster {roster_id}"
        )
    return names


def _draft_season(draft: Mapping[str, Any]) -> int | None:
    try:
        return int(draft.get("season"))
    except (TypeError, ValueError):
        return None


def _draft_is_complete(draft: Mapping[str, Any]) -> bool:
    return str(draft.get("status") or "").lower() == "complete"


def _user_identity_fields(user: Mapping[str, Any]) -> list[str]:
    metadata = user.get("metadata") if isinstance(user.get("metadata"), dict) else {}
    values: list[str] = []
    for raw in (user.get("username"), user.get("display_name"), metadata.get("team_name")):
        if raw:
            values.append(str(raw))
    return values


def _identity_exact_match(query: str, value: str) -> bool:
    return query.casefold() == value.casefold()


def _identity_compact_match(query: str, value: str) -> bool:
    compact_query = _compact_identity(query)
    compact_value = _compact_identity(value)
    return (
        len(compact_query) >= _COMPACT_QUERY_MIN_LEN
        and compact_query in compact_value
    )


def _compact_identity(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def _roster_ids_for_users(
    snapshot: dict[str, Any],
    query: str,
    matcher: Callable[[str, str], bool],
) -> list[int]:
    matched_user_ids = {
        user.get("user_id")
        for user in snapshot.get("users") or []
        if isinstance(user, Mapping)
        and any(matcher(query, value) for value in _user_identity_fields(user))
    }
    roster_ids: list[int] = []
    for roster in snapshot.get("rosters") or []:
        if roster.get("owner_id") in matched_user_ids:
            roster_ids.append(int(roster["roster_id"]))
    return roster_ids


def _as_id_list(raw: Any) -> list[Any]:
    return list(raw) if isinstance(raw, list) else []


def _filled_slot_id(raw: Any) -> str | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text.casefold() in _EMPTY_SLOT_IDS:
        return None
    return text


def _slots_for(
    raw_ids: list[Any],
    positions: list[str],
    *,
    default_position: str,
    players: Mapping[str, Any],
) -> list[LineupSlot]:
    count = max(len(raw_ids), len(positions))
    slots: list[LineupSlot] = []
    for index in range(count):
        position = positions[index] if index < len(positions) else default_position
        sleeper_id = _filled_slot_id(raw_ids[index]) if index < len(raw_ids) else None
        name = None
        if sleeper_id is not None:
            record = players.get(sleeper_id)
            if isinstance(record, Mapping):
                name = str(record.get("full_name") or record.get("search_full_name") or sleeper_id)
            else:
                name = sleeper_id
        slots.append(
            LineupSlot(
                index=index,
                slot_position=position,
                sleeper_id=sleeper_id,
                name=name,
                empty=sleeper_id is None,
            )
        )
    return slots
