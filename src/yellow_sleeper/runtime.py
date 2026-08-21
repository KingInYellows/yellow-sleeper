from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .clients import FantasyCalcClient, SleeperClient, build_shared_client
from .config import Config, load_config
from .obs.logging import configure_logging
from .store import Cache, CacheReadResult

logger = logging.getLogger("yellow_sleeper.runtime")


@dataclass
class Runtime:
    config: Config
    cache: Cache
    http: httpx.AsyncClient
    sleeper: SleeperClient
    fantasycalc: FantasyCalcClient

    async def aclose(self) -> None:
        await self.http.aclose()

    async def players(self, *, force: bool = False) -> tuple[dict[str, Any], str]:
        result = await self.sleeper.get_players_nfl_cached(self.cache, force=force)
        return result.data, result.status

    async def values(self, *, force: bool = False) -> tuple[list[dict[str, Any]], str]:
        result = await self.values_result(force=force)
        return result.data, result.status

    async def values_result(self, *, force: bool = False) -> CacheReadResult:
        return await self.fantasycalc.get_current_values_cached(self.cache, force=force)

    async def snapshot(self, *, force: bool = False) -> tuple[dict[str, Any], str]:
        result = await self.sleeper.get_league_snapshot(
            self.config.static.sleeper_league_id, self.cache, force=force
        )
        return result.data, result.status

    async def draft_state(
        self,
        draft_id: str | None = None,
        *,
        force: bool = False,
    ) -> tuple[dict[str, Any], str]:
        if draft_id is None:
            snapshot, _ = await self.snapshot()
            draft_id = _current_draft_id(snapshot)
        result = await self.sleeper.get_draft_state(draft_id, self.cache, force=force)
        return result.data, result.status

    async def refresh_all(
        self,
        *,
        force: bool = False,
    ) -> tuple[dict[str, str], dict[str, str], list[str], dict[str, str]]:
        prior = self.cache.statuses()
        refreshed: list[str] = []
        failures: dict[str, str] = {}

        refreshers = {
            "sleeper_players_nfl": self.players,
            "fantasycalc_values": self.values,
            "league_snapshot": self.snapshot,
            "draft_state": self.draft_state,
        }
        for key, refresher in refreshers.items():
            try:
                await refresher(force=force)
                refreshed.append(key)
            except Exception as exc:
                # Broad catch: TaskGroup raises ExceptionGroup (not in httpx.HTTPError),
                # asyncio.TimeoutError is independent of httpx, and pydantic ValidationError
                # surfaces from cache stale-fallback paths.
                logger.error(
                    "refresh_all: %r failed: %s", key, exc, exc_info=True
                )
                failures[key] = format_cache_error(exc) or str(exc)[:500]
        post = self.cache.statuses()
        return prior, post, refreshed, failures


_runtime: Runtime | None = None
_runtime_lock = asyncio.Lock()


def create_runtime() -> Runtime:
    config = load_config()
    configure_logging(config.static.cache_dir)
    http = build_shared_client()
    cache = Cache(config.static.cache_dir)
    return Runtime(
        config=config,
        cache=cache,
        http=http,
        sleeper=SleeperClient(http),
        fantasycalc=FantasyCalcClient(http, tep_tier=config.static.tep_tier),
    )


def set_runtime(runtime: Runtime | None) -> None:
    global _runtime
    _runtime = runtime


async def get_runtime() -> Runtime:
    global _runtime
    if _runtime is not None:
        return _runtime
    async with _runtime_lock:
        if _runtime is None:
            _runtime = create_runtime()
        return _runtime


def format_cache_error(error: BaseException | None) -> str | None:
    if error is None:
        return None
    return f"{type(error).__name__}: {error}"[:500]


def _current_draft_id(snapshot: dict[str, Any]) -> str:
    drafts = snapshot.get("drafts", [])
    for draft in drafts:
        if draft.get("status") == "drafting":
            return str(draft["draft_id"])
    if drafts:
        return str(drafts[0]["draft_id"])
    raise ValueError("no draft_id supplied and no league draft found")
