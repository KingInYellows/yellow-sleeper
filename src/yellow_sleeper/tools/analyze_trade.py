from __future__ import annotations

from ..analyze.pipelines import analyze_trade_pipeline
from ..analyze.value import load_overlay_values
from ..models import PolicyOverride
from ..runtime import format_cache_error, get_runtime
from ..server import mcp


@mcp.tool()
async def dynasty_analyze_trade(
    my_send: list[str],
    my_receive: list[str],
    policy_override: dict | None = None,
) -> dict:
    """Return trade resolution, guardrail, value, roster, policy, and source details."""
    runtime = await get_runtime()
    override = PolicyOverride.model_validate(policy_override) if policy_override else None
    policy, config_sources = runtime.config.policy(override)
    snapshot, _ = await runtime.snapshot()
    players, _ = await runtime.players()
    values_result = await runtime.values_result()
    static = runtime.config.static
    overlay = load_overlay_values(static.values_overlay_path)
    output = analyze_trade_pipeline(
        my_send=my_send,
        my_receive=my_receive,
        policy=policy,
        snapshot=snapshot,
        players=players,
        values=values_result.data,
        sleeper_username=static.sleeper_username,
        config_sources=config_sources,
        values_cache_status=values_result.status,
        values_cache_error=format_cache_error(values_result.error),
        overlay=overlay,
        overlay_precedence=static.overlay_precedence,
        overlay_disagreement_pct=static.overlay_disagreement_pct,
        tep_tier=static.tep_tier,
    )
    return output.model_dump(mode="json")
