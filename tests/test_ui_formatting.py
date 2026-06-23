from __future__ import annotations

import unittest

from ghost_dvr.ui.main_window import format_duration


class UiFormattingTests(unittest.TestCase):
    def test_format_duration(self):
        self.assertEqual(format_duration(0), "00:00:00")
        self.assertEqual(format_duration(65), "00:01:05")
        self.assertEqual(format_duration(3661), "01:01:01")


if __name__ == "__main__":
    unittest.main()
