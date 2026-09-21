from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

from .clients import (
    FantasyCalcClient,
    SleeperClient,
    UnsupportedValuationQuery,
    build_shared_client,
)
from .config import Config, IdentityConfigError, load_config
from .obs.logging import configure_logging
from .store import Cache, CacheReadResult
from .store.paths import draft_cache_variant, league_cache_variant

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

    def league_variant(self) -> str:
        self.config.require_identity()
        return league_cache_variant(self.config.static.sleeper_league_id)

    def draft_variant(self, draft_id: str) -> str:
        self.config.require_identity()
        return draft_cache_variant(draft_id, self.config.static.sleeper_league_id)

    async def players(self, *, force: bool = False) -> tuple[dict[str, Any], str]:
        result = await self.sleeper.get_players_nfl_cached(self.cache, force=force)
        return result.data, result.status

    async def values(self, *, force: bool = False) -> tuple[list[dict[str, Any]], str]:
        result = await self.values_result(force=force)
        return result.data, result.status

    async def values_result(self, *, force: bool = False) -> CacheReadResult:
        try:
            return await self.fantasycalc.get_current_values_cached(self.cache, force=force)
        except UnsupportedValuationQuery as exc:
            return CacheReadResult(data=[], status="cached", error=exc)

    async def snapshot(self, *, force: bool = False) -> tuple[dict[str, Any], str]:
        self.config.require_identity()
        result = await self.sleeper.get_league_snapshot(
            self.config.static.sleeper_league_id,
            self.cache,
            force=force,
            variant=self.league_variant(),
        )
        return result.data, result.status

    async def draft_state(
        self,
        draft_id: str | None = None,
        *,
        force: bool = False,
    ) -> tuple[dict[str, Any], str]:
        self.config.require_identity()
        if draft_id is None:
            snapshot, _ = await self.snapshot()
            draft_id = _current_draft_id(snapshot)
        result = await self.sleeper.get_draft_state(
            draft_id,
            self.cache,
            force=force,
            variant=self.draft_variant(draft_id),
        )
        return result.data, result.status

    async def refresh_all(
        self,
        *,
        force: bool = False,
    ) -> tuple[dict[str, str], dict[str, str], list[str], dict[str, str]]:
        prior = self.cache_statuses()
        refreshed: list[str] = []
        failures: dict[str, str] = {}
        identity_error = self.config.identity_error()

        refreshers = {
            "sleeper_players_nfl": self.players,
            "fantasycalc_values": self.values,
            "league_snapshot": self.snapshot,
            "draft_state": self.draft_state,
        }
        for key, refresher in refreshers.items():
            if key in {"league_snapshot", "draft_state"} and identity_error:
                failures[key] = identity_error[:500]
                continue
            if key == "fantasycalc_values" and not self.fantasycalc.supported_profile():
                failures[key] = self.fantasycalc.unsupported_reason()[:500]
                continue
            try:
                await refresher(force=force)
                refreshed.append(key)
            except Exception as exc:
                # Broad catch: TaskGroup raises ExceptionGroup (not in httpx.HTTPError),
                # asyncio.TimeoutError is independent of httpx, and pydantic ValidationError
                # surfaces from cache stale-fallback paths.
                logger.error("refresh_all: %r failed: %s", key, exc, exc_info=True)
                failures[key] = format_cache_error(exc) or str(exc)[:500]
        post = self.cache_statuses()
        return prior, post, refreshed, failures

    def cache_statuses(self) -> dict[str, str]:
        variants: dict[str, str] = {"fantasycalc_values": self.fantasycalc.cache_variant()}
        if self.config.has_identity():
            league_id = self.config.static.sleeper_league_id
            variants["league_snapshot"] = league_cache_variant(league_id)
            draft_id = self._cached_draft_id()
            if draft_id:
                variants["draft_state"] = draft_cache_variant(draft_id, league_id)
        return self.cache.statuses(variants=variants)

    def _cached_draft_id(self) -> str | None:
        if not self.config.has_identity():
            return None
        try:
            snapshot = self.cache.read(
                "league_snapshot",
                variant=league_cache_variant(self.config.static.sleeper_league_id),
            )
        except (FileNotFoundError, OSError, ValueError):
            return None
        if not isinstance(snapshot, dict):
            return None
        try:
            return _current_draft_id(snapshot)
        except ValueError:
            return None


_runtime: Runtime | None = None
_runtime_lock = asyncio.Lock()


def create_runtime() -> Runtime:
    config = load_config()
    configure_logging(config.static.cache_dir, secrets=config.redact_secrets())
    http = build_shared_client()
    cache = Cache(config.static.cache_dir)
    return Runtime(
        config=config,
        cache=cache,
        http=http,
        sleeper=SleeperClient(http),
        fantasycalc=FantasyCalcClient(
            http,
            tep_tier=config.static.tep_tier,
            league_format=config.static.league_format,
        ),
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


# Re-export for tools that catch missing identity.
IdentityConfigError = IdentityConfigError
