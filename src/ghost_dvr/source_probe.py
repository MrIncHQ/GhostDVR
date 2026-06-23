from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ghost_dvr.ffmpeg import find_ffmpeg
from ghost_dvr.secrets import redact_url_credentials


@dataclass(frozen=True)
class StreamProbeResult:
    ok: bool
    codec_name: str | None = None
    codec_type: str | None = None
    width: int | None = None
    height: int | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, bool | int | str | None]:
        return asdict(self)


def probe_stream(stream: str, timeout_seconds: int = 15) -> StreamProbeResult:
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        return StreamProbeResult(ok=False, error="FFmpeg not found")

    ffprobe = str(Path(ffmpeg).with_name("ffprobe.exe"))
    command = [
        ffprobe,
        "-v",
        "error",
        "-rtsp_transport",
        "tcp",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,codec_type,width,height",
        "-of",
        "json",
        stream,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return StreamProbeResult(ok=False, error="Source probe timed out")
    except OSError as exc:
        return StreamProbeResult(ok=False, error=str(exc))

    if result.returncode != 0:
        return StreamProbeResult(
            ok=False,
            error=redact_url_credentials(result.stderr.strip() or "Source probe failed"),
        )

    data: dict[str, Any] = json.loads(result.stdout)
    streams = data.get("streams", [])
    if not streams:
        return StreamProbeResult(ok=False, error="No video stream found")

    stream_info = streams[0]
    return StreamProbeResult(
        ok=True,
        codec_name=stream_info.get("codec_name"),
        codec_type=stream_info.get("codec_type"),
        width=stream_info.get("width"),
        height=stream_info.get("height"),
    )
