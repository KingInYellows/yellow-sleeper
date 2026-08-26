from __future__ import annotations

from typing import Literal

from ..analyze.pipelines import best_player_available_output
from ..runtime import format_cache_error, get_runtime
from ..server import mcp


@mcp.tool()
async def dynasty_best_player_available(
    draft_id: str | None = None,
    position: Literal["QB", "RB", "WR", "TE"] | None = None,
    limit: int = 10,
    rookie_board_source: Literal["local", "fantasycalc", "xlsx"] = "fantasycalc",
) -> dict:
    """Return rookie-eligible available players with factual inclusion reasons."""
    runtime = await get_runtime()
    players, _ = await runtime.players()
    values_result = await runtime.values_result()
    draft_state, _ = await runtime.draft_state(draft_id)
    output = best_player_available_output(
        players=players,
        values=values_result.data,
        draft_state=draft_state,
        position=position,
        limit=limit,
        board_source=rookie_board_source,
        values_cache_status=values_result.status,
        values_cache_error=format_cache_error(values_result.error),
        tep_tier=runtime.config.static.tep_tier,
    )
    return output.model_dump(mode="json")
