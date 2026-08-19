from __future__ import annotations

from ..analyze import find_roster_id_for_username
from ..analyze.pipelines import list_my_picks_output
from ..models import (
    DataStatus,
    FlagSeverity,
    FlagType,
    ListMyPicksOutput,
    PolicyFlag,
    PolicyStatus,
    ResolutionStatus,
)
from ..runtime import get_runtime
from ..server import mcp


@mcp.tool()
async def dynasty_list_my_picks(
    seasons: list[int] | None = None,
    include_traded_away: bool = False,
    as_user: str | None = None,
) -> dict:
    """Return native, traded-in, and optionally traded-away picks for a roster."""
    runtime = await get_runtime()
    snapshot, _ = await runtime.snapshot()
    username = runtime.username(as_user)
    my_roster_id = find_roster_id_for_username(snapshot, username)
    if my_roster_id is None:
        return ListMyPicksOutput(
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
                        f"Configured sleeper_username '{username}' could not be mapped to a "
                        "roster. Verify the username in .yellow-sleeper.yaml."
                    ),
                )
            ],
        ).model_dump(mode="json")
    output = list_my_picks_output(
        snapshot=snapshot,
        my_roster_id=my_roster_id,
        seasons=seasons,
        include_traded_away=include_traded_away,
    )
    return output.model_dump(mode="json")
