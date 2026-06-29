"""Structured JSON logging.

Every log record is emitted as a single JSON line to ``logs/chess_llm.jsonl`` and a
human-readable line to stderr. Attach structured context to any log call via the
``extra={"context": {...}}`` convention, e.g.::

    log.info("llm move chosen", extra={"context": {"game_id": 3, "uci": "e2e4"}})
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from .config import settings

_CONFIGURED = False


class JsonLineFormatter(logging.Formatter):
    """Render each record as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        context = getattr(record, "context", None)
        if isinstance(context, dict):
            payload["context"] = context
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Idempotently install the JSON file handler and a console handler."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    log_dir = Path(settings.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("chess_llm")
    root.setLevel(logging.INFO)
    root.propagate = False

    file_handler = logging.FileHandler(log_dir / "chess_llm.jsonl", encoding="utf-8")
    file_handler.setFormatter(JsonLineFormatter())
    root.addHandler(file_handler)

    console = logging.StreamHandler(sys.stderr)
    console.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
    console.setLevel(logging.WARNING)  # keep the CLI board view uncluttered
    root.addHandler(console)

    _CONFIGURED = True


def get_logger(name: str) -> logging.LoggerAdapter:
    """Return a logger under the ``chess_llm`` namespace."""
    configure_logging()
    return logging.getLogger(f"chess_llm.{name}")  # type: ignore[return-value]
