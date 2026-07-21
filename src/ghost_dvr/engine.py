from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ghost_dvr.clock import LocalClock
from ghost_dvr.hardware.led import LedState, StatusLed, create_status_led
from ghost_dvr.hardware.profile import HardwareProfile, detect_hardware_profile
from ghost_dvr.identity import DeviceIdentity
from ghost_dvr.metadata import RecordingMetadataStore
from ghost_dvr.recording import FfmpegRecorder, RecordingSession
from ghost_dvr.secrets import redact_url_credentials
from ghost_dvr.source_validator import (
    FfprobeSourceValidator,
    FormatOnlySourceValidator,
    SourceValidator,
)
from ghost_dvr.sources.base import Source
from ghost_dvr.sources.factory import create_sources
from ghost_dvr.storage import StorageMonitor
from ghost_dvr.status import write_status


@dataclass(frozen=True)
class SourceStatus:
    source_id: str
    name: str
    source_type: str
    online: bool
    stream: str | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if isinstance(data.get("stream"), str):
            data["stream"] = redact_url_credentials(data["stream"])
        return data


class DvrEngine:
    def __init__(
        self,
        *,
        identity: DeviceIdentity,
        config: dict[str, Any],
        status_file: Path,
        logger: logging.Logger,
        sources: list[Source] | None = None,
        recorder: FfmpegRecorder | None = None,
        storage_monitor: StorageMonitor | None = None,
        metadata_store: RecordingMetadataStore | None = None,
        status_led: StatusLed | None = None,
        clock: LocalClock | None = None,
        hardware_profile: HardwareProfile | None = None,
        source_validator: SourceValidator | None = None,
        recording_source_validator: SourceValidator | None = None,
    ) -> None:
        self.identity = identity
        self.config = config
        self.status_file = status_file
        self.logger = logger
        self.sources = sources if sources is not None else create_sources(config["sources"])
        recording_config = config.get("recording", {})
        self.recorder = recorder or FfmpegRecorder(
            status_file.parent / "recordings",
            segment_minutes=int(recording_config.get("segment_minutes", 15)),
        )
        self.storage_monitor = storage_monitor or StorageMonitor(
            status_file.parent / "recordings",
            warning_percent=int(recording_config.get("storage_warning_percent", 10)),
        )
        self.metadata_store = metadata_store or RecordingMetadataStore()
        self.active_metadata_paths: dict[str, Path] = {}
        self.active_source_ids: list[str] = []
        self._recording_health_sizes: dict[str, int] = {}
        self.recording_requested = False
        time_config = config.get("time", {})
        self.clock = clock or LocalClock(str(time_config.get("timezone", "local")))
        self.hardware_profile = hardware_profile or detect_hardware_profile()
        self.source_validator = source_validator or FormatOnlySourceValidator()
        self.recording_source_validator = (
            recording_source_validator or FfprobeSourceValidator()
        )
        hardware_config = config.get("hardware", {})
        features_config = config.get("features", {})
        self.status_led = status_led or create_status_led(
            logger=logger,
            hardware_config=hardware_config,
            features_config=features_config,
            hardware_profile=self.hardware_profile,
        )
        self.status_led.set_state(LedState.BOOTING)

    def close(self) -> None:
        close_led = getattr(self.status_led, "close", None)
        if callable(close_led):
            close_led()

    @property
    def active_metadata_path(self) -> Path | None:
        return next(iter(self.active_metadata_paths.values()), None)

    @property
    def active_source_id(self) -> str | None:
        return self.active_source_ids[0] if self.active_source_ids else None

    def replace_sources(self, source_configs: list[dict[str, Any]]) -> None:
        if self.recorder.is_recording():
            raise RuntimeError("Stop recording before changing camera settings")
        self.config["sources"] = source_configs
        self.sources = create_sources(source_configs)

    def refresh_sources(self) -> list[SourceStatus]:
        statuses: list[SourceStatus] = []
        for source in self.sources:
            was_online = source.is_online()
            error = self.source_validator.validate(source)
            if error:
                source.disconnect()
                self.logger.warning(
                    "Source Disconnected: %s (%s)",
                    source.get_source_name(),
                    error,
                )
            elif not was_online and source.is_online():
                self.logger.info("Source Connected: %s", source.get_source_name())

            stream = source.get_stream() if source.is_online() else None
            statuses.append(
                SourceStatus(
                    source_id=source.get_source_id(),
                    name=source.get_source_name(),
                    source_type=source.get_source_type(),
                    online=source.is_online(),
                    stream=stream,
                    error=error,
                )
            )
        return statuses

    def snapshot(self) -> dict[str, Any]:
        source_statuses = [status.to_dict() for status in self.refresh_sources()]
        storage_status = self.storage_monitor.snapshot()
        self._apply_recording_limits(storage_status)
        if storage_status.warning:
            self.logger.warning(
                "Storage Warning: %.2f%% remaining",
                storage_status.free_percent,
            )
        self.status_led.set_state(
            self._led_state_for(
                source_statuses=source_statuses,
                recording=self.recorder.is_recording(),
                storage_warning=storage_status.warning,
            )
        )
        return write_status(
            self.status_file,
            self.identity,
            recording=self.recorder.is_recording(),
            sources=source_statuses,
            storage=storage_status.to_dict(),
            timestamp=self.clock.timestamp(),
            hardware_profile=self.hardware_profile.to_dict(),
            recording_duration_seconds=self.recording_duration_seconds(),
            recording_health=self.recording_health(),
        )

    def start_recording(self, source_id: str | None = None) -> dict[str, Any]:
        statuses = self.refresh_sources()
        sources = self._select_recording_sources(statuses, source_id)
        for source in sources:
            validation_error = self._validate_source_for_recording(source.source_id)
            if validation_error:
                raise RuntimeError(f"{source.name}: {validation_error}")
        sessions = self._start_recorder(sources)
        self.recording_requested = True
        self.active_source_ids = [source.source_id for source in sources]
        self.active_metadata_paths = {}
        sources_by_id = {source.source_id: source for source in sources}
        for session in sessions:
            self.active_metadata_paths[session.source_id] = self.metadata_store.create(
                identity=self.identity,
                source=sources_by_id[session.source_id],
                session=session,
            )
            self.logger.info("Recording Started: %s", session.output_pattern)
        return self.snapshot()

    def stop_recording(self) -> dict[str, Any]:
        self.recording_requested = False
        self._stop_active_recording("Recording Stopped")
        return self.snapshot()

    def health_check(self) -> dict[str, Any]:
        if self.recording_requested and not self.recorder.is_recording():
            self.logger.error("Recording Process Failure")
            self._finish_active_metadata()
            source_ids = list(self.active_source_ids)
            self.recording_requested = False
            self.active_source_ids = []
            if self.config.get("recording", {}).get("auto_reconnect", True):
                self.logger.info("Attempting Recording Recovery")
                try:
                    return self.start_recording(source_ids[0] if len(source_ids) == 1 else None)
                except Exception as exc:
                    self.logger.error("Recording Recovery Failed: %s", exc)
        return self.snapshot()

    def _select_recording_sources(
        self,
        statuses: list[SourceStatus],
        source_id: str | None,
    ) -> list[SourceStatus]:
        candidates = [
            status
            for status in statuses
            if status.online and (source_id is None or status.source_id == source_id)
        ]
        if not candidates:
            raise RuntimeError("No online source is available for recording")
        return candidates

    def _start_recorder(self, sources: list[SourceStatus]) -> list[RecordingSession]:
        start_many = getattr(self.recorder, "start_many", None)
        if callable(start_many):
            return list(start_many(sources))
        if len(sources) > 1:
            raise RuntimeError("Recorder does not support multiple cameras")
        return [self.recorder.start(sources[0])]

    def _validate_source_for_recording(self, source_id: str) -> str | None:
        for source in self.sources:
            if source.get_source_id() == source_id:
                return self.recording_source_validator.validate(source)
        return "Recording source is no longer configured"

    def stream_for_source(self, source_id: str) -> str | None:
        for source in self.sources:
            if source.get_source_id() == source_id:
                return source.get_stream()
        return None

    def _finish_active_metadata(self) -> None:
        sessions_by_id = getattr(self.recorder, "sessions", None)
        if isinstance(sessions_by_id, dict):
            sessions = sessions_by_id
        else:
            session = self.recorder.session
            sessions = {session.source_id: session} if session else {}

        for source_id, path in list(self.active_metadata_paths.items()):
            session = sessions.get(source_id)
            if session:
                self.metadata_store.finish(path=path, started_at=session.started_at)
            self.active_metadata_paths.pop(source_id, None)

    def _stop_active_recording(self, log_message: str) -> None:
        was_recording = self.recorder.is_recording()
        if was_recording:
            self._finish_active_metadata()
        self.recorder.stop()
        if was_recording:
            self.active_source_ids = []
            self._recording_health_sizes.clear()
            self.logger.info(log_message)

    def _apply_recording_limits(self, storage_status) -> None:
        if not self.recorder.is_recording():
            return

        recording_config = self.config.get("recording", {})
        max_duration_minutes = int(recording_config.get("max_duration_minutes", 0) or 0)
        if (
            max_duration_minutes > 0
            and self.recording_duration_seconds() >= max_duration_minutes * 60
        ):
            self.recording_requested = False
            self._stop_active_recording("Recording Auto Stop: duration limit reached")
            return

        free_gb_floor = float(recording_config.get("stop_when_free_gb_below", 0) or 0)
        if free_gb_floor > 0 and storage_status.free_gb <= free_gb_floor:
            self.recording_requested = False
            self._stop_active_recording(
                f"Recording Auto Stop: free storage is at or below {free_gb_floor:.2f} GB"
            )

    def recording_duration_seconds(self) -> int:
        if not self.recorder.is_recording():
            return 0
        sessions_by_id = getattr(self.recorder, "sessions", None)
        if isinstance(sessions_by_id, dict) and sessions_by_id:
            started_at = min(session.started_at for session in sessions_by_id.values())
            return max(0, int((self.clock.now() - started_at).total_seconds()))
        session = self.recorder.session
        if session is None:
            return 0
        return max(0, int((self.clock.now() - session.started_at).total_seconds()))

    def recording_health(self) -> list[dict[str, Any]]:
        if not self.recorder.is_recording():
            self._recording_health_sizes.clear()
            return []

        sessions = self._active_sessions()
        health: list[dict[str, Any]] = []
        for source_id, session in sessions.items():
            latest_file = _latest_recording_file(session.output_pattern)
            current_size = latest_file.stat().st_size if latest_file and latest_file.exists() else 0
            previous_size = self._recording_health_sizes.get(source_id)
            growing = previous_size is not None and current_size > previous_size
            self._recording_health_sizes[source_id] = current_size
            if latest_file is None:
                state = "waiting_for_file"
                message = "Waiting for first segment"
            elif previous_size is None:
                state = "checking"
                message = "Checking file growth"
            elif growing:
                state = "writing"
                message = "Writing video data"
            elif current_size > 0:
                state = "stalled"
                message = "File is not growing"
            else:
                state = "empty"
                message = "Recording file is empty"
            health.append(
                {
                    "source_id": source_id,
                    "file": latest_file.name if latest_file else None,
                    "size_bytes": current_size,
                    "growing": growing,
                    "state": state,
                    "message": message,
                }
            )
        return health

    def _active_sessions(self) -> dict[str, RecordingSession]:
        sessions_by_id = getattr(self.recorder, "sessions", None)
        if isinstance(sessions_by_id, dict) and sessions_by_id:
            return dict(sessions_by_id)
        session = self.recorder.session
        return {session.source_id: session} if session else {}

    def _led_state_for(
        self,
        *,
        source_statuses: list[dict[str, Any]],
        recording: bool,
        storage_warning: bool,
    ) -> LedState:
        if storage_warning:
            return LedState.STORAGE_WARNING
        if recording:
            return LedState.RECORDING
        if any(source.get("online", False) for source in source_statuses):
            return LedState.ONLINE
        return LedState.OFFLINE


def _latest_recording_file(output_pattern: Path) -> Path | None:
    parent = output_pattern.parent
    name = output_pattern.name
    if "%03d" not in name:
        return output_pattern if output_pattern.exists() else None
    prefix, suffix = name.split("%03d", 1)
    if not parent.exists():
        return None
    candidates = [
        path
        for path in parent.iterdir()
        if path.is_file() and path.name.startswith(prefix) and path.name.endswith(suffix)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)
