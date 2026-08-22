from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from yellow_sleeper.store import Cache, atomic_write_json


@pytest.mark.asyncio
async def test_atomic_write_json_supports_gzip(tmp_path: Path) -> None:
    path = tmp_path / "sleeper_players_nfl.json.gz"

    atomic_write_json(path, {"players": ["9745"]}, gzipped=True)

    cache = Cache(tmp_path)
    assert cache.read("sleeper_players_nfl") == {"players": ["9745"]}


@pytest.mark.asyncio
async def test_read_or_fetch_returns_cached_when_fresh(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    await cache.write("league_snapshot", {"league": {"league_id": "123"}})

    async def fetcher() -> dict[str, bool]:
        raise AssertionError("fetcher should not be called for fresh cache")

    result = await cache.read_or_fetch("league_snapshot", fetcher)

    assert result.status == "cached"
    assert result.data == {"league": {"league_id": "123"}}


@pytest.mark.asyncio
async def test_read_or_fetch_falls_back_to_stale_cache(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    await cache.write("fantasycalc_values", [{"value": 8200}])
    path = tmp_path / "fantasycalc_values.json"
    old = time.time() - (8 * 60 * 60)
    os.utime(path, (old, old))

    async def fetcher() -> list[dict[str, int]]:
        raise RuntimeError("upstream unavailable")

    result = await cache.read_or_fetch("fantasycalc_values", fetcher)

    assert result.status == "stale"
    assert result.data == [{"value": 8200}]
    assert isinstance(result.error, RuntimeError)


@pytest.mark.asyncio
async def test_read_or_fetch_variant_isolates_cache_files(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    calls: list[str] = []

    async def fetch_te_plus() -> list[dict[str, int]]:
        calls.append("te+")
        return [{"value": 1, "tier": 1}]

    async def fetch_off() -> list[dict[str, int]]:
        calls.append("off")
        return [{"value": 2, "tier": 0}]

    te_plus = await cache.read_or_fetch("fantasycalc_values", fetch_te_plus, variant="te+")
    off = await cache.read_or_fetch("fantasycalc_values", fetch_off, variant="off")

    assert te_plus.status == "fresh"
    assert off.status == "fresh"
    assert te_plus.data != off.data
    assert (tmp_path / "fantasycalc_values__te+.json").exists()
    assert (tmp_path / "fantasycalc_values__off.json").exists()

    # Fresh variant caches must not cross-read.
    cached_te = await cache.read_or_fetch(
        "fantasycalc_values",
        fetch_off,
        variant="te+",
    )
    assert cached_te.status == "cached"
    assert cached_te.data == [{"value": 1, "tier": 1}]
    assert calls == ["te+", "off"]
