"""Logs estructurados en JSON a un archivo rotativo, sin datos sensibles."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_STANDARD = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}

# Defensa en profundidad: el código no registra secretos, pero si algún mensaje de una
# librería incluye uno, se tapa antes de escribirlo.
_KEYS = r"(?:api_token|access_key|access_secret|signature|password|token)"
_SECRET_PATTERNS = [
    re.compile(rf"(?i)\b({_KEYS}=)[^&\s\"']+"),  # query string / form
    re.compile(rf"(?i)(\"{_KEYS}\"\s*:\s*\")[^\"]+"),  # JSON
]


def redact(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(r"\1***", text)
    return text


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        for key, value in vars(record).items():
            if key not in _STANDARD and not key.startswith("_"):
                payload[key] = (
                    value if isinstance(value, int | float | bool) else redact(str(value))
                )
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(log_dir: Path, *, level: int = logging.INFO) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "setid.log"
    handler = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not getattr(h, "_setid", False)]
    handler._setid = True  # type: ignore[attr-defined]
    root.addHandler(handler)
    root.setLevel(level)
    # httpx registra cada URL a nivel INFO; no aporta y alarga el log.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    return path
