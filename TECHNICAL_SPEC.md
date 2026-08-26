---
Version: 1.0
Date: May 11, 2026
Owner: Brad / Yellow Sleeper
Companion to: PRD v0.4.4 (Canonical) and TOOL_CONTRACTS.md v1.0 (Final)
Status: Engineering-authoritative implementation spec
---

# Yellow Sleeper MCP — Technical Specification

This document specifies *how* to build the server. The PRD specifies what to build and why; TOOL_CONTRACTS.md specifies the I/O shapes; this document specifies the modules, libraries, algorithms, concurrency model, testing approach, and distribution mechanism. Where decisions are contested or where best practice has evolved recently, sources are cited.

**Reading order:** §1 (structure) → §2 (cache) → §3 (Sleeper) → §4 (FantasyCalc) → §5 (pick parser) → §6 (trade analyzer pipeline) → §7 (config) → §8 (concurrency) → §9 (logging) → §10 (testing) → §11 (distribution).

---

## 1. Project Structure & Module Layout

### Decision: `src/` layout with one package, eleven tool modules, separate clients and stores.

`src/` layout is the modern Python default for any package intended to be installed (which this is, via `uv tool install .`). Real Python's project-layout reference recommends it specifically for "packages intended to be installed, published, or reused" because it "separates source code from other components and prevents issues with" import resolution during local development. FastMCP itself uses the same layout — "The project follows a standard Python package layout with source code in src/fastmcp/ and tests in tests/."

```
yellow-sleeper/
├── pyproject.toml
├── README.md
├── .yellow-sleeper.yaml.example
├── src/
│   └── yellow_sleeper/
│       ├── __init__.py
│       ├── __main__.py              # python -m yellow_sleeper entry point
│       ├── server.py                # FastMCP instance, lifespan, tool registration
│       ├── config.py                # YAML/env loader, hot-reload, Policy model
│       ├── models/                  # All Pydantic models from TOOL_CONTRACTS.md
│       │   ├── __init__.py
│       │   ├── envelope.py          # ResponseEnvelope, status enums, validators
│       │   ├── shared.py            # SourceNote, PolicyFlag, BlockingRule, etc.
│       │   ├── trade.py             # AnalyzeTradeOutput, ValueMath, RosterContext
│       │   ├── roster.py            # GetMyRosterOutput, FindRosterOutput, etc.
│       │   ├── picks.py             # Pick, TradedPick, ListMyPicksOutput
│       │   ├── values.py            # GetPlayerValueOutput, ValueSourceBreakdown
│       │   ├── bpa.py               # BPACandidate, BestPlayerAvailableOutput
│       │   ├── draft.py             # WhatsOnTheClockOutput, PickContext
│       │   └── health.py            # HealthCheckOutput, LiveProbeResult
│       ├── clients/
│       │   ├── __init__.py
│       │   ├── sleeper.py           # SleeperClient (async, single shared instance)
│       │   ├── fantasycalc.py       # FantasyCalcClient + schema-drift detection
│       │   └── http.py              # Shared AsyncClient factory, retry helper
│       ├── store/
│       │   ├── __init__.py
│       │   ├── cache.py             # File cache: atomic writes, per-key locks, TTL
│       │   └── paths.py             # Cache path helpers (.cache/sleeper_players_nfl.json.gz, etc.)
│       ├── resolve/
│       │   ├── __init__.py
│       │   ├── players.py           # RapidFuzz wrapper, threshold logic
│       │   ├── picks.py             # Pick-parser grammar, lexicon
│       │   └── rosters.py           # find_roster with narrow-margin rule
│       ├── analyze/
│       │   ├── __init__.py
│       │   ├── trade.py             # The pipeline: validate → resolve → guardrail → math → context → flags
│       │   ├── roster.py            # Position depth, age stats, pick inventory diff
│       │   └── value.py             # Multi-source value joining, source_disagreement
│       ├── tools/                   # FastMCP-decorated tool functions, one per file
│       │   ├── __init__.py
│       │   ├── health_check.py
│       │   ├── get_my_roster.py
│       │   ├── find_roster.py
│       │   ├── list_traded_picks.py
│       │   ├── list_my_picks.py
│       │   ├── get_player_value.py
│       │   ├── analyze_trade.py
│       │   ├── league_power_map.py
│       │   ├── whats_on_the_clock.py
│       │   ├── best_player_available.py
│       │   └── refresh_cache.py
│       └── obs/
│           ├── __init__.py
│           ├── logging.py           # JSON formatter, redaction filter, rotation
│           └── caps.py              # truncate_string, truncate_array utilities
└── tests/
    ├── __init__.py
    ├── conftest.py                  # Shared fixtures
    ├── fixtures/                    # Pinned API response samples
    │   ├── sleeper/
    │   └── fantasycalc/
    ├── unit/
    │   ├── test_envelope_validators.py
    │   ├── test_pick_parser.py
    │   ├── test_player_resolver.py
    │   ├── test_cache.py
    │   └── test_config.py
    ├── integration/
    │   ├── test_sleeper_client.py
    │   ├── test_fantasycalc_client.py
    │   └── test_trade_pipeline.py
    └── smoke/                       # The six PRD smoke-test scenarios
        └── test_smoke_questions.py
```

**Why the boundaries are drawn this way:** `clients/` knows about HTTP and source-specific response shapes. `store/` knows about disk and TTLs. `resolve/` knows about fuzzy matching and pick grammar. `analyze/` orchestrates them and produces tool outputs. `tools/` is a thin FastMCP-decoration layer with no business logic — each file is roughly 20 lines that wires inputs, calls `analyze/`, and returns the typed output. This separation makes the smoke tests in `tests/smoke/` runnable without the MCP transport at all, which is essential for fast iteration.

### Single FastMCP instance, single `lifespan`

`src/yellow_sleeper/server.py` is the only place that imports `FastMCP`:

```python
from contextlib import asynccontextmanager
from mcp.server.fastmcp import FastMCP

from .clients.http import build_shared_client
from .config import load_config, ConfigWatcher

@asynccontextmanager
async def lifespan(server: FastMCP):
    config = load_config()
    http_client = build_shared_client()
    watcher = ConfigWatcher(config)
    try:
        yield {"config": config, "http": http_client, "watcher": watcher}
    finally:
        await http_client.aclose()

mcp = FastMCP("yellow-sleeper", lifespan=lifespan)

# Import each tool module to register its @mcp.tool() decorator
from .tools import (
    health_check, get_my_roster, find_roster, list_traded_picks,
    list_my_picks, get_player_value, analyze_trade, league_power_map,
    whats_on_the_clock, best_player_available, refresh_cache,
)
```

`__main__.py` is three lines:
```python
from .server import mcp
if __name__ == "__main__":
    mcp.run()
```

This matches the FastMCP 3.x pattern documented at gofastmcp.com and used in the official SDK examples.

---

## 2. Cache Layer

### Decision: File cache with atomic writes (`tempfile` + `os.replace`), one `asyncio.Lock` per cache key, gzip for the large player file only.

Four cache files, each with the TTL specified in the PRD:

| File | TTL | Format | Why |
|---|---|---|---|
| `.cache/sleeper_players_nfl.json.gz` | 24h | gzipped JSON | Sleeper docs explicitly warn this is ~5MB and should not be called more than once per day. "You should save this information on your own servers as this is not intended to be called every time you need to look up players due to the filesize being close to 5MB in size. You do not need to call this endpoint more than once per day." |
| `.cache/fantasycalc_values.json` | 6h | plain JSON | Small enough not to need compression; gzip would add latency without payoff |
| `.cache/league_snapshot.json` | 5min | plain JSON | Joined rosters + users + traded_picks; prevents three independent fetches per tool call |
| `.cache/draft_state.json` | 30s during active draft / 1h otherwise | plain JSON | Variable TTL — see §3 for the active-draft detection logic |

### Atomic write pattern

Every cache write goes through this function. No exceptions. The reason is concurrency: two tool calls may both detect a stale cache and both try to refresh; without atomic replacement, the second write can truncate the first and leave an unparseable file.

```python
# src/yellow_sleeper/store/cache.py
import os
import tempfile
import gzip
import json
from pathlib import Path
from typing import Any

async def atomic_write_json(path: Path, data: Any, *, gzipped: bool = False) -> None:
    """Write JSON to `path` atomically via tempfile + os.replace.

    Both files (temp and target) live in the same directory so os.replace
    is a real atomic rename on POSIX and Windows. On Windows, os.replace
    is the only call that guarantees atomic replacement of an existing file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        if gzipped:
            with os.fdopen(fd, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb") as gz:
                gz.write(json.dumps(data).encode("utf-8"))
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f)
        os.replace(tmp_path, path)  # atomic
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise
```

### Per-key locks

Each cache file has its own `asyncio.Lock`, held only across the read-modify-write cycle. Two reads can proceed in parallel; two writes against the same key serialize; writes against different keys remain parallel.

```python
# src/yellow_sleeper/store/cache.py
from asyncio import Lock
from collections import defaultdict

class Cache:
    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._locks: dict[str, Lock] = defaultdict(Lock)

    def _lock(self, key: str) -> Lock:
        return self._locks[key]

    async def read_or_fetch(
        self,
        key: str,
        ttl_seconds: int,
        fetcher: Callable[[], Awaitable[Any]],
        *,
        gzipped: bool = False,
    ) -> tuple[Any, CacheStatus]:
        """Return (data, status) where status is one of 'fresh' | 'cached' | 'stale'."""
        path = self.base_dir / f"{key}.json{'.gz' if gzipped else ''}"

        # Fast path: file exists and is within TTL — no lock needed for read
        if path.exists():
            age = time.time() - path.stat().st_mtime
            if age < ttl_seconds:
                return self._read(path, gzipped), "cached"

        # Slow path: stale or missing. Acquire the lock for this key.
        async with self._lock(key):
            # Re-check under lock — another coroutine may have refreshed already
            if path.exists() and (time.time() - path.stat().st_mtime) < ttl_seconds:
                return self._read(path, gzipped), "cached"

            try:
                data = await fetcher()
                await atomic_write_json(path, data, gzipped=gzipped)
                return data, "fresh"
            except Exception as e:
                # Fetch failed — fall back to stale cache if available
                if path.exists():
                    return self._read(path, gzipped), "stale"
                raise
```

### Stale-cache fallback

Returning stale data with `stale=True` and an `explanation` is mandatory per the PRD and `ResponseEnvelope` validator. The fallback path in the code above triggers whenever the fetcher raises *and* a previous cache file exists. The caller (typically a client method) is responsible for tagging the resulting `SourceNote` with `cache_status="stale"`, `stale=True`, and an explanation derived from the caught exception.

### Why not SQLite?

Considered. Rejected because (a) it adds a dep without solving a problem the file cache has, (b) the access pattern is whole-file read/write of cached blobs, not row-level queries, (c) it would require schema migrations on enum additions, which the file cache does not.

---

## 3. Sleeper Client

### Decision: One `httpx.AsyncClient` per process, lifespan-managed, with explicit per-operation timeouts and a single retry on 5xx/network errors.

**Why a shared client, not per-request:** the httpx maintainers' own guidance is explicit. "You should use a single shared client instance. You can use the asyncio_create_task() / asyncio.gather() primitives, but structured concurrency provides a more throughly designed approach to running multiple tasks." The httpx docs reinforce this: "In order to get the most benefit from connection pooling, make sure you're not instantiating multiple client instances - for example by using async with inside a 'hot loop'. This can be achieved either by having a single scoped client that's passed throughout wherever it's needed, or by having a single global client instance."

**Why explicit timeouts:** the FastMCP tutorial flagged this as an anti-pattern. "Do not call httpx.AsyncClient() with no timeout — the default is None (infinite) and a misbehaving upstream will park your tool forever."

The actual httpx default is 5 seconds, not infinite, but the principle stands — be explicit. The 2025 "httpx + asyncio patterns" reference uses this shape, which is what I recommend adopting verbatim:

```python
# src/yellow_sleeper/clients/http.py
import httpx

DEFAULT_TIMEOUT = httpx.Timeout(
    connect=3.0,   # TCP/TLS handshake
    read=5.0,      # waiting for response body
    write=5.0,     # sending request body
    pool=3.0,      # waiting for a free connection from the pool
)

def build_shared_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=DEFAULT_TIMEOUT,
        limits=httpx.Limits(
            max_connections=20,
            max_keepalive_connections=10,
            keepalive_expiry=30.0,
        ),
        headers={"User-Agent": "yellow-sleeper/1.0 (personal use)"},
    )
```

### Sleeper rate limiting

Confirmed across the official docs, the Go wrapper, the Laravel wrapper, the einreke MCP server, and the LangDB hosting page: "Per Sleeper's documentation, you should stay under 1000 API calls per minute to avoid being IP-blocked." This is far above any single-user usage pattern, but a global semaphore at 10 concurrent requests provides a cheap insurance policy against accidental burst loops (e.g., a buggy refresh path).

```python
# src/yellow_sleeper/clients/sleeper.py
from asyncio import Semaphore

class SleeperClient:
    BASE_URL = "https://api.sleeper.app/v1"

    def __init__(self, http: httpx.AsyncClient):
        self._http = http
        self._sem = Semaphore(10)  # courtesy ceiling

    async def _get(self, path: str) -> dict:
        url = f"{self.BASE_URL}{path}"
        async with self._sem:
            response = await self._http.get(url)
            response.raise_for_status()
            return response.json()
```

### Endpoint mapping

| Method | Endpoint | Used by | Cache |
|---|---|---|---|
| `get_state_nfl()` | `GET /state/nfl` | Health probe | none (cheap) |
| `get_players_nfl()` | `GET /players/nfl` | All player lookups | `sleeper_players_nfl.json.gz`, 24h |
| `get_league(league_id)` | `GET /league/{id}` | League metadata | `league_snapshot.json`, 5min |
| `get_rosters(league_id)` | `GET /league/{id}/rosters` | All roster tools | `league_snapshot.json`, 5min |
| `get_users(league_id)` | `GET /league/{id}/users` | Owner names everywhere | `league_snapshot.json`, 5min |
| `get_traded_picks(league_id)` | `GET /league/{id}/traded_picks` | Pick inventory | `league_snapshot.json`, 5min |
| `get_drafts(league_id)` | `GET /league/{id}/drafts` | Locate current draft_id | `league_snapshot.json`, 5min |
| `get_draft(draft_id)` | `GET /draft/{id}` | Draft status, on-the-clock | `draft_state.json`, variable TTL |
| `get_draft_picks(draft_id)` | `GET /draft/{id}/picks` | Recent picks, BPA exclusions | `draft_state.json`, variable TTL |

The `league_snapshot.json` cache is a *single* file that holds the joined `{league, rosters, users, traded_picks, drafts}` payload, populated by a coordinated batch fetch using `asyncio.gather`. This is the change from v0.3 that prevents three round trips per tool call.

### Active-draft detection for draft_state TTL

```python
# src/yellow_sleeper/clients/sleeper.py
def draft_state_ttl(draft: dict) -> int:
    """30s while drafting, 1h otherwise."""
    status = draft.get("status", "complete")
    return 30 if status == "drafting" else 3600
```

`status` values from Sleeper: `pre_draft`, `paused`, `drafting`, `complete`. Treat anything other than `drafting` as a stable state with a 1h TTL.

### Retry policy

Single retry on `httpx.HTTPStatusError` (5xx only) and `httpx.NetworkError`. No exponential backoff — single-user load means we want fast failure to fall back to stale cache rather than blocking the LLM for many seconds.

```python
async def _get_with_retry(self, path: str) -> dict:
    try:
        return await self._get(path)
    except (httpx.HTTPStatusError, httpx.NetworkError) as e:
        if isinstance(e, httpx.HTTPStatusError) and e.response.status_code < 500:
            raise  # don't retry 4xx
        await asyncio.sleep(0.5)
        return await self._get(path)
```

### Probe endpoints (for `force_probe=True`)

```python
async def probe(self) -> LiveProbeResult:
    start = time.monotonic()
    try:
        await self._get("/state/nfl")
        elapsed = int((time.monotonic() - start) * 1000)
        return LiveProbeResult(source="sleeper", reachable=True, latency_ms=elapsed, probed_at=now_utc())
    except Exception as e:
        return LiveProbeResult(source="sleeper", reachable=False, error=str(e)[:500], probed_at=now_utc())
```

`/state/nfl` is cheap, league-independent, and returns ~100 bytes. Use this for the probe rather than `/league/{id}` so the probe doesn't fail when the league configuration is wrong.

---

## 4. FantasyCalc Client

### Decision: Pin the query parameter shape against fixtures; fail open to last-known-good cache on any parse error.

**The reality of this dependency:** the FantasyCalc API is undocumented but stable enough to power the official Python tutorial published by fantasydatapros.com. The request shape is confirmed:

```
GET https://api.fantasycalc.com/values/current?isDynasty=true&numQbs=2&numTeams=14&ppr=1&tep=te+
```

Response shape (per the official tutorial example):

`{'player': {'id': 7569, 'name': 'Justin Jefferson', 'mflId': '14836', 'sleeperId': '6794', 'position': 'WR', 'maybeBirthday': '1999-06-16', 'maybeHeight': '73', 'maybeWeight': 195, 'maybeCollege': 'LSU', 'maybeTeam': 'MIN', 'maybeAge': 24.082668278253426, 'maybeYoe': 3}, 'value': 10726, 'overallRank': 1, 'positionRank': 1, 'trend30Day': -144, 'redraftDynastyValueDifference': 0, 'redraftDynastyValuePercDifference': 0, 'redraftValue': 10726, 'combinedValue': 21452, 'maybeMovingStandardDeviation': 3, 'maybeMovingStandardDeviationPerc': 0, 'maybeMovingStandardDeviationAdjusted': 2, 'displayTrend': False, 'maybeOwner': None, 'starter': False}`

Two things to call out from that shape:

1. **`sleeperId` is a top-level field** on every player record. This is the join key — no fuzzy matching is needed between FantasyCalc and Sleeper data. Important: it can be `None` for a small number of players (deep rookies, retired, recently signed) and the code path must handle that as `missing_value` rather than throwing.

2. **`tep` is a discrete FantasyCalc query parameter** with values omitted (no TEP), `te+`, or `te++`. Numeric `tep=0.5` is **not** accepted (HTTP 404). The Yellow Sleeper league is 0.5 TEP; Stage 2 maps that to **`tep=te+`** (aligned with KeepTradeCut’s TE+ guidance for +.5 PPR). Dynasty responses also include `position=PICK` rows (early/mid/late and slot-specific) used in later Stage 2 milestones as the primary pick-value source, with the static round table as fallback.

### Query parameters for the Yellow Sleeper league

```python
# src/yellow_sleeper/clients/fantasycalc.py
QUERY_PARAMS = {
    "isDynasty": "true",
    "numQbs": "2",      # Superflex
    "numTeams": "14",
    "ppr": "1",         # PPR
    "tep": "te+",       # 0.5 TEP → discrete TE+ tier
}
```

These are derived from `LEAGUE_FORMAT` / `tep_tier` config (`off` | `te+` | `te++`). Default is `te+`. When `tep_tier=off`, the `tep` key is omitted entirely (do not send empty `tep=`). FantasyCalc cache files are isolated by query shape while the contract cache key remains `fantasycalc_values`.

### Schema-drift detection

Adapter validates the response against a Pydantic model immediately on fetch. Any validation failure triggers fallback to stale cache + a `policy_flag` of type `STALE_DATA` with `severity="warning"`.

```python
class FCPlayer(BaseModel):
    id: int
    name: str
    sleeperId: Optional[str] = None
    position: str

class FCRecord(BaseModel):
    player: FCPlayer
    value: float
    overallRank: int
    redraftValue: Optional[float] = None
    trend30Day: Optional[float] = None
    # extra fields ignored via model_config = ConfigDict(extra="ignore")

class FantasyCalcClient:
    BASE_URL = "https://api.fantasycalc.com"

    async def get_current_values(self) -> list[FCRecord]:
        response = await self._http.get(
            f"{self.BASE_URL}/values/current",
            params=self.query_params,  # includes tep=te+ by default
        )
        response.raise_for_status()
        raw = response.json()
        # If parsing fails, the caller sees a ValidationError and falls back to stale cache.
        return [FCRecord.model_validate(r) for r in raw]
```

`extra="ignore"` is deliberate. New FantasyCalc fields (which they add periodically without notice) should not break parsing.

### Index for fast lookup

After fetch, the client builds two lookup dicts:

```python
def index(records: list[FCRecord]) -> dict:
    return {
        "by_sleeper_id": {r.player.sleeperId: r for r in records if r.player.sleeperId},
        "by_name_lower": {r.player.name.lower(): r for r in records},
    }
```

The `by_name_lower` index is the fallback for the rare case where Sleeper has a player without a FantasyCalc record but a name match works. Both indices are rebuilt on every cache refresh.

### Probe

```python
async def probe(self) -> LiveProbeResult:
    start = time.monotonic()
    try:
        response = await self._http.get(
            f"{self.BASE_URL}/values/current",
            params={**self.query_params, "limit": "1"},  # smallest possible response if supported
        )
        response.raise_for_status()
        # Validate at least the first record parses
        records = response.json()
        if not records:
            raise ValueError("empty response")
        FCRecord.model_validate(records[0])
        elapsed = int((time.monotonic() - start) * 1000)
        return LiveProbeResult(source="fantasycalc", reachable=True, latency_ms=elapsed, probed_at=now_utc())
    except Exception as e:
        return LiveProbeResult(source="fantasycalc", reachable=False, error=str(e)[:500], probed_at=now_utc())
```

Note: the `limit=1` parameter is speculative — if FantasyCalc ignores it, the probe still completes (just with more data). Parameter-shape validity is the real signal.

---

## 5. Pick Parser

### Decision: Regex-driven parser with a small lexicon, returning the canonical `pick_token` format from TOOL_CONTRACTS.md §2.5.

The PRD and contracts defer "pick-parsing lexicon" to the spec. Here it is.

### Inputs the parser must handle

Confirmed cases from real dynasty trade conversations:
- `"2027 1st"` — bare season + round
- `"my 2027 1st"` — possessive prefix
- `"2027 1st (via Mike)"` — explicit original-owner annotation
- `"Mike's 2027 1st"` — possessive original-owner
- `"next year's 1st"` — relative season
- `"2027 first"` — written-out round
- `"2027 1.03"` — slot notation (interpreted as 2027 round 1, slot info discarded since we don't have slot before draft)
- `"R1 2027"` — round-first notation
- `"2028 second-rounder"` — colloquial

### Grammar

```python
# src/yellow_sleeper/resolve/picks.py
import re

ROUND_LEXICON = {
    "1": 1, "1st": 1, "first": 1, "i": 1,
    "2": 2, "2nd": 2, "second": 2, "ii": 2,
    "3": 3, "3rd": 3, "third": 3, "iii": 3,
    "4": 4, "4th": 4, "fourth": 4, "iv": 4,
    "5": 5, "5th": 5, "fifth": 5, "v": 5,
}

RELATIVE_SEASON = {"next year": 1, "next year's": 1, "this year": 0, "this year's": 0}

# Captures: optional possessive, optional season, optional round word, optional "(via X)"
PICK_PATTERN = re.compile(
    r"""
    ^\s*
    (?:(?P<owner_possessive>[\w'.-]+)'s\s+)?           # "Mike's "
    (?:(?P<my>my)\s+)?                                  # "my "
    (?:(?P<relative>next\ year'?s?|this\ year'?s?)\s+)?
    (?:(?P<season>\d{4})\s+)?
    (?:r(?P<round_num>\d)|(?P<round_word>1st|2nd|3rd|4th|5th|first|second|third|fourth|fifth)|(?P<round_dot>\d)\.\d+|round\s*(?P<round_explicit>\d))
    (?:\s*\(\s*via\s+(?P<via>[\w\s.-]+?)\s*\))?
    \s*$
    """,
    re.IGNORECASE | re.VERBOSE,
)
```

### Resolution algorithm

1. Apply regex. If no match → `match_confidence=0`, `manual_review=True`, `candidates=[]`. Resolution status NEEDS_CLARIFICATION.
2. Extract season:
   - Absolute (e.g. "2027") → use directly
   - Relative ("next year") → `current_season + 1`
   - Missing → assume current season, but only if a draft is active; otherwise NEEDS_CLARIFICATION
3. Extract round (1–5 supported in MVP; anything else NEEDS_CLARIFICATION).
4. Resolve the *original owner*:
   - Explicit "via Mike" or "Mike's" → run `find_roster("Mike")` with the narrow-margin rule. If single confident match, that's the original owner. Otherwise NEEDS_CLARIFICATION.
   - "my" or no qualifier → Brad's `roster_id`
5. Filter Brad's owned picks by `(season, round)`. Three outcomes:
   - **Exactly one match** → resolve, `match_confidence=100`, return that `pick_token`
   - **Multiple matches** (Brad owns native + traded-in for the same season/round, and the input is unqualified) → `match_confidence=50`, return all candidates with `display_name` distinguishing native vs traded-in
   - **Zero matches** → Brad doesn't own a pick matching the description. Return `match_confidence=0` with explanation "you do not own a pick matching this description"

### Note on `my_receive[]`

For picks on the receive side, the original-owner constraint relaxes — Brad doesn't own picks he's receiving. The parser falls back to: any pick in the league with `(season, round)` matching, original owner resolved if specified. If the receive side specifies "Mike's 2027 1st" and Mike's 2027 1st is currently owned by a third party, that's still a valid receive (Brad would be acquiring it).

### Why a hand-written parser, not a grammar library

Considered `lark` and `pyparsing`. Rejected: the input language is small (maybe 8 templates), the regex is 20 lines, and the failure modes are easier to debug. Adding a parser-generator dep would be over-engineering.

---

## 6. Trade Analyzer Pipeline

### Decision: Strict ordered pipeline. Each stage returns or short-circuits with the appropriate status envelope state.

```
Input
  ↓
[1] Validate input (Pydantic catches malformed)
  ↓
[2] Snapshot policy (config + override) for this call
  ↓
[3] Resolve assets (players + picks → AssetResolution[])
  ↓
[4] Guardrail check (hard_untouchables on my_send only)
  ↓ ↓ (BLOCKED branch: short-circuit to envelope, value_math=None, roster_context=None)
[5] Compute value math (multi-source, source_disagreement, missing_values)
  ↓
[6] Compute roster context (pre/post depth, age stats, pick inventory)
  ↓
[7] Compute advisory policy_flags (protected_players, protected_pick_patterns, stale_data, etc.)
  ↓
[8] Assemble envelope (set policy_status, resolution_status, data_status; run validators)
  ↓
Output
```

### Why this order matters

- **Snapshot policy before resolution** so a YAML hot-reload mid-call cannot make the verdict inconsistent with the flags. Policy is captured at step 2 and threaded through every later stage.
- **Resolve before guardrail check** so the BLOCKED branch can report `asset_resolution[]` even when it short-circuits the rest. The LLM needs to see what *was* resolved on the way to BLOCKED.
- **Guardrail check on my_send only** per the contracts. `my_receive` may contain untouchables (the other team is offering them); that's interesting context, not a block.
- **Value math after guardrail** so BLOCKED trades skip value math entirely. PRD requires `value_math=None` for BLOCKED.
- **Roster context after value math** because roster context computation re-uses some of the same data fetches.
- **Flags last** because some flag types (`stale_data`, `source_disagreement`) depend on data fetched during value math.

### Status computation

```python
def compute_envelope_statuses(
    asset_resolutions: list[AssetResolution],
    blocking_rules: list[BlockingRule],
    value_math: Optional[ValueMath],
) -> tuple[PolicyStatus, ResolutionStatus, DataStatus]:
    policy = PolicyStatus.BLOCKED if blocking_rules else PolicyStatus.OK

    has_ambiguous = any(ar.manual_review for ar in asset_resolutions)
    resolution = ResolutionStatus.NEEDS_CLARIFICATION if has_ambiguous else ResolutionStatus.OK

    if policy == PolicyStatus.BLOCKED:
        data = DataStatus.UNAVAILABLE
    elif value_math is None or all(per_asset has missing values):
        data = DataStatus.UNAVAILABLE
    elif any per_asset has at least one missing value:
        data = DataStatus.PARTIAL
    else:
        data = DataStatus.COMPLETE

    return policy, resolution, data
```

(The `validate_blocked_trade_shape` validator on `AnalyzeTradeOutput` catches any combination violation before it leaves the server.)

### Value math implementation notes

- **Per-asset, per-source.** `value_math.per_asset[]` records every source consulted for every asset, including sources that returned None. This is what gives the LLM enough context to reason about confidence.
- **Send/receive totals only count enabled, non-None sources.** Missing values become `None` in the total when *all* sources are None for that asset; otherwise the available source's value is used.
- **source_disagreement is computed across enabled sources for the same asset.** When XLSX is disabled (MVP default), there's only one source per player, so `source_disagreement` will almost always be null in MVP. It activates meaningfully once Stage 2 spreadsheet overlay lands.

### Roster context implementation notes

- **Pre-state** is fetched from `league_snapshot.json` cache. **Post-state** is computed by applying the trade to the pre-state in memory — no Sleeper write, ever.
- **Age computation** treats picks as age=0 for the pick-conversion logic (rookies haven't aged into the league). This is a simplifying choice; document it in the `source_notes`.
- **Pick inventory keys** use the `season_round` format (`"2027_R1"`) rather than full `pick_token`, because counts aggregate across multiple picks of the same season+round.

---

## 7. Config Loader & Hot-Reload

### Decision: mtime-on-call validate-then-swap. No watchdog, no background tasks.

PRD says config hot-reloads. The two real options are `watchfiles` (background task) or mtime-check on every tool invocation. Mtime is the right call for a single-user, low-throughput server:

- One `os.stat()` call per tool invocation is sub-millisecond
- No dangling background task to manage in the asyncio loop
- Validation failure on reload preserves the previous config rather than crashing
- Easier to test (no time-dependent behavior)

### Config sources and precedence

Per PRD: `tool argument > .yellow-sleeper.yaml > env > built-in default`.

```python
# src/yellow_sleeper/config.py
class StaticConfig(BaseModel):
    sleeper_league_id: str
    sleeper_username: str
    league_format: str
    cache_dir: Path = Field(default=Path(".cache"))

class DynamicPolicy(BaseModel):
    hard_untouchables: list[str] = Field(default_factory=list)
    protected_players: list[str] = Field(default_factory=list)
    protected_pick_patterns: list[str] = Field(default_factory=list)

class Config:
    def __init__(self, static: StaticConfig, policy: DynamicPolicy, yaml_path: Path):
        self.static = static
        self._policy = policy
        self._yaml_path = yaml_path
        self._policy_mtime = yaml_path.stat().st_mtime if yaml_path.exists() else 0.0

    def policy(self, override: Optional[PolicyOverride] = None) -> tuple[DynamicPolicy, list[str]]:
        """Return (effective_policy, config_sources) for this call.

        Checks YAML mtime; reloads if changed and validation succeeds.
        Applies override if provided.
        """
        sources = []
        # mtime check
        if self._yaml_path.exists():
            mtime = self._yaml_path.stat().st_mtime
            if mtime > self._policy_mtime:
                try:
                    new_policy = self._load_yaml_policy()
                    self._policy = new_policy
                    self._policy_mtime = mtime
                    sources.append(".yellow-sleeper.yaml (reloaded)")
                except (yaml.YAMLError, ValidationError) as e:
                    # Validation failed: log, keep previous, do not raise
                    logger.warning("policy reload failed; keeping previous", extra={"error": str(e)})
                    sources.append(".yellow-sleeper.yaml (reload failed, using previous)")
            else:
                sources.append(".yellow-sleeper.yaml")

        effective = self._policy
        if override:
            effective = self._merge(self._policy, override)
            sources.insert(0, "tool_argument")

        return effective, sources
```

### YAML library

Use `ruamel.yaml`, not PyYAML. Reason: Brad edits `.yellow-sleeper.yaml` by hand; `ruamel.yaml` preserves comments and structure on reads. PyYAML strips them.

### Validation

The dynamic policy schema is open to user typos in player names (which is what fuzzy matching is for downstream). But it must reject:
- Non-list values for the three list fields
- Non-string entries in any list
- Empty strings

If any of those fail, the validation error is logged and the previous policy is kept. The tool response surfaces this via `config_sources` listing `"(reload failed, using previous)"` so the LLM can warn Brad that his edit didn't take effect.

---

## 8. Concurrency

### Decision: asyncio everywhere, single shared httpx client, per-cache-key locks, one global Sleeper semaphore. No multiprocessing, no threading.

The server is stdio-bound and single-user. Concurrency exists for one reason: fan-out fetches within a single tool call (e.g., `dynasty_league_power_map` joining 14 rosters with 14 sets of player values).

### Concurrency primitives in use

| Primitive | Where | Purpose |
|---|---|---|
| `asyncio.gather` | Sleeper batch fetch in `league_snapshot` refresh, parallel probes in health_check | Fan-out concurrent fetches |
| `asyncio.Semaphore(10)` | `SleeperClient` | Courtesy rate-limit ceiling |
| `asyncio.Lock` (per cache key) | `store/cache.py` | Prevent duplicate refresh / partial write |
| `asyncio.Timeout` (via httpx) | All HTTP calls | Bounded wait |

### What about `asyncio.TaskGroup` (Python 3.11+)?

The httpx maintainer notes: "At some point we ought to update our docs to help guide more folks towards structured concurrency, rather than working directly with asyncio. I'd either recommend working with Python 3.11 asyncio.TaskGroup." Adopt it where the code uses `gather` purely for parallelism (no need for `return_exceptions`):

```python
async with asyncio.TaskGroup() as tg:
    rosters_task = tg.create_task(client.get_rosters(league_id))
    users_task = tg.create_task(client.get_users(league_id))
    picks_task = tg.create_task(client.get_traded_picks(league_id))

rosters, users, picks = rosters_task.result(), users_task.result(), picks_task.result()
```

TaskGroup gives correct cleanup if any task fails. For the health probes (where we want both probe results regardless of failure), keep `asyncio.gather(..., return_exceptions=True)`.

### No threading, no multiprocessing

There is no CPU-bound work in this server. Fuzzy matching is microseconds. The whole point is I/O.

---

## 9. Logging

### Decision: stdlib `logging` with JSON formatter, redaction filter, 7-day rotation, written to `.cache/logs/server.log`. No third-party logging library.

```python
# src/yellow_sleeper/obs/logging.py
import logging
import logging.handlers
import json
import re

REDACT_KEYS = re.compile(r"league_id|user_id|username", re.IGNORECASE)

class RedactionFilter(logging.Filter):
    """Strip sensitive keys from log record `extra` dicts before they hit the formatter."""
    def filter(self, record: logging.LogRecord) -> bool:
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            record.extra_data = {
                k: ("***REDACTED***" if REDACT_KEYS.search(k) else v)
                for k, v in record.extra_data.items()
            }
        return True

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if hasattr(record, "extra_data"):
            payload["extra"] = record.extra_data
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)

def configure_logging(cache_dir: Path) -> None:
    log_path = cache_dir / "logs" / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.TimedRotatingFileHandler(
        log_path, when="midnight", backupCount=7, encoding="utf-8"
    )
    handler.setFormatter(JSONFormatter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger("yellow_sleeper")
    root.setLevel(logging.INFO)
    root.addHandler(handler)
    root.propagate = False  # don't bubble to stdio, which would corrupt MCP transport
```

**Critical:** `propagate = False` and write to a file, never stderr/stdout. Stdio is the MCP transport — any log output to it corrupts the protocol.

### What to log

- Every tool invocation: tool name, duration, `policy_status`/`resolution_status`/`data_status`
- Every cache miss/refresh: key, duration, status (fresh/cached/stale)
- Every HTTP error: source, endpoint, status code, error class
- Every config reload: result (success/failed-keep-previous)
- Every guardrail block: blocking_rules (asset only; never the full trade context)

### What not to log

- Full trade analysis responses (token-heavy, mostly noise)
- Full FantasyCalc value tables
- `league_id`, `user_id`, `username` (redaction filter catches `extra=` usage; if you use string interpolation directly into the message, that's on you — code review covers it)

---

## 10. Testing Strategy

### Decision: pytest + pytest-asyncio + respx. Three test tiers (unit, integration, smoke). Pinned API response fixtures.

**Why respx over pytest-httpx:** both work fine; respx integrates more cleanly with pytest fixtures and is the more idiomatic choice for httpx-specific testing. The 2025 reflection from Redowan Delowar covers this well: "During tests, respx intercepts HTTP requests made by httpx, allowing you to test against canned responses. The library provides a context manager that acts like an httpx client, so you can set the expected response. This removes the need to manually patch methods like post in httpx.AsyncClient."

### `pyproject.toml` test deps

```toml
[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "respx>=0.21",
    "ruff>=0.4",
]
```

### Three tiers

**Unit tests (`tests/unit/`)** — no I/O, no HTTP. Test pure functions: envelope validators, pick parser, fuzzy resolver, cache atomicity, config merging.

```python
# tests/unit/test_pick_parser.py
@pytest.mark.parametrize("input_str,expected_season,expected_round", [
    ("2027 1st", 2027, 1),
    ("my 2027 1st", 2027, 1),
    ("next year's 2nd", 2027, 2),  # assuming current=2026
    ("Mike's 2027 1st", 2027, 1),
    ("R1 2027", 2027, 1),
])
def test_pick_parser_extracts_season_and_round(input_str, expected_season, expected_round):
    result = parse_pick_description(input_str, current_season=2026)
    assert result.season == expected_season
    assert result.round == expected_round
```

**Integration tests (`tests/integration/`)** — exercise clients against mocked Sleeper/FantasyCalc responses via respx. Fixtures are pinned JSON files in `tests/fixtures/`.

```python
# tests/integration/test_sleeper_client.py
@pytest.mark.asyncio
@respx.mock
async def test_get_rosters_returns_parsed_models():
    respx.get("https://api.sleeper.app/v1/league/123/rosters").respond(
        json=load_fixture("sleeper/rosters_14team.json")
    )
    client = SleeperClient(build_shared_client())
    rosters = await client.get_rosters("123")
    assert len(rosters) == 14
```

**Smoke tests (`tests/smoke/`)** — the six PRD smoke-test questions, run end-to-end against mocked clients and a real cache directory. These are the eval set: did the tool return the right shape, with the right statuses, for each canonical scenario.

```python
# tests/smoke/test_smoke_questions.py
@pytest.mark.asyncio
async def test_smoke_3_blocked_trade_with_untouchable(mocked_clients, tmp_cache):
    """Smoke test 3: Analyze a proposed trade including at least one hard_untouchable (should block)."""
    result = await analyze_trade_pipeline(
        my_send=["Drake London"],
        my_receive=["Bijan Robinson"],
        policy=DynamicPolicy(hard_untouchables=["Drake London"]),
    )
    assert result.policy_status == PolicyStatus.BLOCKED
    assert result.data_status == DataStatus.UNAVAILABLE
    assert result.value_math is None
    assert result.roster_context is None
    assert len(result.blocking_rules) == 1
    assert result.blocking_rules[0].asset == "Drake London"
```

### Fixture management

`tests/fixtures/sleeper/` and `tests/fixtures/fantasycalc/` hold pinned response samples. Refresh quarterly by running a one-off script against the live APIs — never as part of CI. This catches schema drift early without coupling tests to network availability.

### Coverage targets

- Unit: 90%+ of `models/`, `resolve/`, `store/`, `analyze/value.py`
- Integration: every client method, both success and error paths
- Smoke: all six PRD scenarios passing

`pytest-cov` is fine; `coverage.py` is fine. Not a strong preference.

### What not to test

- FastMCP transport. Trust the framework.
- httpx itself.
- Pydantic itself.

---

## 11. Distribution & Client Setup

### Decision: `uv tool install .` from local checkout. No PyPI publish for MVP.

The Yellow Sleeper is a single-user personal tool. Publishing to PyPI is unnecessary and adds version-management overhead. `uv tool install` from a local path is the supported flow.

### `pyproject.toml` essentials

```toml
[project]
name = "yellow-sleeper"
version = "0.1.0"
description = "Local MCP server for the Sleeper fantasy football league."
requires-python = ">=3.11"
dependencies = [
    "mcp[cli]>=1.0",
    "pydantic>=2.7",
    "httpx>=0.27",
    "ruamel.yaml>=0.18",
    "rapidfuzz>=3.9",
]

[project.scripts]
yellow-sleeper = "yellow_sleeper.__main__:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

Note: the script entry point lets the client config invoke `yellow-sleeper` directly rather than `uv run python -m`, which avoids the working-directory dependence.

### Install flow

```bash
cd ~/code/yellow-sleeper
uv tool install .
yellow-sleeper --help  # smoke test
```

### Claude Desktop config

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or the Windows equivalent:

```json
{
  "mcpServers": {
    "yellow-sleeper": {
      "command": "yellow-sleeper",
      "env": {
        "SLEEPER_LEAGUE_ID": "...",
        "SLEEPER_USERNAME": "brad",
        "LEAGUE_FORMAT": "14-team SF PPR 0.5 TEP",
        "CACHE_DIR": "/Users/brad/.yellow-sleeper-cache"
      }
    }
  }
}
```

### Claude Code config

Per the official Anthropic docs, add via the Claude Code CLI:

```bash
claude mcp add yellow-sleeper -- yellow-sleeper
```

with env vars set in the shell environment.

### Codex CLI config

Already captured in PRD v0.4.4:

```toml
[mcp_servers.yellow-sleeper]
command = "yellow-sleeper"

[mcp_servers.yellow-sleeper.env]
SLEEPER_LEAGUE_ID = "..."
SLEEPER_USERNAME = "brad"
LEAGUE_FORMAT = "14-team SF PPR 0.5 TEP"
CACHE_DIR = "/Users/brad/.yellow-sleeper-cache"
```

### `.yellow-sleeper.yaml` example

Stored alongside the project or at `~/.yellow-sleeper.yaml`; path is configurable via `YELLOW_SLEEPER_CONFIG` env var:

```yaml
# Yellow Sleeper trade policy
hard_untouchables:
  - Drake London
  - Harold Fannin

protected_players:
  - Jayden Daniels
  - Jaxon Smith-Njigba

protected_pick_patterns:
  - 2027 1st
  - 2028 1st
```

### Upgrade flow

```bash
cd ~/code/yellow-sleeper
git pull
uv tool install --reinstall .
```

`--reinstall` forces overwrite of the installed entry point.

---

## 12. Open Questions Closed by This Spec

Items previously listed as open in TOOL_CONTRACTS.md §7:

- **Pick-parsing lexicon** — full grammar in §5.
- **`inclusion_reasons` algorithm for BPA** — see §6 framing; specific predicates are: `rookie_status:true`, `position:{Q,R,W,T}`, `not_already_drafted:true`, `value_source:{fantasycalc,xlsx,local}`. The function takes a candidate player + draft state and returns the list of predicates that hold.
- **Concurrency model** — §8.
- **Sleeper probe response semantics** — §3. "Reachable" means HTTP 200 with parseable JSON.
- **FantasyCalc probe parameters** — §4. Always use league's actual `numTeams`/`ppr`/`numQbs`. The `limit=1` addition is speculative but harmless.

---

## 13. Items Deferred to Stage 2

Stage 2 accuracy track (see `STAGE2_PLAN.md`). Schema stays `1.0`; no public `ValueMath` range fields.

Completed:

- TEP-aware FantasyCalc query via `tep=te+` (0.5 TEP mapping)

Still in this Stage 2 track (later PRs):

- FantasyCalc pick ladder as primary pick values (static table remains fallback)
- Spreadsheet/CSV value overlay (`source=xlsx` contract name; CSV file format)
- Conditional / pick-swap trade handling with scenario ranges in `per_asset` (no public `delta_min`/`delta_max`)

Still deferred (not accuracy-critical):

- Multi-user support
- Public HTTP transport
- Docker packaging
- OAuth / authentication
- Live league chat / Sleeper notifications

---

## 14. Document Status

This specification is engineering-authoritative for implementation. Divergence between this document and the PRD or TOOL_CONTRACTS.md is a bug — reconcile by updating this document first, then PR-ing the corresponding PRD/contracts update. Schema changes follow TOOL_CONTRACTS.md §6.
