from __future__ import annotations

from pathlib import Path

from tests.conftest import load_fixture
from yellow_sleeper.analyze.pipelines import (
    _scenario_delta_bounds,
    _strip_conditional_clause,
    analyze_trade_pipeline,
)
from yellow_sleeper.analyze.value import (
    load_overlay_values,
    match_fantasycalc_pick,
    merge_player_value,
    pick_records_by_name,
    pick_value_range,
    pick_value_source,
    values_by_sleeper_id,
)
from yellow_sleeper.config import DynamicPolicy
from yellow_sleeper.models import Pick


def _pick(token_suffix: str, roster_id: int) -> Pick:
    return Pick(
        pick_token=f"pick_2027_r1_orig{token_suffix}",
        display_name="2027 1st",
        season=2027,
        round=1,
        original_owner_roster_id=roster_id,
        original_owner_name="X",
        current_owner_roster_id=roster_id,
        origin="native",
    )


def test_values_by_sleeper_id_excludes_picks() -> None:
    values = load_fixture("fantasycalc/values_current.json")
    index = values_by_sleeper_id(values)
    assert "9745" in index
    assert "FP_2027_early_0" not in index


def test_match_fantasycalc_pick_defaults_to_generic_not_roster_id() -> None:
    values = load_fixture("fantasycalc/values_current.json")
    pick_index = pick_records_by_name(values)
    early_like = _pick("1", 1)
    late_like = _pick("14", 14)
    # Without projected_slot, roster_id must not drive band selection.
    a = match_fantasycalc_pick(early_like, pick_index)
    b = match_fantasycalc_pick(late_like, pick_index)
    assert a is not None and b is not None
    assert a.value == 3000
    assert b.value == 3000


def test_match_fantasycalc_pick_uses_projected_slot_band() -> None:
    values = load_fixture("fantasycalc/values_current.json")
    pick_index = pick_records_by_name(values)
    pick = _pick("1", 99)
    early = match_fantasycalc_pick(pick, pick_index, projected_slot=1)
    late = match_fantasycalc_pick(pick, pick_index, projected_slot=14)
    assert early is not None and late is not None
    assert early.value == 4500
    assert late.value == 2200
    assert early.value > late.value


def test_pick_value_source_uses_fantasycalc_then_falls_back() -> None:
    values = load_fixture("fantasycalc/values_current.json")
    pick_index = pick_records_by_name(values)
    pick = _pick("6", 6)
    src = pick_value_source(1, pick=pick, pick_index=pick_index)
    assert src.source == "fantasycalc"
    assert src.value == 3000

    missing = pick_value_source(3, pick=None, pick_index={})
    assert missing.source == "config_pick_table"
    assert missing.value == 600


def test_pick_value_range_spans_early_to_late() -> None:
    values = load_fixture("fantasycalc/values_current.json")
    pick_index = pick_records_by_name(values)
    pick = _pick("6", 6)
    point, low, high = pick_value_range(pick, pick_index)
    assert point == 3000
    assert low == 2200
    assert high == 4500


def test_load_overlay_and_merge_overlay_wins(tmp_path: Path) -> None:
    path = tmp_path / "values.csv"
    path.write_text("sleeper_id,value\n9991,5000\n", encoding="utf-8")
    overlay = load_overlay_values(path)
    values = load_fixture("fantasycalc/values_current.json")
    index = values_by_sleeper_id(values)
    chosen, sources, disagreement, missing = merge_player_value(
        "9991",
        index,
        overlay,
        valuation_source="auto",
        overlay_precedence="overlay_wins",
        disagreement_pct=10.0,
    )
    assert chosen == 5000
    assert {source.source for source in sources} == {"fantasycalc", "xlsx"}
    assert disagreement is not None
    assert disagreement.max_delta_pct > 10
    assert missing == []


def test_strip_conditional_clause_keeps_base_asset() -> None:
    assert _strip_conditional_clause("2027 1st (if Team A makes playoffs)") == "2027 1st"
    assert _strip_conditional_clause("Jaylen Wright if he plays 10 games") == "Jaylen Wright"
    assert _strip_conditional_clause("Mahomes") == "Mahomes"


def test_scenario_delta_bounds_include_vs_exclude_conditional() -> None:
    # Send conditional player 1000; receive unconditional 3000.
    send = [(1000.0, 1000.0, 1000.0, True)]
    receive = [(3000.0, 3000.0, 3000.0, False)]
    low, high = _scenario_delta_bounds(send, receive)
    # True: 3000-1000=2000; False: 3000-0=3000
    assert low == 2000.0
    assert high == 3000.0


def test_trade_conditional_ranges_diverge(sleeper_snapshot: dict) -> None:
    values = load_fixture("fantasycalc/values_current.json")
    players = load_fixture("sleeper/players_nfl.json")
    result = analyze_trade_pipeline(
        my_send=["Jaylen Wright if he plays 10 games"],
        my_receive=["2027 1st"],
        policy=DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=players,
        values=values,
        sleeper_username="brad",
    )
    assert result.value_math is not None
    assert result.value_math.delta_min is not None
    assert result.value_math.delta_max is not None
    assert result.value_math.delta_min < result.value_math.delta_max
    # Base player name resolves despite the conditional clause.
    assert any(res.resolved_id == "11620" for res in result.asset_resolution)
