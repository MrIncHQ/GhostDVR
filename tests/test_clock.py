from __future__ import annotations

import unittest

from ghost_dvr.clock import LocalClock


class ClockTests(unittest.TestCase):
    def test_local_clock_returns_iso_timestamp(self):
        timestamp = LocalClock("local").timestamp()

        self.assertIn("T", timestamp)

    def test_named_timezone_is_supported(self):
        timestamp = LocalClock("UTC").timestamp()

        self.assertTrue(timestamp.endswith("+00:00"))

    def test_unknown_timezone_is_rejected(self):
        with self.assertRaises(ValueError):
            LocalClock("No/Such_Zone")


if __name__ == "__main__":
    unittest.main()
