from __future__ import annotations

from ..analyze.pipelines import get_my_roster_output
from ..runtime import format_cache_error, get_runtime
from ..server import mcp


@mcp.tool()
async def dynasty_get_my_roster() -> dict:
    """Return Brad's roster with context, policy, and source details."""
    runtime = await get_runtime()
    policy, config_sources = runtime.config.policy()
    snapshot, _ = await runtime.snapshot()
    players, _ = await runtime.players()
    values_result = await runtime.values_result()
    output = get_my_roster_output(
        snapshot=snapshot,
        players=players,
        values=values_result.data,
        sleeper_username=runtime.config.static.sleeper_username,
        policy=policy,
        config_sources=config_sources,
        values_cache_status=values_result.status,
        values_cache_error=format_cache_error(values_result.error),
        tep_tier=runtime.config.static.tep_tier,
    )
    return output.model_dump(mode="json")
