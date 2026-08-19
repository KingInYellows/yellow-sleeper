from __future__ import annotations

from ..analyze.pipelines import get_my_roster_output
from ..runtime import format_cache_error, get_runtime
from ..server import mcp


@mcp.tool()
async def dynasty_get_my_roster(as_user: str | None = None) -> dict:
    """Return the configured owner's roster with context, policy, and source details."""
    runtime = await get_runtime()
    policy, config_sources = runtime.config.policy()
    snapshot, _ = await runtime.snapshot()
    players, _ = await runtime.players()
    values_result = await runtime.values_result()
    overlay = runtime.overlay_for(values_result.data, players)
    output = get_my_roster_output(
        snapshot=snapshot,
        players=players,
        values=values_result.data,
        sleeper_username=runtime.username(as_user),
        policy=policy,
        config_sources=config_sources,
        values_cache_status=values_result.status,
        values_cache_error=format_cache_error(values_result.error),
        overlay=overlay,
    )
    return output.model_dump(mode="json")
