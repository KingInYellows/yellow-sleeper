from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .envelope import ResponseEnvelope

# Default array cap of 25 would silently drop multi-week league history.
# 200 matches TRADED_PICKS_CAP / PR14 pattern with truncated + total_count.
TRANSACTIONS_CAP = 200

TransactionType = Literal["trade", "waiver", "free_agent"]


class ListTransactionsInput(BaseModel):
    """Week selection: weeks OR week_start/week_end OR default 0..leg (or 0..18)."""

    weeks: list[int] | None = Field(
        None,
        max_length=20,
        description=(
            "Explicit weeks to fetch (include 0 for offseason). "
            "When set, week_start/week_end are ignored."
        ),
    )
    week_start: int | None = Field(
        None,
        ge=0,
        le=25,
        description="Inclusive start week when weeks is null.",
    )
    week_end: int | None = Field(
        None,
        ge=0,
        le=25,
        description="Inclusive end week when weeks is null.",
    )
    roster_id: int | None = Field(
        None,
        description="If set, keep only transactions whose roster_ids include this roster.",
    )
    type: TransactionType | None = Field(
        None,
        description="Filter to trade, waiver, or free_agent.",
    )
    status: str | None = Field(
        None,
        max_length=50,
        description="Filter by Sleeper status (e.g. complete).",
    )


class TransactionPlayerMove(BaseModel):
    sleeper_id: str = Field(..., max_length=20)
    roster_id: int
    name: str = Field(..., max_length=100)
    position: str | None = Field(None, max_length=10)
    team: str | None = Field(None, max_length=10)


class TransactionDraftPick(BaseModel):
    season: int
    round: int = Field(..., ge=1, le=10)
    original_owner_roster_id: int
    previous_owner_roster_id: int | None = None
    current_owner_roster_id: int
    original_owner_name: str = Field(..., max_length=100)
    previous_owner_name: str | None = Field(None, max_length=100)
    current_owner_name: str = Field(..., max_length=100)
    pick_token: str = Field(..., max_length=30)
    display_name: str = Field(..., max_length=100)


class WaiverBudgetTransfer(BaseModel):
    sender: int
    receiver: int
    amount: int
    sender_name: str = Field(..., max_length=100)
    receiver_name: str = Field(..., max_length=100)


class WeekTypeCount(BaseModel):
    week: int
    counts: dict[str, int] = Field(default_factory=dict)


class TransactionRecord(BaseModel):
    """Near-raw Sleeper transaction with name enrichment for Ledger snapshotting."""

    transaction_id: str = Field(..., max_length=40)
    type: str = Field(..., max_length=30)
    status: str = Field(..., max_length=50)
    week: int = Field(..., ge=0, le=25, description="Sleeper leg / NFL week.")
    created: int | None = Field(None, description="Sleeper created epoch ms.")
    status_updated: int | None = Field(None, description="Sleeper status_updated epoch ms.")
    created_iso: str | None = Field(None, max_length=40)
    status_updated_iso: str | None = Field(None, max_length=40)
    roster_ids: list[int] = Field(default_factory=list, max_length=20)
    roster_owner_names: list[str] = Field(default_factory=list, max_length=20)
    consenter_ids: list[int] = Field(default_factory=list, max_length=20)
    creator: str | None = Field(None, max_length=40)
    adds: dict[str, int] | None = Field(
        None,
        description="Near-raw Sleeper adds map (player_id → roster_id). May be null.",
    )
    drops: dict[str, int] | None = Field(
        None,
        description="Near-raw Sleeper drops map (player_id → roster_id). May be null.",
    )
    adds_named: list[TransactionPlayerMove] = Field(default_factory=list, max_length=50)
    drops_named: list[TransactionPlayerMove] = Field(default_factory=list, max_length=50)
    draft_picks: list[TransactionDraftPick] = Field(default_factory=list, max_length=25)
    waiver_budget: list[WaiverBudgetTransfer] = Field(default_factory=list, max_length=25)
    settings: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class ListTransactionsOutput(ResponseEnvelope):
    transactions: list[TransactionRecord] = Field(..., max_length=TRANSACTIONS_CAP)
    truncated: bool = False
    total_count: int = Field(0, ge=0)
    weeks_fetched: list[int] = Field(default_factory=list, max_length=20)
    week_type_counts: list[WeekTypeCount] = Field(default_factory=list, max_length=25)
