from __future__ import annotations

from datetime import UTC, datetime

from tests.conftest import load_fixture
from yellow_sleeper.analyze.pipelines import analyze_trade_pipeline, get_player_value_output
from yellow_sleeper.config import DynamicPolicy
from yellow_sleeper.models import DataStatus, FlagType, PolicyStatus


def test_get_player_value_surfaces_stale_fantasycalc_values() -> None:
    result = get_player_value_output(
        player="Drake London",
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        values_cache_status="stale",
        values_cache_error="FantasyCalc validation failed",
        league_format="14-team SF PPR 0.5 TEP",
    )

    assert result.data_status == DataStatus.PARTIAL
    assert result.policy_flags[0].type == FlagType.STALE_DATA
    assert result.source_notes[0].cache_status == "stale"
    assert result.source_notes[0].stale is True
    explanation = result.source_notes[0].explanation or ""
    assert "FantasyCalc validation failed" in explanation
    assert "tep=te+" in explanation
    assert "R1=3000" in explanation
    assert "unsupported approximations" not in explanation.lower()


def test_stale_trade_notes_keep_tep_and_pick_table(sleeper_snapshot: dict) -> None:
    result = analyze_trade_pipeline(
        my_send=["Drake London"],
        my_receive=["Bijan Robinson"],
        policy=DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="casey",
        values_cache_status="stale",
        values_cache_error="FantasyCalc validation failed",
        league_format="14-team SF PPR 0.5 TEP",
    )

    notes = " ".join(note.explanation or "" for note in result.source_notes)
    assert "FantasyCalc validation failed" in notes
    assert "tep=te+" in notes
    assert "R1=3000" in notes


def test_trade_per_asset_timestamps_match_injected_cache_ts(sleeper_snapshot: dict) -> None:
    cache_ts = datetime(2024, 1, 15, 12, 0, tzinfo=UTC)
    result = analyze_trade_pipeline(
        my_send=["Drake London"],
        my_receive=["Bijan Robinson"],
        policy=DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="casey",
        values_timestamp=cache_ts,
        league_format="14-team SF PPR 0.5 TEP",
    )

    assert result.policy_status == PolicyStatus.OK
    assert result.value_math is not None
    assert result.value_math.per_asset
    for asset in result.value_math.per_asset:
        sources = asset["sources"]
        assert sources
        for source in sources:
            timestamp = source.timestamp if hasattr(source, "timestamp") else source["timestamp"]
            assert timestamp == cache_ts
    value_notes = [note for note in result.source_notes if note.field == "value_math"]
    assert value_notes
    assert value_notes[0].timestamp == cache_ts
