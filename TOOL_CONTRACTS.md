---

## Version: 1.0 (Final) Date: May 11, 2026 Owner: Brad / Yellow Sleeper Companion to: PRD v0.4.4 (Polished Canonical Edition) Schema_version: "1.0" Status: Engineering-authoritative contracts for the eleven dynasty\_\* tools

# Yellow Sleeper MCP — Tool Contracts

This document is the engineering source of truth for tool input/output shapes. The PRD describes *what* each tool returns and why; this document specifies *exactly* the Pydantic models, field types, validators, and JSON examples engineering codes against and tests assert against.

**Conventions used throughout:**

* All models are Pydantic v2 (`from pydantic import BaseModel, Field`).
* All field names are `snake_case`.
* Optional fields use `Optional[T] = None`; never `Union[T, None]`.
* Every field has a `Field(..., description=...)` so FastMCP propagates the description to the MCP tool schema.
* All responses inherit from `ResponseEnvelope` (defined below).
* All tools may raise `TransportError` (defined below) for non-domain failures; domain failures are expressed via the tri-state status fields, not exceptions.
* All string fields are truncated and control-char-stripped per the PRD caps: `user_input ≤ 200`, `names ≤ 100`, `notes/errors ≤ 500`, arrays default `≤ 25`, full response `≤ 25,000 tokens`.
* All categorical fields use `Enum` (not `Literal`) for IDE ergonomics, schema introspection, and consistency. Schema evolution policy is documented in §6.

---

## 1\. Shared Models

These models are defined once and referenced by every tool contract below.

### 1.1 Status Enums

```python
from enum import Enum

class PolicyStatus(str, Enum):
    OK = "OK"
    BLOCKED = "BLOCKED"

class ResolutionStatus(str, Enum):
    OK = "OK"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"

class DataStatus(str, Enum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"
    UNAVAILABLE = "UNAVAILABLE"

class FlagSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"

class FlagType(str, Enum):
    PROTECTED_PLAYER = "protected_player"
    PROTECTED_PICK_PATTERN = "protected_pick_pattern"
    MISSING_VALUE = "missing_value"
    SOURCE_DISAGREEMENT = "source_disagreement"
    STALE_DATA = "stale_data"
    AMBIGUOUS_RESOLUTION = "ambiguous_resolution"
    CONDITIONAL_OR_SWAP_TRADE = "conditional_or_swap_trade"

```

### 1.2 SourceNote

Per-field provenance. Attached to every response that surfaces data from Sleeper, FantasyCalc, the spreadsheet, or local config.

```python
class SourceNote(BaseModel):
    field: str = Field(..., max_length=100, description="Dotted path of the field this note describes, e.g. 'value_math.send_total'.")
    source: Literal\["sleeper", "fantasycalc", "xlsx", "local_config", "computed"\] = Field(..., description="Origin of the data.")
    timestamp: datetime = Field(..., description="UTC timestamp the source data was fetched or computed.")
    cache_status: Literal\["fresh", "cached", "stale"\] = Field(..., description="'fresh' = just fetched; 'cached' = within TTL; 'stale' = served past TTL because refresh failed.")
    stale: bool = Field(False, description="True iff cache_status == 'stale'. Duplicated for ergonomics; LLMs filter on this.")
    explanation: Optional\[str\] = Field(None, max_length=500, description="Required when stale=True. Explains why stale data was returned (e.g. 'FantasyCalc fetch failed, serving last-known-good from 14h ago').")

```

### 1.3 PolicyFlag

Advisory flag raised by the server. Never blocks. Always returned in `policy_flags[]` and surfaced to the LLM for weighing.

```python
class PolicyFlag(BaseModel):
    type: FlagType = Field(..., description="Categorical flag type from the FlagType enum. LLM routes interpretation by this field.")
    asset: Optional\[str\] = Field(None, max_length=100, description="Player name, pick_token, or null if flag is non-asset-specific.")
    rule_source: Literal\[".yellow-sleeper.yaml", "tool_argument", "computed"\] = Field(..., description="Where the rule that produced this flag came from.")
    severity: FlagSeverity = Field(..., description="'info' = neutral context; 'warning' = LLM should weigh carefully but not refuse.")
    reason: str = Field(..., max_length=500, description="Agent-readable explanation. Written as a fact, not a recommendation.")

```

### 1.4 BlockingRule

Populated only when `policy_status == BLOCKED`. Explains every guardrail violation in `my_send[]`.

```python
class BlockingRule(BaseModel):
    rule: Literal\["hard_untouchable"\] = Field(..., description="The named guardrail. Only 'hard_untouchable' is implemented in MVP. Adding new guardrails is a breaking change per §6.")
    asset: str = Field(..., max_length=100, description="The asset that triggered the block.")
    matched_against: str = Field(..., max_length=100, description="The entry from hard_untouchables that matched.")
    match_confidence: int = Field(..., ge=0, le=100, description="Fuzzy match score (0–100). Must be ≥ 88 for a block to fire.")
    rule_source: Literal\[".yellow-sleeper.yaml", "tool_argument"\] = Field(..., description="Where the hard_untouchables list came from.")

```

### 1.5 AssetResolution

Per-asset resolution record. Returned for every asset in `my_send[]` and `my_receive[]` regardless of outcome. Players and picks share this shape but follow different scoring conventions — see §4.

```python
class Candidate(BaseModel):
    sleeper_id: Optional\[str\] = Field(None, max_length=20, description="Populated for player candidates. Null for pick candidates.")
    pick_token: Optional\[str\] = Field(None, max_length=30, description="Populated for pick candidates. Null for player candidates.")
    name: str = Field(..., max_length=100, description="For players: full name. For picks: display_name like '2027 1st (via Mike Johnson)'.")
    position: Optional\[str\] = Field(None, max_length=10)
    team: Optional\[str\] = Field(None, max_length=10)
    match_confidence: int = Field(..., ge=0, le=100)

class AssetResolution(BaseModel):
    input: str = Field(..., max_length=200, description="The raw asset string the user supplied.")
    asset_type: Literal\["player", "pick"\] = Field(..., description="Picks resolve through structured natural-language parse; players resolve through fuzzy string match. Scoring differs — see §4.")
    resolved_id: Optional\[str\] = Field(None, max_length=30, description="Sleeper ID for players (e.g. '11620'), or pick_token for picks (e.g. 'pick_2027_r1_orig3'). Null when unresolved.")
    match_confidence: int = Field(
        ...,
        ge=0,
        le=100,
        description=(
            "For players (fuzzy string match): ≥88 = resolved; \[70, 88) = NEEDS_CLARIFICATION with candidates\[\]; <70 = failed. "
            "For picks (structured natural-language parse): 100 = parsed to exactly one owned pick; 50 = parsed structurally but matches multiple owned picks (NEEDS_CLARIFICATION); 0 = unparseable. "
            "The 50 value is a convention; intermediate scores are not used for picks."
        )
    )
    candidates: List\[Candidate\] = Field(default_factory=list, max_length=5, description="Populated when match_confidence indicates ambiguity per §4.")
    manual_review: bool = Field(False, description="True when match_confidence indicates clarification is needed (players: \[70, 88); picks: 50).")

```

### 1.6 ValueMath

Trade value math. Always advisory — never produces a verdict.

```python
class ValueSourceBreakdown(BaseModel):
    source: Literal\["fantasycalc", "xlsx", "config_pick_table"\]
    value: Optional\[float\] = Field(None, description="Null when this source has no value for this asset.")
    timestamp: datetime
    enabled: bool = Field(..., description="False if the source is disabled by config (e.g. XLSX_OVERRIDE_ENABLED=false).")

class SourceDisagreement(BaseModel):
    max_delta_pct: float = Field(..., description="Largest percentage spread between any two enabled sources.")
    sources: List\[ValueSourceBreakdown\] = Field(..., max_length=10)

class ValueMath(BaseModel):
    send_total: Optional\[float\] = Field(None, description="Sum of resolved send-side values. Null if data_status == UNAVAILABLE.")
    receive_total: Optional\[float\] = Field(None)
    delta: Optional\[float\] = Field(None, description="receive_total - send_total. Server returns the raw number; LLM interprets.")
    delta_pct: Optional\[float\] = Field(None, description="delta / send_total \* 100. Null when send_total is 0 or null.")
    per_asset: List\[Dict\[str, Any\]\] = Field(default_factory=list, description="Per-asset value breakdown for transparency. Each entry: {asset, side: 'send'|'receive', value, sources\[\]}.")
    source_disagreement: Optional\[SourceDisagreement\] = Field(None, description="Present only when ≥2 enabled sources differ by >25% for at least one asset.")

```

### 1.7 RosterContext

The data block that makes `dynasty_analyze_trade` useful to the LLM. Pre/post snapshot of roster shape.

```python
class PositionDepthChange(BaseModel):
    position: Literal\["QB", "RB", "WR", "TE"\]
    pre: int = Field(..., ge=0)
    post: int = Field(..., ge=0)
    delta: int = Field(..., description="post - pre. Can be negative.")

class AgeStats(BaseModel):
    pre_avg: float
    pre_median: float
    post_avg: float
    post_median: float
    by_position: Dict\[str, Dict\[str, float\]\] = Field(default_factory=dict, description="Optional per-position breakdown: {position: {pre_avg, post_avg, ...}}.")

class PickInventorySummary(BaseModel):
    pre: Dict\[str, int\] = Field(..., description="Counts by season+round, e.g. {'2026_R1': 1, '2027_R1': 2}.")
    post: Dict\[str, int\] = Field(...)
    delta: Dict\[str, int\] = Field(...)

class RosterContext(BaseModel):
    position_depth_change: List\[PositionDepthChange\]
    age_stats: AgeStats
    pick_inventory_summary: PickInventorySummary

```

### 1.8 ResponseEnvelope

Every tool response inherits from this. Defines the tri-state status and the always-present fields.

```python
class ResponseEnvelope(BaseModel):
    schema_version: Literal\["1.0"\] = "1.0"
    policy_status: PolicyStatus
    resolution_status: ResolutionStatus
    data_status: DataStatus
    blocking_rules: List\[BlockingRule\] = Field(default_factory=list, description="Populated only when policy_status == BLOCKED. Empty otherwise.")
    policy_flags: List\[PolicyFlag\] = Field(default_factory=list, max_length=25)
    source_notes: List\[SourceNote\] = Field(default_factory=list, max_length=25)
    config_sources: List\[str\] = Field(default_factory=list, description="Ordered list showing which config sources applied to this call, e.g. \['tool_argument', '.yellow-sleeper.yaml'\].")

```

**Status interaction rules (encoded as validators, not just convention):**

* `blocking_rules` MUST be non-empty when `policy_status == BLOCKED`; MUST be empty otherwise.
* A response may have any combination of the three statuses. BLOCKED does not short-circuit resolution or data evaluation; the server still attempts asset resolution and value math where feasible. The LLM evaluates the three statuses independently.
* `policy_status == BLOCKED` MAY coexist with `value_math == None` in `dynasty_analyze_trade` (the PRD specifies the server "will not return trade math" for blocked trades). In that case `data_status == UNAVAILABLE` is the correct co-state.

### 1.9 TransportError

For non-domain failures only (network unreachable, malformed input that fails Pydantic validation before reaching tool logic, etc.). Domain failures use the tri-state envelope, not this.

```python
class TransportError(BaseModel):
    ok: Literal\[False\] = False
    error_type: Literal\[
        "validation_error",
        "transport_error",
        "internal_error",
    \]
    message: str = Field(..., max_length=500)
    retry_hint: Optional\[str\] = Field(None, max_length=500)

```

---

## 2\. Tool Contracts

Each tool below specifies: Pydantic input model, Pydantic output model (extending `ResponseEnvelope`), happy-path JSON example, and one notable status-branch example. Examples are usable as test fixtures.

### 2.1 dynasty_health_check

**Purpose:** Confirm config, cache freshness, and source reachability. Run at session start. Cache-only by default; pass `force_probe=True` for a live HTTP probe of Sleeper and FantasyCalc (recommended before live draft windows).

```python
class HealthCheckInput(BaseModel):
    force_probe: bool = Field(
        False,
        description=(
            "When True, perform live HTTP probes to Sleeper and FantasyCalc in parallel. "
            "Adds 1–3 seconds. Recommended before live draft windows or after suspected source outages. "
            "When False (default), only cached state is reported."
        )
    )

class LiveProbeResult(BaseModel):
    source: Literal\["sleeper", "fantasycalc"\]
    reachable: bool
    latency_ms: Optional\[int\] = Field(None, ge=0)
    error: Optional\[str\] = Field(None, max_length=500)
    probed_at: datetime

class HealthCheckOutput(ResponseEnvelope):
    status_msgs: List\[str\] = Field(default_factory=list, max_length=10)
    cache_status: Dict\[str, Literal\["fresh", "cached", "stale", "missing"\]\] = Field(
        ..., description="Keyed by cache file: sleeper_players_nfl, fantasycalc_values, league_snapshot, draft_state."
    )
    league_id: str = Field(..., max_length=20)
    user: str = Field(..., max_length=100)
    errors: List\[str\] = Field(default_factory=list, max_length=10)
    live_probe_results: Optional\[List\[LiveProbeResult\]\] = Field(
        None,
        description="Populated only when force_probe=True. Null otherwise."
    )

```

**Status envelope mapping for the health check:**

| Cache state | force_probe | Probe result | `data_status` | `policy_flags` |
| --- | --- | --- | --- | --- |
| All fresh | False | n/a | COMPLETE | — |
| Any stale/missing | False | n/a | PARTIAL | `stale_data` per source |
| All fresh | True | All reachable | COMPLETE | — |
| All fresh | True | Some unreachable | PARTIAL | `stale_data` (warning) per unreachable |
| Some stale | True | All reachable | PARTIAL | `stale_data` per stale |
| All stale/missing | True | All unreachable | UNAVAILABLE | warnings on each |

**Probe targets:**

* Sleeper: `GET /v1/state/nfl` (cheap, league-independent) + `GET /v1/league/<id>` (confirms configured league still resolves).
* FantasyCalc: `GET /values/current` with the league's actual `numTeams`/`numQbs`/`ppr` parameters (confirms parameter shape still works — the main schema-drift risk).

**Happy-path example (default, no probe):**

```json
{
  "schema_version": "1.0",
  "policy_status": "OK",
  "resolution_status": "OK",
  "data_status": "COMPLETE",
  "blocking_rules": \[\],
  "policy_flags": \[\],
  "source_notes": \[
    {"field": "league_id", "source": "local_config", "timestamp": "2026-05-11T14:00:00Z", "cache_status": "fresh", "stale": false, "explanation": null}
  \],
  "config_sources": \[".yellow-sleeper.yaml", "env"\],
  "status_msgs": \["all caches within TTL"\],
  "cache_status": {
    "sleeper_players_nfl": "cached",
    "fantasycalc_values": "cached",
    "league_snapshot": "fresh",
    "draft_state": "missing"
  },
  "league_id": "1234567890",
  "user": "brad",
  "errors": \[\],
  "live_probe_results": null
}

```

### 2.2 dynasty_get_my_roster

**Purpose:** Return Brad's roster grouped by position with values, ages, source notes, and advisory flags.

```python
class RosterPlayer(BaseModel):
    sleeper_id: str = Field(..., max_length=20)
    name: str = Field(..., max_length=100)
    position: Literal\["QB", "RB", "WR", "TE"\]
    team: Optional\[str\] = Field(None, max_length=10)
    age: Optional\[float\] = None
    value: Optional\[float\] = Field(None, description="Null when no value source returned a value; reason in source_notes.")
    rookie_status: bool = False
    value_sources: List\[ValueSourceBreakdown\] = Field(default_factory=list)

class PositionalDepth(BaseModel):
    position: Literal\["QB", "RB", "WR", "TE"\]
    count: int = Field(..., ge=0)
    starters_required: int = Field(..., ge=0, description="From LEAGUE_FORMAT; e.g. 1 QB + Superflex slot can hold a 2nd QB.")

class GroupedRoster(BaseModel):
    position: Literal\["QB", "RB", "WR", "TE"\]
    players: List\[RosterPlayer\] = Field(..., max_length=25)

class LineupSlot(BaseModel):
    index: int
    slot_position: str
    sleeper_id: Optional\[str\] = None
    name: Optional\[str\] = None
    empty: bool = False

class GetMyRosterOutput(ResponseEnvelope):
    grouped_roster: List\[GroupedRoster\]
    positional_depth: List\[PositionalDepth\]
    age_stats: AgeStats
    missing_values: List\[str\] = Field(default_factory=list, max_length=25, description="sleeper_ids with no value from any enabled source.")
    starters: List\[LineupSlot\] = Field(default_factory=list, max_length=25)
    reserve: List\[LineupSlot\] = Field(default_factory=list, max_length=25)
    taxi: List\[LineupSlot\] = Field(default_factory=list, max_length=25)
    player_count: int = 0
    roster_spots: int = 0
    over_capacity: bool = False

```

Input: none.

**Happy-path example (abbreviated):**

```json
{
  "schema_version": "1.0",
  "policy_status": "OK",
  "resolution_status": "OK",
  "data_status": "COMPLETE",
  "blocking_rules": \[\],
  "policy_flags": \[
    {"type": "protected_player", "asset": "Drake London", "rule_source": ".yellow-sleeper.yaml", "severity": "info", "reason": "Drake London is on protected_players list."}
  \],
  "source_notes": \[
    {"field": "grouped_roster", "source": "sleeper", "timestamp": "2026-05-11T14:00:00Z", "cache_status": "fresh", "stale": false, "explanation": null},
    {"field": "grouped_roster\[\].value", "source": "fantasycalc", "timestamp": "2026-05-11T11:30:00Z", "cache_status": "cached", "stale": false, "explanation": null}
  \],
  "config_sources": \[".yellow-sleeper.yaml"\],
  "grouped_roster": \[
    {"position": "WR", "players": \[
      {"sleeper_id": "9745", "name": "Drake London", "position": "WR", "team": "ATL", "age": 24.6, "value": 8200, "rookie_status": false, "value_sources": \[{"source": "fantasycalc", "value": 8200, "timestamp": "2026-05-11T11:30:00Z", "enabled": true}\]}
    \]}
  \],
  "positional_depth": \[{"position": "WR", "count": 7, "starters_required": 3}\],
  "age_stats": {"pre_avg": 25.2, "pre_median": 24.8, "post_avg": 25.2, "post_median": 24.8, "by_position": {}},
  "missing_values": \[\]
}

```

### 2.3 dynasty_find_roster

**Purpose:** Fuzzy lookup of a roster by team name, owner display name, or username. Uses the **narrow-margin rule**: even when the top match scores ≥88, if the second-best match scores within 5 points, the result is NEEDS_CLARIFICATION.

```python
class FindRosterInput(BaseModel):
    search_term: str = Field(..., min_length=1, max_length=200)

class RosterMatch(BaseModel):
    roster_id: int
    owner_name: str = Field(..., max_length=100)
    username: str = Field(..., max_length=100)
    match_confidence: int = Field(..., ge=0, le=100)
    matched_field: Literal\["team_name", "display_name", "username"\] = Field(..., description="Which field the search_term scored highest against.")

class FindRosterOutput(ResponseEnvelope):
    matched: Optional\[RosterMatch\] = Field(
        None,
        description="Populated when exactly one match scores ≥88 AND the second-best match (if any) scores at least 5 points lower. Otherwise null and \`alternatives\` is populated."
    )
    alternatives: List\[RosterMatch\] = Field(default_factory=list, max_length=5)

```

**NEEDS_CLARIFICATION example (three Mikes):**

```json
{
  "schema_version": "1.0",
  "policy_status": "OK",
  "resolution_status": "NEEDS_CLARIFICATION",
  "data_status": "COMPLETE",
  "blocking_rules": \[\],
  "policy_flags": \[{"type": "ambiguous_resolution", "asset": "mike", "rule_source": "computed", "severity": "warning", "reason": "Search term matched multiple rosters within 5 points of each other."}\],
  "source_notes": \[{"field": "alternatives", "source": "sleeper", "timestamp": "2026-05-11T14:00:00Z", "cache_status": "fresh", "stale": false, "explanation": null}\],
  "config_sources": \[\],
  "matched": null,
  "alternatives": \[
    {"roster_id": 4, "owner_name": "Mike Smith", "username": "mikes", "match_confidence": 92, "matched_field": "display_name"},
    {"roster_id": 11, "owner_name": "Mike Johnson", "username": "bigmike", "match_confidence": 89, "matched_field": "display_name"},
    {"roster_id": 7, "owner_name": "Big Mike's Wagon", "username": "wagon", "match_confidence": 82, "matched_field": "team_name"}
  \]
}

```

### 2.4 dynasty_list_traded_picks

**Purpose:** Return all Sleeper traded-pick records with original, previous, and current owner attribution.

```python
class ListTradedPicksInput(BaseModel):
    seasons: Optional\[List\[int\]\] = Field(None, max_length=3, description="If null, defaults to \[current, current+1, current+2\].")

class TradedPick(BaseModel):
    pick_token: str = Field(..., max_length=30, description="Canonical pick identifier (see §2.5 Pick).")
    display_name: str = Field(..., max_length=100)
    season: int
    round: int = Field(..., ge=1, le=10)
    original_owner_roster_id: int
    previous_owner_roster_id: Optional\[int\] = None
    current_owner_roster_id: int
    original_owner_name: str = Field(..., max_length=100)
    current_owner_name: str = Field(..., max_length=100)

class ListTradedPicksOutput(ResponseEnvelope):
    picks: List\[TradedPick\] = Field(..., max_length=200)
    truncated: bool = Field(False, description="True when more traded picks exist than picks\[\]. Never silently drop rows.")
    total_count: int = Field(0, description="Full matching traded-pick count before the output cap.")

```

### 2.5 dynasty_list_my_picks

**Purpose:** Return Brad's full pick inventory: native + traded-in − traded-away. Implements the pick inventory algorithm from PRD §"Pick Inventory Algorithm".

**Pick token canonical format:** `pick_{season}_r{round}_orig{original_owner_roster_id}`. Examples: `pick_2027_r1_orig3` (2027 first-round pick originally owned by roster 3), `pick_2028_r2_orig11` (Brad's native 2028 2nd, if his roster_id is 11). The `orig` segment is the **original owner's roster_id** and is stable across trades — do not confuse with pick slot.

```python
class ListMyPicksInput(BaseModel):
    seasons: Optional\[List\[int\]\] = Field(None, max_length=3)
    include_traded_away: bool = False

class Pick(BaseModel):
    pick_token: str = Field(
        ...,
        max_length=30,
        pattern=r"^pick\_\\d{4}\_r\\d+\_orig\\d+$",
        description=(
            "Canonical pick identifier. Format: pick\_<season>\_r<round>\_orig<original_owner_roster_id>. "
            "Example: 'pick_2027_r1_orig3'. The 'orig' segment is the original owner's roster_id and is "
            "stable across trades; do not confuse it with pick slot."
        )
    )
    display_name: str = Field(
        ...,
        max_length=100,
        description="Human/LLM-readable form for surfacing to the user. Example: '2027 1st (via Mike Johnson)' or '2027 1st (native)'."
    )
    season: int = Field(..., ge=2020, le=2099)
    round: int = Field(..., ge=1, le=10)
    original_owner_roster_id: int
    original_owner_name: str = Field(..., max_length=100)
    current_owner_roster_id: int
    origin: Literal\["native", "traded_in", "traded_away"\]

class ListMyPicksOutput(ResponseEnvelope):
    owned_picks: List\[Pick\] = Field(default_factory=list, max_length=25)
    traded_away_picks: List\[Pick\] = Field(default_factory=list, max_length=25)
    unresolved: List\[str\] = Field(default_factory=list, max_length=10, description="Any traded_picks records that could not be overlaid onto the native grid.")

```

### 2.6 dynasty_get_player_value

**Purpose:** Multi-source value lookup for a single player. Wrong-value risk is high (silently contaminates downstream LLM reasoning), so the NEEDS_CLARIFICATION + candidates pattern applies — see §4.

```python
class GetPlayerValueInput(BaseModel):
    player: str = Field(..., max_length=100, description="Player name or Sleeper ID.")
    valuation_source: Literal\["fantasycalc", "xlsx", "auto"\] = "auto"

class GetPlayerValueOutput(ResponseEnvelope):
    sleeper_id: Optional\[str\] = Field(None, max_length=20)
    name: Optional\[str\] = Field(None, max_length=100)
    value: Optional\[float\] = None
    value_sources: List\[ValueSourceBreakdown\] = Field(default_factory=list)
    source_disagreement: Optional\[SourceDisagreement\] = None
    missing_values: List\[str\] = Field(default_factory=list, max_length=5, description="Source names that returned no value for this player.")
    candidates: List\[Candidate\] = Field(default_factory=list, max_length=5, description="Populated when fuzzy match falls in \[70, 88). Resolution_status is NEEDS_CLARIFICATION.")

```

### 2.7 dynasty_analyze_trade

**Purpose:** Resolve assets, enforce hard guardrails, compute value math, attach roster context, raise advisory flags. **Returns no verdict.**

**Asset resolution semantics:** Players resolve via fuzzy string match (`≥88` resolves; `[70, 88)` returns NEEDS_CLARIFICATION with candidates; `<70` fails). Picks resolve via structured natural-language parse (`100` resolves to a single owned pick; `50` indicates the description parses but matches multiple owned picks — NEEDS_CLARIFICATION with candidates; `0` is unparseable). See §4 for the full threshold table.

```python
class PolicyOverride(BaseModel):
    hard_untouchables: Optional\[List\[str\]\] = Field(None, max_length=25)
    protected_players: Optional\[List\[str\]\] = Field(None, max_length=25)
    protected_pick_patterns: Optional\[List\[str\]\] = Field(None, max_length=25)

class AnalyzeTradeInput(BaseModel):
    my_send: List\[str\] = Field(..., min_length=1, max_length=10, description="Assets Brad would give up. Player names or natural-language pick descriptions like '2027 1st'.")
    my_receive: List\[str\] = Field(..., min_length=1, max_length=10)
    policy_override: Optional\[PolicyOverride\] = None

class AnalyzeTradeOutput(ResponseEnvelope):
    asset_resolution: List\[AssetResolution\] = Field(..., description="One entry per asset across my_send and my_receive.")
    value_math: Optional\[ValueMath\] = Field(None, description="Null when policy_status == BLOCKED or data_status == UNAVAILABLE.")
    roster_context: Optional\[RosterContext\] = Field(None, description="Null when policy_status == BLOCKED.")

```

**BLOCKED example:**

```json
{
  "schema_version": "1.0",
  "policy_status": "BLOCKED",
  "resolution_status": "OK",
  "data_status": "UNAVAILABLE",
  "blocking_rules": \[
    {"rule": "hard_untouchable", "asset": "Drake London", "matched_against": "Drake London", "match_confidence": 100, "rule_source": ".yellow-sleeper.yaml"}
  \],
  "policy_flags": \[\],
  "source_notes": \[
    {"field": "asset_resolution", "source": "sleeper", "timestamp": "2026-05-11T14:00:00Z", "cache_status": "fresh", "stale": false, "explanation": null}
  \],
  "config_sources": \[".yellow-sleeper.yaml"\],
  "asset_resolution": \[
    {"input": "Drake London", "asset_type": "player", "resolved_id": "9745", "match_confidence": 100, "candidates": \[\], "manual_review": false},
    {"input": "Bijan Robinson", "asset_type": "player", "resolved_id": "9491", "match_confidence": 100, "candidates": \[\], "manual_review": false}
  \],
  "value_math": null,
  "roster_context": null
}

```

**Happy-path OK example (abbreviated):**

```json
{
  "schema_version": "1.0",
  "policy_status": "OK",
  "resolution_status": "OK",
  "data_status": "COMPLETE",
  "blocking_rules": \[\],
  "policy_flags": \[
    {"type": "protected_pick_pattern", "asset": "pick_2027_r1_orig11", "rule_source": ".yellow-sleeper.yaml", "severity": "warning", "reason": "2027 1st matches protected_pick_patterns. LLM should weigh carefully."}
  \],
  "source_notes": \[
    {"field": "value_math", "source": "fantasycalc", "timestamp": "2026-05-11T11:30:00Z", "cache_status": "cached", "stale": false, "explanation": null}
  \],
  "config_sources": \[".yellow-sleeper.yaml"\],
  "asset_resolution": \[
    {"input": "my 2027 1st", "asset_type": "pick", "resolved_id": "pick_2027_r1_orig11", "match_confidence": 100, "candidates": \[\], "manual_review": false},
    {"input": "Jaylen Wright", "asset_type": "player", "resolved_id": "11620", "match_confidence": 100, "candidates": \[\], "manual_review": false}
  \],
  "value_math": {
    "send_total": 4200, "receive_total": 4500, "delta": 300, "delta_pct": 7.14,
    "per_asset": \[
      {"asset": "pick_2027_r1_orig11", "side": "send", "value": 3000, "sources": \[{"source": "config_pick_table", "value": 3000, "timestamp": "2026-05-11T00:00:00Z", "enabled": true}\]},
      {"asset": "11620", "side": "receive", "value": 4500, "sources": \[{"source": "fantasycalc", "value": 4500, "timestamp": "2026-05-11T11:30:00Z", "enabled": true}\]}
    \],
    "source_disagreement": null
  },
  "roster_context": {
    "position_depth_change": \[{"position": "RB", "pre": 5, "post": 6, "delta": 1}\],
    "age_stats": {"pre_avg": 25.2, "pre_median": 24.8, "post_avg": 25.0, "post_median": 24.5, "by_position": {}},
    "pick_inventory_summary": {"pre": {"2027_R1": 2}, "post": {"2027_R1": 1}, "delta": {"2027_R1": -1}}
  }
}

```

**Ambiguous pick example (**`my 2027 1st` **when Brad owns two):**

```json
{
  "schema_version": "1.0",
  "policy_status": "OK",
  "resolution_status": "NEEDS_CLARIFICATION",
  "data_status": "PARTIAL",
  "blocking_rules": \[\],
  "policy_flags": \[
    {"type": "ambiguous_resolution", "asset": "my 2027 1st", "rule_source": "computed", "severity": "warning", "reason": "Description matches multiple owned picks. LLM should ask Brad which one."}
  \],
  "source_notes": \[\],
  "config_sources": \[".yellow-sleeper.yaml"\],
  "asset_resolution": \[
    {
      "input": "my 2027 1st",
      "asset_type": "pick",
      "resolved_id": null,
      "match_confidence": 50,
      "manual_review": true,
      "candidates": \[
        {"pick_token": "pick_2027_r1_orig11", "name": "2027 1st (native)", "match_confidence": 50},
        {"pick_token": "pick_2027_r1_orig3", "name": "2027 1st (via Mike Johnson)", "match_confidence": 50}
      \]
    }
  \],
  "value_math": null,
  "roster_context": null
}

```

### 2.8 dynasty_league_power_map

**Purpose:** Per-team rollups for all 14 teams. **Returns no rank, no tier, no total.** The LLM ranks and tiers.

```python
class TeamRollup(BaseModel):
    roster_id: int
    owner_name: str = Field(..., max_length=100)
    username: str = Field(..., max_length=100)
    positional_rollups: Dict\[Literal\["QB", "RB", "WR", "TE"\], float\] = Field(..., description="Sum of FantasyCalc values per position.")
    roster_total: float
    pick_total: Optional\[float\] = Field(None, description="Null when include_pick_value=False.")
    roster_age: AgeStats
    missing_flags: List\[str\] = Field(default_factory=list, max_length=10, description="Names with no value source.")
    context_summary: str = Field(..., max_length=500, description="Factual summary, e.g. 'oldest roster in league, strongest at WR, thinnest at QB'. No recommendation language.")

class LeaguePowerMapInput(BaseModel):
    include_pick_value: bool = False

class LeaguePowerMapOutput(ResponseEnvelope):
    teams: List\[TeamRollup\] = Field(..., min_length=1, max_length=20)

```

### 2.9 dynasty_whats_on_the_clock

**Purpose:** Current draft state and recent picks.

```python
class WhatsOnTheClockInput(BaseModel):
    draft_id: Optional\[str\] = Field(None, max_length=20)
    pool: Literal\["rookies_only", "all"\] = "rookies_only"

class PickContext(BaseModel):
    round: int = Field(..., ge=1)
    slot: int = Field(..., ge=1)
    on_the_clock_owner: str = Field(..., max_length=100)
    on_the_clock_team: str = Field(..., max_length=100)

class RecentPick(BaseModel):
    round: int
    slot: int
    sleeper_id: str = Field(..., max_length=20)
    name: str = Field(..., max_length=100)
    position: str = Field(..., max_length=10)
    drafted_by_owner: str = Field(..., max_length=100)

class WhatsOnTheClockOutput(ResponseEnvelope):
    draft_status: Literal\["drafting", "not_started", "complete"\]
    pick_context: Optional\[PickContext\] = Field(None, description="Null when draft_status != 'drafting'.")
    recent_picks: List\[RecentPick\] = Field(default_factory=list, max_length=10)

```

### 2.10 dynasty_best_player_available

**Purpose:** Return rookie-eligible BPA candidates. **Inclusion reasons are facts about list membership, not arguments for selection.** This tool has no fuzzy-resolve surface — inputs are structured filters, not free-text queries — so NEEDS_CLARIFICATION semantics do not apply (see §4).

```python
class BestPlayerAvailableInput(BaseModel):
    draft_id: Optional\[str\] = Field(None, max_length=20)
    position: Optional\[Literal\["QB", "RB", "WR", "TE"\]\] = None
    limit: int = Field(10, ge=1, le=25)
    rookie_board_source: Literal\["local", "fantasycalc", "xlsx"\] = "fantasycalc"

class BPACandidate(BaseModel):
    sleeper_id: str = Field(..., max_length=20)
    name: str = Field(..., max_length=100)
    position: Literal\["QB", "RB", "WR", "TE"\]
    value: Optional\[float\] = None
    rookie_status: bool
    prior_drafted: bool = Field(..., description="True iff this player has already been selected in the current draft.")
    inclusion_reasons: List\[str\] = Field(..., max_length=5, description="Factual reasons for list membership only. Examples: 'rookie_status:true', 'position:RB', 'not_already_drafted:true', 'value_source:fantasycalc'. NOT arguments for selecting the player.")

class BestPlayerAvailableOutput(ResponseEnvelope):
    candidates: List\[BPACandidate\] = Field(..., max_length=25)
    excluded_count: int = Field(..., ge=0, description="Count of players filtered out (already drafted, wrong position, non-rookie when rookies_only, etc.).")
    board_source: Literal\["local", "fantasycalc", "xlsx"\]

```

### 2.11 dynasty_refresh_cache

**Purpose:** Manually refresh player and value caches.

```python
class RefreshCacheInput(BaseModel):
    force: bool = Field(False, description="When True, refresh even if cache is within TTL.")

class CacheRefreshResult(BaseModel):
    cache_key: Literal\["sleeper_players_nfl", "fantasycalc_values", "league_snapshot", "draft_state"\]
    success: bool
    error: Optional\[str\] = Field(None, max_length=500)

class RefreshCacheOutput(ResponseEnvelope):
    refreshed: List\[CacheRefreshResult\] = Field(default_factory=list)
    failures: List\[CacheRefreshResult\] = Field(default_factory=list)
    prior_status: Dict\[str, Literal\["fresh", "cached", "stale", "missing"\]\] = Field(...)
    post_status: Dict\[str, Literal\["fresh", "cached", "stale", "missing"\]\] = Field(...)

```

---

## 3\. Cross-Cutting Validators

These are model-level validators that run on every response before it leaves the server. They encode the PRD's invariants as code, not convention.

```python
from pydantic import model_validator

class ResponseEnvelope(BaseModel):
    # ... fields as above ...

    @model_validator(mode="after")
    def \_validate_blocking_consistency(self):
        if self.policy_status == PolicyStatus.BLOCKED and not self.blocking_rules:
            raise ValueError("policy_status=BLOCKED requires non-empty blocking_rules")
        if self.policy_status == PolicyStatus.OK and self.blocking_rules:
            raise ValueError("policy_status=OK requires empty blocking_rules")
        return self

    @model_validator(mode="after")
    def \_validate_stale_explanation(self):
        for note in self.source_notes:
            if note.stale and not note.explanation:
                raise ValueError(f"source_note for field={note.field} is stale; explanation is required")
            if note.cache_status == "stale" and not note.stale:
                raise ValueError(f"source_note for field={note.field}: cache_status=stale must set stale=True")
        return self

```

Trade-specific validator on `AnalyzeTradeOutput`:

```python
class AnalyzeTradeOutput(ResponseEnvelope):
    # ... fields ...

    @model_validator(mode="after")
    def \_validate_blocked_trade_shape(self):
        if self.policy_status == PolicyStatus.BLOCKED:
            if self.value_math is not None:
                raise ValueError("BLOCKED trades must not return value_math")
            if self.roster_context is not None:
                raise ValueError("BLOCKED trades must not return roster_context")
            if self.data_status != DataStatus.UNAVAILABLE:
                raise ValueError("BLOCKED trades must have data_status=UNAVAILABLE")
        return self

```

Find-roster-specific validator enforces the narrow-margin rule:

```python
class FindRosterOutput(ResponseEnvelope):
    # ... fields ...

    @model_validator(mode="after")
    def \_validate_narrow_margin(self):
        if self.matched is not None and self.alternatives:
            top = self.matched.match_confidence
            for alt in self.alternatives:
                if top - alt.match_confidence < 5:
                    raise ValueError(
                        "narrow-margin rule: when top match is within 5 points of any alternative, "
                        "matched must be None and resolution_status must be NEEDS_CLARIFICATION"
                    )
        return self

```

---

## 4\. Fuzzy Matching & Resolution Thresholds

Resolution thresholds vary by tool because the cost of a wrong match varies. The table below is canonical; tool-section descriptions reference this.

| Tool | Match type | Resolve | Clarify (NEEDS_CLARIFICATION) | Fail |
| --- | --- | --- | --- | --- |
| `dynasty_analyze_trade` (players) | fuzzy string | ≥88 | \[70, 88) → `candidates[]` | <70 |
| `dynasty_analyze_trade` (picks) | structured parse | 100 (exactly one owned pick matches) | 50 (description matches multiple owned picks) → `candidates[]` | 0 (unparseable) |
| `dynasty_get_player_value` | fuzzy string | ≥88 | \[70, 88) → `candidates[]` | <70 |
| `dynasty_find_roster` | fuzzy string | ≥88 **and** ≥5pt gap to next-best match | otherwise → `alternatives[]` | <70 |
| `dynasty_best_player_available` | n/a | structured filters only — no fuzzy surface | — | — |

**Why the variance:**

* **Trade analyzer** and **player value** carry the highest wrong-match cost: bad resolution silently contaminates downstream LLM reasoning. Strict thresholds.
* **Find roster** adds the narrow-margin rule because the "three Mikes" failure mode is real — a single high-confidence match can still be ambiguous if a second match is nearly as good. Three searchable fields (team_name, display_name, username) compound this.
* **Picks** use a different scoring convention because the match isn't continuous — descriptions either parse-and-resolve to one pick, parse-and-resolve to many, or don't parse at all. The 100/50/0 convention preserves the same status semantics without faking continuous scores.
* **BPA** has no fuzzy surface — its inputs are structured filters (position, limit, source). The "Candidate" name there refers to draft candidates, not disambiguation candidates.

**Fuzzy implementation:** RapidFuzz `WRatio` for player and roster string matching. Picks use a hand-written natural-language parser (regex + lexicon for "1st"/"2nd"/"3rd", "next year", "2027", etc.) feeding into the canonical `pick_token` format.

---

## 5\. Field Cap Enforcement

The PRD specifies global caps; this section says *how* to enforce them. Truncation happens at serialization time via a single utility, not scattered through tool logic.

```python
def truncate_string(s: str, max_length: int) -> str:
    """Strip control characters, then truncate to max_length. Append '…' if truncated."""
    cleaned = "".join(ch for ch in s if ch.isprintable() or ch in ("\\n", "\\t"))
    if len(cleaned) <= max_length:
        return cleaned
    return cleaned\[: max_length - 1\] + "…"

def truncate_array(items: list, max_length: int) -> list:
    return items\[:max_length\]

```

Cap reference table (matches PRD §"Tool Contracts"):

| Field class | Max length | Notes |
| --- | --- | --- |
| User input | 200 | `search_term`, `player` input field |
| Names / IDs | 100 | player name, owner name, username |
| Source IDs | 20 | sleeper_id, league_id |
| Pick tokens | 30 | pick_token |
| Position | 10 | QB, RB, WR, TE |
| Notes / errors | 500 | source_note.explanation, error.message |
| Arrays (default) | 25 | overridden per field |
| Total response | 25,000 tok | LLM-side ceiling; enforced at serialize |

---

## 6\. Schema Evolution Policy

**Additive changes (minor** `schema_version` **bump recommended for clarity):**

* Adding a new field to an existing model
* Adding a new value to a closed enum (`FlagType`, `PolicyStatus`, etc.)
* Loosening a constraint (e.g., raising a max_length)
* Adding a new optional input parameter
* Adding a new tool

These bump `1.0 → 1.1`.

**Breaking changes (major** `schema_version` **bump required):**

* Renaming a field
* Retyping a field (e.g., `int` → `str`)
* Removing a field, enum value, or tool
* Tightening a constraint in a way that rejects previously-valid data
* Changing the meaning of an existing field
* Adding a new value to `BlockingRule.rule` (because the guardrail surface is intentionally tight)

These bump `1.0 → 2.0`.

**Every** `schema_version` **change requires:**

1. Update of the `Schema_version` line in the PRD header
2. A new entry in a `Schema Changelog` section in the PRD
3. Update of the `schema_version` `Literal` in `ResponseEnvelope`

---

## 7\. Open Questions for the TECHNICAL_SPEC

Items the contracts surface that belong to the technical spec, not here:

* Pick-parsing lexicon: full grammar for natural-language pick descriptions ("my 2027 1st", "next year's 2nd", "Mike's 2028", "2027 1.03"). The contract specifies the output format and resolution thresholds; the spec specifies the parser.
* Exact algorithm for `inclusion_reasons` generation in BPA: which predicates fire under which conditions.
* Concurrency model for cache writes during a live draft (per-key `asyncio.Lock` is in the PRD; the implementation belongs in the spec).
* The Sleeper `/state/nfl` and `/league/<id>` probe response shapes and what counts as "reachable" (200 with parseable JSON, presumably; spec confirms).
* FantasyCalc probe parameter selection: should the probe always use the league's actual `numTeams`/`ppr`/`numQbs`, or a minimal fixed set?

---

## 8\. Document Status

This contracts document is engineering-authoritative for tool I/O shapes. Any divergence between this document and PRD v0.4.4 is a bug in this document; report and reconcile. Schema-breaking changes follow the policy in §6 and require a parallel update to the PRD's `Schema_version` field.