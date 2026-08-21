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
        user="brad",
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
        sleeper_username="brad",
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


def test_smoke_7_pick_ladder_differentiates_early_vs_late(sleeper_snapshot: dict) -> None:
    from yellow_sleeper.analyze.value import pick_records_by_name, pick_value_source
    from yellow_sleeper.models import Pick

    values = load_fixture("fantasycalc/values_current.json")
    pick_index = pick_records_by_name(values)
    early = Pick(
        pick_token="pick_2027_r1_orig1",
        display_name="2027 1st",
        season=2027,
        round=1,
        original_owner_roster_id=1,
        original_owner_name="A",
        current_owner_roster_id=1,
        origin="native",
    )
    late = Pick(
        pick_token="pick_2027_r1_orig14",
        display_name="2027 1st",
        season=2027,
        round=1,
        original_owner_roster_id=14,
        original_owner_name="N",
        current_owner_roster_id=14,
        origin="native",
    )
    early_src = pick_value_source(1, pick=early, pick_index=pick_index)
    late_src = pick_value_source(1, pick=late, pick_index=pick_index)
    assert early_src.source == "fantasycalc"
    assert late_src.source == "fantasycalc"
    assert early_src.value == 4500
    assert late_src.value == 2200

    result = analyze_trade_pipeline(
        my_send=["2027 3rd"],
        my_receive=["Jaylen Wright"],
        policy=DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=values,
        sleeper_username="brad",
    )
    assert result.value_math is not None
    send_asset = next(item for item in result.value_math.per_asset if item["side"] == "send")
    # No FC 2027 3rd ladder row → static config_pick_table fallback still works.
    assert send_asset["value"] in {600, 1200, 3000}
    assert result.value_math.delta_min is not None
    assert result.value_math.delta_max is not None


def test_smoke_8_overlay_wins_and_source_disagreement(sleeper_snapshot: dict) -> None:
    from yellow_sleeper.analyze.pipelines import get_player_value_output

    result = get_player_value_output(
        player="Harold Fannin",
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        valuation_source="auto",
        overlay={"9991": 5000.0},
        overlay_precedence="overlay_wins",
        overlay_disagreement_pct=10.0,
        tep_tier="te+",
    )
    assert result.value == 5000
    assert result.source_disagreement is not None
    assert any(flag.type.value == "source_disagreement" for flag in result.policy_flags)


def test_smoke_9_conditional_trade_flags_and_partial_range(sleeper_snapshot: dict) -> None:
    result = analyze_trade_pipeline(
        my_send=["Jaylen Wright if he plays 10 games"],
        my_receive=["2027 1st"],
        policy=DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="brad",
    )
    assert any(flag.type.value == "conditional_or_swap_trade" for flag in result.policy_flags)
    assert result.resolution_status == ResolutionStatus.NEEDS_CLARIFICATION
    assert result.data_status == DataStatus.PARTIAL
