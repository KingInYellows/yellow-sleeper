from __future__ import annotations

from typing import Any

import pytest
import respx

from tests.conftest import load_fixture
from yellow_sleeper.analyze.transactions import (
    DEFAULT_WEEK_END_WHEN_LEG_MISSING,
    list_transactions_output,
    resolve_transaction_weeks,
)
from yellow_sleeper.clients import FantasyCalcClient, SleeperClient, build_shared_client
from yellow_sleeper.config import Config, DynamicPolicy, StaticConfig
from yellow_sleeper.models import TRANSACTIONS_CAP
from yellow_sleeper.runtime import Runtime
from yellow_sleeper.store import Cache


def _players() -> dict[str, Any]:
    return load_fixture("sleeper/players_nfl.json")


def _raw_week0() -> list[dict[str, Any]]:
    return load_fixture("sleeper/transactions_week0.json")


def _raw_week1() -> list[dict[str, Any]]:
    return load_fixture("sleeper/transactions_week1.json")


def test_resolve_weeks_explicit_list(sleeper_snapshot: dict) -> None:
    assert resolve_transaction_weeks(snapshot=sleeper_snapshot, weeks=[2, 0, 2]) == [0, 2]


def test_resolve_weeks_range(sleeper_snapshot: dict) -> None:
    assert resolve_transaction_weeks(
        snapshot=sleeper_snapshot, week_start=0, week_end=2
    ) == [0, 1, 2]


def test_resolve_weeks_default_without_leg(sleeper_snapshot: dict) -> None:
    weeks = resolve_transaction_weeks(snapshot=sleeper_snapshot)
    assert weeks[0] == 0
    assert weeks[-1] == DEFAULT_WEEK_END_WHEN_LEG_MISSING
    assert len(weeks) == DEFAULT_WEEK_END_WHEN_LEG_MISSING + 1


def test_resolve_weeks_default_with_leg(sleeper_snapshot: dict) -> None:
    snapshot = {
        **sleeper_snapshot,
        "league": {
            **sleeper_snapshot["league"],
            "settings": {**sleeper_snapshot["league"].get("settings", {}), "leg": 3},
        },
    }
    assert resolve_transaction_weeks(snapshot=snapshot) == [0, 1, 2, 3]


def test_trade_with_draft_picks_enriched(sleeper_snapshot: dict) -> None:
    result = list_transactions_output(
        raw_transactions=_raw_week0(),
        snapshot=sleeper_snapshot,
        players=_players(),
        weeks_fetched=[0],
    )
    assert result.total_count == 1
    assert result.truncated is False
    txn = result.transactions[0]
    assert txn.type == "trade"
    assert txn.adds is None
    assert txn.adds_named == []
    assert txn.roster_owner_names == ["Brad Schwarzkopf", "Mike Johnson"]
    picks = {pick.pick_token: pick for pick in txn.draft_picks}
    assert picks["pick_2027_r1_orig3"].original_owner_name == "Mike Johnson"
    assert picks["pick_2027_r1_orig3"].current_owner_name == "Brad Schwarzkopf"
    assert picks["pick_2027_r2_orig11"].current_owner_name == "Mike Johnson"
    assert txn.waiver_budget[0].amount == 25
    assert txn.waiver_budget[0].sender_name == "Brad Schwarzkopf"


def test_free_agent_named_adds_and_drops(sleeper_snapshot: dict) -> None:
    result = list_transactions_output(
        raw_transactions=_raw_week1(),
        snapshot=sleeper_snapshot,
        players=_players(),
        weeks_fetched=[1],
        type="free_agent",
    )
    assert result.total_count == 2
    by_id = {txn.transaction_id: txn for txn in result.transactions}
    fa = by_id["tx-week1-fa-1"]
    assert fa.adds == {"9991": 11}
    assert fa.adds_named[0].name == "Harold Fannin"
    assert fa.drops_named[0].name == "Jaylen Wright"


def test_null_adds_preserved(sleeper_snapshot: dict) -> None:
    result = list_transactions_output(
        raw_transactions=_raw_week1(),
        snapshot=sleeper_snapshot,
        players=_players(),
        weeks_fetched=[1],
    )
    null_adds = next(
        txn for txn in result.transactions if txn.transaction_id == "tx-week1-fa-null-adds"
    )
    assert null_adds.adds is None
    assert null_adds.adds_named == []
    assert null_adds.drops == {"5000": 4}
    assert null_adds.drops_named[0].name == "Mike Evans"


def test_filters_roster_type_status(sleeper_snapshot: dict) -> None:
    result = list_transactions_output(
        raw_transactions=_raw_week0() + _raw_week1(),
        snapshot=sleeper_snapshot,
        players=_players(),
        weeks_fetched=[0, 1],
        roster_id=11,
        type="trade",
        status="complete",
    )
    assert result.total_count == 1
    assert result.transactions[0].transaction_id == "tx-week0-trade-1"


def test_week_type_counts(sleeper_snapshot: dict) -> None:
    result = list_transactions_output(
        raw_transactions=_raw_week0() + _raw_week1(),
        snapshot=sleeper_snapshot,
        players=_players(),
        weeks_fetched=[0, 1],
    )
    by_week = {row.week: row.counts for row in result.week_type_counts}
    assert by_week[0] == {"trade": 1}
    assert by_week[1]["free_agent"] == 2
    assert by_week[1]["waiver"] == 1


def test_truncation_flags_instead_of_silent_drop(sleeper_snapshot: dict) -> None:
    raw = []
    for i in range(TRANSACTIONS_CAP + 5):
        raw.append(
            {
                "type": "free_agent",
                "transaction_id": f"tx-cap-{i}",
                "status": "complete",
                "leg": 1,
                "roster_ids": [11],
                "adds": None,
                "drops": None,
                "draft_picks": [],
                "waiver_budget": [],
                "created": 1700000000000 + i,
                "status_updated": 1700000000000 + i,
            }
        )
    result = list_transactions_output(
        raw_transactions=raw,
        snapshot=sleeper_snapshot,
        players=_players(),
        weeks_fetched=[1],
    )
    assert result.truncated is True
    assert result.total_count == TRANSACTIONS_CAP + 5
    assert len(result.transactions) == TRANSACTIONS_CAP
    assert result.data_status.value == "PARTIAL"


@pytest.mark.asyncio
@respx.mock
async def test_week_range_fetch_via_client() -> None:
    league_id = "1234567890"
    respx.get(f"https://api.sleeper.app/v1/league/{league_id}/transactions/0").respond(
        json=_raw_week0()
    )
    respx.get(f"https://api.sleeper.app/v1/league/{league_id}/transactions/1").respond(
        json=_raw_week1()
    )
    async with build_shared_client() as http:
        client = SleeperClient(http)
        week0 = await client.get_transactions(league_id, 0)
        week1 = await client.get_transactions(league_id, 1)
    assert len(week0) == 1
    assert week0[0]["type"] == "trade"
    assert len(week1) == 3
    assert any(txn.get("adds") is None for txn in week1)


@pytest.mark.asyncio
@respx.mock
async def test_runtime_fetch_transactions_gather(tmp_path) -> None:
    league_id = "1234567890"
    respx.get(f"https://api.sleeper.app/v1/league/{league_id}/transactions/0").respond(
        json=_raw_week0()
    )
    respx.get(f"https://api.sleeper.app/v1/league/{league_id}/transactions/1").respond(
        json=_raw_week1()
    )
    async with build_shared_client() as http:
        runtime = Runtime(
            config=Config(
                static=StaticConfig(
                    sleeper_league_id=league_id,
                    sleeper_username="brad",
                    cache_dir=tmp_path,
                ),
                policy=DynamicPolicy(),
                yaml_path=tmp_path / ".yellow-sleeper.yaml",
                static_sources=["test"],
            ),
            cache=Cache(tmp_path),
            http=http,
            sleeper=SleeperClient(http),
            fantasycalc=FantasyCalcClient(http),
        )
        combined = await runtime.fetch_transactions([0, 1])
    assert len(combined) == 4
    assert {txn["leg"] for txn in combined} == {0, 1}
