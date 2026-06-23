from __future__ import annotations

import unittest
from unittest.mock import patch

from ghost_dvr.source_probe import StreamProbeResult
from ghost_dvr.source_validator import FfprobeSourceValidator, FormatOnlySourceValidator
from ghost_dvr.sources.base import SourceConfig
from ghost_dvr.sources.mock import MockVideoSource
from ghost_dvr.sources.rtsp import RtspSource


class SourceValidatorTests(unittest.TestCase):
    def test_format_only_validator_connects_source(self):
        source = MockVideoSource(
            SourceConfig(
                source_id="source-1",
                name="Mock",
                source_type="mock",
                address="test_video.mp4",
            )
        )

        error = FormatOnlySourceValidator().validate(source)

        self.assertIsNone(error)
        self.assertTrue(source.is_online())

    def test_ffprobe_validator_checks_rtsp_stream(self):
        source = RtspSource(
            SourceConfig(
                source_id="source-1",
                name="Camera",
                source_type="rtsp",
                address="rtsp://camera/stream",
            )
        )

        with patch(
            "ghost_dvr.source_validator.probe_stream",
            return_value=StreamProbeResult(ok=True),
        ):
            error = FfprobeSourceValidator().validate(source)

        self.assertIsNone(error)
        self.assertTrue(source.is_online())

    def test_ffprobe_validator_returns_probe_error(self):
        source = RtspSource(
            SourceConfig(
                source_id="source-1",
                name="Camera",
                source_type="rtsp",
                address="rtsp://camera/stream",
            )
        )

        with patch(
            "ghost_dvr.source_validator.probe_stream",
            return_value=StreamProbeResult(ok=False, error="No video stream found"),
        ):
            error = FfprobeSourceValidator().validate(source)

        self.assertEqual(error, "No video stream found")


if __name__ == "__main__":
    unittest.main()
