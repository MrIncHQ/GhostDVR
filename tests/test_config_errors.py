from __future__ import annotations

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


if __name__ == "__main__":
    unittest.main()
