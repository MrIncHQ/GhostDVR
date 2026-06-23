from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from ghost_dvr.ffmpeg import find_ffmpeg


@dataclass(frozen=True)
class RecordingSession:
    source_id: str
    output_pattern: Path
    started_at: datetime


class RecordableSource(Protocol):
    source_id: str
    source_type: str
    online: bool
    stream: str | None


class FfmpegRecorder:
    def __init__(self, recordings_dir: Path, segment_minutes: int = 15) -> None:
        self.recordings_dir = recordings_dir
        self.segment_minutes = segment_minutes
        self.process: subprocess.Popen[bytes] | None = None
        self.session: RecordingSession | None = None

    def is_recording(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def build_command(self, source: RecordableSource, output_pattern: Path) -> list[str]:
        input_args = []
        if source.source_type == "mock":
            input_args = ["-re", "-stream_loop", "-1"]
        elif source.source_type == "rtsp":
            input_args = ["-rtsp_transport", "tcp"]

        output_format = "segment"
        output_suffix = str(output_pattern)
        return [
            find_ffmpeg() or "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "warning",
            *input_args,
            "-i",
            source.stream or "",
            "-c",
            "copy",
            "-f",
            output_format,
            "-segment_time",
            str(self.segment_minutes * 60),
            "-reset_timestamps",
            "1",
            output_suffix,
        ]

    def start(self, source: RecordableSource) -> RecordingSession:
        if self.is_recording():
            raise RuntimeError("Recording is already active")
        if not source.online or not source.stream:
            raise RuntimeError("Cannot record from an offline source")

        self.recordings_dir.mkdir(parents=True, exist_ok=True)
        started_at = datetime.now().astimezone()
        output_pattern = self.recordings_dir / f"{started_at:%Y-%m-%d_%H-%M-%S}_%03d.mkv"
        command = self.build_command(source, output_pattern)

        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.session = RecordingSession(
            source_id=source.source_id,
            output_pattern=output_pattern,
            started_at=started_at,
        )
        return self.session

    def stop(self) -> None:
        if self.process is None:
            return
        if self.process.poll() is None:
            try:
                if self.process.stdin:
                    self.process.stdin.write(b"q")
                    self.process.stdin.flush()
                self.process.wait(timeout=10)
            except (BrokenPipeError, OSError, subprocess.TimeoutExpired):
                if self.process.poll() is None:
                    self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)
        self.process = None
        self.session = None
