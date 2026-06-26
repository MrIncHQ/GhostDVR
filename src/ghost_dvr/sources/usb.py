from __future__ import annotations

from pathlib import Path

from ghost_dvr.sources.base import Source, SourceConfig


class UsbCameraSource(Source):
    def connect(self) -> None:
        address = self.config.address.strip()
        if not address:
            self._online = False
            raise ValueError("USB sources require a device address")
        if address.startswith("/dev/") and not Path(address).exists():
            self._online = False
            raise FileNotFoundError(address)
        self._online = True

    def get_stream(self) -> str:
        return self.config.address
