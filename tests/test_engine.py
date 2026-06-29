from __future__ import annotations

import json
import logging
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from ghost_dvr.engine import DvrEngine
from ghost_dvr.engine import SourceStatus
from ghost_dvr.hardware.led import LedState
from ghost_dvr.identity import DeviceIdentity
from ghost_dvr.recording import RecordingSession
from ghost_dvr.sources.base import SourceConfig
from ghost_dvr.sources.mock import MockVideoSource
from ghost_dvr.storage import StorageStatus


class EngineTests(unittest.TestCase):
    def test_source_status_redacts_credentials(self):
        status = SourceStatus(
            source_id="source-1",
            name="Camera",
            source_type="rtsp",
            online=True,
            stream="rtsp://camera-user:camera-pass@example.test:554/stream",
        )

        self.assertEqual(
            status.to_dict()["stream"],
            "rtsp://<credentials>@example.test:554/stream",
        )

    def test_snapshot_connects_sources_and_writes_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            status_file = Path(temp_dir) / "status.json"
            identity = DeviceIdentity(
                uuid="00000000-0000-0000-0000-000000000000",
                device_id="TEST",
                hostname="ghostdvr-test",
            )
            source = MockVideoSource(
                SourceConfig(
                    source_id="source-1",
                    name="Mock Video",
                    source_type="mock",
                    address="test_video.mp4",
                )
            )
            engine = DvrEngine(
                identity=identity,
                config={"sources": []},
                status_file=status_file,
                logger=logging.getLogger("test.engine"),
                sources=[source],
                status_led=FakeStatusLed(),
            )

            status = engine.snapshot()

            self.assertTrue(status["source_online"])
            self.assertIn("storage", status)
            self.assertIn("free_gb", status["storage"])
            self.assertEqual(status["sources"][0]["source_id"], "source-1")
            self.assertEqual(status["sources"][0]["name"], "Mock Video")
            self.assertTrue(status["sources"][0]["online"])
            self.assertEqual(json.loads(status_file.read_text())["device_id"], "TEST")

    def test_snapshot_reports_source_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            status_file = Path(temp_dir) / "status.json"
            identity = DeviceIdentity(
                uuid="00000000-0000-0000-0000-000000000000",
                device_id="TEST",
                hostname="ghostdvr-test",
            )
            source = MockVideoSource(
                SourceConfig(
                    source_id="source-1",
                    name="Missing Video",
                    source_type="mock",
                    address=str(Path(temp_dir) / "missing.mp4"),
                ),
                require_file=True,
            )
            logger = logging.getLogger("test.engine.missing")
            logger.addHandler(logging.NullHandler())
            logger.propagate = False
            engine = DvrEngine(
                identity=identity,
                config={"sources": []},
                status_file=status_file,
                logger=logger,
                sources=[source],
                status_led=FakeStatusLed(),
            )

            status = engine.snapshot()

            self.assertFalse(status["source_online"])
            self.assertFalse(status["sources"][0]["online"])
            self.assertIn("missing.mp4", status["sources"][0]["error"])

    def test_snapshot_uses_injected_storage_monitor(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = DvrEngine(
                identity=DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
                config={"sources": []},
                status_file=Path(temp_dir) / "status.json",
                logger=logging.getLogger("test.engine.storage"),
                sources=[],
                storage_monitor=FakeStorageMonitor(),
                status_led=FakeStatusLed(),
            )

            status = engine.snapshot()

            self.assertEqual(status["storage"]["free_gb"], 50.0)
            self.assertFalse(status["storage"]["warning"])

    def test_snapshot_sets_led_state_from_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            led = FakeStatusLed()
            engine = DvrEngine(
                identity=DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
                config={"sources": []},
                status_file=Path(temp_dir) / "status.json",
                logger=logging.getLogger("test.engine.led"),
                sources=[
                    MockVideoSource(
                        SourceConfig(
                            source_id="source-1",
                            name="Mock Video",
                            source_type="mock",
                            address="test_video.mp4",
                        )
                    )
                ],
                storage_monitor=FakeStorageMonitor(),
                status_led=led,
            )

            engine.snapshot()

            self.assertEqual(led.state, LedState.ONLINE)

    def test_start_and_stop_recording_use_recorder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FakeRecorder(Path(temp_dir))
            engine = DvrEngine(
                identity=DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
                config={"sources": [], "recording": {"segment_minutes": 15}},
                status_file=Path(temp_dir) / "status.json",
                logger=logging.getLogger("test.engine.recording"),
                sources=[
                    MockVideoSource(
                        SourceConfig(
                            source_id="source-1",
                            name="Mock Video",
                            source_type="mock",
                            address="test_video.mp4",
                        )
                    )
                ],
                recorder=recorder,
                storage_monitor=FakeStorageMonitor(),
                status_led=FakeStatusLed(),
                recording_source_validator=FakeSourceValidator(),
            )

            started = engine.start_recording()
            self.assertTrue(started["recording"])
            self.assertEqual(recorder.started_source_id, "source-1")
            self.assertIsNotNone(engine.active_metadata_path)
            self.assertEqual(started["recording_duration_seconds"], 0)

            stopped = engine.stop_recording()
            self.assertFalse(stopped["recording"])
            self.assertIsNone(engine.active_metadata_path)
            self.assertEqual(stopped["recording_duration_seconds"], 0)

    def test_start_recording_records_all_online_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FakeMultiRecorder(Path(temp_dir))
            engine = DvrEngine(
                identity=DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
                config={"sources": [], "recording": {"segment_minutes": 15}},
                status_file=Path(temp_dir) / "status.json",
                logger=logging.getLogger("test.engine.multi-recording"),
                sources=[
                    MockVideoSource(
                        SourceConfig(
                            source_id="source-1",
                            name="Back PTZ",
                            source_type="mock",
                            address="test_video.mp4",
                        )
                    ),
                    MockVideoSource(
                        SourceConfig(
                            source_id="source-2",
                            name="Driveway",
                            source_type="mock",
                            address="test_video.mp4",
                        )
                    ),
                ],
                recorder=recorder,
                storage_monitor=FakeStorageMonitor(),
                status_led=FakeStatusLed(),
                recording_source_validator=FakeSourceValidator(),
            )

            started = engine.start_recording()

            self.assertTrue(started["recording"])
            self.assertEqual(recorder.started_source_ids, ["source-1", "source-2"])
            self.assertEqual(engine.active_source_ids, ["source-1", "source-2"])
            self.assertEqual(set(engine.active_metadata_paths), {"source-1", "source-2"})

            engine.stop_recording()

            self.assertEqual(recorder.stop_count, 1)
            self.assertEqual(engine.active_metadata_paths, {})

    def test_recording_duration_uses_active_session_start_time(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FakeRecorder(Path(temp_dir))
            clock = FakeClock()
            engine = DvrEngine(
                identity=DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
                config={"sources": [], "recording": {"segment_minutes": 15}},
                status_file=Path(temp_dir) / "status.json",
                logger=logging.getLogger("test.engine.duration"),
                sources=[
                    MockVideoSource(
                        SourceConfig(
                            source_id="source-1",
                            name="Mock Video",
                            source_type="mock",
                            address="test_video.mp4",
                        )
                    )
                ],
                recorder=recorder,
                storage_monitor=FakeStorageMonitor(),
                status_led=FakeStatusLed(),
                clock=clock,
                recording_source_validator=FakeSourceValidator(),
            )

            engine.start_recording()
            recorder.session = RecordingSession(
                source_id="source-1",
                output_pattern=Path(temp_dir) / "duration_%03d.mkv",
                started_at=clock.current,
            )
            clock.current = clock.current + timedelta(seconds=65)
            status = engine.snapshot()

            self.assertEqual(status["recording_duration_seconds"], 65)

    def test_snapshot_auto_stops_when_duration_limit_is_reached(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FakeRecorder(Path(temp_dir))
            clock = FakeClock()
            engine = DvrEngine(
                identity=DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
                config={
                    "sources": [],
                    "recording": {
                        "segment_minutes": 15,
                        "max_duration_minutes": 15,
                        "stop_when_free_gb_below": 2.0,
                    },
                },
                status_file=Path(temp_dir) / "status.json",
                logger=logging.getLogger("test.engine.duration-limit"),
                sources=[
                    MockVideoSource(
                        SourceConfig(
                            source_id="source-1",
                            name="Mock Video",
                            source_type="mock",
                            address="test_video.mp4",
                        )
                    )
                ],
                recorder=recorder,
                storage_monitor=FakeStorageMonitor(),
                status_led=FakeStatusLed(),
                clock=clock,
                recording_source_validator=FakeSourceValidator(),
            )

            engine.start_recording()
            recorder.session = RecordingSession(
                source_id="source-1",
                output_pattern=Path(temp_dir) / "duration_limit_%03d.mkv",
                started_at=clock.current,
            )
            clock.current = clock.current + timedelta(minutes=15)
            status = engine.snapshot()

            self.assertFalse(status["recording"])
            self.assertFalse(engine.recording_requested)
            self.assertEqual(recorder.stop_count, 1)

    def test_snapshot_auto_stops_when_free_space_floor_is_reached(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FakeRecorder(Path(temp_dir))
            engine = DvrEngine(
                identity=DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
                config={
                    "sources": [],
                    "recording": {
                        "segment_minutes": 15,
                        "max_duration_minutes": 0,
                        "stop_when_free_gb_below": 5.0,
                    },
                },
                status_file=Path(temp_dir) / "status.json",
                logger=logging.getLogger("test.engine.storage-floor"),
                sources=[
                    MockVideoSource(
                        SourceConfig(
                            source_id="source-1",
                            name="Mock Video",
                            source_type="mock",
                            address="test_video.mp4",
                        )
                    )
                ],
                recorder=recorder,
                storage_monitor=FakeStorageMonitor(free_gb=5.0),
                status_led=FakeStatusLed(),
                recording_source_validator=FakeSourceValidator(),
            )

            status = engine.start_recording()

            self.assertFalse(status["recording"])
            self.assertFalse(engine.recording_requested)
            self.assertEqual(recorder.stop_count, 1)

    def test_health_check_recovers_failed_recording_when_requested(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FakeRecorder(Path(temp_dir))
            logger = logging.getLogger("test.engine.health")
            logger.addHandler(logging.NullHandler())
            logger.propagate = False
            engine = DvrEngine(
                identity=DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
                config={
                    "sources": [],
                    "recording": {"auto_reconnect": True, "segment_minutes": 15},
                },
                status_file=Path(temp_dir) / "status.json",
                logger=logger,
                sources=[
                    MockVideoSource(
                        SourceConfig(
                            source_id="source-1",
                            name="Mock Video",
                            source_type="mock",
                            address="test_video.mp4",
                        )
                    )
                ],
                recorder=recorder,
                storage_monitor=FakeStorageMonitor(),
                status_led=FakeStatusLed(),
                recording_source_validator=FakeSourceValidator(),
            )

            engine.start_recording()
            recorder.recording = False
            status = engine.health_check()

            self.assertTrue(status["recording"])
            self.assertEqual(recorder.start_count, 2)
            self.assertTrue(engine.recording_requested)

    def test_start_recording_fails_when_recording_validator_rejects_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recorder = FakeRecorder(Path(temp_dir))
            engine = DvrEngine(
                identity=DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
                config={"sources": [], "recording": {"segment_minutes": 15}},
                status_file=Path(temp_dir) / "status.json",
                logger=logging.getLogger("test.engine.validation"),
                sources=[
                    MockVideoSource(
                        SourceConfig(
                            source_id="source-1",
                            name="Mock Video",
                            source_type="mock",
                            address="test_video.mp4",
                        )
                    )
                ],
                recorder=recorder,
                storage_monitor=FakeStorageMonitor(),
                status_led=FakeStatusLed(),
                recording_source_validator=FakeSourceValidator("Probe failed"),
            )

            with self.assertRaisesRegex(RuntimeError, "Probe failed"):
                engine.start_recording()

            self.assertEqual(recorder.start_count, 0)

    def test_close_releases_status_led_when_supported(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            led = ClosableStatusLed()
            engine = DvrEngine(
                identity=DeviceIdentity(
                    uuid="00000000-0000-0000-0000-000000000000",
                    device_id="TEST",
                    hostname="ghostdvr-test",
                ),
                config={"sources": []},
                status_file=Path(temp_dir) / "status.json",
                logger=logging.getLogger("test.engine.close"),
                sources=[],
                status_led=led,
            )

            engine.close()

            self.assertTrue(led.closed)


if __name__ == "__main__":
    unittest.main()


class FakeRecorder:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.recording = False
        self.started_source_id: str | None = None
        self.session: RecordingSession | None = None
        self.start_count = 0
        self.stop_count = 0

    def is_recording(self) -> bool:
        return self.recording

    def start(self, source):
        self.recording = True
        self.started_source_id = source.source_id
        self.start_count += 1
        self.session = RecordingSession(
            source_id=source.source_id,
            output_pattern=self.output_dir / f"test_{self.start_count}_%03d.mp4",
            started_at=__import__("datetime").datetime.now().astimezone(),
        )
        return self.session

    def stop(self) -> None:
        self.stop_count += 1
        self.recording = False


class FakeMultiRecorder(FakeRecorder):
    def __init__(self, output_dir: Path) -> None:
        super().__init__(output_dir)
        self.started_source_ids: list[str] = []
        self.sessions: dict[str, RecordingSession] = {}

    def start_many(self, sources):
        self.recording = True
        self.start_count += 1
        self.started_source_ids = [source.source_id for source in sources]
        now = __import__("datetime").datetime.now().astimezone()
        self.sessions = {
            source.source_id: RecordingSession(
                source_id=source.source_id,
                output_pattern=self.output_dir / f"{source.source_id}_%03d.mp4",
                started_at=now,
            )
            for source in sources
        }
        self.session = next(iter(self.sessions.values()), None)
        return list(self.sessions.values())

    def stop(self) -> None:
        super().stop()
        self.sessions = {}


class FakeStorageMonitor:
    def __init__(self, free_gb: float = 50.0) -> None:
        self.free_gb = free_gb

    def snapshot(self) -> StorageStatus:
        return StorageStatus(
            path="recordings",
            total_gb=100.0,
            used_gb=100.0 - self.free_gb,
            free_gb=self.free_gb,
            free_percent=self.free_gb,
            warning=self.free_gb <= 10.0,
        )


class FakeStatusLed:
    def __init__(self) -> None:
        self.state = LedState.BOOTING

    def set_state(self, state: LedState) -> None:
        self.state = state


class ClosableStatusLed(FakeStatusLed):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    def close(self) -> None:
        self.closed = True


class FakeSourceValidator:
    def __init__(self, error: str | None = None) -> None:
        self.error = error

    def validate(self, source) -> str | None:
        source.connect()
        return self.error


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 6, 23, 0, 0, 0).astimezone()

    def now(self):
        return self.current

    def timestamp(self) -> str:
        return self.current.isoformat(timespec="seconds")
