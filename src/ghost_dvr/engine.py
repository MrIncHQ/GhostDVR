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
from ghost_dvr.recording import FfmpegRecorder
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
        self.active_metadata_path: Path | None = None
        self.active_source_id: str | None = None
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
        )

    def start_recording(self, source_id: str | None = None) -> dict[str, Any]:
        statuses = self.refresh_sources()
        source = self._select_recording_source(statuses, source_id)
        validation_error = self._validate_source_for_recording(source.source_id)
        if validation_error:
            raise RuntimeError(validation_error)
        session = self.recorder.start(source)
        self.recording_requested = True
        self.active_source_id = source.source_id
        self.active_metadata_path = self.metadata_store.create(
            identity=self.identity,
            source=source,
            session=session,
        )
        self.logger.info("Recording Started: %s", session.output_pattern)
        return self.snapshot()

    def stop_recording(self) -> dict[str, Any]:
        self.recording_requested = False
        was_recording = self.recorder.is_recording()
        if was_recording:
            self._finish_active_metadata()
        self.recorder.stop()
        if was_recording:
            self.active_source_id = None
            self.logger.info("Recording Stopped")
        return self.snapshot()

    def health_check(self) -> dict[str, Any]:
        if self.recording_requested and not self.recorder.is_recording():
            self.logger.error("Recording Process Failure")
            self._finish_active_metadata()
            source_id = self.active_source_id
            self.recording_requested = False
            self.active_source_id = None
            if self.config.get("recording", {}).get("auto_reconnect", True):
                self.logger.info("Attempting Recording Recovery")
                try:
                    return self.start_recording(source_id)
                except Exception as exc:
                    self.logger.error("Recording Recovery Failed: %s", exc)
        return self.snapshot()

    def _select_recording_source(
        self,
        statuses: list[SourceStatus],
        source_id: str | None,
    ) -> SourceStatus:
        candidates = [
            status
            for status in statuses
            if status.online and (source_id is None or status.source_id == source_id)
        ]
        if not candidates:
            raise RuntimeError("No online source is available for recording")
        return candidates[0]

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
        session = self.recorder.session
        if self.active_metadata_path and session:
            self.metadata_store.finish(
                path=self.active_metadata_path,
                started_at=session.started_at,
            )
            self.active_metadata_path = None

    def recording_duration_seconds(self) -> int:
        session = self.recorder.session
        if not self.recorder.is_recording() or session is None:
            return 0
        return max(0, int((self.clock.now() - session.started_at).total_seconds()))

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
