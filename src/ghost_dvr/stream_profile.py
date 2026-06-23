from __future__ import annotations

from pathlib import Path


def describe_stream_profile(stream: str, source_type: str) -> str:
    if source_type == "mock":
        return f"Mock File ({Path(stream).name})"
    if source_type != "rtsp":
        return source_type

    lowered = stream.lower()
    if "h264preview_01_main" in lowered:
        return "Reolink Main Stream (H.264)"
    if "h264preview_01_sub" in lowered:
        return "Reolink Sub Stream (H.264)"
    if "h265preview_01_main" in lowered:
        return "Reolink Main Stream (H.265/HEVC)"
    if "h265preview_01_sub" in lowered:
        return "Reolink Sub Stream (H.265/HEVC)"
    return "RTSP Stream"
