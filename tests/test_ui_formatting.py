from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ghost_dvr.ui.main_window import (
    duration_label_to_minutes,
    duration_minutes_to_label,
    format_duration,
    resolve_recordings_dir,
)


class UiFormattingTests(unittest.TestCase):
    def test_format_duration(self):
        self.assertEqual(format_duration(0), "00:00:00")
        self.assertEqual(format_duration(65), "00:01:05")
        self.assertEqual(format_duration(3661), "01:01:01")

    def test_duration_setting_labels(self):
        self.assertEqual(duration_label_to_minutes("15 minutes"), 15)
        self.assertEqual(duration_label_to_minutes("1 hour"), 60)
        self.assertEqual(duration_label_to_minutes("Infinite"), 0)
        self.assertEqual(duration_minutes_to_label(30), "30 minutes")
        self.assertEqual(duration_minutes_to_label(0), "Infinite")
        self.assertEqual(duration_minutes_to_label(999), "Infinite")

    def test_resolve_recordings_dir_uses_fallback_for_blank_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fallback = root / "runtime" / "recordings"

            selected = resolve_recordings_dir(
                "",
                runtime_dir=root / "runtime",
                fallback_dir=fallback,
            )

            self.assertEqual(selected, fallback)
            self.assertTrue(fallback.exists())

    def test_resolve_recordings_dir_accepts_relative_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            selected = resolve_recordings_dir(
                "external",
                runtime_dir=root / "runtime",
                fallback_dir=root / "runtime" / "recordings",
            )

            self.assertEqual(selected, root / "runtime" / "external")
            self.assertTrue(selected.exists())


if __name__ == "__main__":
    unittest.main()
