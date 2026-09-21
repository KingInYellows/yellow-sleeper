from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict

from ..models import LiveProbeResult
from ..store import Cache
from ..store.paths import fantasycalc_cache_variant

TepTier = Literal["off", "te+", "te++"]
FormatTep = Literal["te+", "te++"]

_VALID_TEP_TIERS: set[TepTier] = {"off", "te+", "te++"}
_VALID_NUM_TEAMS = frozenset({"8", "10", "12", "14"})
_VALID_NUM_QBS = frozenset({"1", "2"})
_VALID_PPR = frozenset({"0", "0.5", "1"})

_TEAM_COUNT_RE = re.compile(r"(?<!\d)(8|10|12|14)(?:\s*-?\s*team)?\b")
_TEP_AMOUNT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*tep\b")
_TE_PLUS_PLUS_RE = re.compile(r"te\s*\+\+")

PICK_TABLE_EXPLANATION = (
    "The static round table (R1=3000, R2=1200, R3=600, R4=300, R5=100) is fallback "
    "only when neither a generic PICK row nor Early/Mid/Late bands exist; it is not "
    "freshly fetched provider data."
)

PICK_PROVIDER_EXPLANATION = (
    "Pick values use generic FantasyCalc '{season} {ordinal}' PICK rows "
    "(e.g. '2027 1st'; never roster_id as a slot). Band-only Early/Mid/Late rows "
    "surface a low/high range; the single-number field stays empty."
)

UNSUPPORTED_FORMAT_NOTE = (
    "FantasyCalc values were not fetched for this league_format. This is not a "
    "silent reuse of another format's board."
)


class UnsupportedValuationQuery(ValueError):
    """Raised when league settings cannot be mapped to a documented FantasyCalc query."""

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__("; ".join(reasons)[:500])


@dataclass(frozen=True)
class FantasyCalcQuery:
    supported: bool
    params: dict[str, str]
    reasons: tuple[str, ...]
    tep_tier: TepTier
    league_format: str

    def encoded_query(self) -> str:
        return "&".join(f"{key}={self.params[key]}" for key in sorted(self.params))


def build_query_params(
    tep_tier: TepTier = "te+",
    *,
    num_teams: str = "14",
    num_qbs: str = "2",
    ppr: str = "1",
) -> dict[str, str]:
    """Build FantasyCalc /values/current query params.

    ``tep_tier='off'`` sends documented ``tep=none`` (empty ``tep=`` errors on
    the API). League 0.5 TEP maps to discrete ``te+``; ``tep=0.5`` is not a
    documented value. Documented enums: numTeams 8/10/12/14, numQbs 1/2,
    ppr 0/0.5/1, tep none/te+/te++ (FantasyCalc API docs, 2026-09-21).
    Re-implements the PR #16 query-shape idea (head 3a253dd) with attribution.
    """
    if tep_tier not in _VALID_TEP_TIERS:
        raise ValueError(f"invalid tep_tier {tep_tier!r}; expected off, te+, or te++")
    if num_teams not in _VALID_NUM_TEAMS:
        raise ValueError(f"invalid numTeams {num_teams!r}; expected 8, 10, 12, or 14")
    if num_qbs not in _VALID_NUM_QBS:
        raise ValueError(f"invalid numQbs {num_qbs!r}; expected 1 or 2")
    if ppr not in _VALID_PPR:
        raise ValueError(f"invalid ppr {ppr!r}; expected 0, 0.5, or 1")
    params = {
        "isDynasty": "true",
        "numQbs": num_qbs,
        "numTeams": num_teams,
        "ppr": ppr,
        "tep": "none" if tep_tier == "off" else tep_tier,
    }
    return params


QUERY_PARAMS = build_query_params("te+")


class FCPlayer(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: int
    name: str
    sleeperId: str | None = None
    position: str


class FCRecord(BaseModel):
    model_config = ConfigDict(extra="ignore")

    player: FCPlayer
    value: float
    overallRank: int
    redraftValue: float | None = None
    trend30Day: float | None = None


class FantasyCalcClient:
    BASE_URL = "https://api.fantasycalc.com"

    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        tep_tier: TepTier = "te+",
        query_params: dict[str, str] | None = None,
        league_format: str = "14-team SF PPR 0.5 TEP",
        query: FantasyCalcQuery | None = None,
    ) -> None:
        self._http = http
        self.league_format = league_format
        self.query = query if query is not None else resolve_fantasycalc_query(
            league_format, tep_tier=tep_tier
        )
        self.tep_tier = self.query.tep_tier if self.query.supported else tep_tier
        if query_params is not None:
            self.query_params = query_params
        elif self.query.supported:
            self.query_params = dict(self.query.params)
        else:
            self.query_params = {}

    def cache_variant(self, *, overlay_active: bool = False) -> str:
        if not self.query.supported or not self.query_params:
            return fantasycalc_cache_variant(
                {"unsupported": "1"}, overlay_active=overlay_active
            )
        return fantasycalc_cache_variant(
            self.query_params, overlay_active=overlay_active
        )

    def supported_profile(self) -> bool:
        return self.query.supported

    def unsupported_reason(self) -> str:
        if self.query.supported:
            return ""
        return "; ".join(self.query.reasons)[:500]

    async def get_current_values(self) -> list[FCRecord]:
        if not self.query.supported:
            raise UnsupportedValuationQuery(self.query.reasons)
        response = await self._http.get(
            f"{self.BASE_URL}/values/current",
            params=self.query_params,
        )
        response.raise_for_status()
        raw = response.json()
        # ValidationError on any record propagates intentionally so Cache.read_or_fetch
        # serves stale on bad upstream payloads — covered by
        # test_fantasycalc_malformed_response_falls_back_to_stale_cache.
        return [FCRecord.model_validate(record) for record in raw]

    async def get_current_values_cached(
        self,
        cache: Cache,
        *,
        force: bool = False,
        overlay_active: bool = False,
    ):
        if not self.query.supported:
            raise UnsupportedValuationQuery(self.query.reasons)

        async def fetch() -> list[dict]:
            return [record.model_dump(mode="json") for record in await self.get_current_values()]

        return await cache.read_or_fetch(
            "fantasycalc_values",
            fetch,
            force=force,
            variant=self.cache_variant(overlay_active=overlay_active),
        )

    async def probe(self) -> LiveProbeResult:
        if not self.query.supported:
            return LiveProbeResult(
                source="fantasycalc",
                reachable=False,
                error=self.unsupported_reason()[:500],
                probed_at=datetime.now(UTC),
            )
        start = time.monotonic()
        try:
            response = await self._http.get(
                f"{self.BASE_URL}/values/current",
                params={**self.query_params, "limit": "1"},
            )
            response.raise_for_status()
            records = response.json()
            if not records:
                raise ValueError("empty response")
            FCRecord.model_validate(records[0])
            elapsed = int((time.monotonic() - start) * 1000)
            return LiveProbeResult(
                source="fantasycalc",
                reachable=True,
                latency_ms=elapsed,
                probed_at=datetime.now(UTC),
            )
        except Exception as exc:
            return LiveProbeResult(
                source="fantasycalc",
                reachable=False,
                error=str(exc)[:500],
                probed_at=datetime.now(UTC),
            )


def index_records(records: list[FCRecord]) -> dict[str, dict[str, FCRecord]]:
    return {
        "by_sleeper_id": {
            record.player.sleeperId: record
            for record in records
            if record.player.sleeperId and record.player.position != "PICK"
        },
        "by_name_lower": {
            record.player.name.lower(): record
            for record in records
            if record.player.position != "PICK"
        },
    }


def resolve_fantasycalc_query(
    league_format: str | None,
    *,
    tep_tier: TepTier = "te+",
) -> FantasyCalcQuery:
    """Map configured league settings to a documented FantasyCalc query or reasons."""
    format_text = league_format or ""
    reasons: list[str] = []
    if tep_tier not in _VALID_TEP_TIERS:
        reasons.append(f"invalid tep_tier {tep_tier!r}")
        return FantasyCalcQuery(False, {}, tuple(reasons), "off", format_text)

    lowered = format_text.lower()
    num_teams = _parse_num_teams(lowered, reasons)
    num_qbs = _parse_num_qbs(lowered, reasons)
    ppr = _parse_ppr(lowered, reasons)
    format_tep = _parse_format_tep(lowered, reasons)
    resolved_tep, tep_reasons = _resolve_tep_param(format_tep, tep_tier)
    reasons.extend(tep_reasons)

    if reasons or num_teams is None or num_qbs is None or ppr is None or resolved_tep is None:
        if not reasons:
            reasons.append("league_format does not map to a documented FantasyCalc query")
        return FantasyCalcQuery(False, {}, tuple(reasons), tep_tier, format_text)

    params = build_query_params(
        resolved_tep, num_teams=num_teams, num_qbs=num_qbs, ppr=ppr
    )
    return FantasyCalcQuery(True, params, (), resolved_tep, format_text)


def _parse_num_teams(lowered: str, reasons: list[str]) -> str | None:
    matches = _TEAM_COUNT_RE.findall(lowered)
    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return unique[0]
    if not unique:
        reasons.append("league_format has no documented numTeams (8, 10, 12, or 14)")
        return None
    reasons.append(f"league_format has conflicting team counts {unique}")
    return None


def _parse_num_qbs(lowered: str, reasons: list[str]) -> str | None:
    has_1qb = bool(re.search(r"\b1\s*qb\b", lowered))
    has_sf = (
        "superflex" in lowered
        or bool(re.search(r"\bsf\b", lowered))
        or bool(re.search(r"\b2\s*qb\b", lowered))
    )
    if has_1qb and has_sf:
        reasons.append("league_format lists both Superflex/2QB and 1QB")
        return None
    if has_sf:
        return "2"
    if has_1qb:
        return "1"
    reasons.append("league_format does not specify Superflex/2QB or 1QB")
    return None


def _parse_ppr(lowered: str, reasons: list[str]) -> str | None:
    if re.search(r"\bnon[\s-]*ppr\b", lowered):
        return "0"
    if re.search(r"\b0\s*ppr\b", lowered) and not re.search(r"0\.5\s*ppr", lowered):
        return "0"
    if re.search(r"\bhalf[\s-]*ppr\b", lowered) or re.search(r"0\.5\s*ppr", lowered):
        return "0.5"
    if re.search(r"\bppr\s*0\.5\b(?!\s*tep)", lowered):
        return "0.5"
    if re.search(r"\bppr\b", lowered):
        return "1"
    reasons.append("league_format does not specify documented ppr (0, 0.5, or 1)")
    return None


def _parse_format_tep(lowered: str, reasons: list[str]) -> FormatTep | Literal["invalid"] | None:
    has_te_plus_plus = bool(_TE_PLUS_PLUS_RE.search(lowered))
    amounts = _TEP_AMOUNT_RE.findall(lowered)
    if has_te_plus_plus and amounts:
        reasons.append("league_format lists both a numeric TEP amount and te++")
        return "invalid"
    if has_te_plus_plus:
        return "te++"
    if not amounts:
        return None
    if all(amount == "0.5" for amount in amounts):
        return "te+"
    reasons.append(
        "league_format TEP is not a documented FantasyCalc tep value "
        "(none, te+ for 0.5 TEP, or te++)"
    )
    return "invalid"


def _resolve_tep_param(
    format_tep: FormatTep | Literal["invalid"] | None,
    tep_tier: TepTier,
) -> tuple[TepTier | None, list[str]]:
    if format_tep == "invalid":
        return None, []
    if format_tep == "te+" and tep_tier == "te++":
        return None, ["league_format 0.5 TEP maps to tep=te+, not te++"]
    if format_tep == "te+" and tep_tier == "off":
        return None, ["league_format requests 0.5 TEP (te+) but tep_tier=off"]
    if format_tep == "te++" and tep_tier == "off":
        return None, ["league_format requests te++ but tep_tier=off"]
    if format_tep == "te+":
        return "te+", []
    if format_tep == "te++":
        return "te++", []
    if format_tep is None:
        if tep_tier == "te++":
            return "te++", []
        return "off", []
    never: FormatTep = format_tep
    raise RuntimeError(f"unhandled format_tep: {never}")


def query_source_explanation(query: FantasyCalcQuery) -> str:
    if not query.supported:
        detail = "; ".join(query.reasons) if query.reasons else UNSUPPORTED_FORMAT_NOTE
        return f"{UNSUPPORTED_FORMAT_NOTE} {detail}".strip()
    encoded = query.encoded_query()
    tep = query.tep_tier
    if tep == "off":
        tep_note = "tep=none (non-TEP board; documented default none)."
    elif tep == "te+":
        tep_note = (
            "tep=te+ (discrete TE+ tier approximating 0.5 TEP; not a continuous 0.5 float)."
        )
    elif tep == "te++":
        tep_note = "tep=te++ (discrete heavy TE-premium tier)."
    else:
        never: TepTier = tep
        raise RuntimeError(f"unhandled tep_tier: {never}")
    return f"FantasyCalc values requested with {encoded}. {tep_note}"


def tep_source_explanation(tep_tier: TepTier, *, league_format: str | None = None) -> str:
    query = resolve_fantasycalc_query(league_format, tep_tier=tep_tier)
    if league_format is None:
        if tep_tier == "off":
            return (
                "FantasyCalc values requested with tep=none (non-TEP board; not a 0.5 TEP model)."
            )
        if tep_tier == "te+":
            return (
                "FantasyCalc values use tep=te+ (discrete TE+ tier approximating 0.5 TEP; "
                "not a continuous 0.5 float). Documented by go-fantasycalc as te+/te++."
            )
        if tep_tier == "te++":
            return "FantasyCalc values use tep=te++ (discrete heavy TE-premium tier)."
        never: TepTier = tep_tier
        raise RuntimeError(f"unhandled tep_tier: {never}")
    return query_source_explanation(query)


def format_looks_supported(league_format: str | None, *, tep_tier: TepTier = "te+") -> bool:
    """True when league_format maps to a documented FantasyCalc query.

    Empty format is unsupported. Team counts outside {8,10,12,14}, SF+1QB
    conflicts, missing PPR, and undocumented TEP amounts do not send a query.
    """
    return resolve_fantasycalc_query(league_format, tep_tier=tep_tier).supported
