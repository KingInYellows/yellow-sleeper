from __future__ import annotations

from copy import deepcopy
from typing import Any

from tests.conftest import load_fixture
from yellow_sleeper.analyze import (
    build_pick_inventory,
    build_roster_lineup,
    find_roster_id_for_username,
)
from yellow_sleeper.analyze.pipelines import (
    analyze_trade_pipeline,
    get_my_roster_output,
    list_traded_picks_output,
)
from yellow_sleeper.config import DynamicPolicy
from yellow_sleeper.models import DataStatus, ResolutionStatus


def _omit_usernames(snapshot: dict[str, Any]) -> dict[str, Any]:
    mutated = deepcopy(snapshot)
    for user in mutated["users"]:
        user.pop("username", None)
        if user.get("user_id") == "u11":
            user["display_name"] = "BradSchwarzkopf"
    return mutated


def _completed_2026_draft(snapshot: dict[str, Any]) -> dict[str, Any]:
    mutated = deepcopy(snapshot)
    mutated["league"] = {**mutated["league"], "status": "in_season"}
    mutated["drafts"] = [
        {**draft, "status": "complete"} if str(draft.get("season")) == "2026" else draft
        for draft in mutated["drafts"]
    ]
    mutated["traded_picks"] = [
        *mutated["traded_picks"],
        {"season": "2026", "round": 2, "roster_id": 11, "previous_owner_id": 11, "owner_id": 4},
    ]
    return mutated


def _overcapacity_live_roster(snapshot: dict[str, Any]) -> dict[str, Any]:
    mutated = deepcopy(snapshot)
    mutated["league"] = {
        **mutated["league"],
        "roster_positions": [
            "QB",
            "RB",
            "RB",
            "WR",
            "WR",
            "WR",
            "TE",
            "FLEX",
            "SUPER_FLEX",
            *["BN"] * 16,
        ],
    }
    extra_ids = [f"9{index:03d}" for index in range(29)]
    mutated["rosters"][10] = {
        **mutated["rosters"][10],
        "players": ["6786", "9745", "12345", "9991", *extra_ids],
        "starters": ["6786", "9745", "12345", "0", "0", "0", "0", "0", "0"],
        "reserve": None,
        "taxi": None,
    }
    return mutated


def test_find_roster_id_live_users_omit_username_key(sleeper_snapshot: dict) -> None:
    snapshot = _omit_usernames(sleeper_snapshot)

    assert find_roster_id_for_username(snapshot, "brad") == 11
    assert find_roster_id_for_username(snapshot, "BradSchwarzkopf") == 11
    assert find_roster_id_for_username(snapshot, "YELLOW SLEEPER") == 11


def test_find_roster_id_never_invents_roster_zero(sleeper_snapshot: dict) -> None:
    assert find_roster_id_for_username(sleeper_snapshot, "nobody-in-this-league") is None
    assert find_roster_id_for_username(sleeper_snapshot, "") is None


def test_analyze_trade_does_not_fall_back_to_roster_zero(sleeper_snapshot: dict) -> None:
    result = analyze_trade_pipeline(
        my_send=["Drake London"],
        my_receive=["Bijan Robinson"],
        policy=DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="not-a-league-member",
    )

    assert result.resolution_status == ResolutionStatus.NEEDS_CLARIFICATION
    assert result.data_status == DataStatus.UNAVAILABLE
    assert result.value_math is None
    assert result.roster_context is None


def test_completed_rookie_draft_drops_spent_season_from_capital(
    sleeper_snapshot: dict,
) -> None:
    snapshot = _completed_2026_draft(sleeper_snapshot)
    inventory = build_pick_inventory(snapshot, my_roster_id=11, include_traded_away=True)

    owned_seasons = {pick.season for pick in inventory.owned_picks}
    away_seasons = {pick.season for pick in inventory.traded_away_picks}
    owned_tokens = {pick.pick_token for pick in inventory.owned_picks}

    assert 2026 not in owned_seasons
    assert 2026 not in away_seasons
    assert 2027 in owned_seasons
    assert 2028 in owned_seasons
    assert 2029 in owned_seasons
    assert "pick_2026_r1_orig11" not in owned_tokens
    assert "pick_2027_r2_orig11" not in owned_tokens
    assert any(pick.season == 2026 and pick.round == 2 for pick in inventory.traded_picks)


def test_drafting_season_still_counts_current_year_as_capital(sleeper_snapshot: dict) -> None:
    inventory = build_pick_inventory(sleeper_snapshot, my_roster_id=11)

    assert any(pick.season == 2026 for pick in inventory.owned_picks)
    assert not any(pick.season == 2029 for pick in inventory.owned_picks)


def test_list_traded_picks_returns_full_68_row_market(sleeper_snapshot: dict) -> None:
    snapshot = deepcopy(sleeper_snapshot)
    snapshot["traded_picks"] = [
        {
            "season": "2027",
            "round": (index % 5) + 1,
            "roster_id": (index % 14) + 1,
            "previous_owner_id": (index % 14) + 1,
            "owner_id": ((index + 3) % 14) + 1,
        }
        for index in range(68)
    ]

    result = list_traded_picks_output(snapshot=snapshot, my_roster_id=11)

    assert result.total_count == 68
    assert len(result.picks) == 68
    assert result.truncated is False
    assert result.data_status == DataStatus.COMPLETE


def test_list_traded_picks_flags_truncation_instead_of_silent_drop(
    sleeper_snapshot: dict,
) -> None:
    snapshot = deepcopy(sleeper_snapshot)
    snapshot["traded_picks"] = [
        {
            "season": "2027",
            "round": (index % 5) + 1,
            "roster_id": (index % 14) + 1,
            "previous_owner_id": (index % 14) + 1,
            "owner_id": ((index + 1) % 14) + 1,
        }
        for index in range(201)
    ]

    result = list_traded_picks_output(snapshot=snapshot, my_roster_id=11)

    assert result.total_count == 201
    assert len(result.picks) == 200
    assert result.truncated is True
    assert result.data_status == DataStatus.PARTIAL
    assert any(note.explanation and "201" in note.explanation for note in result.source_notes)


def test_roster_lineup_treats_null_benches_and_zero_starters() -> None:
    roster = {
        "players": ["6786", "9745", "12345"],
        "starters": ["6786", "9745", "0", "0"],
        "reserve": None,
        "taxi": None,
    }
    positions = ["QB", "RB", "TE", "FLEX", "BN", "BN", "IR", "TAXI"]
    players = load_fixture("sleeper/players_nfl.json")

    lineup = build_roster_lineup(roster, positions, players)

    assert [slot.slot_position for slot in lineup.starters] == ["QB", "RB", "TE", "FLEX"]
    assert lineup.starters[0].empty is False
    assert lineup.starters[0].name == "Jayden Daniels"
    assert lineup.starters[2].empty is True
    assert lineup.starters[2].sleeper_id is None
    assert lineup.starters[2].slot_position == "TE"
    assert lineup.starters[3].empty is True
    assert lineup.starters[3].slot_position == "FLEX"
    assert len(lineup.reserve) == 1
    assert lineup.reserve[0].slot_position == "IR"
    assert lineup.reserve[0].empty is True
    assert lineup.taxi[0].empty is True
    assert lineup.taxi[0].slot_position == "TAXI"
    assert lineup.player_count == 3
    assert lineup.roster_spots == 8
    assert lineup.over_capacity is False


def test_get_my_roster_surfaces_overcapacity_and_empty_starters(sleeper_snapshot: dict) -> None:
    snapshot = _overcapacity_live_roster(sleeper_snapshot)
    result = get_my_roster_output(
        snapshot=snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="brad",
        policy=DynamicPolicy(),
        config_sources=[".yellow-sleeper.yaml"],
    )

    assert result.player_count == 33
    assert result.roster_spots == 25
    assert result.over_capacity is True
    assert result.reserve == []
    assert result.taxi == []
    empty_starter_positions = [slot.slot_position for slot in result.starters if slot.empty]
    assert "TE" in empty_starter_positions
    assert "FLEX" in empty_starter_positions
