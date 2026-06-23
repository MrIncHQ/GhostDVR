from __future__ import annotations

from urllib.parse import quote, urlparse, urlunparse

from ghost_dvr.sources.base import Source, SourceConfig


class RtspSource(Source):
    def connect(self) -> None:
        parsed = urlparse(self.config.address)
        if parsed.scheme.lower() != "rtsp" or not parsed.netloc:
            self._online = False
            raise ValueError("RTSP sources require an rtsp:// address")
        self._online = True

    def get_stream(self) -> str:
        if not self.config.username:
            return self.config.address

        parsed = urlparse(self.config.address)
        if parsed.username:
            return self.config.address

        username = quote(self.config.username, safe="")
        password = quote(self.config.password or "", safe="")
        credentials = username if not password else f"{username}:{password}"
        netloc = f"{credentials}@{parsed.netloc}"
        return urlunparse(
            (
                parsed.scheme,
                netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
