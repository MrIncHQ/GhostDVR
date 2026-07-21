from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ghost_dvr.ffmpeg import find_ffmpeg, find_ffprobe
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

    ffprobe = find_ffprobe(ffmpeg)
    if ffprobe is None:
        return StreamProbeResult(ok=False, error="FFprobe not found")

    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,codec_type,width,height",
        "-of",
        "json",
    ]
    if stream.lower().startswith("rtsp://"):
        command[3:3] = ["-rtsp_transport", "tcp"]
    command.append(stream)

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
        detail = result.stderr.strip() or "Source probe failed"
        return StreamProbeResult(
            ok=False,
            error=friendly_probe_error(detail),
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


def friendly_probe_error(error: str) -> str:
    detail = redact_url_credentials(error.strip() or "Source probe failed")
    lower = detail.lower()
    if "401" in lower or "unauthorized" in lower:
        return "Camera login failed. Check the username and password."
    if "403" in lower or "forbidden" in lower:
        return "Camera refused access. Check camera permissions or RTSP settings."
    if "404" in lower or "stream not found" in lower:
        return "Camera stream path was not found. Check the RTSP URL path."
    if "timed out" in lower or "timeout" in lower:
        return "Camera connection timed out. Check that the camera is online and reachable from this device."
    if "connection refused" in lower:
        return "Camera refused the connection. Check the IP address, port, and whether RTSP is enabled."
    if "no route to host" in lower or "host is unreachable" in lower or "network is unreachable" in lower:
        return "Camera is not reachable from this device. Check network, IP address, and VLAN/Wi-Fi routing."
    if "invalid data found" in lower or "could not find codec parameters" in lower:
        return "Camera stream opened but the video format could not be read. Try a different stream profile."
    return detail.splitlines()[-1] if detail else "Source probe failed"
