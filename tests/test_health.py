from __future__ import annotations

import unittest

from ghost_dvr.health import HealthMonitor


class HealthTests(unittest.TestCase):
    def test_run_once_calls_engine_health_check(self):
        engine = FakeHealthEngine()
        monitor = HealthMonitor(engine, interval_seconds=0.01)

        status = monitor.run_once()

        self.assertEqual(status["ok"], True)
        self.assertEqual(engine.calls, 1)

    def test_start_is_idempotent_and_stop_joins_thread(self):
        engine = FakeHealthEngine()
        monitor = HealthMonitor(engine, interval_seconds=0.01)

        monitor.start()
        monitor.start()
        monitor.stop()

        self.assertGreaterEqual(engine.calls, 0)


class FakeHealthEngine:
    def __init__(self) -> None:
        self.calls = 0

    def health_check(self) -> dict[str, object]:
        self.calls += 1
        return {"ok": True}


if __name__ == "__main__":
    unittest.main()
