from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from yellow_sleeper.clients.fantasycalc import build_query_params
from yellow_sleeper.store import Cache, atomic_write_json
from yellow_sleeper.store.paths import (
    draft_cache_variant,
    fantasycalc_cache_variant,
    league_cache_variant,
)

LEAGUE_A = "1111111111"
LEAGUE_B = "2222222222"
DRAFT_A = "draft-aaa"
DRAFT_B = "draft-bbb"


@pytest.mark.asyncio
async def test_atomic_write_json_supports_gzip(tmp_path: Path) -> None:
    path = tmp_path / "sleeper_players_nfl.json.gz"

    atomic_write_json(path, {"players": ["9745"]}, gzipped=True)

    cache = Cache(tmp_path)
    assert cache.read("sleeper_players_nfl") == {"players": ["9745"]}


@pytest.mark.asyncio
async def test_read_or_fetch_returns_cached_when_fresh(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    variant = league_cache_variant(LEAGUE_A)
    await cache.write("league_snapshot", {"league": {"league_id": LEAGUE_A}}, variant=variant)

    async def fetcher() -> dict[str, bool]:
        raise AssertionError("fetcher should not be called for fresh cache")

    result = await cache.read_or_fetch("league_snapshot", fetcher, variant=variant)

    assert result.status == "cached"
    assert result.data == {"league": {"league_id": LEAGUE_A}}


@pytest.mark.asyncio
async def test_read_or_fetch_falls_back_to_stale_cache_within_identity(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    variant = fantasycalc_cache_variant(build_query_params("te+"))
    await cache.write("fantasycalc_values", [{"value": 8200}], variant=variant)
    path = tmp_path / f"fantasycalc_values__{variant}.json"
    old = time.time() - (8 * 60 * 60)
    os.utime(path, (old, old))

    async def fetcher() -> list[dict[str, int]]:
        raise RuntimeError("upstream unavailable")

    result = await cache.read_or_fetch("fantasycalc_values", fetcher, variant=variant)

    assert result.status == "stale"
    assert result.data == [{"value": 8200}]
    assert isinstance(result.error, RuntimeError)
    assert result.path == path


@pytest.mark.asyncio
async def test_scoped_keys_require_variant(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    with pytest.raises(ValueError, match="requires a scope variant"):
        await cache.write("league_snapshot", {"league": {}})
    with pytest.raises(ValueError, match="requires a scope variant"):
        cache.read("fantasycalc_values")
    assert cache.status("draft_state") == "missing"


@pytest.mark.asyncio
async def test_league_cache_does_not_satisfy_another_league(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    variant_a = league_cache_variant(LEAGUE_A)
    variant_b = league_cache_variant(LEAGUE_B)
    await cache.write("league_snapshot", {"league": {"league_id": LEAGUE_A}}, variant=variant_a)

    assert cache.read("league_snapshot", variant=variant_a)["league"]["league_id"] == LEAGUE_A
    with pytest.raises(FileNotFoundError):
        cache.read("league_snapshot", variant=variant_b)
    assert cache.status("league_snapshot", variant=variant_b) == "missing"
    assert cache.status("league_snapshot", variant=variant_a) in {"fresh", "cached"}


@pytest.mark.asyncio
async def test_draft_cache_is_isolated_by_draft_and_league(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    variant_a = draft_cache_variant(DRAFT_A, LEAGUE_A)
    other_draft = draft_cache_variant(DRAFT_B, LEAGUE_A)
    other_league = draft_cache_variant(DRAFT_A, LEAGUE_B)
    await cache.write("draft_state", {"draft": {"draft_id": DRAFT_A}}, variant=variant_a)

    assert cache.read("draft_state", variant=variant_a)["draft"]["draft_id"] == DRAFT_A
    with pytest.raises(FileNotFoundError):
        cache.read("draft_state", variant=other_draft)
    with pytest.raises(FileNotFoundError):
        cache.read("draft_state", variant=other_league)


@pytest.mark.asyncio
async def test_valuation_cache_is_isolated_by_query_shape(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    te_plus = fantasycalc_cache_variant(build_query_params("te+"))
    te_off = fantasycalc_cache_variant(build_query_params("off"))
    await cache.write("fantasycalc_values", [{"tep": "te+"}], variant=te_plus)

    assert cache.read("fantasycalc_values", variant=te_plus) == [{"tep": "te+"}]
    with pytest.raises(FileNotFoundError):
        cache.read("fantasycalc_values", variant=te_off)
    assert te_plus != te_off
    assert "v1" in te_plus
    assert "tep-te+" in te_plus


@pytest.mark.asyncio
async def test_scoped_reads_never_use_legacy_unscoped_files(tmp_path: Path) -> None:
    cache = Cache(tmp_path)
    (tmp_path / "league_snapshot.json").write_text('{"league": {"legacy": true}}', encoding="utf-8")
    (tmp_path / "fantasycalc_values.json").write_text("[]", encoding="utf-8")
    (tmp_path / "draft_state.json").write_text("{}", encoding="utf-8")

    variant = league_cache_variant(LEAGUE_A)
    with pytest.raises(FileNotFoundError):
        cache.read("league_snapshot", variant=variant)
    assert cache.status("league_snapshot", variant=variant) == "missing"

    async def fetcher() -> dict[str, str]:
        return {"league": "fresh-identity"}

    result = await cache.read_or_fetch("league_snapshot", fetcher, variant=variant)
    assert result.status == "fresh"
    assert result.data == {"league": "fresh-identity"}
    assert result.path == tmp_path / f"league_snapshot__{variant}.json"
    assert cache.read("league_snapshot", variant=variant) != {"league": {"legacy": True}}
