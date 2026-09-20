from __future__ import annotations

import json
import logging
import logging.handlers
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

REDACT_KEYS = re.compile(
    r"league_id|user_id|username|sleeper_username|sleeper_league",
    re.IGNORECASE,
)
LEAGUE_URL_RE = re.compile(
    r"(https?://[^\s\"']*?/league/)([^/\s\"'?]+)",
    re.IGNORECASE,
)
REDACTED = "***REDACTED***"

_redact_secrets: tuple[str, ...] = ()


def set_redact_secrets(values: Iterable[str]) -> None:
    unique = {value for value in values if value and len(value) >= 4}
    global _redact_secrets
    _redact_secrets = tuple(sorted(unique, key=len, reverse=True))


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.args = _redact_args(record.args)
        if isinstance(record.msg, str):
            record.msg = redact_text(record.msg)
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            record.extra_data = redact_structure(record.extra_data)
        return True


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
        }
        if hasattr(record, "extra_data"):
            payload["extra"] = redact_structure(record.extra_data)
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(cache_dir: Path, *, secrets: Iterable[str] = ()) -> None:
    set_redact_secrets(secrets)
    log_path = cache_dir / "logs" / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.TimedRotatingFileHandler(
        log_path,
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    handler.setFormatter(JSONFormatter())
    handler.addFilter(RedactionFilter())

    root = logging.getLogger("yellow_sleeper")
    root.setLevel(logging.INFO)
    root.handlers.clear()
    root.addHandler(handler)
    root.propagate = False


def redact_text(value: str) -> str:
    redacted = LEAGUE_URL_RE.sub(rf"\1{REDACTED}", value)
    for secret in _redact_secrets:
        redacted = redacted.replace(secret, REDACTED)
    return redacted


def redact_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: REDACTED if REDACT_KEYS.search(str(key)) else redact_structure(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_structure(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_structure(item) for item in value)
    if isinstance(value, str):
        return redact_text(value)
    return value


def _redact_args(args: Any) -> Any:
    if isinstance(args, dict):
        return redact_structure(args)
    if isinstance(args, tuple):
        return tuple(redact_structure(item) for item in args)
    return redact_structure(args)
