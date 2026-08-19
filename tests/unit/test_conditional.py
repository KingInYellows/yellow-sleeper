from __future__ import annotations

from yellow_sleeper.analyze.conditional import (
    inspect_trade_assets,
    is_conditional_or_swap,
    unresolved_or_resolution,
)
from yellow_sleeper.analyze.pipelines import analyze_trade_pipeline
from yellow_sleeper.config import DynamicPolicy
from yellow_sleeper.models import ResolutionStatus


def test_detects_or_swap_and_if_language() -> None:
    assert is_conditional_or_swap("Sam LaPorta or Kenyon Sadiq")
    assert is_conditional_or_swap("swap LaPorta for Kittle")
    assert is_conditional_or_swap("London if they win")
    assert is_conditional_or_swap("Bijan unless injured")
    assert is_conditional_or_swap("only if 2027 1st is late")
    assert is_conditional_or_swap("conditional first")
    assert is_conditional_or_swap("contingent on playoffs")
    assert not is_conditional_or_swap("Drake London")
    assert inspect_trade_assets(["Drake London", "A or B"]) == ["A or B"]


def test_unresolved_or_resolution_lists_both_candidates() -> None:
    players = {
        "111": {
            "player_id": "111",
            "full_name": "Sam LaPorta",
            "position": "TE",
            "search_full_name": "samlaporta",
        },
        "222": {
            "player_id": "222",
            "full_name": "Kenyon Sadiq",
            "position": "TE",
            "search_full_name": "kenyonsadiq",
        },
    }
    resolution = unresolved_or_resolution(
        "Sam LaPorta or Kenyon Sadiq",
        side="send",
        players=players,
    )
    assert resolution.manual_review is True
    assert resolution.resolved_id is None
    names = {candidate.name for candidate in resolution.candidates}
    assert "Sam LaPorta" in names
    assert "Kenyon Sadiq" in names


def test_analyze_trade_or_package_needs_clarification(sleeper_snapshot: dict) -> None:
    players = {
        "9745": {
            "player_id": "9745",
            "full_name": "Drake London",
            "position": "WR",
            "search_full_name": "drakelondon",
        },
        "111": {
            "player_id": "111",
            "full_name": "Sam LaPorta",
            "position": "TE",
            "search_full_name": "samlaporta",
        },
        "222": {
            "player_id": "222",
            "full_name": "Kenyon Sadiq",
            "position": "TE",
            "search_full_name": "kenyonsadiq",
        },
    }
    result = analyze_trade_pipeline(
        my_send=["Sam LaPorta or Kenyon Sadiq"],
        my_receive=["Drake London"],
        policy=DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=players,
        values=[],
    )
    assert result.resolution_status == ResolutionStatus.NEEDS_CLARIFICATION
    assert result.value_math is None
    types = {flag.type.value for flag in result.policy_flags}
    assert "conditional_or_swap_trade" in types
    send = next(item for item in result.asset_resolution if "or" in item.input)
    assert send.manual_review is True
    assert len(send.candidates) == 2
