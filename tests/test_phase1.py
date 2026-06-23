from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ghost_dvr.app import bootstrap
from ghost_dvr.identity import load_or_create_identity
from ghost_dvr.logging_setup import close_event_logger
from ghost_dvr.paths import RuntimePaths


class Phase1Tests(unittest.TestCase):
    def test_bootstrap_creates_phase1_runtime_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = RuntimePaths(Path(temp_dir))

            result = bootstrap(paths)

            self.assertTrue(paths.config_file.exists())
            self.assertTrue(paths.identity_file.exists())
            self.assertTrue(paths.log_file.exists())
            self.assertTrue(paths.status_file.exists())
            self.assertTrue(result["identity"]["device_id"])
            self.assertIn("sources", result["status"])
            close_event_logger()

    def test_identity_is_generated_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            identity_file = Path(temp_dir) / "identity.json"

            first = load_or_create_identity(identity_file)
            second = load_or_create_identity(identity_file)

            self.assertEqual(second, first)

    def test_config_contains_stable_identity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = RuntimePaths(Path(temp_dir))
            result = bootstrap(paths)

            config = json.loads(paths.config_file.read_text(encoding="utf-8"))

            self.assertEqual(config["device"]["uuid"], result["identity"]["uuid"])
            self.assertEqual(
                config["device"]["device_id"],
                result["identity"]["device_id"],
            )
            self.assertEqual(
                config["device"]["hostname"],
                result["identity"]["hostname"],
            )
            close_event_logger()

    def test_existing_empty_sources_get_default_mock_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = RuntimePaths(Path(temp_dir))
            paths.ensure()
            identity = load_or_create_identity(paths.identity_file)
            paths.config_file.write_text(
                json.dumps(
                    {
                        "device": {
                            "uuid": identity.uuid,
                            "device_id": identity.device_id,
                            "hostname": identity.hostname,
                        },
                        "sources": [],
                    }
                ),
                encoding="utf-8",
            )

            result = bootstrap(paths)

            self.assertEqual(result["config"]["sources"][0]["source_type"], "mock")
            close_event_logger()

    def test_existing_config_gets_missing_nested_defaults(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = RuntimePaths(Path(temp_dir))
            paths.ensure()
            identity = load_or_create_identity(paths.identity_file)
            paths.config_file.write_text(
                json.dumps(
                    {
                        "device": {
                            "uuid": identity.uuid,
                            "device_id": identity.device_id,
                            "hostname": identity.hostname,
                        },
                        "hardware": {
                            "auto_detect": True,
                        },
                        "sources": [
                            {
                                "source_id": "custom",
                                "name": "Custom",
                                "source_type": "mock",
                                "address": "custom.mp4",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = bootstrap(paths)

            self.assertEqual(result["config"]["hardware"]["gpio_led_pin"], 18)
            self.assertEqual(result["config"]["sources"][0]["source_id"], "custom")
            close_event_logger()


if __name__ == "__main__":
    unittest.main()
