from __future__ import annotations

from tests.conftest import load_fixture
from yellow_sleeper.analyze.pipelines import (
    analyze_trade_pipeline,
    best_player_available_output,
    find_roster_output,
    get_my_roster_output,
    health_check_output,
    list_my_picks_output,
)
from yellow_sleeper.config import DynamicPolicy
from yellow_sleeper.models import DataStatus, PolicyStatus, ResolutionStatus


def test_smoke_1_health_check_standard_envelope() -> None:
    result = health_check_output(
        cache_status={
            "sleeper_players_nfl": "cached",
            "fantasycalc_values": "cached",
            "league_snapshot": "fresh",
            "draft_state": "cached",
        },
        league_id="1234567890",
        user="casey",
        config_sources=[".yellow-sleeper.yaml", "env"],
    )

    assert result.schema_version == "1.0"
    assert result.policy_status == PolicyStatus.OK
    assert result.resolution_status == ResolutionStatus.OK
    assert result.data_status == DataStatus.COMPLETE
    assert result.policy_flags == []
    assert result.source_notes


def test_smoke_2_my_roster_surfaces_values_and_policy_flags(sleeper_snapshot: dict) -> None:
    result = get_my_roster_output(
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="casey",
        policy=DynamicPolicy(protected_players=["Jayden Daniels"]),
        config_sources=[".yellow-sleeper.yaml"],
    )

    assert result.data_status == DataStatus.COMPLETE
    assert any(group.position == "QB" and group.players for group in result.grouped_roster)
    assert result.policy_flags[0].asset == "Jayden Daniels"
    assert result.source_notes


def test_smoke_3_find_roster_three_mikes_needs_clarification(sleeper_snapshot: dict) -> None:
    result = find_roster_output("mike", sleeper_snapshot)

    assert result.resolution_status == ResolutionStatus.NEEDS_CLARIFICATION
    assert result.matched is None
    assert len(result.alternatives) >= 2
    assert result.policy_flags[0].type.value == "ambiguous_resolution"


def test_smoke_4_pick_inventory_native_grid_plus_overlay(sleeper_snapshot: dict) -> None:
    result = list_my_picks_output(
        snapshot=sleeper_snapshot,
        my_roster_id=11,
        seasons=[2027],
        include_traded_away=True,
    )

    owned = {pick.pick_token for pick in result.owned_picks}
    away = {pick.pick_token for pick in result.traded_away_picks}
    assert "pick_2027_r1_orig11" in owned
    assert "pick_2027_r1_orig3" in owned
    assert "pick_2027_r2_orig11" in away
    assert result.data_status == DataStatus.COMPLETE


def test_smoke_5_blocked_trade_with_hard_untouchable(sleeper_snapshot: dict) -> None:
    result = analyze_trade_pipeline(
        my_send=["Drake London"],
        my_receive=["Bijan Robinson"],
        policy=DynamicPolicy(hard_untouchables=["Drake London"]),
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="casey",
        config_sources=[".yellow-sleeper.yaml"],
    )

    assert result.policy_status == PolicyStatus.BLOCKED
    assert result.data_status == DataStatus.UNAVAILABLE
    assert result.value_math is None
    assert result.roster_context is None
    assert result.blocking_rules[0].asset == "Drake London"


def test_smoke_6_best_player_available_excludes_drafted_rookies() -> None:
    players = load_fixture("sleeper/players_nfl.json")
    values = load_fixture("fantasycalc/values_current.json")
    draft_state = {
        "draft": load_fixture("sleeper/draft.json"),
        "picks": load_fixture("sleeper/draft_picks.json"),
    }

    result = best_player_available_output(
        players=players,
        values=values,
        draft_state=draft_state,
        position=None,
        limit=10,
    )

    candidate_ids = {candidate.sleeper_id for candidate in result.candidates}
    assert "11500" in candidate_ids
    assert "11501" not in candidate_ids
    assert "11502" not in candidate_ids
    assert all(
        "not_already_drafted:true" in candidate.inclusion_reasons
        for candidate in result.candidates
    )


def test_smoke_overlay_synthetic_row_overrides_fantasycalc() -> None:
    from yellow_sleeper.analyze.pipelines import get_player_value_output
    from yellow_sleeper.analyze.value import OverlayResult

    result = get_player_value_output(
        player="Harold Fannin",
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        overlay=OverlayResult(status="loaded", values={"9991": 5000.0}),
        league_format="14-team SF PPR 0.5 TEP",
    )
    assert result.value == 5000
    assert result.source_notes[0].source == "xlsx"
    assert result.source_disagreement is not None


def test_smoke_conditional_or_swap_is_partial_range_not_one_value(sleeper_snapshot: dict) -> None:
    result = analyze_trade_pipeline(
        my_send=["Jaylen Wright if he plays 10 games"],
        my_receive=["Harold Fannin"],
        policy=DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="casey",
        league_format="14-team SF PPR 0.5 TEP",
    )
    assert any(flag.type.value == "conditional_or_swap_trade" for flag in result.policy_flags)
    assert result.resolution_status == ResolutionStatus.NEEDS_CLARIFICATION
    assert result.data_status == DataStatus.PARTIAL
    assert result.value_math is not None
    assert result.value_math.delta is None
    assert result.value_math.delta_min is not None
    assert result.value_math.delta_max is not None
    assert result.value_math.delta_min != result.value_math.delta_max
