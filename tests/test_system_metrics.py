from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghost_dvr.system_metrics import system_metrics


class SystemMetricsTests(unittest.TestCase):
    def test_reads_linux_memory_temperature_and_uptime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            meminfo = root / "meminfo"
            uptime = root / "uptime"
            temperature = root / "temp"
            meminfo.write_text(
                "MemTotal:        512000 kB\n"
                "MemAvailable:   128000 kB\n",
                encoding="utf-8",
            )
            uptime.write_text("3661.00 100.00\n", encoding="utf-8")
            temperature.write_text("43125\n", encoding="utf-8")

            with patch("os.getloadavg", return_value=(0.25, 0.5, 0.75), create=True):
                metrics = system_metrics(
                    meminfo_path=meminfo,
                    uptime_path=uptime,
                    temperature_path=temperature,
                )

            self.assertEqual(metrics["load"], {"1m": 0.25, "5m": 0.5, "15m": 0.75})
            self.assertEqual(metrics["memory"]["total_mb"], 500.0)
            self.assertEqual(metrics["memory"]["used_mb"], 375.0)
            self.assertEqual(metrics["memory"]["used_percent"], 75.0)
            self.assertEqual(metrics["temperature_c"], 43.1)
            self.assertEqual(metrics["uptime_seconds"], 3661)

    def test_missing_linux_files_return_none_values(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing"

            metrics = system_metrics(
                meminfo_path=missing,
                uptime_path=missing,
                temperature_path=missing,
            )

            self.assertIsNone(metrics["memory"])
            self.assertIsNone(metrics["temperature_c"])
            self.assertIsNone(metrics["uptime_seconds"])


if __name__ == "__main__":
    unittest.main()
