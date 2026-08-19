from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from ..models import Pick, TradedPick
from ..resolve.picks import pick_token, round_label

logger = logging.getLogger("yellow_sleeper.analyze.roster")


@dataclass(frozen=True)
class PickInventory:
    league_picks: list[Pick]
    owned_picks: list[Pick]
    traded_away_picks: list[Pick]
    traded_picks: list[TradedPick]
    unresolved: list[str]


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


def find_roster_id_for_username(snapshot: dict[str, Any], username: str) -> int | None:
    needle = (username or "").strip().lower()
    if not needle:
        return None
    user_id = None
    for user in snapshot.get("users", []):
        metadata = user.get("metadata") if isinstance(user.get("metadata"), dict) else {}
        candidates = [
            user.get("username"),
            user.get("display_name"),
            metadata.get("team_name"),
            user.get("user_id"),
        ]
        if any(_norm(candidate) == needle for candidate in candidates):
            user_id = user.get("user_id")
            break
    if user_id is None:
        return None
    for roster in snapshot.get("rosters", []):
        if roster.get("owner_id") == user_id:
            return int(roster["roster_id"])
    return None


def _norm(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text or None


def build_pick_inventory(
    snapshot: dict[str, Any],
    *,
    my_roster_id: int,
    seasons: list[int] | None = None,
    include_traded_away: bool = False,
    rounds: int = 5,
) -> PickInventory:
    selected_seasons = seasons or [
        current_season(snapshot),
        current_season(snapshot) + 1,
        current_season(snapshot) + 2,
    ]
    rosters = [int(roster["roster_id"]) for roster in snapshot.get("rosters", [])]
    names = _roster_names(snapshot)
    grid: dict[tuple[int, int, int], int] = {
        (season, round_number, roster_id): roster_id
        for season in selected_seasons
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
        if season not in selected_seasons:
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
    traded_picks = _traded_pick_models(snapshot, selected_seasons, names, unresolved)
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
