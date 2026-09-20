from __future__ import annotations

import re
import time
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from ..models import LiveProbeResult
from ..store import Cache
from ..store.paths import fantasycalc_cache_variant

TepTier = Literal["off", "te+", "te++"]

BASE_QUERY_PARAMS = {
    "isDynasty": "true",
    "numQbs": "2",
    "numTeams": "14",
    "ppr": "1",
}

_VALID_TEP_TIERS: set[TepTier] = {"off", "te+", "te++"}

PICK_TABLE_EXPLANATION = (
    "Pick values use the internal static round table (R1=3000, R2=1200, R3=600, "
    "R4=300, R5=100), not FantasyCalc pick rows."
)

UNSUPPORTED_FORMAT_NOTE = (
    "Supported valuation profile is 14-team Superflex PPR. Other league_format "
    "strings still use that pinned FantasyCalc query and are unsupported approximations."
)


def build_query_params(tep_tier: TepTier = "te+") -> dict[str, str]:
    """Build FantasyCalc /values/current query params.

    ``tep_tier='off'`` omits the param (empty ``tep=`` errors on the API).
    League 0.5 TEP maps to discrete ``te+``; ``tep=0.5`` is not a documented value.
    Re-implements the PR #16 query-shape idea (head 3a253dd) with attribution.
    """
    if tep_tier not in _VALID_TEP_TIERS:
        raise ValueError(f"invalid tep_tier {tep_tier!r}; expected off, te+, or te++")
    params = dict(BASE_QUERY_PARAMS)
    if tep_tier != "off":
        params["tep"] = tep_tier
    return params


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
        league_format: str = "14-team SF PPR 0.5 TEP",
    ) -> None:
        self._http = http
        self.tep_tier = tep_tier
        self.league_format = league_format
        self.query_params = (
            query_params if query_params is not None else build_query_params(tep_tier)
        )

    def cache_variant(self) -> str:
        return fantasycalc_cache_variant(self.query_params)

    def supported_profile(self) -> bool:
        return format_looks_supported(self.league_format)

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

        return await cache.read_or_fetch(
            "fantasycalc_values",
            fetch,
            force=force,
            variant=self.cache_variant(),
        )

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
            record.player.sleeperId: record
            for record in records
            if record.player.sleeperId and record.player.position != "PICK"
        },
        "by_name_lower": {
            record.player.name.lower(): record
            for record in records
            if record.player.position != "PICK"
        },
    }


def tep_source_explanation(tep_tier: TepTier, *, league_format: str | None = None) -> str:
    if tep_tier == "off":
        text = (
            "FantasyCalc values requested without TEP (non-TEP board; not a 0.5 TEP model)."
        )
    elif tep_tier == "te+":
        text = (
            "FantasyCalc values use tep=te+ (discrete TE+ tier approximating 0.5 TEP; "
            "not a continuous 0.5 float). Documented by go-fantasycalc as te+/te++."
        )
    elif tep_tier == "te++":
        text = "FantasyCalc values use tep=te++ (discrete heavy TE-premium tier)."
    else:
        never: TepTier = tep_tier
        raise RuntimeError(f"unhandled tep_tier: {never}")
    if league_format is not None and not format_looks_supported(league_format):
        text = f"{text} {UNSUPPORTED_FORMAT_NOTE}"
    return text


def format_looks_supported(league_format: str | None) -> bool:
    """True only for the advertised 14-team Superflex full-PPR 0.5 TEP profile.

    Empty format is unsupported. ``0.5 PPR`` / half-PPR / non-PPR / ``1.5 TEP``
    must not match just because the string contains ``14``, ``sf``, and ``ppr``.
    """
    if not league_format or not league_format.strip():
        return False
    lowered = league_format.lower()
    if "14" not in lowered:
        return False
    if "sf" not in lowered and "superflex" not in lowered:
        return False
    if re.search(r"\bnon[\s-]*ppr\b", lowered):
        return False
    if re.search(r"\bhalf[\s-]*ppr\b", lowered):
        return False
    if re.search(r"0\.5\s*ppr", lowered):
        return False
    if re.search(r"\bppr\s*0\.5\b(?!\s*tep)", lowered):
        return False
    if not re.search(r"\bppr\b", lowered):
        return False
    tep_amounts = re.findall(r"(\d+(?:\.\d+)?)\s*tep\b", lowered)
    return all(amount == "0.5" for amount in tep_amounts)
