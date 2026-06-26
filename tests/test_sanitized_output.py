from __future__ import annotations

import unittest

from ghost_dvr.app import sanitized_config


class SanitizedOutputTests(unittest.TestCase):
    def test_sanitized_config_redacts_source_password(self):
        config = {
            "sources": [
                {
                    "source_id": "source-1",
                    "source_type": "rtsp",
                    "username": "camera-user",
                    "password": "camera-pass",
                }
            ]
        }

        sanitized = sanitized_config(config)

        self.assertEqual(sanitized["sources"][0]["password"], "<redacted>")
        self.assertEqual(config["sources"][0]["password"], "camera-pass")

    def test_sanitized_config_redacts_web_admin_token(self):
        config = {"web": {"admin_token": "local-admin-token"}}

        sanitized = sanitized_config(config)

        self.assertEqual(sanitized["web"]["admin_token"], "<redacted>")
        self.assertEqual(config["web"]["admin_token"], "local-admin-token")


if __name__ == "__main__":
    unittest.main()
