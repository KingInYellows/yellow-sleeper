from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from tests.helpers import SYNTHETIC_LEAGUE_ID, SYNTHETIC_USERNAME, seed_scoped_cache

EXPECTED_TOOLS = {
    "dynasty_health_check",
    "dynasty_get_my_roster",
    "dynasty_find_roster",
    "dynasty_list_traded_picks",
    "dynasty_list_my_picks",
    "dynasty_get_player_value",
    "dynasty_analyze_trade",
    "dynasty_league_power_map",
    "dynasty_whats_on_the_clock",
    "dynasty_best_player_available",
    "dynasty_refresh_cache",
}


def _tool_json(result) -> dict:
    if result.isError:
        texts = [getattr(block, "text", "") for block in result.content]
        raise AssertionError(f"tool error: {texts}")
    if result.structuredContent:
        return result.structuredContent
    texts = [block.text for block in result.content if getattr(block, "text", None)]
    assert texts, "tool result had no text content"
    return json.loads(texts[0])


def _server_env(cache_dir: Path, *, with_identity: bool) -> dict[str, str]:
    env = os.environ.copy()
    env["CACHE_DIR"] = str(cache_dir)
    env["YELLOW_SLEEPER_CONFIG"] = str(cache_dir / "no-config.yaml")
    env["PYTHONUNBUFFERED"] = "1"
    if with_identity:
        env["SLEEPER_LEAGUE_ID"] = SYNTHETIC_LEAGUE_ID
        env["SLEEPER_USERNAME"] = SYNTHETIC_USERNAME
    else:
        env.pop("SLEEPER_LEAGUE_ID", None)
        env.pop("SLEEPER_USERNAME", None)
    return env


def _params(cache_dir: Path, *, with_identity: bool) -> StdioServerParameters:
    return StdioServerParameters(
        command="uv",
        args=["run", "yellow-sleeper"],
        env=_server_env(cache_dir, with_identity=with_identity),
        cwd=str(Path(__file__).resolve().parents[2]),
    )


@pytest.mark.asyncio
async def test_mcp_stdio_initialize_tools_list_and_synthetic_calls(tmp_path: Path) -> None:
    await seed_scoped_cache(tmp_path)
    params = _params(tmp_path, with_identity=True)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            assert init.serverInfo.name
            tools = await session.list_tools()
            names = {tool.name for tool in tools.tools}
            assert names == EXPECTED_TOOLS
            assert len(names) == 11

            health = await session.call_tool("dynasty_health_check", {})
            health_payload = _tool_json(health)
            assert health_payload["user"] == SYNTHETIC_USERNAME
            assert health_payload["league_id"] == SYNTHETIC_LEAGUE_ID

            value = await session.call_tool(
                "dynasty_get_player_value", {"player": "Drake London"}
            )
            value_payload = _tool_json(value)
            assert value_payload["name"] == "Drake London"
            assert value_payload["value"] == 8200
            notes = " ".join(
                note.get("explanation") or "" for note in value_payload.get("source_notes") or []
            )
            assert "te+" in notes
            assert "R1=3000" in notes

            traded = await session.call_tool("dynasty_list_traded_picks", {})
            traded_payload = _tool_json(traded)
            assert traded_payload["resolution_status"] == "ok"
            assert traded_payload["total_count"] >= 1
            assert any(
                pick.get("current_owner_name") == "Casey Quinn"
                for pick in traded_payload["picks"]
            )


@pytest.mark.asyncio
async def test_mcp_stdio_health_without_identity(tmp_path: Path) -> None:
    params = _params(tmp_path, with_identity=False)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            health = await session.call_tool("dynasty_health_check", {})
            payload = _tool_json(health)
            assert payload["league_id"] == "unconfigured"
            assert payload["errors"]
            assert "sleeper_league_id" in payload["errors"][0]
