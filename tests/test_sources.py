from __future__ import annotations

import unittest

from ghost_dvr.sources.base import SourceConfig
from ghost_dvr.sources.factory import create_source, create_sources
from ghost_dvr.sources.mock import MockVideoSource
from ghost_dvr.sources.rtsp import RtspSource
from ghost_dvr.sources.usb import UsbCameraSource


class SourceTests(unittest.TestCase):
    def test_mock_source_supports_disconnect_and_reconnect(self):
        source = MockVideoSource(
            SourceConfig(
                source_id="source-1",
                name="Test Video",
                source_type="mock",
                address="test_video.mp4",
            )
        )

        source.connect()
        self.assertTrue(source.is_online())
        self.assertEqual(source.get_stream(), "test_video.mp4")

        source.simulate_disconnect()
        self.assertFalse(source.is_online())

        source.simulate_reconnect()
        self.assertTrue(source.is_online())

    def test_rtsp_source_requires_rtsp_address(self):
        source = RtspSource(
            SourceConfig(
                source_id="source-1",
                name="Basement Camera",
                source_type="rtsp",
                address="http://example.test/stream",
            )
        )

        with self.assertRaises(ValueError):
            source.connect()

    def test_rtsp_source_injects_credentials_for_stream(self):
        source = RtspSource(
            SourceConfig(
                source_id="source-1",
                name="Basement Camera",
                source_type="rtsp",
                address="rtsp://192.0.2.10/stream1",
                username="camera-user",
                password="camera pass",
            )
        )

        self.assertEqual(
            source.get_stream(),
            "rtsp://camera-user:camera%20pass@192.0.2.10/stream1",
        )

    def test_rtsp_source_keeps_credentials_already_in_url(self):
        source = RtspSource(
            SourceConfig(
                source_id="source-1",
                name="Basement Camera",
                source_type="rtsp",
                address="rtsp://camera-user:camera-pass@example.test/stream1",
                username="other-user",
                password="other-pass",
            )
        )

        self.assertEqual(source.get_stream(), "rtsp://camera-user:camera-pass@example.test/stream1")

    def test_factory_creates_supported_sources(self):
        sources = create_sources(
            [
                {
                    "source_id": "mock-1",
                    "name": "Mock Video",
                    "source_type": "mock",
                    "address": "test_video.mp4",
                },
                {
                    "source_id": "rtsp-1",
                    "name": "Basement Camera",
                    "source_type": "rtsp",
                    "address": "rtsp://192.0.2.10/stream1",
                },
                {
                    "source_id": "usb-1",
                    "name": "USB Camera",
                    "source_type": "usb",
                    "address": "/dev/video0",
                },
            ]
        )

        self.assertIsInstance(sources[0], MockVideoSource)
        self.assertIsInstance(sources[1], RtspSource)
        self.assertIsInstance(sources[2], UsbCameraSource)

    def test_usb_source_requires_address(self):
        source = UsbCameraSource(
            SourceConfig(
                source_id="usb-1",
                name="USB Camera",
                source_type="usb",
                address="",
            )
        )

        with self.assertRaises(ValueError):
            source.connect()

    def test_usb_source_uses_device_address_as_stream(self):
        source = UsbCameraSource(
            SourceConfig(
                source_id="usb-1",
                name="USB Camera",
                source_type="usb",
                address="video=Integrated Camera",
            )
        )

        source.connect()

        self.assertTrue(source.is_online())
        self.assertEqual(source.get_stream(), "video=Integrated Camera")

    def test_factory_rejects_unknown_source_type(self):
        config = SourceConfig(
            source_id="bad-1",
            name="Unknown",
            source_type="unknown",
            address="none",
        )

        with self.assertRaises(ValueError):
            create_source(config)



if __name__ == "__main__":
    unittest.main()
