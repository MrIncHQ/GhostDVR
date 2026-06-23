from __future__ import annotations

from typing import Protocol

from ghost_dvr.source_probe import probe_stream
from ghost_dvr.sources.base import Source


class SourceValidator(Protocol):
    def validate(self, source: Source) -> str | None:
        raise NotImplementedError


class FormatOnlySourceValidator:
    def validate(self, source: Source) -> str | None:
        try:
            source.connect()
            return None
        except Exception as exc:
            return str(exc)


class FfprobeSourceValidator:
    def __init__(self, timeout_seconds: int = 15) -> None:
        self.timeout_seconds = timeout_seconds

    def validate(self, source: Source) -> str | None:
        try:
            source.connect()
            stream = source.get_stream()
        except Exception as exc:
            return str(exc)

        if source.get_source_type() != "rtsp":
            return None

        result = probe_stream(stream, timeout_seconds=self.timeout_seconds)
        if result.ok:
            return None
        return result.error or "Source validation failed"
