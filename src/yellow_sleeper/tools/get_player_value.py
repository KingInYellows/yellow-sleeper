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
    values_result = await runtime.values_result()
    overlay = runtime.overlay_for(values_result.data, players)
    output = get_player_value_output(
        player=player,
        players=players,
        values=values_result.data,
        valuation_source=valuation_source,
        values_cache_status=values_result.status,
        values_cache_error=format_cache_error(values_result.error),
        overlay=overlay,
    )
    return output.model_dump(mode="json")
