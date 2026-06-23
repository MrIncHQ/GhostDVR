from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


VIDEO_EXTENSIONS = {".mkv", ".mp4"}


@dataclass(frozen=True)
class RecordingEntry:
    video_file: str
    metadata_file: str | None
    size_bytes: int
    status: str
    duration_seconds: int | None = None
    source_name: str | None = None
    source_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def needs_attention(self) -> bool:
        return self.status != "ok"


def list_recordings(recordings_dir: Path) -> list[RecordingEntry]:
    if not recordings_dir.exists():
        return []

    entries: list[RecordingEntry] = []
    for video_file in sorted(recordings_dir.iterdir(), key=lambda item: item.name):
        if not video_file.is_file() or video_file.suffix.lower() not in VIDEO_EXTENSIONS:
            continue

        metadata_file = _metadata_file_for(video_file)
        metadata = _read_metadata(metadata_file)
        size_bytes = video_file.stat().st_size
        entries.append(
            RecordingEntry(
                video_file=video_file.name,
                metadata_file=metadata_file.name if metadata_file.exists() else None,
                size_bytes=size_bytes,
                status=_status_for(video_file, metadata_file, size_bytes),
                duration_seconds=metadata.get("duration_seconds"),
                source_name=metadata.get("source_name"),
                source_type=metadata.get("source_type"),
            )
        )
    return entries


def recordings_report(recordings_dir: Path) -> dict[str, Any]:
    recordings = list_recordings(recordings_dir)
    return {
        "recordings_dir": str(recordings_dir),
        "count": len(recordings),
        "ok_count": sum(1 for item in recordings if item.status == "ok"),
        "attention_count": sum(1 for item in recordings if item.status != "ok"),
        "recordings": [item.to_dict() for item in recordings],
    }


def cleanup_plan(recordings_dir: Path) -> dict[str, Any]:
    recordings = list_recordings(recordings_dir)
    delete_files: list[str] = []
    for entry in recordings:
        if not entry.needs_attention:
            continue
        delete_files.append(entry.video_file)
        if entry.metadata_file:
            delete_files.append(entry.metadata_file)

    return {
        "recordings_dir": str(recordings_dir),
        "delete_count": len(delete_files),
        "delete_files": delete_files,
    }


def cleanup_attention_recordings(recordings_dir: Path) -> dict[str, Any]:
    plan = cleanup_plan(recordings_dir)
    deleted: list[str] = []
    for name in plan["delete_files"]:
        path = recordings_dir / str(name)
        if path.exists() and path.is_file():
            path.unlink()
            deleted.append(name)
    return {
        "recordings_dir": str(recordings_dir),
        "deleted_count": len(deleted),
        "deleted_files": deleted,
    }


def _metadata_file_for(video_file: Path) -> Path:
    stem = video_file.stem
    if stem.endswith("_000"):
        stem = stem.removesuffix("_000")
    return video_file.with_name(f"{stem}.json")


def _read_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _status_for(video_file: Path, metadata_file: Path, size_bytes: int) -> str:
    if size_bytes == 0:
        return "empty_file"
    if not metadata_file.exists():
        return "missing_metadata"
    if video_file.suffix.lower() == ".mp4":
        return "legacy_mp4_check_playback"
    return "ok"
