from __future__ import annotations

import unittest

from ghost_dvr.setup_wizard import build_source_config


class SetupWizardTests(unittest.TestCase):
    def test_build_source_config_normalizes_defaults(self):
        config = build_source_config(
            source_type="",
            name="",
            address="",
        )

        self.assertEqual(config["source_type"], "mock")
        self.assertEqual(config["name"], "Source 1")
        self.assertEqual(config["address"], "test_video.mp4")
        self.assertIsNone(config["username"])

    def test_build_source_config_keeps_rtsp_details(self):
        config = build_source_config(
            source_type="RTSP",
            name="Basement Camera",
            address="rtsp://192.0.2.10/stream",
            username="camera-user",
            password="camera-pass",
            stream_path="/stream",
        )

        self.assertEqual(config["source_type"], "rtsp")
        self.assertEqual(config["username"], "camera-user")
        self.assertEqual(config["password"], "camera-pass")
        self.assertEqual(config["stream_path"], "/stream")

    def test_build_source_config_accepts_usb_source(self):
        config = build_source_config(
            source_type="USB",
            name="Local Webcam",
            address="/dev/video0",
        )

        self.assertEqual(config["source_type"], "usb")
        self.assertEqual(config["address"], "/dev/video0")

    def test_build_source_config_rejects_rtps_typo(self):
        with self.assertRaises(ValueError):
            build_source_config(
                source_type="rtps",
                name="POE",
                address="rtps://example.test:554/stream1",
            )



if __name__ == "__main__":
    unittest.main()
