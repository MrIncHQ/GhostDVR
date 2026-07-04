from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ghost_dvr.config import load_or_create_config
from ghost_dvr.identity import DeviceIdentity


class ConfigErrorTests(unittest.TestCase):
    def test_invalid_json_error_includes_file_and_location(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text('{"bad": nope}', encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "line 1, column 9"):
                load_or_create_config(
                    path,
                    DeviceIdentity(
                        uuid="00000000-0000-0000-0000-000000000000",
                        device_id="TEST",
                        hostname="ghostdvr-test",
                    ),
                )

    def test_load_removes_obsolete_web_admin_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            path.write_text(
                json.dumps(
                    {
                        "web": {
                            "host": "0.0.0.0",
                            "port": 8080,
                            "admin_token": "old-token",
                        },
                        "sources": [
                            {
                                "source_id": "source-1",
                                "name": "Mock Video",
                                "source_type": "mock",
                                "address": "test_video.mp4",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            config = load_or_create_config(
                path,
                DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
            )

            self.assertNotIn("admin_token", config["web"])
            self.assertNotIn("admin_token", json.loads(path.read_text())["web"])

    def test_new_config_requires_web_auth_setup_decision(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"

            config = load_or_create_config(
                path,
                DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
            )

            self.assertEqual(config["web_auth"]["mode"], "unset")


if __name__ == "__main__":
    unittest.main()
