from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghost_dvr.autostart import api_autostart_status, set_api_autostart


class AutostartTests(unittest.TestCase):
    def test_windows_startup_file_can_be_enabled_and_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_root = Path(temp_dir) / "GhostDVR"
            app_root.mkdir()
            (app_root / "Run_Ghost_DVR_API.bat").write_text("@echo off\n", encoding="utf-8")
            appdata = Path(temp_dir) / "AppData"

            with patch("platform.system", return_value="Windows"), patch.dict(
                "os.environ",
                {"APPDATA": str(appdata)},
            ):
                enabled = set_api_autostart(app_root, True)

                self.assertTrue(enabled.enabled)
                self.assertTrue(Path(enabled.target).exists())
                self.assertIn("Run_Ghost_DVR_API.bat", Path(enabled.target).read_text(encoding="utf-8"))

                disabled = set_api_autostart(app_root, False)

                self.assertFalse(disabled.enabled)
                self.assertFalse(Path(enabled.target).exists())

    def test_linux_systemd_user_service_can_be_enabled_and_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_root = Path(temp_dir) / "GhostDVR"
            app_root.mkdir()
            (app_root / "Run_Ghost_DVR_API_Pi.sh").write_text("#!/bin/sh\n", encoding="utf-8")
            home = Path(temp_dir) / "home"

            with patch("platform.system", return_value="Linux"), patch("pathlib.Path.home", return_value=home), patch(
                "ghost_dvr.autostart.subprocess.run"
            ) as run:
                enabled = set_api_autostart(app_root, True)

                self.assertTrue(enabled.enabled)
                self.assertTrue(Path(enabled.target).exists())
                self.assertIn("ExecStart=/bin/sh", Path(enabled.target).read_text(encoding="utf-8"))
                run.assert_any_call(
                    ["systemctl", "--user", "enable", "ghost-dvr-api.service"],
                    check=True,
                    stdout=-3,
                    stderr=-3,
                )

                disabled = set_api_autostart(app_root, False)

                self.assertFalse(disabled.enabled)
                self.assertFalse(Path(enabled.target).exists())

    def test_unsupported_platform_reports_not_supported(self):
        with patch("platform.system", return_value="Darwin"):
            status = api_autostart_status(Path("GhostDVR"))

        self.assertFalse(status.supported)
        self.assertFalse(status.enabled)


if __name__ == "__main__":
    unittest.main()
