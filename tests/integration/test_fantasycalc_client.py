from __future__ import annotations

import os
import time

import pytest
import respx

from tests.conftest import load_fixture
from yellow_sleeper.clients import FantasyCalcClient, build_shared_client, index_records
from yellow_sleeper.clients.fantasycalc import (
    PICK_TABLE_EXPLANATION,
    QUERY_PARAMS,
    build_query_params,
    format_looks_supported,
    tep_source_explanation,
)
from yellow_sleeper.store import Cache
from yellow_sleeper.store.paths import fantasycalc_cache_variant


def test_build_query_params_te_plus_and_off() -> None:
    te_plus = build_query_params("te+")
    assert te_plus == {
        "isDynasty": "true",
        "numQbs": "2",
        "numTeams": "14",
        "ppr": "1",
        "tep": "te+",
    }
    assert QUERY_PARAMS == te_plus
    off = build_query_params("off")
    assert "tep" not in off
    assert off["numQbs"] == "2"
    te_heavy = build_query_params("te++")
    assert te_heavy["tep"] == "te++"
    assert fantasycalc_cache_variant(te_plus) != fantasycalc_cache_variant(off)
    assert "v1" in fantasycalc_cache_variant(te_plus)


def test_invalid_tep_tier_rejected() -> None:
    with pytest.raises(ValueError, match="invalid tep_tier"):
        build_query_params("0.5")  # type: ignore[arg-type]


def test_tep_and_pick_table_explanations() -> None:
    text = tep_source_explanation("te+", league_format="14-team SF PPR 0.5 TEP")
    assert "tep=te+" in text
    assert "0.5 float" not in text or "not a continuous" in text
    assert "unsupported approximations" not in text.lower()
    unsupported = tep_source_explanation("te+", league_format="12-team 1QB")
    assert "unsupported" in unsupported.lower()
    assert "R1=3000" in PICK_TABLE_EXPLANATION


@pytest.mark.parametrize(
    ("league_format", "supported"),
    [
        ("14-team SF PPR 0.5 TEP", True),
        ("14-team Superflex PPR 0.5 TEP", True),
        ("14-team SF PPR", False),
        ("214-team SF PPR 0.5 TEP", False),
        ("114-team SF PPR 0.5 TEP", False),
        ("14-team SF 1QB PPR 0.5 TEP", False),
        ("14-team Superflex 1QB PPR 0.5 TEP", False),
        ("14-team SF 0.5 PPR", False),
        ("14-team SF half-PPR", False),
        ("14-team SF non-PPR", False),
        ("14-team SF PPR 1.5 TEP", False),
        ("", False),
        ("12-team 1QB", False),
    ],
)
def test_format_looks_supported_rejects_near_matches(league_format: str, supported: bool) -> None:
    assert format_looks_supported(league_format) is supported
    note = tep_source_explanation("te+", league_format=league_format)
    if supported:
        assert "unsupported approximations" not in note.lower()
    else:
        assert "unsupported approximations" in note.lower()


def test_empty_format_is_labeled_unsupported() -> None:
    assert format_looks_supported(None) is False
    assert format_looks_supported("") is False
    assert "unsupported approximations" in tep_source_explanation("te+", league_format="").lower()
    # Unspecified None does not attach the approximation sentence.
    assert "unsupported approximations" not in tep_source_explanation("te+").lower()


def test_supported_profile_uses_format_helper() -> None:
    client = FantasyCalcClient(object(), league_format="14-team SF PPR 0.5 TEP")  # type: ignore[arg-type]
    assert client.supported_profile() is True
    client.league_format = "14-team SF 0.5 PPR"
    assert client.supported_profile() is False


@pytest.mark.asyncio
@respx.mock
async def test_fantasycalc_client_validates_and_indexes_records() -> None:
    route = respx.get("https://api.fantasycalc.com/values/current").respond(
        json=load_fixture("fantasycalc/values_current.json")
    )
    async with build_shared_client() as http:
        client = FantasyCalcClient(http)

        records = await client.get_current_values()

    index = index_records(records)
    assert index["by_sleeper_id"]["9745"].value == 8200
    assert index["by_name_lower"]["drake london"].player.sleeperId == "9745"
    assert "tep=te+" in str(route.calls[0].request.url) or dict(route.calls[0].request.url.params)[
        "tep"
    ] == "te+"


@pytest.mark.asyncio
@respx.mock
async def test_fantasycalc_malformed_response_falls_back_to_stale_cache(
    tmp_path,
) -> None:
    cached = load_fixture("fantasycalc/values_current.json")
    cache = Cache(tmp_path)
    async with build_shared_client() as http:
        client = FantasyCalcClient(http)
        variant = client.cache_variant()
        await cache.write("fantasycalc_values", cached, variant=variant)
        old = time.time() - (8 * 60 * 60)
        os.utime(tmp_path / f"fantasycalc_values__{variant}.json", (old, old))
        respx.get("https://api.fantasycalc.com/values/current").respond(
            json=[{"player": {"id": 1, "name": "Broken", "position": "WR"}}]
        )

        result = await client.get_current_values_cached(cache)

    assert result.status == "stale"
    assert result.data == cached
    assert result.error is not None


@pytest.mark.asyncio
@respx.mock
async def test_tep_off_omits_query_param() -> None:
    route = respx.get("https://api.fantasycalc.com/values/current").respond(json=[])
    async with build_shared_client() as http:
        client = FantasyCalcClient(http, tep_tier="off")
        await client.get_current_values()
    params = dict(route.calls[0].request.url.params)
    assert "tep" not in params
    assert params["isDynasty"] == "true"
