from __future__ import annotations

import sys
from pathlib import Path

import pytest
import respx

from tests.helpers import SYNTHETIC_LEAGUE_ID, SYNTHETIC_USERNAME, seed_scoped_cache
from yellow_sleeper import runtime as runtime_mod
from yellow_sleeper.__main__ import main
from yellow_sleeper.clients import FantasyCalcClient, SleeperClient, build_shared_client
from yellow_sleeper.config import IdentityConfigError, load_config
from yellow_sleeper.runtime import Runtime
from yellow_sleeper.store import Cache
from yellow_sleeper.store.paths import league_cache_variant
from yellow_sleeper.tools.list_traded_picks import dynasty_list_traded_picks


def test_help_works_without_identity(capsys: pytest.CaptureFixture[str], monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["yellow-sleeper", "--help"])
    assert main() == 0
    output = capsys.readouterr().out
    assert "sleeper_league_id" in output
    assert "dynasty_health_check" in output


@pytest.mark.asyncio
@respx.mock
async def test_snapshot_errors_before_league_http_when_identity_missing(tmp_path: Path) -> None:
    route = respx.route(host="api.sleeper.app").respond(200, json={})
    config = load_config(env={"CACHE_DIR": str(tmp_path)}, config_path=tmp_path / "missing.yaml")
    async with build_shared_client() as http:
        runtime = Runtime(
            config=config,
            cache=Cache(tmp_path),
            http=http,
            sleeper=SleeperClient(http),
            fantasycalc=FantasyCalcClient(http),
        )
        with pytest.raises(IdentityConfigError, match="sleeper_league_id"):
            await runtime.snapshot()
    assert route.call_count == 0


@pytest.mark.asyncio
@respx.mock
async def test_refresh_skips_league_and_draft_without_identity(tmp_path: Path) -> None:
    sleeper_route = respx.route(host="api.sleeper.app").respond(200, json={"ok": True})
    fc_route = respx.get("https://api.fantasycalc.com/values/current").respond(json=[])
    config = load_config(env={"CACHE_DIR": str(tmp_path)}, config_path=tmp_path / "missing.yaml")
    async with build_shared_client() as http:
        runtime = Runtime(
            config=config,
            cache=Cache(tmp_path),
            http=http,
            sleeper=SleeperClient(http),
            fantasycalc=FantasyCalcClient(http),
        )
        _prior, post, refreshed, failures = await runtime.refresh_all()
    assert "league_snapshot" in failures
    assert "draft_state" in failures
    assert not any("/league/" in str(call.request.url) for call in sleeper_route.calls)
    assert "sleeper_players_nfl" in refreshed or "sleeper_players_nfl" in failures
    assert post["league_snapshot"] == "missing"
    assert fc_route.called or "fantasycalc_values" in failures


@pytest.mark.asyncio
async def test_health_statuses_use_same_identity_keys(tmp_path: Path) -> None:
    env = {
        "SLEEPER_LEAGUE_ID": SYNTHETIC_LEAGUE_ID,
        "SLEEPER_USERNAME": SYNTHETIC_USERNAME,
        "CACHE_DIR": str(tmp_path),
    }
    config = load_config(env=env, config_path=tmp_path / "missing.yaml")
    await seed_scoped_cache(tmp_path)
    async with build_shared_client() as http:
        runtime = Runtime(
            config=config,
            cache=Cache(tmp_path),
            http=http,
            sleeper=SleeperClient(http),
            fantasycalc=FantasyCalcClient(http),
        )
        statuses = runtime.cache_statuses()
    assert statuses["league_snapshot"] in {"fresh", "cached"}
    assert statuses["fantasycalc_values"] in {"fresh", "cached"}
    snapshot_path = tmp_path / f"league_snapshot__{league_cache_variant(SYNTHETIC_LEAGUE_ID)}.json"
    assert snapshot_path.exists()


@pytest.mark.asyncio
async def test_list_traded_picks_uses_username_roster_helper(tmp_path: Path) -> None:
    env = {
        "SLEEPER_LEAGUE_ID": SYNTHETIC_LEAGUE_ID,
        "SLEEPER_USERNAME": SYNTHETIC_USERNAME,
        "CACHE_DIR": str(tmp_path),
    }
    config = load_config(env=env, config_path=tmp_path / "missing.yaml")
    await seed_scoped_cache(tmp_path)
    async with build_shared_client() as http:
        bound = Runtime(
            config=config,
            cache=Cache(tmp_path),
            http=http,
            sleeper=SleeperClient(http),
            fantasycalc=FantasyCalcClient(http),
        )
        runtime_mod.set_runtime(bound)
        try:
            payload = await dynasty_list_traded_picks()
        finally:
            runtime_mod.set_runtime(None)
    assert payload["resolution_status"] == "OK"
    assert payload["picks"]
    assert any(pick.get("current_owner_name") == "Casey Quinn" for pick in payload["picks"])


@pytest.mark.asyncio
async def test_list_traded_picks_does_not_hardcode_roster_zero(tmp_path: Path) -> None:
    env = {
        "SLEEPER_LEAGUE_ID": SYNTHETIC_LEAGUE_ID,
        "SLEEPER_USERNAME": "nobody-in-this-league",
        "CACHE_DIR": str(tmp_path),
    }
    config = load_config(env=env, config_path=tmp_path / "missing.yaml")
    await seed_scoped_cache(tmp_path)
    async with build_shared_client() as http:
        bound = Runtime(
            config=config,
            cache=Cache(tmp_path),
            http=http,
            sleeper=SleeperClient(http),
            fantasycalc=FantasyCalcClient(http),
        )
        runtime_mod.set_runtime(bound)
        try:
            payload = await dynasty_list_traded_picks()
        finally:
            runtime_mod.set_runtime(None)
    assert payload["resolution_status"] == "NEEDS_CLARIFICATION"
    assert payload["picks"] == []
    assert payload["data_status"] == "UNAVAILABLE"

