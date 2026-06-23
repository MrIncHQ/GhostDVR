from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ghost_dvr.recording_library import cleanup_attention_recordings, cleanup_plan


class RecordingCleanupTests(unittest.TestCase):
    def test_cleanup_plan_targets_attention_files_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recordings_dir = Path(temp_dir)
            (recordings_dir / "bad_000.mkv").write_bytes(b"")
            (recordings_dir / "good_000.mkv").write_bytes(b"video")
            (recordings_dir / "good.json").write_text(
                json.dumps({"duration_seconds": 1}),
                encoding="utf-8",
            )

            plan = cleanup_plan(recordings_dir)

            self.assertEqual(plan["delete_files"], ["bad_000.mkv"])

    def test_cleanup_deletes_attention_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recordings_dir = Path(temp_dir)
            bad = recordings_dir / "bad_000.mkv"
            bad.write_bytes(b"")

            result = cleanup_attention_recordings(recordings_dir)

            self.assertEqual(result["deleted_files"], ["bad_000.mkv"])
            self.assertFalse(bad.exists())


if __name__ == "__main__":
    unittest.main()
