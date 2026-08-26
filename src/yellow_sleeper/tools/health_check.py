from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from ..analyze.pipelines import health_check_output
from ..models.health import LiveProbeResult
from ..runtime import get_runtime
from ..server import mcp

_PROBE_SOURCES = ("sleeper", "fantasycalc")


@mcp.tool()
async def dynasty_health_check(force_probe: bool = False) -> dict:
    """Return config, cache freshness, and source reachability details."""
    runtime = await get_runtime()
    probes = None
    if force_probe:
        raw_results = await asyncio.gather(
            runtime.sleeper.probe(),
            runtime.fantasycalc.probe(),
            return_exceptions=True,
        )
        probes = [
            result
            if isinstance(result, LiveProbeResult)
            else LiveProbeResult(
                source=_PROBE_SOURCES[i],  # type: ignore[arg-type]
                reachable=False,
                error=str(result)[:500],
                probed_at=datetime.now(UTC),
            )
            for i, result in enumerate(raw_results)
        ]
    output = health_check_output(
        cache_status=runtime.cache_statuses(),
        league_id=runtime.config.static.sleeper_league_id,
        user=runtime.config.static.sleeper_username,
        config_sources=runtime.config.static_sources,
        live_probe_results=probes,
    )
    return output.model_dump(mode="json")
