from __future__ import annotations

from ..analyze import find_roster_id_for_username
from ..analyze.pipelines import list_traded_picks_output
from ..models import (
    DataStatus,
    FlagSeverity,
    FlagType,
    ListTradedPicksOutput,
    PolicyFlag,
    PolicyStatus,
    ResolutionStatus,
)
from ..runtime import get_runtime
from ..server import mcp


@mcp.tool()
async def dynasty_list_traded_picks(seasons: list[int] | None = None) -> dict:
    """Return enriched Sleeper traded-pick records for the configured league."""
    runtime = await get_runtime()
    snapshot, _ = await runtime.snapshot()
    username = runtime.config.static.sleeper_username
    my_roster_id = find_roster_id_for_username(snapshot, username)
    if my_roster_id is None:
        return ListTradedPicksOutput(
            policy_status=PolicyStatus.OK,
            resolution_status=ResolutionStatus.NEEDS_CLARIFICATION,
            data_status=DataStatus.UNAVAILABLE,
            policy_flags=[
                PolicyFlag(
                    type=FlagType.AMBIGUOUS_RESOLUTION,
                    asset=username,
                    rule_source="computed",
                    severity=FlagSeverity.WARNING,
                    reason=(
                        "Configured sleeper_username did not map to a roster. "
                        "Verify the username in .yellow-sleeper.yaml."
                    ),
                )
            ],
            picks=[],
            truncated=False,
            total_count=0,
        ).model_dump(mode="json")
    output = list_traded_picks_output(
        snapshot=snapshot, my_roster_id=my_roster_id, seasons=seasons
    )
    return output.model_dump(mode="json")
