from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghost_dvr.preview import PreviewFrameGrabber


class PreviewTests(unittest.TestCase):
    def test_grab_returns_error_when_stream_is_blank(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            result = PreviewFrameGrabber(Path(temp_dir)).grab("")

            self.assertIsNone(result.image_path)
            self.assertEqual(result.error, "No stream available")

    def test_grab_returns_error_when_ffmpeg_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = PreviewFrameGrabber(Path(temp_dir)).grab("test_video.mp4")

            self.assertIsNone(result.image_path)
            self.assertEqual(result.error, "FFmpeg not found")

    def test_grab_returns_error_when_ffmpeg_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            error = subprocess.CalledProcessError(
                returncode=1,
                cmd=["ffmpeg"],
                stderr=b"bad input",
            )
            with patch("subprocess.run", side_effect=error):
                result = PreviewFrameGrabber(Path(temp_dir)).grab("bad.mp4")

            self.assertIsNone(result.image_path)
            self.assertEqual(result.error, "bad input")

    def test_grab_returns_created_image_path(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            preview_dir = Path(temp_dir)

            def fake_run(*args, **kwargs):
                (preview_dir / "source.png").write_bytes(b"png")

            with patch("subprocess.run", side_effect=fake_run):
                result = PreviewFrameGrabber(preview_dir).grab("test_video.mp4")

            self.assertEqual(result.image_path, preview_dir / "source.png")
            self.assertIsNone(result.error)


if __name__ == "__main__":
    unittest.main()
