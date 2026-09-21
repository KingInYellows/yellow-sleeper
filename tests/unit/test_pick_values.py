from __future__ import annotations

from datetime import UTC, datetime

from tests.conftest import load_fixture
from yellow_sleeper.analyze.pipelines import (
    analyze_trade_pipeline,
    get_player_value_output,
    league_power_map_output,
)
from yellow_sleeper.analyze.value import (
    match_fantasycalc_pick,
    match_fantasycalc_pick_bands,
    pick_records_by_name,
    pick_value_source,
    resolve_pick_value,
)
from yellow_sleeper.config import DynamicPolicy
from yellow_sleeper.models import DataStatus, Pick


def _pick(season: int, round_number: int, orig: int = 11) -> Pick:
    return Pick(
        pick_token=f"pick_{season}_r{round_number}_orig{orig}",
        display_name=f"{season} round {round_number}",
        season=season,
        round=round_number,
        original_owner_roster_id=orig,
        original_owner_name="Casey",
        current_owner_roster_id=11,
        origin="native",
    )


def test_generic_pick_row_beats_static_table_and_ignores_bands() -> None:
    pick_index = pick_records_by_name(load_fixture("fantasycalc/values_current.json"))
    first = _pick(2027, 1)
    matched = match_fantasycalc_pick(first, pick_index)
    assert matched is not None
    assert matched.player.name == "2027 1st"
    assert matched.value == 4100
    source = pick_value_source(1, pick=first, pick_index=pick_index)
    assert source.source == "fantasycalc"
    assert source.value == 4100
    assert pick_index["2027 1st (early)"].value == 4500


def test_missing_pick_row_falls_back_to_labeled_static_table() -> None:
    pick_index = pick_records_by_name(load_fixture("fantasycalc/values_current.json"))
    fourth = _pick(2027, 4)
    source = pick_value_source(4, pick=fourth, pick_index=pick_index)
    assert source.source == "config_pick_table"
    assert source.value == 300.0
    empty = pick_value_source(1, pick=_pick(2027, 1), pick_index={})
    assert empty.source == "config_pick_table"
    assert empty.value == 3000.0


def test_band_rows_without_generic_are_a_range_not_a_slot() -> None:
    pick_index = pick_records_by_name(load_fixture("fantasycalc/values_current.json"))
    second = _pick(2028, 2)
    assert match_fantasycalc_pick(second, pick_index) is None
    bands = match_fantasycalc_pick_bands(second, pick_index)
    assert bands is not None
    assert bands.low == 700
    assert bands.high == 1800
    assert bands.bands == (("Early", 1800.0), ("Mid", 1100.0), ("Late", 700.0))
    resolved = resolve_pick_value(2, pick=second, pick_index=pick_index)
    assert resolved.source.source == "fantasycalc"
    assert resolved.source.value is None
    note = resolved.band_range.explanation(second) if resolved.band_range else ""
    assert "low=700" in note
    assert "high=1800" in note
    assert "Early=1800" in note
    assert "Mid=1100" in note
    assert "Late=700" in note
    assert "1200" not in note


def test_generic_row_still_wins_when_bands_also_exist() -> None:
    pick_index = pick_records_by_name(load_fixture("fantasycalc/values_current.json"))
    first = _pick(2027, 1)
    resolved = resolve_pick_value(1, pick=first, pick_index=pick_index)
    assert resolved.source.value == 4100
    assert resolved.band_range is None
    assert match_fantasycalc_pick_bands(first, pick_index) is not None


def test_trade_pick_uses_fantasycalc_generic_row(sleeper_snapshot: dict) -> None:
    result = analyze_trade_pipeline(
        my_send=["2027 1st (via Mike Johnson)"],
        my_receive=["Jaylen Wright"],
        policy=DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="casey",
        league_format="14-team SF PPR 0.5 TEP",
        values_timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=UTC),
    )
    assert result.value_math is not None
    pick_asset = next(
        asset
        for asset in result.value_math.per_asset
        if str(asset["asset"]).startswith("pick_2027_r1_")
    )
    assert pick_asset["value"] == 4100
    assert pick_asset["sources"][0].source == "fantasycalc"
    notes = " ".join(note.explanation or "" for note in result.source_notes)
    assert "PICK rows" in notes
    assert "fallback" in notes.lower()


def test_unsupported_format_does_not_use_mismatched_board() -> None:
    result = get_player_value_output(
        player="Drake London",
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        league_format="16-team SF PPR 0.5 TEP",
    )
    assert result.value is None
    assert result.data_status == DataStatus.PARTIAL
    explanation = result.source_notes[0].explanation or ""
    assert "not fetched" in explanation.lower()
    assert "16-team" in explanation or "numTeams" in explanation


def test_power_map_pick_total_uses_provider_rows(sleeper_snapshot: dict) -> None:
    values = load_fixture("fantasycalc/values_current.json")
    players_only = [row for row in values if row["player"]["position"] != "PICK"]
    with_picks = league_power_map_output(
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=values,
        include_pick_value=True,
        league_format="14-team SF PPR 0.5 TEP",
    )
    without_picks = league_power_map_output(
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=players_only,
        include_pick_value=True,
        league_format="14-team SF PPR 0.5 TEP",
    )
    casey_with = next(team for team in with_picks.teams if team.username == "casey")
    casey_without = next(team for team in without_picks.teams if team.username == "casey")
    assert casey_with.pick_total is not None
    assert casey_without.pick_total is not None
    assert casey_with.pick_total != casey_without.pick_total


def test_trade_band_only_pick_is_partial_range_not_static_slot(
    sleeper_snapshot: dict,
) -> None:
    result = analyze_trade_pipeline(
        my_send=["2028 2nd"],
        my_receive=["Jaylen Wright"],
        policy=DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="casey",
        league_format="14-team SF PPR 0.5 TEP",
        values_timestamp=datetime(2024, 1, 15, 12, 0, tzinfo=UTC),
    )
    assert result.value_math is not None
    pick_asset = next(
        asset
        for asset in result.value_math.per_asset
        if str(asset["asset"]).startswith("pick_2028_r2_")
    )
    assert pick_asset["value"] is None
    assert pick_asset["sources"][0].source == "fantasycalc"
    assert pick_asset["sources"][0].value is None
    assert result.data_status == DataStatus.PARTIAL
    notes = " ".join(note.explanation or "" for note in result.source_notes)
    assert "low=700" in notes
    assert "high=1800" in notes
    assert "Early=1800" in notes
    assert "Mid=1100" in notes
    assert "Late=700" in notes
    flag_reasons = " ".join(flag.reason for flag in result.policy_flags)
    assert "low=700" in flag_reasons


def test_power_map_band_only_pick_does_not_add_static_slot(sleeper_snapshot: dict) -> None:
    values = load_fixture("fantasycalc/values_current.json")
    without_2028_second_bands = [
        row
        for row in values
        if not str(row["player"]["name"]).startswith("2028 2nd (")
    ]
    with_bands = league_power_map_output(
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=values,
        include_pick_value=True,
        league_format="14-team SF PPR 0.5 TEP",
    )
    without_bands = league_power_map_output(
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=without_2028_second_bands,
        include_pick_value=True,
        league_format="14-team SF PPR 0.5 TEP",
    )
    casey_with = next(team for team in with_bands.teams if team.username == "casey")
    casey_without = next(team for team in without_bands.teams if team.username == "casey")
    assert casey_with.pick_total is not None
    assert casey_without.pick_total is not None
    # Band-only 2028 2nd must not contribute static R2=1200.
    assert casey_with.pick_total == casey_without.pick_total - 1200
    assert with_bands.data_status == DataStatus.PARTIAL
    notes = " ".join(note.explanation or "" for note in with_bands.source_notes)
    assert "low=700" in notes
    assert "Early=1800" in notes
