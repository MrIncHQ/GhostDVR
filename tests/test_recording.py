from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghost_dvr.engine import SourceStatus
from ghost_dvr.recording import FfmpegRecorder


class RecordingTests(unittest.TestCase):
    def test_ffmpeg_command_uses_stream_copy_and_segments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FfmpegRecorder(Path(temp_dir), segment_minutes=15)
            source = SourceStatus(
                source_id="source-1",
                name="Mock Video",
                source_type="mock",
                online=True,
                stream="test_video.mp4",
            )

            command = recorder.build_command(source, Path(temp_dir) / "out_%03d.mkv")

            self.assertIn("-c", command)
            self.assertIn("copy", command)
            self.assertIn("-f", command)
            self.assertIn("segment", command)
            self.assertIn("-segment_time", command)
            self.assertIn("900", command)
            self.assertIn("test_video.mp4", command)

    def test_ffmpeg_command_uses_tcp_for_rtsp_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FfmpegRecorder(Path(temp_dir), segment_minutes=15)
            source = SourceStatus(
                source_id="source-1",
                name="POE",
                source_type="rtsp",
                online=True,
                stream="rtsp://camera/stream",
            )

            command = recorder.build_command(source, Path(temp_dir) / "out_%03d.mkv")

            self.assertLess(command.index("-rtsp_transport"), command.index("-i"))
            self.assertIn("tcp", command)

    def test_ffmpeg_command_loops_mock_source_in_realtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FfmpegRecorder(Path(temp_dir), segment_minutes=15)
            source = SourceStatus(
                source_id="source-1",
                name="Mock Video",
                source_type="mock",
                online=True,
                stream="test_video.mp4",
            )

            command = recorder.build_command(source, Path(temp_dir) / "out_%03d.mkv")

            self.assertLess(command.index("-re"), command.index("-i"))
            self.assertLess(command.index("-stream_loop"), command.index("-i"))
            self.assertIn("-1", command)

    def test_ffmpeg_command_uses_v4l2_for_linux_usb_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FfmpegRecorder(Path(temp_dir), segment_minutes=15)
            source = SourceStatus(
                source_id="usb-1",
                name="USB",
                source_type="usb",
                online=True,
                stream="/dev/video0",
            )

            with patch("platform.system", return_value="Linux"):
                command = recorder.build_command(source, Path(temp_dir) / "out_%03d.mkv")

            self.assertLess(command.index("-f"), command.index("-i"))
            self.assertIn("v4l2", command)
            self.assertIn("libx264", command)
            self.assertIn("-an", command)

    def test_ffmpeg_command_uses_dshow_for_windows_usb_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FfmpegRecorder(Path(temp_dir), segment_minutes=15)
            source = SourceStatus(
                source_id="usb-1",
                name="USB",
                source_type="usb",
                online=True,
                stream="video=Integrated Camera",
            )

            with patch("platform.system", return_value="Windows"):
                command = recorder.build_command(source, Path(temp_dir) / "out_%03d.mkv")

            self.assertLess(command.index("-f"), command.index("-i"))
            self.assertIn("dshow", command)
            self.assertIn("video=Integrated Camera", command)

    def test_start_rejects_offline_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FfmpegRecorder(Path(temp_dir))
            source = SourceStatus(
                source_id="source-1",
                name="Mock Video",
                source_type="mock",
                online=False,
                stream=None,
            )

            with self.assertRaises(RuntimeError):
                recorder.start(source)


if __name__ == "__main__":
    unittest.main()
