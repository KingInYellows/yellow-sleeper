from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from typing import Any

import httpx

from ..models import LiveProbeResult
from ..store import Cache, CacheReadResult


class SleeperClient:
    BASE_URL = "https://api.sleeper.app/v1"

    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http
        self._sem = asyncio.Semaphore(10)

    async def get_state_nfl(self) -> dict[str, Any]:
        return await self._get_with_retry("/state/nfl")

    async def get_players_nfl(self) -> dict[str, Any]:
        return await self._get_with_retry("/players/nfl")

    async def get_league(self, league_id: str) -> dict[str, Any]:
        return await self._get_with_retry(f"/league/{league_id}")

    async def get_rosters(self, league_id: str) -> list[dict[str, Any]]:
        return await self._get_with_retry(f"/league/{league_id}/rosters")

    async def get_users(self, league_id: str) -> list[dict[str, Any]]:
        return await self._get_with_retry(f"/league/{league_id}/users")

    async def get_traded_picks(self, league_id: str) -> list[dict[str, Any]]:
        return await self._get_with_retry(f"/league/{league_id}/traded_picks")

    async def get_transactions(self, league_id: str, round: int) -> list[dict[str, Any]]:
        return await self._get_with_retry(f"/league/{league_id}/transactions/{round}")

    async def get_drafts(self, league_id: str) -> list[dict[str, Any]]:
        return await self._get_with_retry(f"/league/{league_id}/drafts")

    async def get_draft(self, draft_id: str) -> dict[str, Any]:
        return await self._get_with_retry(f"/draft/{draft_id}")

    async def get_draft_picks(self, draft_id: str) -> list[dict[str, Any]]:
        return await self._get_with_retry(f"/draft/{draft_id}/picks")

    async def get_players_nfl_cached(self, cache: Cache, *, force: bool = False):
        return await cache.read_or_fetch("sleeper_players_nfl", self.get_players_nfl, force=force)

    async def get_league_snapshot(
        self,
        league_id: str,
        cache: Cache | None = None,
        *,
        force: bool = False,
    ) -> CacheReadResult:
        async def fetch() -> dict[str, Any]:
            async with asyncio.TaskGroup() as tg:
                league_task = tg.create_task(self.get_league(league_id))
                rosters_task = tg.create_task(self.get_rosters(league_id))
                users_task = tg.create_task(self.get_users(league_id))
                picks_task = tg.create_task(self.get_traded_picks(league_id))
                drafts_task = tg.create_task(self.get_drafts(league_id))
            return {
                "league": league_task.result(),
                "rosters": rosters_task.result(),
                "users": users_task.result(),
                "traded_picks": picks_task.result(),
                "drafts": drafts_task.result(),
            }

        if cache is None:
            return CacheReadResult(await fetch(), "fresh")
        return await cache.read_or_fetch("league_snapshot", fetch, force=force)

    async def get_draft_state(
        self,
        draft_id: str,
        cache: Cache | None = None,
        *,
        force: bool = False,
    ) -> CacheReadResult:
        async def fetch() -> dict[str, Any]:
            async with asyncio.TaskGroup() as tg:
                draft_task = tg.create_task(self.get_draft(draft_id))
                picks_task = tg.create_task(self.get_draft_picks(draft_id))
            return {"draft": draft_task.result(), "picks": picks_task.result()}

        if cache is None:
            return CacheReadResult(await fetch(), "fresh")

        # Drop TTL from 1h to 30s once cached state shows the draft is active so
        # tools polling whats_on_the_clock see new picks within the round.
        ttl_seconds: int | None = None
        try:
            cached = cache.read("draft_state")
        except (FileNotFoundError, OSError):
            cached = None
        if isinstance(cached, dict):
            ttl_seconds = draft_state_ttl(cached.get("draft", {}))

        return await cache.read_or_fetch(
            "draft_state", fetch, ttl_seconds=ttl_seconds, force=force
        )

    async def probe(self) -> LiveProbeResult:
        start = time.monotonic()
        try:
            await self.get_state_nfl()
            elapsed = int((time.monotonic() - start) * 1000)
            return LiveProbeResult(
                source="sleeper",
                reachable=True,
                latency_ms=elapsed,
                probed_at=datetime.now(UTC),
            )
        except Exception as exc:
            return LiveProbeResult(
                source="sleeper",
                reachable=False,
                error=str(exc)[:500],
                probed_at=datetime.now(UTC),
            )

    async def _get_with_retry(self, path: str) -> Any:
        try:
            return await self._get(path)
        except (httpx.HTTPStatusError, httpx.NetworkError, httpx.TimeoutException) as exc:
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                raise
            await asyncio.sleep(0.5)
            return await self._get(path)

    async def _get(self, path: str) -> Any:
        async with self._sem:
            response = await self._http.get(f"{self.BASE_URL}{path}")
            response.raise_for_status()
            return response.json()


def draft_state_ttl(draft: dict[str, Any]) -> int:
    return 30 if draft.get("status", "complete") == "drafting" else 3600
