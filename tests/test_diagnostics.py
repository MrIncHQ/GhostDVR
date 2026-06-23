from __future__ import annotations

import unittest
from unittest.mock import patch

from ghost_dvr.diagnostics import check_ffmpeg, run_diagnostics


class DiagnosticsTests(unittest.TestCase):
    def test_check_ffmpeg_reports_missing_binary(self):
        with patch("ghost_dvr.diagnostics.find_ffmpeg", return_value=None):
            status = check_ffmpeg()

        self.assertFalse(status.available)
        self.assertEqual(status.name, "ffmpeg")
        self.assertIn("not found", status.detail)

    def test_run_diagnostics_includes_ffmpeg(self):
        statuses = run_diagnostics()

        self.assertEqual(statuses[0].name, "ffmpeg")


if __name__ == "__main__":
    unittest.main()
