from __future__ import annotations

from inspect import signature

from yellow_sleeper.models import (
    AnalyzeTradeInput,
    BestPlayerAvailableInput,
    FindRosterInput,
    GetPlayerValueInput,
    HealthCheckInput,
    LeaguePowerMapInput,
    ListMyPicksInput,
    ListTradedPicksInput,
    ListTransactionsInput,
    RefreshCacheInput,
    WhatsOnTheClockInput,
)
from yellow_sleeper.tools.analyze_trade import dynasty_analyze_trade
from yellow_sleeper.tools.best_player_available import dynasty_best_player_available
from yellow_sleeper.tools.find_roster import dynasty_find_roster
from yellow_sleeper.tools.get_player_value import dynasty_get_player_value
from yellow_sleeper.tools.health_check import dynasty_health_check
from yellow_sleeper.tools.league_power_map import dynasty_league_power_map
from yellow_sleeper.tools.list_my_picks import dynasty_list_my_picks
from yellow_sleeper.tools.list_traded_picks import dynasty_list_traded_picks
from yellow_sleeper.tools.list_transactions import dynasty_list_transactions
from yellow_sleeper.tools.refresh_cache import dynasty_refresh_cache
from yellow_sleeper.tools.whats_on_the_clock import dynasty_whats_on_the_clock


def test_tool_wrappers_expose_contract_inputs() -> None:
    pairs = [
        (HealthCheckInput, dynasty_health_check),
        (FindRosterInput, dynasty_find_roster),
        (ListTradedPicksInput, dynasty_list_traded_picks),
        (ListTransactionsInput, dynasty_list_transactions),
        (ListMyPicksInput, dynasty_list_my_picks),
        (GetPlayerValueInput, dynasty_get_player_value),
        (AnalyzeTradeInput, dynasty_analyze_trade),
        (LeaguePowerMapInput, dynasty_league_power_map),
        (WhatsOnTheClockInput, dynasty_whats_on_the_clock),
        (BestPlayerAvailableInput, dynasty_best_player_available),
        (RefreshCacheInput, dynasty_refresh_cache),
    ]

    for model, tool in pairs:
        assert set(model.model_fields).issubset(signature(tool).parameters)


def test_get_player_value_wrapper_default_matches_contract() -> None:
    params = signature(dynasty_get_player_value).parameters

    assert params["valuation_source"].default == "auto"


def test_whats_on_the_clock_wrapper_default_matches_contract() -> None:
    params = signature(dynasty_whats_on_the_clock).parameters

    assert params["pool"].default == "rookies_only"
