from __future__ import annotations

from pathlib import Path

from ghost_dvr.sources.base import Source, SourceConfig


class MockVideoSource(Source):
    def __init__(self, config: SourceConfig, require_file: bool = False) -> None:
        super().__init__(config)
        self.require_file = require_file

    def connect(self) -> None:
        if self.require_file and not Path(self.config.address).exists():
            self._online = False
            raise FileNotFoundError(self.config.address)
        self._online = True

    def simulate_disconnect(self) -> None:
        self._online = False

    def simulate_reconnect(self) -> None:
        self._online = True

    def get_stream(self) -> str:
        return self.config.address
