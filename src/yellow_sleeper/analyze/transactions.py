from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ..models import (
    TRANSACTIONS_CAP,
    DataStatus,
    ListTransactionsOutput,
    PolicyStatus,
    ResolutionStatus,
    SourceNote,
    TransactionDraftPick,
    TransactionPlayerMove,
    TransactionRecord,
    WaiverBudgetTransfer,
    WeekTypeCount,
)
from ..obs.caps import truncate_string
from ..resolve.picks import pick_token, round_label
from .roster import _roster_names

CACHE_STATUS_FRESH = "fresh"

DEFAULT_WEEK_END_WHEN_LEG_MISSING = 18

def _source_note(
    field: str,
    source: str,
    *,
    cache_status: str = CACHE_STATUS_FRESH,
    explanation: str | None = None,
) -> SourceNote:
    stale = cache_status == "stale"
    return SourceNote(
        field=field,
        source=source,  # type: ignore[arg-type]
        timestamp=datetime.now(UTC),
        cache_status=cache_status,  # type: ignore[arg-type]
        stale=stale,
        explanation=truncate_string(explanation, 500) if explanation else None,
    )


def resolve_transaction_weeks(
    *,
    snapshot: dict[str, Any],
    weeks: list[int] | None = None,
    week_start: int | None = None,
    week_end: int | None = None,
) -> list[int]:
    """Resolve which Sleeper transaction weeks to fetch.

    Priority:
    1. Explicit ``weeks`` list (week_start/week_end ignored).
    2. Inclusive ``week_start``..``week_end`` (missing bound defaults to 0 / leg-or-18).
    3. Default inclusive ``0..league.settings.leg``, or ``0..18`` when leg is missing.

    Week 0 is included by default so offseason transactions are visible.
    """
    if weeks is not None:
        return sorted({int(w) for w in weeks if int(w) >= 0})

    default_end = _default_week_end(snapshot)
    start = 0 if week_start is None else int(week_start)
    end = default_end if week_end is None else int(week_end)
    if week_start is None and week_end is None:
        start, end = 0, default_end
    if end < start:
        start, end = end, start
    return list(range(start, end + 1))


def list_transactions_output(
    *,
    raw_transactions: list[dict[str, Any]],
    snapshot: dict[str, Any],
    players: Mapping[str, Any],
    weeks_fetched: list[int] | None = None,
    roster_id: int | None = None,
    type: str | None = None,
    status: str | None = None,
) -> ListTransactionsOutput:
    """Enrich and filter near-raw Sleeper transactions into ListTransactionsOutput."""
    names = _roster_names(snapshot)
    filtered: list[TransactionRecord] = []
    for raw in raw_transactions:
        record = _enrich_transaction(raw, players=players, names=names)
        if roster_id is not None and roster_id not in record.roster_ids:
            continue
        if type is not None and record.type != type:
            continue
        if status is not None and record.status != status:
            continue
        filtered.append(record)

    filtered.sort(key=lambda txn: (txn.week, txn.created or 0, txn.transaction_id))
    total_count = len(filtered)
    truncated = total_count > TRANSACTIONS_CAP
    capped = filtered[:TRANSACTIONS_CAP]
    fetched = list(weeks_fetched or sorted({txn.week for txn in filtered}))
    source_notes = [_source_note("transactions", "sleeper", cache_status=CACHE_STATUS_FRESH)]
    if truncated:
        source_notes.append(
            _source_note(
                "transactions",
                "sleeper",
                explanation=(
                    f"Returned {TRANSACTIONS_CAP} of {total_count} transactions; "
                    "remainder omitted by output cap."
                ),
            )
        )
    return ListTransactionsOutput(
        policy_status=PolicyStatus.OK,
        resolution_status=ResolutionStatus.OK,
        data_status=DataStatus.PARTIAL if truncated else DataStatus.COMPLETE,
        source_notes=source_notes,
        transactions=capped,
        truncated=truncated,
        total_count=total_count,
        weeks_fetched=fetched,
        week_type_counts=_week_type_counts(filtered),
    )


def _default_week_end(snapshot: dict[str, Any]) -> int:
    league = snapshot.get("league") or {}
    settings = league.get("settings") or {}
    leg = settings.get("leg")
    try:
        if leg is not None:
            return max(0, int(leg))
    except (TypeError, ValueError):
        pass
    return DEFAULT_WEEK_END_WHEN_LEG_MISSING


def _enrich_transaction(
    raw: dict[str, Any],
    *,
    players: Mapping[str, Any],
    names: dict[int, str],
) -> TransactionRecord:
    roster_ids = [int(rid) for rid in (raw.get("roster_ids") or [])]
    adds = raw.get("adds")
    drops = raw.get("drops")
    # Preserve null vs empty-map distinction for Ledger; coerce non-dict to None.
    adds_map = adds if isinstance(adds, dict) else None
    drops_map = drops if isinstance(drops, dict) else None
    created = _as_int(raw.get("created"))
    status_updated = _as_int(raw.get("status_updated"))
    week = _as_int(raw.get("leg"))
    if week is None:
        week = 0
    return TransactionRecord(
        transaction_id=str(raw.get("transaction_id") or ""),
        type=str(raw.get("type") or "unknown"),
        status=str(raw.get("status") or "unknown"),
        week=week,
        created=created,
        status_updated=status_updated,
        created_iso=_ms_to_iso(created),
        status_updated_iso=_ms_to_iso(status_updated),
        roster_ids=roster_ids,
        roster_owner_names=[
            truncate_string(names.get(rid, f"Roster {rid}"), 100) for rid in roster_ids
        ],
        consenter_ids=[int(rid) for rid in (raw.get("consenter_ids") or [])],
        creator=str(raw["creator"]) if raw.get("creator") is not None else None,
        adds={str(k): int(v) for k, v in adds_map.items()} if adds_map is not None else None,
        drops={str(k): int(v) for k, v in drops_map.items()} if drops_map is not None else None,
        adds_named=_named_moves(adds_map, players),
        drops_named=_named_moves(drops_map, players),
        draft_picks=_enrich_draft_picks(raw.get("draft_picks") or [], names),
        waiver_budget=_enrich_waiver_budget(raw.get("waiver_budget") or [], names),
        settings=raw.get("settings") if isinstance(raw.get("settings"), dict) else None,
        metadata=raw.get("metadata") if isinstance(raw.get("metadata"), dict) else None,
    )


def _named_moves(
    moves: dict[str, Any] | None,
    players: Mapping[str, Any],
) -> list[TransactionPlayerMove]:
    if not moves:
        return []
    named: list[TransactionPlayerMove] = []
    for player_id, roster_id in moves.items():
        raw = players.get(str(player_id))
        if isinstance(raw, Mapping):
            name = str(
                raw.get("full_name")
                or raw.get("search_full_name")
                or f"{raw.get('first_name', '')} {raw.get('last_name', '')}".strip()
                or player_id
            )
            position = raw.get("position")
            team = raw.get("team")
        else:
            name = str(player_id)
            position = None
            team = None
        named.append(
            TransactionPlayerMove(
                sleeper_id=str(player_id),
                roster_id=int(roster_id),
                name=truncate_string(name, 100),
                position=str(position)[:10] if position else None,
                team=str(team)[:10] if team else None,
            )
        )
    return named


def _enrich_draft_picks(
    picks: list[Any],
    names: dict[int, str],
) -> list[TransactionDraftPick]:
    enriched: list[TransactionDraftPick] = []
    for raw in picks:
        if not isinstance(raw, Mapping):
            continue
        try:
            season = int(raw["season"])
            round_number = int(raw["round"])
            original = int(raw["roster_id"])
            current = int(raw["owner_id"])
            previous_raw = raw.get("previous_owner_id")
            previous = int(previous_raw) if previous_raw is not None else None
        except (KeyError, TypeError, ValueError):
            continue
        original_name = str(names.get(original, f"Roster {original}"))
        current_name = str(names.get(current, f"Roster {current}"))
        previous_name = (
            str(names.get(previous, f"Roster {previous}")) if previous is not None else None
        )
        enriched.append(
            TransactionDraftPick(
                season=season,
                round=round_number,
                original_owner_roster_id=original,
                previous_owner_roster_id=previous,
                current_owner_roster_id=current,
                original_owner_name=truncate_string(original_name, 100),
                previous_owner_name=(
                    truncate_string(previous_name, 100) if previous_name else None
                ),
                current_owner_name=truncate_string(current_name, 100),
                pick_token=pick_token(season, round_number, original),
                display_name=truncate_string(
                    f"{season} {round_label(round_number)} (via {original_name})",
                    100,
                ),
            )
        )
    return enriched


def _enrich_waiver_budget(
    transfers: list[Any],
    names: dict[int, str],
) -> list[WaiverBudgetTransfer]:
    enriched: list[WaiverBudgetTransfer] = []
    for raw in transfers:
        if not isinstance(raw, Mapping):
            continue
        try:
            sender = int(raw["sender"])
            receiver = int(raw["receiver"])
            amount = int(raw["amount"])
        except (KeyError, TypeError, ValueError):
            continue
        enriched.append(
            WaiverBudgetTransfer(
                sender=sender,
                receiver=receiver,
                amount=amount,
                sender_name=truncate_string(names.get(sender, f"Roster {sender}"), 100),
                receiver_name=truncate_string(names.get(receiver, f"Roster {receiver}"), 100),
            )
        )
    return enriched


def _week_type_counts(transactions: list[TransactionRecord]) -> list[WeekTypeCount]:
    by_week: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for txn in transactions:
        by_week[txn.week][txn.type] += 1
    return [
        WeekTypeCount(week=week, counts=dict(sorted(counts.items())))
        for week, counts in sorted(by_week.items())
    ]


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _ms_to_iso(ms: int | None) -> str | None:
    if ms is None:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=UTC).isoformat().replace("+00:00", "Z")
    except (OverflowError, OSError, ValueError):
        return None
