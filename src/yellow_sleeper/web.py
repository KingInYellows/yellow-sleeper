"""Desk JSON API plus streamable HTTP MCP transport."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .runtime import create_runtime, set_runtime
from .tools.analyze_trade import dynasty_analyze_trade
from .tools.best_player_available import dynasty_best_player_available
from .tools.find_roster import dynasty_find_roster
from .tools.get_my_roster import dynasty_get_my_roster
from .tools.get_player_value import dynasty_get_player_value
from .tools.health_check import dynasty_health_check
from .tools.league_power_map import dynasty_league_power_map
from .tools.list_my_picks import dynasty_list_my_picks
from .tools.list_traded_picks import dynasty_list_traded_picks
from .tools.refresh_cache import dynasty_refresh_cache
from .tools.whats_on_the_clock import dynasty_whats_on_the_clock

TOOLS: dict[str, Callable[..., Any]] = {
    "dynasty_analyze_trade": dynasty_analyze_trade,
    "dynasty_best_player_available": dynasty_best_player_available,
    "dynasty_find_roster": dynasty_find_roster,
    "dynasty_get_my_roster": dynasty_get_my_roster,
    "dynasty_get_player_value": dynasty_get_player_value,
    "dynasty_health_check": dynasty_health_check,
    "dynasty_league_power_map": dynasty_league_power_map,
    "dynasty_list_my_picks": dynasty_list_my_picks,
    "dynasty_list_traded_picks": dynasty_list_traded_picks,
    "dynasty_refresh_cache": dynasty_refresh_cache,
    "dynasty_whats_on_the_clock": dynasty_whats_on_the_clock,
}


@asynccontextmanager
async def lifespan(_app: Starlette):
    runtime = create_runtime()
    set_runtime(runtime)
    try:
        yield
    finally:
        try:
            await runtime.aclose()
        finally:
            set_runtime(None)


async def health(_request: Request) -> JSONResponse:
    return JSONResponse({"ok": True, "tools": len(TOOLS), "stage": 2})


async def root(_request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "service": "yellow-sleeper",
            "health": "/health",
            "tools": "/tools/{name}",
            "stage": 2,
        }
    )


async def call_tool(request: Request) -> JSONResponse:
    name = request.path_params["name"]
    handler = TOOLS.get(name)
    if handler is None:
        return JSONResponse({"error": f"unknown tool: {name}"}, status_code=404)
    try:
        payload = await request.json()
    except Exception:
        return JSONResponse({"error": "request body must be JSON"}, status_code=400)
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        return JSONResponse({"error": "request body must be a JSON object"}, status_code=400)
    try:
        result = handler(**payload)
        if inspect.isawaitable(result):
            result = await result
    except TypeError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except Exception as exc:
        return JSONResponse({"error": str(exc)[:500]}, status_code=500)
    return JSONResponse(result)


app = Starlette(
    lifespan=lifespan,
    routes=[
        Route("/", root),
        Route("/health", health),
        Route("/tools/{name}", call_tool, methods=["POST"]),
    ],
)


def serve_http(host: str = "127.0.0.1", port: int = 8091) -> None:
    import uvicorn

    uvicorn.run(app, host=host, port=port, log_level="info")


def serve_mcp_http(host: str = "127.0.0.1", port: int = 8092) -> None:
    from .server import mcp

    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport="streamable-http")
