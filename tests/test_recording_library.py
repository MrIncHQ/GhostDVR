from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ghost_dvr.recording_library import list_recordings, recordings_report


class RecordingLibraryTests(unittest.TestCase):
    def test_list_recordings_matches_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recordings_dir = Path(temp_dir)
            video = recordings_dir / "2026-06-23_12-00-00_000.mkv"
            video.write_bytes(b"video")
            (recordings_dir / "2026-06-23_12-00-00.json").write_text(
                json.dumps(
                    {
                        "source_name": "POE Test",
                        "source_type": "rtsp",
                        "duration_seconds": 10,
                    }
                ),
                encoding="utf-8",
            )

            recordings = list_recordings(recordings_dir)

            self.assertEqual(len(recordings), 1)
            self.assertEqual(recordings[0].status, "ok")
            self.assertEqual(recordings[0].duration_seconds, 10)
            self.assertEqual(recordings[0].source_name, "POE Test")

    def test_list_recordings_flags_empty_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recordings_dir = Path(temp_dir)
            (recordings_dir / "bad_000.mkv").write_bytes(b"")

            recordings = list_recordings(recordings_dir)

            self.assertEqual(recordings[0].status, "empty_file")

    def test_recordings_report_counts_attention_items(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recordings_dir = Path(temp_dir)
            (recordings_dir / "bad_000.mkv").write_bytes(b"")

            report = recordings_report(recordings_dir)

            self.assertEqual(report["count"], 1)
            self.assertEqual(report["ok_count"], 0)
            self.assertEqual(report["attention_count"], 1)


if __name__ == "__main__":
    unittest.main()
