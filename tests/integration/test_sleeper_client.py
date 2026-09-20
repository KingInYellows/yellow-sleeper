from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from tests.conftest import load_fixture
from yellow_sleeper.clients import SleeperClient, build_shared_client, draft_state_ttl
from yellow_sleeper.store import Cache


@pytest.mark.asyncio
@respx.mock
async def test_sleeper_client_fetches_league_snapshot() -> None:
    league_id = "1234567890"
    respx.get(f"https://api.sleeper.app/v1/league/{league_id}").respond(
        json=load_fixture("sleeper/league.json")
    )
    respx.get(f"https://api.sleeper.app/v1/league/{league_id}/rosters").respond(
        json=load_fixture("sleeper/rosters_14team.json")
    )
    respx.get(f"https://api.sleeper.app/v1/league/{league_id}/users").respond(
        json=load_fixture("sleeper/users_14team.json")
    )
    respx.get(f"https://api.sleeper.app/v1/league/{league_id}/traded_picks").respond(
        json=load_fixture("sleeper/traded_picks.json")
    )
    respx.get(f"https://api.sleeper.app/v1/league/{league_id}/drafts").respond(
        json=load_fixture("sleeper/drafts.json")
    )
    async with build_shared_client() as http:
        client = SleeperClient(http)

        result = await client.get_league_snapshot(league_id)

    assert result.data["league"]["league_id"] == league_id
    assert len(result.data["rosters"]) == 14
    assert len(result.data["users"]) == 14


@pytest.mark.asyncio
@respx.mock
async def test_sleeper_client_does_not_retry_4xx() -> None:
    route = respx.get("https://api.sleeper.app/v1/league/bad").respond(404, json={"error": "no"})
    async with build_shared_client() as http:
        client = SleeperClient(http)
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_league("bad")

    assert route.call_count == 1


def test_draft_state_ttl() -> None:
    assert draft_state_ttl({"status": "drafting"}) == 30
    assert draft_state_ttl({"status": "complete"}) == 3600


@pytest.mark.asyncio
@respx.mock
async def test_cached_snapshot_requires_variant_before_http(tmp_path: Path) -> None:
    route = respx.route(host="api.sleeper.app").respond(200, json={})
    cache = Cache(tmp_path)
    async with build_shared_client() as http:
        client = SleeperClient(http)
        with pytest.raises(ValueError, match="requires a scope variant"):
            await client.get_league_snapshot("1234567890", cache)
        with pytest.raises(ValueError, match="requires a scope variant"):
            await client.get_draft_state("draft-1", cache)
    assert route.call_count == 0
