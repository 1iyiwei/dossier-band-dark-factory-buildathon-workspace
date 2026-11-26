"""The service clock: moved only by reset and POST /_test/clock (spec 3.4)."""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone

from .errors import validation_failed

_RFC3339 = re.compile(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})")


def try_parse_timestamp(value: object) -> datetime | None:
    """An RFC 3339 timestamp with an explicit offset, else None."""
    if not isinstance(value, str) or not _RFC3339.fullmatch(value):
        return None
    try:
        parsed = datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def parse_timestamp(value: str) -> datetime:
    """An RFC 3339 timestamp with an explicit offset, else 422."""
    parsed = try_parse_timestamp(value)
    if parsed is None:
        raise validation_failed("timestamp must be RFC 3339 with an explicit offset")
    return parsed


class Clock:
    """Follows the system time until the first reset, then stands still between calls."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._fixed: datetime | None = None

    def now(self) -> datetime:
        with self._lock:
            return self._fixed if self._fixed is not None else _system_now()

    def reset(self, now: datetime) -> None:
        with self._lock:
            self._fixed = now

    def advance_to(self, now: datetime) -> None:
        """Move the clock; a time earlier than the current one is refused and changes nothing."""
        with self._lock:
            current = self._fixed if self._fixed is not None else _system_now()
            if now < current:
                raise validation_failed("now is earlier than the clock's current time")
            self._fixed = now


def _system_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
