import logging
import sys
from typing import Any

from app.core.config import get_settings


class StructuredFormatter(logging.Formatter):
    """JSON-ready key=value formatter for production log aggregation."""

    def format(self, record: logging.LogRecord) -> str:
        parts: list[str] = [
            f"timestamp={self.formatTime(record, self.datefmt)}",
            f"level={record.levelname}",
            f"logger={record.name}",
            f"message={record.getMessage()}",
        ]
        if record.exc_info:
            parts.append(f"exception={self.formatException(record.exc_info)}")
        for key, value in getattr(record, "extra_fields", {}).items():
            parts.append(f"{key}={value}")
        return " ".join(parts)


def setup_logging() -> None:
    settings = get_settings()
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(settings.log_level.upper())

    handler = logging.StreamHandler(sys.stdout)
    if settings.log_json:
        handler.setFormatter(StructuredFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            ),
        )
    root.addHandler(handler)

    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def log_extra(**fields: Any) -> dict[str, Any]:
    """Attach structured fields to a log record via LoggerAdapter or filter."""
    return {"extra_fields": fields}
