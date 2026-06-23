from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from ghost_dvr.ffmpeg import find_ffmpeg
from ghost_dvr.secrets import redact_url_credentials


@dataclass(frozen=True)
class PreviewResult:
    image_path: Path | None
    error: str | None = None


class PreviewFrameGrabber:
    def __init__(
        self,
        preview_dir: Path,
        *,
        ffmpeg_path: str = "ffmpeg",
        timeout_seconds: int = 5,
    ) -> None:
        self.preview_dir = preview_dir
        self.ffmpeg_path = ffmpeg_path
        self.timeout_seconds = timeout_seconds

    def grab(self, stream: str, source_id: str = "source") -> PreviewResult:
        if not stream:
            return PreviewResult(None, "No stream available")

        self.preview_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.preview_dir / f"{source_id}.png"
        ffmpeg_path = find_ffmpeg() or self.ffmpeg_path
        command = [
            ffmpeg_path,
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-rtsp_transport",
            "tcp",
            "-i",
            stream,
            "-frames:v",
            "1",
            "-vf",
            "scale=720:-1",
            str(output_path),
        ]

        try:
            subprocess.run(
                command,
                check=True,
                capture_output=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError:
            return PreviewResult(None, "FFmpeg not found")
        except subprocess.TimeoutExpired:
            return PreviewResult(None, "Preview timed out")
        except subprocess.CalledProcessError as exc:
            error = exc.stderr.decode("utf-8", errors="ignore").strip()
            return PreviewResult(None, redact_url_credentials(error) or "Preview frame failed")

        if not output_path.exists():
            return PreviewResult(None, "Preview frame was not created")
        return PreviewResult(output_path)
