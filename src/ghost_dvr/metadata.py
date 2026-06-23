from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ghost_dvr.identity import DeviceIdentity
from ghost_dvr.recording import RecordingSession


class MetadataSource(Protocol):
    name: str
    source_type: str


@dataclass(frozen=True)
class RecordingMetadata:
    device_id: str
    source_name: str
    source_type: str
    recording_start: str
    duration_seconds: int | None
    video_pattern: str

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "device_id": self.device_id,
            "source_name": self.source_name,
            "source_type": self.source_type,
            "recording_start": self.recording_start,
            "duration_seconds": self.duration_seconds,
            "video_pattern": self.video_pattern,
        }


class RecordingMetadataStore:
    def create(
        self,
        *,
        identity: DeviceIdentity,
        source: MetadataSource,
        session: RecordingSession,
    ) -> Path:
        path = self.metadata_path_for(session.output_pattern)
        metadata = RecordingMetadata(
            device_id=identity.device_id,
            source_name=source.name,
            source_type=source.source_type,
            recording_start=session.started_at.isoformat(timespec="seconds"),
            duration_seconds=None,
            video_pattern=str(session.output_pattern),
        )
        self._write(path, metadata.to_dict())
        return path

    def finish(
        self,
        *,
        path: Path,
        started_at: datetime,
        stopped_at: datetime | None = None,
    ) -> None:
        data = json.loads(path.read_text(encoding="utf-8"))
        stop_time = stopped_at or datetime.now().astimezone()
        data["duration_seconds"] = max(0, int((stop_time - started_at).total_seconds()))
        self._write(path, data)

    def metadata_path_for(self, output_pattern: Path) -> Path:
        stem = output_pattern.stem.replace("_%03d", "")
        return output_pattern.with_name(f"{stem}.json")

    def _write(self, path: Path, data: dict[str, str | int | None]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)
            file.write("\n")
