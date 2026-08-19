from __future__ import annotations

from ..analyze.pipelines import league_power_map_output
from ..runtime import format_cache_error, get_runtime
from ..server import mcp


@mcp.tool()
async def dynasty_league_power_map(include_pick_value: bool = False) -> dict:
    """Return per-team dynasty rollups with source details."""
    runtime = await get_runtime()
    snapshot, _ = await runtime.snapshot()
    players, _ = await runtime.players()
    values_result = await runtime.values_result()
    overlay = runtime.overlay_for(values_result.data, players)
    output = league_power_map_output(
        snapshot=snapshot,
        players=players,
        values=values_result.data,
        include_pick_value=include_pick_value,
        values_cache_status=values_result.status,
        values_cache_error=format_cache_error(values_result.error),
        overlay=overlay,
    )
    return output.model_dump(mode="json")
