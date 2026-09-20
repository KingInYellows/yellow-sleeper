from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CacheKey = Literal["sleeper_players_nfl", "fantasycalc_values", "league_snapshot", "draft_state"]

VALUES_CACHE_SCHEMA = "v1"


@dataclass(frozen=True)
class CacheSpec:
    key: CacheKey
    ttl_seconds: int
    gzipped: bool = False
    scoped: bool = False


CACHE_SPECS: dict[CacheKey, CacheSpec] = {
    "sleeper_players_nfl": CacheSpec("sleeper_players_nfl", 24 * 60 * 60, gzipped=True),
    "fantasycalc_values": CacheSpec("fantasycalc_values", 6 * 60 * 60, scoped=True),
    "league_snapshot": CacheSpec("league_snapshot", 5 * 60, scoped=True),
    "draft_state": CacheSpec("draft_state", 60 * 60, scoped=True),
}


def safe_cache_token(value: str, *, max_len: int = 96) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_+" else "_" for ch in value).strip("_")
    if not cleaned:
        cleaned = "empty"
    if len(cleaned) <= max_len:
        return cleaned
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    keep = max_len - 13
    return f"{cleaned[:keep]}_{digest}"


def league_cache_variant(league_id: str) -> str:
    return safe_cache_token(league_id)


def draft_cache_variant(draft_id: str, league_id: str) -> str:
    return safe_cache_token(f"{draft_id}__league-{league_id}")


def fantasycalc_cache_variant(query_params: dict[str, str]) -> str:
    encoded = "_".join(f"{key}-{query_params[key]}" for key in sorted(query_params))
    return safe_cache_token(f"{VALUES_CACHE_SCHEMA}__{encoded}")


def cache_path(
    base_dir: Path,
    key: CacheKey,
    *,
    gzipped: bool | None = None,
    variant: str | None = None,
) -> Path:
    spec = CACHE_SPECS[key]
    use_gzip = spec.gzipped if gzipped is None else gzipped
    suffix = ".json.gz" if use_gzip else ".json"
    if spec.scoped and variant:
        return base_dir / f"{key}__{safe_cache_token(variant)}{suffix}"
    return base_dir / f"{key}{suffix}"
