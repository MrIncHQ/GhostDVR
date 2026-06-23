from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ghost_dvr.storage import StorageMonitor, StorageSelector


class StorageTests(unittest.TestCase):
    def test_storage_snapshot_reports_disk_usage(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            status = StorageMonitor(Path(temp_dir)).snapshot()

            self.assertEqual(status.path, str(Path(temp_dir)))
            self.assertGreater(status.total_gb, 0)
            self.assertGreaterEqual(status.free_gb, 0)
            self.assertGreaterEqual(status.used_gb, 0)
            self.assertGreaterEqual(status.free_percent, 0)
            self.assertLessEqual(status.free_percent, 100)

    def test_storage_warning_uses_configured_threshold(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            status = StorageMonitor(Path(temp_dir), warning_percent=100).snapshot()

            self.assertTrue(status.warning)

    def test_storage_selector_prefers_first_usable_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            preferred = Path(temp_dir) / "external"
            fallback = Path(temp_dir) / "runtime" / "recordings"

            selected = StorageSelector(
                preferred_paths=[preferred],
                fallback_path=fallback,
            ).select_recordings_dir()

            self.assertEqual(selected, preferred)

    def test_storage_selector_falls_back_when_no_preferred_paths_exist(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fallback = Path(temp_dir) / "runtime" / "recordings"

            selected = StorageSelector(
                preferred_paths=[],
                fallback_path=fallback,
            ).select_recordings_dir()

            self.assertEqual(selected, fallback)
            self.assertTrue(fallback.exists())


if __name__ == "__main__":
    unittest.main()
