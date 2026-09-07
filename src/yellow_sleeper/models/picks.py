from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .envelope import ResponseEnvelope

# Default array cap of 25 silently drops a 14-team traded-pick market (live ~68).
# 200 covers 14 teams × 5 rounds × multiple seasons with room for repeats.
TRADED_PICKS_CAP = 200


class ListTradedPicksInput(BaseModel):
    seasons: list[int] | None = Field(None, max_length=3)


class TradedPick(BaseModel):
    pick_token: str = Field(..., max_length=30)
    display_name: str = Field(..., max_length=100)
    season: int
    round: int = Field(..., ge=1, le=10)
    original_owner_roster_id: int
    previous_owner_roster_id: int | None = None
    current_owner_roster_id: int
    original_owner_name: str = Field(..., max_length=100)
    current_owner_name: str = Field(..., max_length=100)


class ListTradedPicksOutput(ResponseEnvelope):
    picks: list[TradedPick] = Field(..., max_length=TRADED_PICKS_CAP)
    truncated: bool = False
    total_count: int = Field(0, ge=0)


class ListMyPicksInput(BaseModel):
    seasons: list[int] | None = Field(None, max_length=3)
    include_traded_away: bool = False


class Pick(BaseModel):
    pick_token: str = Field(..., max_length=30, pattern=r"^pick_\d{4}_r\d+_orig\d+$")
    display_name: str = Field(..., max_length=100)
    season: int = Field(..., ge=2020, le=2099)
    round: int = Field(..., ge=1, le=10)
    original_owner_roster_id: int
    original_owner_name: str = Field(..., max_length=100)
    current_owner_roster_id: int
    origin: Literal["native", "traded_in", "traded_away"]


class ListMyPicksOutput(ResponseEnvelope):
    owned_picks: list[Pick] = Field(default_factory=list, max_length=25)
    traded_away_picks: list[Pick] = Field(default_factory=list, max_length=25)
    unresolved: list[str] = Field(default_factory=list, max_length=10)
