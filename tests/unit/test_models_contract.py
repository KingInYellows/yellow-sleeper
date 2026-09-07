from __future__ import annotations

from yellow_sleeper import models


def test_contract_models_are_exported() -> None:
    expected = {
        "ResponseEnvelope",
        "TransportError",
        "SourceNote",
        "PolicyFlag",
        "BlockingRule",
        "Candidate",
        "AssetResolution",
        "ValueSourceBreakdown",
        "SourceDisagreement",
        "ValueMath",
        "RosterContext",
        "HealthCheckInput",
        "HealthCheckOutput",
        "GetMyRosterOutput",
        "LineupSlot",
        "FindRosterOutput",
        "ListTradedPicksOutput",
        "ListMyPicksOutput",
        "GetPlayerValueOutput",
        "AnalyzeTradeOutput",
        "LeaguePowerMapOutput",
        "WhatsOnTheClockOutput",
        "BestPlayerAvailableOutput",
        "RefreshCacheOutput",
    }
    for name in expected:
        assert hasattr(models, name), name
