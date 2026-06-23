from __future__ import annotations

import unittest

from ghost_dvr.sources.base import SourceConfig
from ghost_dvr.sources.factory import create_source, create_sources
from ghost_dvr.sources.mock import MockVideoSource
from ghost_dvr.sources.rtsp import RtspSource


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
                address="rtsp://192.168.1.10/stream1",
                username="admin",
                password="p@ss word",
            )
        )

        self.assertEqual(
            source.get_stream(),
            "rtsp://admin:p%40ss%20word@192.168.1.10/stream1",
        )

    def test_rtsp_source_keeps_credentials_already_in_url(self):
        source = RtspSource(
            SourceConfig(
                source_id="source-1",
                name="Basement Camera",
                source_type="rtsp",
                address="rtsp://admin:secret@192.168.1.10/stream1",
                username="other",
                password="other",
            )
        )

        self.assertEqual(source.get_stream(), "rtsp://admin:secret@192.168.1.10/stream1")

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
                    "address": "rtsp://192.168.1.10/stream1",
                },
            ]
        )

        self.assertIsInstance(sources[0], MockVideoSource)
        self.assertIsInstance(sources[1], RtspSource)

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
