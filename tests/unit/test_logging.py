from __future__ import annotations

import json
import logging
from pathlib import Path

from yellow_sleeper.obs.logging import configure_logging, redact_text, set_redact_secrets

SENTINEL_LEAGUE = "sentinel-league-9999"
SENTINEL_USER = "sentinel-user-alpha"
SENTINEL_URL = f"https://api.sleeper.app/v1/league/{SENTINEL_LEAGUE}/rosters"


def _flush() -> None:
    for handler in logging.getLogger("yellow_sleeper").handlers:
        handler.flush()


def _log_text(tmp_path: Path) -> str:
    return (tmp_path / "logs" / "server.log").read_text(encoding="utf-8")


def test_logging_writes_json_and_redacts_sensitive_extra(tmp_path: Path) -> None:
    configure_logging(tmp_path, secrets=(SENTINEL_LEAGUE, SENTINEL_USER))
    logger = logging.getLogger("yellow_sleeper.test")

    logger.info(
        "tool invocation",
        extra={
            "extra_data": {
                "league_id": SENTINEL_LEAGUE,
                "nested": {"username": SENTINEL_USER},
                "ok": "visible",
            }
        },
    )
    _flush()

    payload = json.loads(_log_text(tmp_path).splitlines()[0])
    assert payload["msg"] == "tool invocation"
    assert payload["extra"]["league_id"] == "***REDACTED***"
    assert payload["extra"]["nested"]["username"] == "***REDACTED***"
    assert payload["extra"]["ok"] == "visible"
    text = _log_text(tmp_path)
    assert SENTINEL_LEAGUE not in text
    assert SENTINEL_USER not in text


def test_logging_redacts_messages_args_exceptions_and_urls(tmp_path: Path) -> None:
    configure_logging(tmp_path, secrets=(SENTINEL_LEAGUE, SENTINEL_USER))
    logger = logging.getLogger("yellow_sleeper.test")

    logger.info("configured user %s league %s", SENTINEL_USER, SENTINEL_LEAGUE)
    logger.info("GET %s", SENTINEL_URL)
    try:
        raise RuntimeError(f"failed for {SENTINEL_USER} at {SENTINEL_URL}")
    except RuntimeError:
        logger.exception("snapshot failed")
    _flush()

    text = _log_text(tmp_path)
    assert SENTINEL_LEAGUE not in text
    assert SENTINEL_USER not in text
    assert "***REDACTED***" in text
    assert f"/league/{SENTINEL_LEAGUE}" not in text
    assert "/league/***REDACTED***" in text


def test_redact_text_leaves_unrelated_content() -> None:
    set_redact_secrets((SENTINEL_USER,))
    assert redact_text("visible-token") == "visible-token"
    assert redact_text(f"user={SENTINEL_USER}") == "user=***REDACTED***"


def test_mcp_tool_payloads_are_not_redacted_by_logger_helpers() -> None:
    """Redaction is for yellow_sleeper logs, not dynasty_* JSON responses."""
    payload = {
        "league_id": SENTINEL_LEAGUE,
        "user": SENTINEL_USER,
        "picks": [{"current_owner_name": SENTINEL_USER}],
    }
    assert payload["league_id"] == SENTINEL_LEAGUE
    assert payload["user"] == SENTINEL_USER
