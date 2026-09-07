
---

Version: 0.4.4 (Polished Canonical Edition) Date: May 11, 2026 Owner: Brad / Yellow Sleeper Canonical status: Product requirements source of truth Target clients: Claude Code and Codex MVP architecture: Single local stdio MCP server with LLM-first context output and minimal guardrails Transport: stdio (subprocess, stdin/stdout) Schema_version: "1.0"

---

# Yellow Sleeper MCP Server PRD v0.4.4

### TL;DR

Single-user, local MCP server that provides structured, source-rich dynasty league data to LLM agents (Claude Code, Codex) and enforces only three hard guardrails: (1) untouchable block, (2) asset resolution required, (3) no-write actions. All domain context, value surface, and policy rules are returned only for LLM advisory/consumption. Verdicts, recommendations, and subjective scores are strictly out of scope for the server. This PRD is canonical and self-contained, no dependency on former drafts.

---

## MVP Definition of Done

* Stdio subprocess server with MCP-compatible contract (Claude/Codex ready), using official SDK (see code import below).
* Structured JSON per tool response with field-level source, freshness/staleness, caps per field and explicit null + reason on data holes.
* Statuses are independent and all three are always returned. For any call, policy_status, resolution_status, and data_status may be in any combination; e.g., BLOCKED + NEEDS_CLARIFICATION + PARTIAL. The LLM must evaluate them independently.
* All dynamic config (untouchables, protected assets/picks) loaded from args/YAML/env, always surfaced in each response.
* No write-action tools, no verdicts/recommendations/context_scores, no multi-user or public endpoint, no tokenbowl-mcp code dependency unless license is permissive.
* Explicit agent contract for all tool outputs (see final section).

---

## Status Fields (Explicit Tri-state)

Every response surfaces:

* "policy_status": "OK" | "BLOCKED"
  * BLOCKED only for detected untouchables in my_send\[\]
* "resolution_status": "OK" | "NEEDS_CLARIFICATION"
  * NEEDS_CLARIFICATION for ambiguous asset, fuzzy \[70–88), or totally unresolved (<70)
* "data_status": "COMPLETE" | "PARTIAL" | "UNAVAILABLE"
  * PARTIAL if value math can only be partially completed or other non-blocking gaps. UNAVAILABLE if no values for a trade are available at all.
* "schema_version": "1.0"

---

## Data Source of Truth Table

| Domain | MVP source of truth | Override allowed? |
| --- | --- | --- |
| Rosters/ownership | Sleeper | No |
| Users/owners | Sleeper | No |
| Draft state | Sleeper | No |
| Traded picks | Sleeper | No |
| Player identity | Sleeper player cache | Rare fallback only |
| Player values | FantasyCalc | Yes (Stage 2 xlsx) |
| Pick values | Static table/config | Yes |
| Rookie board | Local board/config | Yes |
| Trade policy | Tool args / YAML | Yes |

---

## Pick Inventory Algorithm (native grid plus traded overlay)

1. Supported seasons: current draft + two forward. After the current season's rookie draft is complete, spent picks are no longer capital — the native-grid window starts at season+1. Traded-pick market listings still default to [current, current+1, current+2].
2. Native grid: Cartesian product of (season × round × roster).
3. Native pick: original/current owner = roster.
4. Fetch Sleeper traded_picks. For each, overlay on matching native grid slot by season, round, original_owner_roster_id, set new current owner from owner_id.
5. Join roster IDs to display names from Sleeper users.
6. Filter to Brad’s picks for dynasty_list_my_picks.
7. Never infer projected slot unless explicit order, draft, or projection exists (no server “guessing”).

---

## Tool Contracts (Explicit, Agent-Usable)

All responses include schema_version, policy_status, resolution_status, data_status, and source_notes\[\]. Array fields default max 25, field-specific string/truncation caps: user input=200, names=100, source notes/errors=500, arrays=25 max unless stated, whole response ≤25k tokens.

policy_flags\[\]: { type, asset, rule_source, severity (info|warning), reason/flag }

policy_override YAML example:

```yaml
policy_override:
  hard_untouchables: \["Drake London", "Harold Fannin"\]
  protected_players: \["Jayden Daniels", "Jaxon Smith-Njigba"\]
  protected_pick_patterns: \["2027 1st", "2028 1st"\]

```

### 1\. dynasty_health_check

Input: none Output:

* status_msgs\[\] (≤10)
* cache_status
* league_id
* user
* config_sources\[\]
* errors\[\]
* ...standard status envelope

### 2\. dynasty_get_my_roster

Input: none Output:

* grouped_roster\[\] (by position, age, value, rookie, source)
* positional_depth (by position)
* age_stats (mean, median, by position)
* policy_flags\[\]
* source_notes\[\]
* ...status envelope

### 3\. dynasty_find_roster

Input: search_term (≤200 chars) Output:

* roster_id
* owner_name
* username
* match_confidence
* alternatives\[\] (≤5)
* ...status envelope

### 4\. dynasty_list_traded_picks

Input: seasons\[\] (≤3) Output: picks\[\] with enriched attribution, source_notes\[\]

* ...status envelope

### 5\. dynasty_list_my_picks

Input: seasons\[\] (optional), include_traded_away? (bool) Output: owned_picks\[\], traded_away_picks\[\], unresolved\[\], source_notes\[\]

* ...status envelope

### 6\. dynasty_get_player_value

Input: player (≤100 chars), valuation_source? (fantasycalc|xlsx|auto) Output:

* value
* value_sources\[\] (name, value, timestamp, enabled)
* source_disagreement (if ≥2 sources differ >25%)
* source_notes\[\], missing_values\[\]
* ...status envelope

### 7\. dynasty_analyze_trade

Input: my_send\[\], my_receive\[\], policy_override? Output:

* policy_status
* resolution_status
* data_status
* blocking_rules\[\]
* asset_resolution\[\] (input, resolved_id, match_confidence, candidates\[\])
* value_math (send_total, receive_total, delta, delta_pct, source_disagreement)
* policy_flags\[\]
* roster_context (position_depth_change, age_stats, pick_inventory_summary)
* source_notes\[\]
* ...status envelope

### 8\. dynasty_league_power_map

Input: include_pick_value? (bool) Output:

* teams\[\] (roster_id, owner, username, positional_rollups, pick_total, roster_age, missing_flags, context_summary)
* ...status envelope

### 9\. dynasty_whats_on_the_clock

Input: draft_id?, pool? Output:

* draft_status (current, not-started, complete)
* pick_context (round, slot, on-the-clock owner, team)
* recent_picks\[\] (≤10)
* source_notes\[\]
* ...status envelope

### 10\. dynasty_best_player_available

Input: draft_id?, position?, limit?, rookie_board_source? Output:

* candidates\[\] (player_id, name (≤100), position, value, rookie_status, prior_drafted, inclusion_reasons\[\] (≤5, e.g., \["rookie_status:true", "position:RB", "not_already_drafted:true", "value_source:fantasycalc"\]), source_notes\[\])
* excluded_count
* board_source
* ...status envelope
* Note: inclusion_reasons\[\] are factual reasons for listing; they are not arguments for selecting that player. Example: \["rookie_status:true", "position:RB", "not_already_drafted:true", "value_source:fantasycalc"\].

### 11\. dynasty_refresh_cache

Input: force? (bool, default false) Output:

* refreshed\[\]
* failures\[\]
* prior_status\[\]
* post_status\[\]
* ...status envelope

---

## LLM Consumption Contract

* The MCP server only returns facts, joins, context, and flag/info fields—never verdicts, recommendations, or strategy.
* Agents/LLMs must process statuses independently: BLOCKED is a guardrail, NEEDS_CLARIFICATION triggers a clarification prompt, PARTIAL/UNAVAILABLE are surfaced directly to user as data-quality context.
* Agents/LLMs use inclusion_reasons for BPA only to surface context for candidate inclusion; they are not arguments for specific actions.
* Source notes/staleness flags inform the user of value or draft data age.
* Never claim the server can write to Sleeper or automate transactions.
* Missing/ambiguous values and agent-confidence limits are strictly surfaced—never filled in or fabricated.

---

## Additional Implementor Notes

* Field-caps as above; response max 25,000 tokens; trim arrays to fit
* Protocol/SDK: use from mcp.server.fastmcp import FastMCP for official MCP Python SDK integration.
* Codex CLI config example:

```
\[mcp_servers.yellow-sleeper\]
command = "uv"
args = \["run", "python", "-m", "yellow_sleeper"\]
cwd = "/path/to/yellow-sleeper"

\[mcp_servers.yellow-sleeper.env\]
SLEEPER_LEAGUE_ID = "..."
SLEEPER_USERNAME = "..."
LEAGUE_FORMAT = "14-team SF PPR 0.5 TEP"
CACHE_DIR = ".cache"

```

* All major future technical/scope/contract changes to be double-documented in PRD and TOOL_CONTRACTS.md (& version bump for any breaking change).

---

## Docstring & UX Style Guide

* Tool docstrings: one sentence, action/subject first, agent-discoverable (“Return Brad’s X with all context/policy/source details.”)
* Arrays, messages, and context fields: concise/factual, no recommendation language by server.

---

## Product Status

This is the agent/coding canonical base PRD for MVP. No other version, tool, or document is required to implement, test, or reason about the MCP server’s required MVP behaviors.

---