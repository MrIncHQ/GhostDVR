from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass

from ghost_dvr.ffmpeg import find_ffmpeg


@dataclass(frozen=True)
class DependencyStatus:
    name: str
    available: bool
    detail: str

    def to_dict(self) -> dict[str, str | bool]:
        return asdict(self)


def check_ffmpeg() -> DependencyStatus:
    path = find_ffmpeg()
    if path is None:
        return DependencyStatus(
            name="ffmpeg",
            available=False,
            detail="FFmpeg was not found on PATH",
        )

    try:
        result = subprocess.run(
            [path, "-version"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return DependencyStatus(
            name="ffmpeg",
            available=False,
            detail=str(exc),
        )

    first_line = result.stdout.splitlines()[0] if result.stdout else path
    return DependencyStatus(name="ffmpeg", available=True, detail=first_line)


def run_diagnostics() -> list[DependencyStatus]:
    return [check_ffmpeg()]
