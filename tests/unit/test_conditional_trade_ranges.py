from __future__ import annotations

import time

from tests.conftest import load_fixture
from yellow_sleeper.analyze.pipelines import (
    _scenario_delta_bounds,
    analyze_trade_pipeline,
)
from yellow_sleeper.analyze.trade_phrases import (
    is_open_ended_trade,
    normalize_trade_asset,
    or_choice_parts,
    strip_conditional_clause,
)
from yellow_sleeper.config import DynamicPolicy
from yellow_sleeper.models import DataStatus, FlagType, PolicyStatus, ResolutionStatus


def _trade(
    sleeper_snapshot: dict,
    my_send: list[str],
    my_receive: list[str],
    *,
    policy: DynamicPolicy | None = None,
):
    return analyze_trade_pipeline(
        my_send=my_send,
        my_receive=my_receive,
        policy=policy or DynamicPolicy(),
        snapshot=sleeper_snapshot,
        players=load_fixture("sleeper/players_nfl.json"),
        values=load_fixture("fantasycalc/values_current.json"),
        sleeper_username="casey",
        league_format="14-team SF PPR 0.5 TEP",
    )


def test_strip_conditional_clause_keeps_base_asset() -> None:
    assert strip_conditional_clause("2027 1st (if Team A makes playoffs)") == "2027 1st"
    assert strip_conditional_clause("Jaylen Wright if he plays 10 games") == "Jaylen Wright"
    assert strip_conditional_clause("Mahomes") == "Mahomes"


def test_or_and_swap_normalization() -> None:
    assert or_choice_parts("Drake London or Bijan Robinson") == [
        "Drake London",
        "Bijan Robinson",
    ]
    assert normalize_trade_asset("swap 2027 1sts") == "2027 1st"
    assert is_open_ended_trade(["Jaylen Wright"]) is False
    assert is_open_ended_trade(["Jaylen Wright if he plays"]) is True


def test_normal_trade_still_returns_one_delta(sleeper_snapshot: dict) -> None:
    result = _trade(sleeper_snapshot, ["Jaylen Wright"], ["Harold Fannin"])

    assert result.policy_status == PolicyStatus.OK
    assert result.resolution_status == ResolutionStatus.OK
    assert result.data_status == DataStatus.COMPLETE
    assert result.value_math is not None
    assert result.value_math.delta is not None
    assert result.value_math.delta_pct is not None
    assert result.value_math.send_total == 4500
    assert result.value_math.receive_total == 3600
    assert result.value_math.delta == -900
    assert result.value_math.delta_min is None
    assert result.value_math.delta_max is None
    assert all(flag.type != FlagType.CONDITIONAL_OR_SWAP_TRADE for flag in result.policy_flags)
    assert result.roster_context is not None


def test_conditional_trade_returns_range_not_one_delta(sleeper_snapshot: dict) -> None:
    result = _trade(
        sleeper_snapshot,
        ["Jaylen Wright if he plays 10 games"],
        ["Harold Fannin"],
    )

    assert result.resolution_status == ResolutionStatus.NEEDS_CLARIFICATION
    assert result.data_status == DataStatus.PARTIAL
    assert result.roster_context is None
    assert any(flag.type == FlagType.CONDITIONAL_OR_SWAP_TRADE for flag in result.policy_flags)
    assert result.value_math is not None
    assert result.value_math.delta is None
    assert result.value_math.delta_pct is None
    assert result.value_math.send_total is None
    assert result.value_math.receive_total is None
    assert result.value_math.delta_min is not None
    assert result.value_math.delta_max is not None
    assert result.value_math.delta_min < result.value_math.delta_max
    # Include: 3600-4500=-900. Omit send: 3600-0=3600.
    assert result.value_math.delta_min == -900
    assert result.value_math.delta_max == 3600
    assert any(res.resolved_id == "11620" for res in result.asset_resolution)


def test_or_trade_returns_candidates_not_one_winner(sleeper_snapshot: dict) -> None:
    result = _trade(
        sleeper_snapshot,
        ["Jaylen Wright"],
        ["Drake London or Bijan Robinson"],
    )

    assert result.resolution_status == ResolutionStatus.NEEDS_CLARIFICATION
    assert result.data_status == DataStatus.PARTIAL
    assert any(flag.type == FlagType.CONDITIONAL_OR_SWAP_TRADE for flag in result.policy_flags)
    assert result.value_math is not None
    assert result.value_math.delta is None
    or_asset = next(
        res for res in result.asset_resolution if " or " in res.input.lower()
    )
    assert or_asset.resolved_id is None
    assert or_asset.manual_review is True
    names = {candidate.name for candidate in or_asset.candidates}
    ids = {candidate.sleeper_id for candidate in or_asset.candidates}
    assert names >= {"Drake London", "Bijan Robinson"}
    assert ids >= {"9745", "9491"}
    assert result.value_math.delta_min is not None
    assert result.value_math.delta_max is not None
    assert result.value_math.delta_min < result.value_math.delta_max
    # 8200-4500=3700 vs 9000-4500=4500
    assert result.value_math.delta_min == 3700
    assert result.value_math.delta_max == 4500


def test_pick_swap_returns_candidates_not_one_value(sleeper_snapshot: dict) -> None:
    result = _trade(sleeper_snapshot, ["swap 2027 1sts"], ["Jaylen Wright"])

    assert result.resolution_status == ResolutionStatus.NEEDS_CLARIFICATION
    assert result.data_status == DataStatus.PARTIAL
    assert any(flag.type == FlagType.CONDITIONAL_OR_SWAP_TRADE for flag in result.policy_flags)
    assert result.value_math is not None
    assert result.value_math.delta is None
    swap_asset = next(res for res in result.asset_resolution if "swap" in res.input.lower())
    tokens = {candidate.pick_token for candidate in swap_asset.candidates}
    assert "pick_2027_r1_orig11" in tokens
    assert "pick_2027_r1_orig3" in tokens
    assert swap_asset.resolved_id is None or swap_asset.candidates


def test_conditional_hard_untouchable_still_blocks(sleeper_snapshot: dict) -> None:
    result = _trade(
        sleeper_snapshot,
        ["Drake London if he stays healthy"],
        ["Bijan Robinson"],
        policy=DynamicPolicy(hard_untouchables=["Drake London"]),
    )

    assert result.policy_status == PolicyStatus.BLOCKED
    assert result.value_math is None
    assert result.blocking_rules[0].asset == "Drake London"


def test_mixed_or_hard_untouchable_player_still_blocks(sleeper_snapshot: dict) -> None:
    result = _trade(
        sleeper_snapshot,
        ["Drake London or 2027 1st"],
        ["Bijan Robinson"],
        policy=DynamicPolicy(hard_untouchables=["Drake London"]),
    )

    mixed = next(res for res in result.asset_resolution if " or " in res.input.lower())
    assert any(candidate.sleeper_id == "9745" for candidate in mixed.candidates)
    assert any(candidate.pick_token for candidate in mixed.candidates)
    assert result.policy_status == PolicyStatus.BLOCKED
    assert result.value_math is None
    assert any(rule.matched_against == "Drake London" for rule in result.blocking_rules)
    assert any("Drake London" in rule.asset for rule in result.blocking_rules)


def test_or_range_bounds_stay_bounded_without_cartesian_product() -> None:
    # Six five-way assets per side is 5^12 (~244 million) deltas under full enumeration.
    send_options = [[float(base + offset) for offset in range(5)] for base in range(6)]
    receive_options = [
        [float(10 + base + offset) for offset in range(5)] for base in range(6)
    ]
    cartesian = 1
    for options in send_options + receive_options:
        cartesian *= len(options)
    assert cartesian == 5**12

    started = time.perf_counter()
    bounds = _scenario_delta_bounds(send_options, receive_options)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    send_min = sum(min(options) for options in send_options)
    send_max = sum(max(options) for options in send_options)
    receive_min = sum(min(options) for options in receive_options)
    receive_max = sum(max(options) for options in receive_options)
    assert bounds == (receive_min - send_max, receive_max - send_min)
