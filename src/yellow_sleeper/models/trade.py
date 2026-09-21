from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from .envelope import DataStatus, PolicyStatus, ResponseEnvelope
from .shared import AssetResolution
from .values import SourceDisagreement


class ValueMath(BaseModel):
    send_total: float | None = None
    receive_total: float | None = None
    delta: float | None = None
    delta_pct: float | None = None
    delta_min: float | None = None
    delta_max: float | None = None
    per_asset: list[dict[str, Any]] = Field(default_factory=list)
    source_disagreement: SourceDisagreement | None = None


class PositionDepthChange(BaseModel):
    position: Literal["QB", "RB", "WR", "TE"]
    pre: int = Field(..., ge=0)
    post: int = Field(..., ge=0)
    delta: int


class AgeStats(BaseModel):
    pre_avg: float
    pre_median: float
    post_avg: float
    post_median: float
    by_position: dict[str, dict[str, float]] = Field(default_factory=dict)


class PickInventorySummary(BaseModel):
    pre: dict[str, int]
    post: dict[str, int]
    delta: dict[str, int]


class RosterContext(BaseModel):
    position_depth_change: list[PositionDepthChange]
    age_stats: AgeStats
    pick_inventory_summary: PickInventorySummary


class PolicyOverride(BaseModel):
    hard_untouchables: list[str] | None = Field(None, max_length=25)
    protected_players: list[str] | None = Field(None, max_length=25)
    protected_pick_patterns: list[str] | None = Field(None, max_length=25)


class AnalyzeTradeInput(BaseModel):
    my_send: list[str] = Field(..., min_length=1, max_length=10)
    my_receive: list[str] = Field(..., min_length=1, max_length=10)
    policy_override: PolicyOverride | None = None


class AnalyzeTradeOutput(ResponseEnvelope):
    asset_resolution: list[AssetResolution]
    value_math: ValueMath | None = None
    roster_context: RosterContext | None = None

    @model_validator(mode="after")
    def _validate_blocked_trade_shape(self) -> AnalyzeTradeOutput:
        if self.policy_status == PolicyStatus.BLOCKED:
            if self.value_math is not None:
                raise ValueError("BLOCKED trades must not return value_math")
            if self.roster_context is not None:
                raise ValueError("BLOCKED trades must not return roster_context")
            if self.data_status != DataStatus.UNAVAILABLE:
                raise ValueError("BLOCKED trades must have data_status=UNAVAILABLE")
        return self
