from __future__ import annotations

from pathlib import Path

import pytest

from tests.conftest import load_fixture
from tests.helpers import SYNTHETIC_LEAGUE_ID, SYNTHETIC_USERNAME, seed_scoped_cache
from yellow_sleeper.analyze.pipelines import analyze_trade_pipeline, get_player_value_output
from yellow_sleeper.analyze.value import (
    OverlayResult,
    load_overlay_values,
    merge_player_value,
    values_by_sleeper_id,
)
from yellow_sleeper.clients import FantasyCalcClient, SleeperClient, build_shared_client
from yellow_sleeper.clients.fantasycalc import build_query_params
from yellow_sleeper.config import DynamicPolicy, load_config
from yellow_sleeper.models import FlagType
from yellow_sleeper.runtime import Runtime
from yellow_sleeper.store import Cache
from yellow_sleeper.store.paths import fantasycalc_cache_variant


def test_load_overlay_disabled_when_path_unset() -> None:
    result = load_overlay_values(None)
    assert result.status == "disabled"
    assert result.active is False
    assert result.values == {}


def test_load_overlay_missing_file_is_explicit(tmp_path: Path) -> None:
    missing = tmp_path / "gone.csv"
    result = load_overlay_values(missing)
    assert result.status == "missing"
    assert result.active is False
    assert result.values == {}
    assert result.message is not None
    assert "does not exist" in result.message
    assert "not labeled as overlay" in result.message


def test_load_overlay_reads_sleeper_id_csv(tmp_path: Path) -> None:
    path = tmp_path / "values.csv"
    path.write_text("sleeper_id,value,name\n9991,5000,Example Tight End\n", encoding="utf-8")
    result = load_overlay_values(path)
    assert result.status == "loaded"
    assert result.active is True
    assert result.values == {"9991": 5000.0}


def test_merge_overlay_wins_and_flags_disagreement() -> None:
    values = load_fixture("fantasycalc/values_current.json")
    index = values_by_sleeper_id(values)
    overlay = OverlayResult(status="loaded", values={"9991": 5000.0})
    chosen, sources, disagreement, missing = merge_player_value(
        "9991",
        index,
        overlay,
        valuation_source="auto",
    )
    assert chosen == 5000.0
    assert {source.source for source in sources} == {"fantasycalc", "xlsx"}
    assert disagreement is not None
    assert disagreement.max_delta_pct > 25
    assert missing == []


def test_merge_disabled_overlay_matches_fantasycalc_only() -> None:
    values = load_fixture("fantasycalc/values_current.json")
    index = values_by_sleeper_id(values)
    chosen, sources, disagreement, missing = merge_player_value(
        "9745",
        index,
        OverlayResult(status="disabled"),
        valuation_source="auto",
    )
    assert chosen == 8200
    assert [source.source for source in sources] == ["fantasycalc"]
    assert disagreement is None
    assert missing == []


def test_get_player_value_overlay_wins_and_names_xlsx(sleeper_snapshot: dict) -> None:
    del sleeper_snapshot
    result = get_player_value_output(
        player="Harold Fannin",
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        valuation_source="auto",
        overlay=OverlayResult(status="loaded", values={"9991": 5000.0}),
        league_format="14-team SF PPR 0.5 TEP",
    )
    assert result.value == 5000
    assert result.source_disagreement is not None
    assert any(note.source == "xlsx" and note.field == "value" for note in result.source_notes)
    assert any(flag.type == FlagType.SOURCE_DISAGREEMENT for flag in result.policy_flags)
    assert "xlsx" in (result.source_notes[0].explanation or "").lower() or any(
        note.source == "xlsx" for note in result.source_notes
    )


def test_get_player_value_missing_overlay_is_explicit_not_silent_fallback() -> None:
    overlay = OverlayResult(
        status="missing",
        path=Path("/tmp/missing-overlay.csv"),
        message=(
            "Configured CSV overlay path does not exist: /tmp/missing-overlay.csv. "
            "FantasyCalc was not labeled as overlay."
        ),
    )
    result = get_player_value_output(
        player="Drake London",
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        valuation_source="auto",
        overlay=overlay,
        league_format="14-team SF PPR 0.5 TEP",
    )
    assert result.value == 8200
    assert result.source_notes[0].source == "fantasycalc"
    explanations = " ".join(note.explanation or "" for note in result.source_notes)
    assert "not labeled as overlay" in explanations
    assert any(
        flag.type == FlagType.MISSING_VALUE and flag.asset == "xlsx"
        for flag in result.policy_flags
    )
    assert not any(
        note.source == "xlsx"
        and note.field == "value"
        and "overlay wins" in (note.explanation or "").lower()
        for note in result.source_notes
    )


def test_get_player_value_xlsx_missing_file_does_not_use_fantasycalc() -> None:
    overlay = OverlayResult(
        status="missing",
        message=(
            "Configured CSV overlay path does not exist: gone.csv. "
            "FantasyCalc was not labeled as overlay."
        ),
    )
    result = get_player_value_output(
        player="Drake London",
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        valuation_source="xlsx",
        overlay=overlay,
        league_format="14-team SF PPR 0.5 TEP",
    )
    assert result.value is None
    assert "xlsx" in result.missing_values
    assert result.source_notes[0].source == "xlsx"
    assert "not labeled as overlay" in (result.source_notes[0].explanation or "")


def test_default_player_value_path_unchanged_without_overlay() -> None:
    with_default = get_player_value_output(
        player="Drake London",
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        league_format="14-team SF PPR 0.5 TEP",
    )
    with_disabled = get_player_value_output(
        player="Drake London",
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        overlay=OverlayResult(status="disabled"),
        league_format="14-team SF PPR 0.5 TEP",
    )
    assert with_default.value == 8200
    assert with_disabled.value == 8200
    assert with_default.source_notes[0].source == "fantasycalc"
    assert with_disabled.source_notes[0].source == "fantasycalc"
    assert [source.source for source in with_default.value_sources] == ["fantasycalc"]
    assert [source.source for source in with_disabled.value_sources] == ["fantasycalc"]


def test_trade_overlay_wins_on_player_asset(sleeper_snapshot: dict) -> None:
    result = analyze_trade_pipeline(
        my_send=["Harold Fannin"],
        my_receive=["Jaylen Wright"],
        policy=DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="casey",
        overlay=OverlayResult(status="loaded", values={"9991": 5000.0}),
        league_format="14-team SF PPR 0.5 TEP",
    )
    assert result.value_math is not None
    send_asset = next(item for item in result.value_math.per_asset if item["side"] == "send")
    assert send_asset["value"] == 5000
    assert any(source.source == "xlsx" for source in send_asset["sources"])
    assert result.value_math.source_disagreement is not None
    assert any(note.source == "xlsx" for note in result.source_notes)


@pytest.mark.asyncio
async def test_runtime_overlay_cache_does_not_use_no_overlay_board(tmp_path: Path) -> None:
    overlay_path = tmp_path / "values.csv"
    overlay_path.write_text("sleeper_id,value\n9991,5000\n", encoding="utf-8")
    await seed_scoped_cache(tmp_path)
    config = load_config(
        env={
            "SLEEPER_LEAGUE_ID": SYNTHETIC_LEAGUE_ID,
            "SLEEPER_USERNAME": SYNTHETIC_USERNAME,
            "CACHE_DIR": str(tmp_path),
            "YELLOW_SLEEPER_VALUES_OVERLAY_PATH": str(overlay_path),
        },
        config_path=tmp_path / "missing.yaml",
    )
    async with build_shared_client() as http:
        runtime = Runtime(
            config=config,
            cache=Cache(tmp_path),
            http=http,
            sleeper=SleeperClient(http),
            fantasycalc=FantasyCalcClient(http),
        )
        assert runtime.overlay_result().active is True
        statuses = runtime.cache_statuses()
    assert statuses["fantasycalc_values"] == "missing"
    no_overlay = fantasycalc_cache_variant(build_query_params("te+"))
    assert (tmp_path / f"fantasycalc_values__{no_overlay}.json").exists()
