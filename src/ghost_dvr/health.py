from __future__ import annotations

import threading
from typing import Protocol


class HealthCheckedEngine(Protocol):
    def health_check(self) -> dict[str, object]:
        raise NotImplementedError


class HealthMonitor:
    def __init__(self, engine: HealthCheckedEngine, interval_seconds: float = 5.0) -> None:
        self.engine = engine
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="ghost-dvr-health-monitor",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=self.interval_seconds + 1)

    def run_once(self) -> dict[str, object]:
        return self.engine.health_check()

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            self.engine.health_check()
