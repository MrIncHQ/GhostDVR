from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class LocalClock:
    def __init__(self, timezone_name: str = "local") -> None:
        self.timezone_name = timezone_name
        self.timezone = self._load_timezone(timezone_name)

    def now(self) -> datetime:
        if self.timezone is None:
            return datetime.now().astimezone()
        return datetime.now(self.timezone)

    def timestamp(self) -> str:
        return self.now().isoformat(timespec="seconds")

    def _load_timezone(self, timezone_name: str):
        if timezone_name.lower() in {"", "local"}:
            return None
        if timezone_name.upper() == "UTC":
            return UTC
        try:
            return ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {timezone_name}") from exc
