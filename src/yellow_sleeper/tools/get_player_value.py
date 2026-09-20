from __future__ import annotations

from typing import Literal

from ..analyze.pipelines import get_player_value_output
from ..runtime import format_cache_error, get_runtime
from ..server import mcp


@mcp.tool()
async def dynasty_get_player_value(
    player: str,
    valuation_source: Literal["fantasycalc", "xlsx", "auto"] = "auto",
) -> dict:
    """Return a player's value with source and resolution details."""
    runtime = await get_runtime()
    players, _ = await runtime.players()
    values_timestamp = None
    if valuation_source == "xlsx":
        values = []
        values_cache_status = "fresh"
        values_cache_error = None
    else:
        values_result = await runtime.values_result()
        values = values_result.data
        values_cache_status = values_result.status
        values_cache_error = format_cache_error(values_result.error)
        values_timestamp = values_result.source_timestamp()
    output = get_player_value_output(
        player=player,
        players=players,
        values=values,
        valuation_source=valuation_source,
        values_cache_status=values_cache_status,
        values_cache_error=values_cache_error,
        tep_tier=runtime.config.static.tep_tier,
        league_format=runtime.config.static.league_format,
        values_timestamp=values_timestamp,
    )
    return output.model_dump(mode="json")
