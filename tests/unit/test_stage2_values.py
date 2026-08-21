from __future__ import annotations

from pathlib import Path

from tests.conftest import load_fixture
from yellow_sleeper.analyze.value import (
    load_overlay_values,
    match_fantasycalc_pick,
    merge_player_value,
    pick_records_by_name,
    pick_value_range,
    pick_value_source,
    values_by_sleeper_id,
)
from yellow_sleeper.models import Pick


def test_values_by_sleeper_id_excludes_picks() -> None:
    values = load_fixture("fantasycalc/values_current.json")
    index = values_by_sleeper_id(values)
    assert "9745" in index
    assert "FP_2027_early_0" not in index


def test_match_fantasycalc_pick_prefers_band_then_generic() -> None:
    values = load_fixture("fantasycalc/values_current.json")
    pick_index = pick_records_by_name(values)
    early_pick = Pick(
        pick_token="pick_2027_r1_orig1",
        display_name="2027 1st",
        season=2027,
        round=1,
        original_owner_roster_id=1,
        original_owner_name="A",
        current_owner_roster_id=1,
        origin="native",
    )
    late_pick = Pick(
        pick_token="pick_2027_r1_orig14",
        display_name="2027 1st",
        season=2027,
        round=1,
        original_owner_roster_id=14,
        original_owner_name="N",
        current_owner_roster_id=14,
        origin="native",
    )
    early = match_fantasycalc_pick(early_pick, pick_index)
    late = match_fantasycalc_pick(late_pick, pick_index)
    assert early is not None and late is not None
    assert early.value == 4500
    assert late.value == 2200
    assert early.value > late.value


def test_pick_value_source_uses_fantasycalc_then_falls_back() -> None:
    values = load_fixture("fantasycalc/values_current.json")
    pick_index = pick_records_by_name(values)
    pick = Pick(
        pick_token="pick_2027_r1_orig6",
        display_name="2027 1st",
        season=2027,
        round=1,
        original_owner_roster_id=6,
        original_owner_name="F",
        current_owner_roster_id=6,
        origin="native",
    )
    src = pick_value_source(1, pick=pick, pick_index=pick_index)
    assert src.source == "fantasycalc"
    assert src.value == 3200

    missing = pick_value_source(3, pick=None, pick_index={})
    assert missing.source == "config_pick_table"
    assert missing.value == 600


def test_pick_value_range_spans_early_to_late() -> None:
    values = load_fixture("fantasycalc/values_current.json")
    pick_index = pick_records_by_name(values)
    pick = Pick(
        pick_token="pick_2027_r1_orig6",
        display_name="2027 1st",
        season=2027,
        round=1,
        original_owner_roster_id=6,
        original_owner_name="F",
        current_owner_roster_id=6,
        origin="native",
    )
    point, low, high = pick_value_range(pick, pick_index)
    assert point == 3200
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
