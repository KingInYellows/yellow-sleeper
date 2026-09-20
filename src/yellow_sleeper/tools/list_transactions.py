from __future__ import annotations

from typing import Literal

from ..analyze.transactions import list_transactions_output, resolve_transaction_weeks
from ..runtime import get_runtime
from ..server import mcp


@mcp.tool()
async def dynasty_list_transactions(
    weeks: list[int] | None = None,
    week_start: int | None = None,
    week_end: int | None = None,
    roster_id: int | None = None,
    type: Literal["trade", "waiver", "free_agent"] | None = None,
    status: str | None = None,
) -> dict:
    """Return enriched Sleeper league transactions for selected weeks.

    Pending/proposed offers are not supported (public GET history only).
    Default weeks: 0 through league.settings.leg, or 0..18 when leg is missing.
    """
    runtime = await get_runtime()
    snapshot, _ = await runtime.snapshot()
    players, _ = await runtime.players()
    resolved_weeks = resolve_transaction_weeks(
        snapshot=snapshot,
        weeks=weeks,
        week_start=week_start,
        week_end=week_end,
    )
    raw = await runtime.fetch_transactions(resolved_weeks)
    output = list_transactions_output(
        raw_transactions=raw,
        snapshot=snapshot,
        players=players,
        weeks_fetched=resolved_weeks,
        roster_id=roster_id,
        type=type,
        status=status,
    )
    return output.model_dump(mode="json")
