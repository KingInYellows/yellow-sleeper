from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import tempfile
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .paths import CACHE_SPECS, CacheKey, cache_path

logger = logging.getLogger("yellow_sleeper.store.cache")

CacheStatus = Literal["fresh", "cached", "stale"]
HealthCacheStatus = Literal["fresh", "cached", "stale", "missing"]


@dataclass(frozen=True)
class CacheReadResult:
    data: Any
    status: CacheStatus
    error: Exception | None = None
    path: Path | None = None

    def source_timestamp(self) -> datetime:
        if self.path is not None and self.path.exists():
            return datetime.fromtimestamp(self.path.stat().st_mtime, UTC)
        return datetime.now(UTC)


def atomic_write_json(path: Path, data: Any, *, gzipped: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        if gzipped:
            with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb") as gz:
                gz.write(json.dumps(data).encode("utf-8"))
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(data, file)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


class Cache:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def read_or_fetch(
        self,
        key: CacheKey,
        fetcher: Callable[[], Awaitable[Any]],
        *,
        ttl_seconds: int | None = None,
        gzipped: bool | None = None,
        force: bool = False,
        variant: str | None = None,
    ) -> CacheReadResult:
        spec = CACHE_SPECS[key]
        self._require_scope(key, variant)
        ttl = spec.ttl_seconds if ttl_seconds is None else ttl_seconds
        use_gzip = spec.gzipped if gzipped is None else gzipped
        path = self._resolved_path(key, gzipped=use_gzip, variant=variant)
        lock_key = f"{key}:{variant}" if variant else key

        if not force and self._is_fresh(path, ttl):
            return CacheReadResult(self._read(path, gzipped=use_gzip), "cached", path=path)

        async with self._locks[lock_key]:
            if not force and self._is_fresh(path, ttl):
                return CacheReadResult(self._read(path, gzipped=use_gzip), "cached", path=path)
            try:
                data = await fetcher()
                await asyncio.to_thread(atomic_write_json, path, data, gzipped=use_gzip)
                return CacheReadResult(data, "fresh", path=path)
            except Exception as exc:
                if path.exists():
                    logger.warning(
                        "cache fetch failed for %r, serving stale: %s",
                        key,
                        exc,
                        exc_info=True,
                    )
                    try:
                        stale_data = self._read(path, gzipped=use_gzip)
                    except (OSError, ValueError) as read_exc:
                        logger.warning(
                            "stale cache read failed for %r after fetch failure: %s",
                            key,
                            read_exc,
                            exc_info=True,
                        )
                        raise exc from read_exc
                    return CacheReadResult(stale_data, "stale", exc, path=path)
                raise

    async def write(
        self,
        key: CacheKey,
        data: Any,
        *,
        gzipped: bool | None = None,
        variant: str | None = None,
    ) -> None:
        spec = CACHE_SPECS[key]
        self._require_scope(key, variant)
        use_gzip = spec.gzipped if gzipped is None else gzipped
        path = self._resolved_path(key, gzipped=use_gzip, variant=variant)
        await asyncio.to_thread(atomic_write_json, path, data, gzipped=use_gzip)

    def read(
        self,
        key: CacheKey,
        *,
        gzipped: bool | None = None,
        variant: str | None = None,
    ) -> Any:
        spec = CACHE_SPECS[key]
        self._require_scope(key, variant)
        use_gzip = spec.gzipped if gzipped is None else gzipped
        return self._read(
            self._resolved_path(key, gzipped=use_gzip, variant=variant),
            gzipped=use_gzip,
        )

    def status(
        self,
        key: CacheKey,
        *,
        ttl_seconds: int | None = None,
        variant: str | None = None,
    ) -> HealthCacheStatus:
        spec = CACHE_SPECS[key]
        if spec.scoped and not variant:
            return "missing"
        ttl = spec.ttl_seconds if ttl_seconds is None else ttl_seconds
        path = self._resolved_path(key, gzipped=spec.gzipped, variant=variant)
        if not path.exists():
            return "missing"
        age = time.time() - path.stat().st_mtime
        if age < min(ttl, 30):
            return "fresh"
        if age < ttl:
            return "cached"
        return "stale"

    def statuses(
        self,
        variants: Mapping[str, str] | None = None,
    ) -> dict[str, HealthCacheStatus]:
        variant_map = dict(variants or {})
        return {key: self.status(key, variant=variant_map.get(key)) for key in CACHE_SPECS}

    def _resolved_path(
        self, key: CacheKey, *, gzipped: bool, variant: str | None = None
    ) -> Path:
        return cache_path(self.base_dir, key, gzipped=gzipped, variant=variant)

    @staticmethod
    def _require_scope(key: CacheKey, variant: str | None) -> None:
        if CACHE_SPECS[key].scoped and not variant:
            raise ValueError(
                f"cache key {key!r} requires a scope variant; unscoped files are never used"
            )

    @staticmethod
    def _is_fresh(path: Path, ttl_seconds: int) -> bool:
        return path.exists() and (time.time() - path.stat().st_mtime) < ttl_seconds

    @staticmethod
    def _read(path: Path, *, gzipped: bool) -> Any:
        if gzipped:
            with gzip.open(path, "rt", encoding="utf-8") as file:
                return json.load(file)
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
