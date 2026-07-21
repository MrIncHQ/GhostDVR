from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from ghost_dvr.identity import DeviceIdentity


def build_status(
    identity: DeviceIdentity,
    *,
    recording: bool = False,
    sources: list[dict[str, Any]] | None = None,
    storage_free_gb: float | None = None,
    storage: dict[str, Any] | None = None,
    timestamp: str | None = None,
    hardware_profile: dict[str, Any] | None = None,
    recording_duration_seconds: int = 0,
    recording_health: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    source_statuses = sources or []
    storage_status = storage or {}
    return {
        "device_id": identity.device_id,
        "hostname": identity.hostname,
        "recording": recording,
        "recording_duration_seconds": recording_duration_seconds,
        "source_online": any(source.get("online", False) for source in source_statuses),
        "sources": source_statuses,
        "storage": storage_status,
        "storage_free_gb": storage_status.get("free_gb", storage_free_gb),
        "hardware_profile": hardware_profile or {},
        "recording_health": recording_health or [],
        "timestamp": timestamp
        or datetime.now().astimezone().isoformat(timespec="seconds"),
    }


def write_status(
    path: Path,
    identity: DeviceIdentity,
    *,
    recording: bool = False,
    sources: list[dict[str, Any]] | None = None,
    storage_free_gb: float | None = None,
    storage: dict[str, Any] | None = None,
    timestamp: str | None = None,
    hardware_profile: dict[str, Any] | None = None,
    recording_duration_seconds: int = 0,
    recording_health: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    status = build_status(
        identity,
        recording=recording,
        sources=sources,
        storage_free_gb=storage_free_gb,
        storage=storage,
        timestamp=timestamp,
        hardware_profile=hardware_profile,
        recording_duration_seconds=recording_duration_seconds,
        recording_health=recording_health,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(status, file, indent=2)
        file.write("\n")
    return status
