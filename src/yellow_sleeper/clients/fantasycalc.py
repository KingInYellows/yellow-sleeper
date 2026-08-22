from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from ..models import LiveProbeResult
from ..store import Cache

TepTier = Literal["off", "te+", "te++"]

BASE_QUERY_PARAMS = {
    "isDynasty": "true",
    "numQbs": "2",
    "numTeams": "14",
    "ppr": "1",
}


def build_query_params(tep_tier: TepTier = "te+") -> dict[str, str]:
    """Build FantasyCalc /values/current query params.

    ``tep_tier='off'`` omits the param entirely (empty ``tep=`` errors on the API).
    League 0.5 TEP maps to ``te+``; ``tep=0.5`` is not accepted (HTTP 404).
    """
    params = dict(BASE_QUERY_PARAMS)
    if tep_tier != "off":
        params["tep"] = tep_tier
    return params


# Default query shape for Stage 2 (14-team SF PPR 0.5 TEP → tep=te+).
QUERY_PARAMS = build_query_params("te+")


class FCPlayer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    sleeperId: str | None = None
    position: str


class FCRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    player: FCPlayer
    value: float
    overallRank: int
    redraftValue: float | None = None
    trend30Day: float | None = None


class FantasyCalcClient:
    BASE_URL = "https://api.fantasycalc.com"

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        tep_tier: TepTier = "te+",
        query_params: dict[str, str] | None = None,
    ) -> None:
        self._http = http
        self.tep_tier = tep_tier
        self.query_params = (
            query_params if query_params is not None else build_query_params(tep_tier)
        )

    async def get_current_values(self) -> list[FCRecord]:
        response = await self._http.get(
            f"{self.BASE_URL}/values/current",
            params=self.query_params,
        )
        response.raise_for_status()
        raw = response.json()
        # ValidationError on any record propagates intentionally so Cache.read_or_fetch
        # serves stale on bad upstream payloads — covered by
        # test_fantasycalc_malformed_response_falls_back_to_stale_cache.
        return [FCRecord.model_validate(record) for record in raw]

    async def get_current_values_cached(self, cache: Cache, *, force: bool = False):
        async def fetch() -> list[dict]:
            return [record.model_dump(mode="json") for record in await self.get_current_values()]

        # Partition by effective query shape (includes tep) so custom params
        # and tier switches cannot serve the wrong TTL board.
        return await cache.read_or_fetch(
            "fantasycalc_values",
            fetch,
            force=force,
            variant=self._cache_variant(),
        )

    def _cache_variant(self) -> str:
        if not self.query_params:
            return self.tep_tier
        encoded = "_".join(f"{key}-{self.query_params[key]}" for key in sorted(self.query_params))
        return f"{self.tep_tier}__{encoded}"

    async def probe(self) -> LiveProbeResult:
        start = time.monotonic()
        try:
            response = await self._http.get(
                f"{self.BASE_URL}/values/current",
                params={**self.query_params, "limit": "1"},
            )
            response.raise_for_status()
            records = response.json()
            if not records:
                raise ValueError("empty response")
            FCRecord.model_validate(records[0])
            elapsed = int((time.monotonic() - start) * 1000)
            return LiveProbeResult(
                source="fantasycalc",
                reachable=True,
                latency_ms=elapsed,
                probed_at=datetime.now(UTC),
            )
        except Exception as exc:
            return LiveProbeResult(
                source="fantasycalc",
                reachable=False,
                error=str(exc)[:500],
                probed_at=datetime.now(UTC),
            )


def index_records(records: list[FCRecord]) -> dict[str, dict[str, FCRecord]]:
    return {
        "by_sleeper_id": {
            record.player.sleeperId: record for record in records if record.player.sleeperId
        },
        "by_name_lower": {record.player.name.lower(): record for record in records},
    }


def tep_source_explanation(tep_tier: TepTier) -> str:
    if tep_tier == "off":
        return "FantasyCalc values requested without TEP (non-TEP board)."
    if tep_tier == "te+":
        return (
            "FantasyCalc values use tep=te+ (discrete TE+ tier; maps to league 0.5 TEP, "
            "not a continuous 0.5 float)."
        )
    return "FantasyCalc values use tep=te++ (discrete heavy TE-premium tier)."
