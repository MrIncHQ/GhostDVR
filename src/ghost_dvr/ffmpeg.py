from __future__ import annotations

import os
import shutil
from pathlib import Path


def find_ffmpeg() -> str | None:
    path = shutil.which("ffmpeg")
    if path:
        return path

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    package_root = (
        Path(local_app_data)
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    )
    if not package_root.exists():
        return None

    for build_dir in package_root.glob("ffmpeg-*-full_build"):
        candidate = build_dir / "bin" / "ffmpeg.exe"
        try:
            if candidate.exists():
                return str(candidate)
        except OSError:
                return str(candidate)
    return None


def find_ffprobe(ffmpeg_path: str | None = None) -> str | None:
    path = shutil.which("ffprobe")
    if path:
        return path

    if ffmpeg_path:
        ffmpeg = Path(ffmpeg_path)
        candidates = [ffmpeg.with_name("ffprobe"), ffmpeg.with_name("ffprobe.exe")]
        for candidate in candidates:
            try:
                if candidate.exists():
                    return str(candidate)
            except OSError:
                return str(candidate)

    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None

    package_root = (
        Path(local_app_data)
        / "Microsoft"
        / "WinGet"
        / "Packages"
        / "Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe"
    )
    if not package_root.exists():
        return None

    for build_dir in package_root.glob("ffmpeg-*-full_build"):
        candidate = build_dir / "bin" / "ffprobe.exe"
        try:
            if candidate.exists():
                return str(candidate)
        except OSError:
            return str(candidate)
    return None
