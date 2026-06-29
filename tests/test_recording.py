from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghost_dvr.engine import SourceStatus
from ghost_dvr.recording import FfmpegRecorder, MultiSourceFfmpegRecorder


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
            self.assertIn("-map", command)
            self.assertIn("0:v:0", command)
            self.assertIn("0:a?", command)
            self.assertIn("-segment_format", command)
            self.assertIn("matroska", command)
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
            self.assertLess(command.index("-use_wallclock_as_timestamps"), command.index("-i"))
            self.assertIn("+genpts+discardcorrupt", command)
            self.assertIn("0:v:0", command)
            self.assertIn("0:a?", command)

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
            self.assertIn("0:v:0", command)
            self.assertNotIn("0:a?", command)
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

    def test_start_includes_safe_source_name_in_output_pattern(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FfmpegRecorder(Path(temp_dir))
            source = SourceStatus(
                source_id="source-1",
                name="Back PTZ / Main",
                source_type="mock",
                online=True,
                stream="test_video.mp4",
            )

            with patch("subprocess.Popen", return_value=FakeProcess()):
                session = recorder.start(source)

            self.assertTrue(session.output_pattern.name.startswith("Back_PTZ_Main_"))

    def test_multi_source_recorder_starts_one_session_per_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = MultiSourceFfmpegRecorder(Path(temp_dir))
            sources = [
                SourceStatus(
                    source_id="source-1",
                    name="Back PTZ",
                    source_type="mock",
                    online=True,
                    stream="test_video.mp4",
                ),
                SourceStatus(
                    source_id="source-2",
                    name="Driveway",
                    source_type="mock",
                    online=True,
                    stream="test_video.mp4",
                ),
            ]

            with patch("subprocess.Popen", side_effect=[FakeProcess(), FakeProcess()]):
                sessions = recorder.start_many(sources)

            self.assertEqual([session.source_id for session in sessions], ["source-1", "source-2"])
            self.assertEqual(set(recorder.sessions), {"source-1", "source-2"})
            self.assertTrue(recorder.sessions["source-1"].output_pattern.name.startswith("Back_PTZ_"))
            self.assertTrue(recorder.sessions["source-2"].output_pattern.name.startswith("Driveway_"))


class FakeProcess:
    def __init__(self) -> None:
        self.stdin = None

    def poll(self):
        return None

    def wait(self, timeout=None):
        return 0


if __name__ == "__main__":
    unittest.main()
