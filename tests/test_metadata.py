from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from ghost_dvr.engine import SourceStatus
from ghost_dvr.identity import DeviceIdentity
from ghost_dvr.metadata import RecordingMetadataStore
from ghost_dvr.recording import RecordingSession


class MetadataTests(unittest.TestCase):
    def test_metadata_created_from_recording_session(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RecordingMetadataStore()
            started_at = datetime(2026, 6, 22, 20, 0, 0).astimezone()
            session = RecordingSession(
                source_id="source-1",
                output_pattern=Path(temp_dir) / "2026-06-22_20-00-00_%03d.mp4",
                started_at=started_at,
            )
            source = SourceStatus(
                source_id="source-1",
                name="Basement Camera",
                source_type="rtsp",
                online=True,
                stream="rtsp://example.test/stream",
            )

            path = store.create(
                identity=DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="K8F3",
                    hostname="ghostdvr-k8f3",
                ),
                source=source,
                session=session,
            )

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(path.name, "2026-06-22_20-00-00.json")
            self.assertEqual(data["device_id"], "K8F3")
            self.assertEqual(data["source_name"], "Basement Camera")
            self.assertEqual(data["source_type"], "rtsp")
            self.assertIsNone(data["duration_seconds"])

    def test_metadata_finish_updates_duration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            store = RecordingMetadataStore()
            path = Path(temp_dir) / "recording.json"
            path.write_text(
                json.dumps({"duration_seconds": None}),
                encoding="utf-8",
            )
            started_at = datetime(2026, 6, 22, 20, 0, 0).astimezone()

            store.finish(
                path=path,
                started_at=started_at,
                stopped_at=started_at + timedelta(seconds=900),
            )

            data = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(data["duration_seconds"], 900)


if __name__ == "__main__":
    unittest.main()
