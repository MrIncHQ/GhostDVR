from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ghost_dvr.ffmpeg import find_ffmpeg, find_ffprobe


class FfmpegResolverTests(unittest.TestCase):
    def test_find_ffmpeg_prefers_path(self):
        with patch("shutil.which", return_value="C:/bin/ffmpeg.exe"):
            self.assertEqual(find_ffmpeg(), "C:/bin/ffmpeg.exe")

    def test_find_ffmpeg_returns_none_without_path_or_localappdata(self):
        with patch("shutil.which", return_value=None), patch.dict("os.environ", {}, clear=True):
            self.assertIsNone(find_ffmpeg())

    def test_find_ffmpeg_finds_winget_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            package_bin = (
                Path(temp_dir)
                / "Microsoft"
                / "WinGet"
                / "Packages"
                / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
                / "ffmpeg-8.1.1-full_build"
                / "bin"
            )
            package_bin.mkdir(parents=True)
            ffmpeg = package_bin / "ffmpeg.exe"
            ffmpeg.write_text("", encoding="utf-8")

            with patch("shutil.which", return_value=None), patch.dict(
                "os.environ",
                {"LOCALAPPDATA": temp_dir},
            ):
                self.assertEqual(find_ffmpeg(), str(ffmpeg))

    def test_find_ffprobe_prefers_path(self):
        with patch("shutil.which", return_value="/usr/bin/ffprobe"):
            self.assertEqual(find_ffprobe("/usr/bin/ffmpeg"), "/usr/bin/ffprobe")

    def test_find_ffprobe_uses_linux_sibling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ffmpeg = Path(temp_dir) / "ffmpeg"
            ffprobe = Path(temp_dir) / "ffprobe"
            ffmpeg.write_text("", encoding="utf-8")
            ffprobe.write_text("", encoding="utf-8")

            with patch("shutil.which", return_value=None), patch.dict(
                "os.environ",
                {},
                clear=True,
            ):
                self.assertEqual(find_ffprobe(str(ffmpeg)), str(ffprobe))

    def test_find_ffprobe_uses_windows_sibling(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            ffmpeg = Path(temp_dir) / "ffmpeg.exe"
            ffprobe = Path(temp_dir) / "ffprobe.exe"
            ffmpeg.write_text("", encoding="utf-8")
            ffprobe.write_text("", encoding="utf-8")

            with patch("shutil.which", return_value=None), patch.dict(
                "os.environ",
                {},
                clear=True,
            ):
                self.assertEqual(find_ffprobe(str(ffmpeg)), str(ffprobe))


if __name__ == "__main__":
    unittest.main()
