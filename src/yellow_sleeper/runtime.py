from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from .analyze.overlay import OverlayBook, build_overlay
from .analyze.tep import tep_explanation
from .clients import FantasyCalcClient, SleeperClient, build_shared_client
from .clients.xlsx import UserBookRow, load_user_book
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
    _user_book: dict[str, UserBookRow] | None = field(default=None, repr=False)

    async def aclose(self) -> None:
        await self.http.aclose()

    def username(self, as_user: str | None = None) -> str:
        candidate = (as_user or self.config.static.sleeper_username or "").strip()
        return candidate or self.config.static.sleeper_username

    def tep_note(self) -> str:
        return tep_explanation(self.config.static.tep)

    def xlsx_path(self) -> Path | None:
        return self.config.static.xlsx_path

    def user_book(self) -> dict[str, UserBookRow]:
        if not self.config.static.xlsx_enabled:
            return {}
        path = self.xlsx_path()
        if path is None or not path.exists():
            return {}
        if self._user_book is None:
            self._user_book = load_user_book(path)
        return self._user_book

    def overlay_for(
        self,
        values: list[dict[str, Any]] | list[Any],
        players: dict[str, Any],
    ) -> OverlayBook:
        return build_overlay(
            values,
            players,
            tep=self.config.static.tep,
            user_book=self.user_book(),
        )

    def display_values(
        self,
        values: list[dict[str, Any]] | list[Any],
        players: dict[str, Any],
    ) -> dict[str, float]:
        return self.overlay_for(values, players).display

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
                logger.error("refresh_all: %r failed: %s", key, exc, exc_info=True)
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
        fantasycalc=FantasyCalcClient(http),
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
