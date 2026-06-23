from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from ghost_dvr.source_probe import probe_stream


class SourceProbeTests(unittest.TestCase):
    def test_probe_reports_missing_ffmpeg(self):
        with patch("ghost_dvr.source_probe.find_ffmpeg", return_value=None):
            result = probe_stream("rtsp://camera/stream")

        self.assertFalse(result.ok)
        self.assertEqual(result.error, "FFmpeg not found")

    def test_probe_reports_video_stream(self):
        completed = subprocess.CompletedProcess(
            args=["ffprobe"],
            returncode=0,
            stdout='{"streams":[{"codec_name":"h264","codec_type":"video","width":896,"height":512}]}',
            stderr="",
        )
        with patch("ghost_dvr.source_probe.find_ffmpeg", return_value="C:/bin/ffmpeg.exe"), patch(
            "subprocess.run",
            return_value=completed,
        ):
            result = probe_stream("rtsp://camera/stream")

        self.assertTrue(result.ok)
        self.assertEqual(result.codec_name, "h264")
        self.assertEqual(result.width, 896)
        self.assertEqual(result.height, 512)

    def test_probe_redacts_credentials_in_error(self):
        completed = subprocess.CompletedProcess(
            args=["ffprobe"],
            returncode=1,
            stdout="",
            stderr="Error opening rtsp://camera-user:camera-pass@camera.example/stream",
        )
        with patch("ghost_dvr.source_probe.find_ffmpeg", return_value="C:/bin/ffmpeg.exe"), patch(
            "subprocess.run",
            return_value=completed,
        ):
            result = probe_stream("rtsp://camera-user:camera-pass@camera.example/stream")

        self.assertFalse(result.ok)
        self.assertNotIn("camera-pass", result.error or "")


if __name__ == "__main__":
    unittest.main()
