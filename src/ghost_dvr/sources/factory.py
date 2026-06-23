from __future__ import annotations

from typing import Any

from ghost_dvr.sources.base import Source, SourceConfig
from ghost_dvr.sources.mock import MockVideoSource
from ghost_dvr.sources.rtsp import RtspSource


def source_config_from_dict(data: dict[str, Any]) -> SourceConfig:
    return SourceConfig(
        source_id=data["source_id"],
        name=data["name"],
        source_type=data["source_type"],
        address=data["address"],
        username=data.get("username"),
        password=data.get("password"),
        stream_path=data.get("stream_path"),
    )


def create_source(config: SourceConfig) -> Source:
    source_type = config.source_type.lower()
    if source_type == "mock":
        return MockVideoSource(config)
    if source_type == "rtsp":
        return RtspSource(config)
    raise ValueError(f"Unsupported source type: {config.source_type}")


def create_sources(config_data: list[dict[str, Any]]) -> list[Source]:
    return [create_source(source_config_from_dict(item)) for item in config_data]
