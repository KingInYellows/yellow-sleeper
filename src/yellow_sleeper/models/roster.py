from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from .envelope import ResolutionStatus, ResponseEnvelope
from .trade import AgeStats
from .values import ValueSourceBreakdown


class RosterPlayer(BaseModel):
    sleeper_id: str = Field(..., max_length=20)
    name: str = Field(..., max_length=100)
    position: Literal["QB", "RB", "WR", "TE"]
    team: str | None = Field(None, max_length=10)
    age: float | None = None
    value: float | None = None
    rookie_status: bool = False
    value_sources: list[ValueSourceBreakdown] = Field(default_factory=list)


class PositionalDepth(BaseModel):
    position: Literal["QB", "RB", "WR", "TE"]
    count: int = Field(..., ge=0)
    starters_required: int = Field(..., ge=0)


class GroupedRoster(BaseModel):
    position: Literal["QB", "RB", "WR", "TE"]
    players: list[RosterPlayer] = Field(..., max_length=25)


class LineupSlot(BaseModel):
    index: int = Field(..., ge=0)
    slot_position: str = Field(..., max_length=20)
    sleeper_id: str | None = Field(None, max_length=20)
    name: str | None = Field(None, max_length=100)
    empty: bool = False


class GetMyRosterOutput(ResponseEnvelope):
    grouped_roster: list[GroupedRoster]
    positional_depth: list[PositionalDepth]
    age_stats: AgeStats
    missing_values: list[str] = Field(default_factory=list, max_length=25)
    starters: list[LineupSlot] = Field(default_factory=list, max_length=25)
    reserve: list[LineupSlot] = Field(default_factory=list, max_length=25)
    taxi: list[LineupSlot] = Field(default_factory=list, max_length=25)
    player_count: int = Field(0, ge=0)
    roster_spots: int = Field(0, ge=0)
    over_capacity: bool = False


class FindRosterInput(BaseModel):
    search_term: str = Field(..., min_length=1, max_length=200)


class RosterMatch(BaseModel):
    roster_id: int
    owner_name: str = Field(..., max_length=100)
    username: str = Field(..., max_length=100)
    match_confidence: int = Field(..., ge=0, le=100)
    matched_field: Literal["team_name", "display_name", "username"]


class FindRosterOutput(ResponseEnvelope):
    matched: RosterMatch | None = None
    alternatives: list[RosterMatch] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _validate_narrow_margin(self) -> FindRosterOutput:
        if self.matched is not None and self.alternatives:
            top = self.matched.match_confidence
            for alt in self.alternatives:
                if top - alt.match_confidence < 5:
                    raise ValueError(
                        "narrow-margin rule: when top match is within 5 points of any "
                        "alternative, matched must be None and resolution_status must be "
                        "NEEDS_CLARIFICATION"
                    )
        if (
            self.matched is not None
            and self.resolution_status == ResolutionStatus.NEEDS_CLARIFICATION
        ):
            raise ValueError("NEEDS_CLARIFICATION roster responses must not include matched")
        return self


class TeamRollup(BaseModel):
    roster_id: int
    owner_name: str = Field(..., max_length=100)
    username: str = Field(..., max_length=100)
    positional_rollups: dict[Literal["QB", "RB", "WR", "TE"], float]
    roster_total: float
    pick_total: float | None = None
    roster_age: AgeStats
    missing_flags: list[str] = Field(default_factory=list, max_length=10)
    context_summary: str = Field(..., max_length=500)


class LeaguePowerMapInput(BaseModel):
    include_pick_value: bool = False


class LeaguePowerMapOutput(ResponseEnvelope):
    teams: list[TeamRollup] = Field(..., min_length=1, max_length=20)
