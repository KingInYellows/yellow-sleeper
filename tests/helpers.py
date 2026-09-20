from __future__ import annotations

from pathlib import Path
from typing import Any

from tests.conftest import load_fixture
from yellow_sleeper.clients.fantasycalc import build_query_params
from yellow_sleeper.store import Cache
from yellow_sleeper.store.paths import fantasycalc_cache_variant, league_cache_variant

SYNTHETIC_LEAGUE_ID = "1234567890"
SYNTHETIC_USERNAME = "casey"
SYNTHETIC_DISPLAY = "Casey Quinn"
SYNTHETIC_COMPACT = "CaseyQuinn"
SYNTHETIC_TEAM = "Yellow Sleeper OK"


def sleeper_snapshot_dict() -> dict[str, Any]:
    return {
        "league": load_fixture("sleeper/league.json"),
        "rosters": load_fixture("sleeper/rosters_14team.json"),
        "users": load_fixture("sleeper/users_14team.json"),
        "traded_picks": load_fixture("sleeper/traded_picks.json"),
        "drafts": load_fixture("sleeper/drafts.json"),
    }


async def seed_scoped_cache(cache_dir: Path) -> Cache:
    cache = Cache(cache_dir)
    await cache.write("sleeper_players_nfl", load_fixture("sleeper/players_nfl.json"))
    await cache.write(
        "league_snapshot",
        sleeper_snapshot_dict(),
        variant=league_cache_variant(SYNTHETIC_LEAGUE_ID),
    )
    await cache.write(
        "fantasycalc_values",
        load_fixture("fantasycalc/values_current.json"),
        variant=fantasycalc_cache_variant(build_query_params("te+")),
    )
    return cache
