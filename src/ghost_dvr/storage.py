from __future__ import annotations

import shutil
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class StorageStatus:
    path: str
    total_gb: float
    used_gb: float
    free_gb: float
    free_percent: float
    warning: bool

    def to_dict(self) -> dict[str, float | str | bool]:
        return asdict(self)


class StorageMonitor:
    def __init__(self, path: Path, warning_percent: int = 10) -> None:
        self.path = path
        self.warning_percent = warning_percent

    def snapshot(self) -> StorageStatus:
        self.path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(self.path)
        total_gb = _bytes_to_gb(usage.total)
        used_gb = _bytes_to_gb(usage.used)
        free_gb = _bytes_to_gb(usage.free)
        free_percent = round((usage.free / usage.total) * 100, 2) if usage.total else 0.0
        return StorageStatus(
            path=str(self.path),
            total_gb=total_gb,
            used_gb=used_gb,
            free_gb=free_gb,
            free_percent=free_percent,
            warning=free_percent <= self.warning_percent,
        )


class StorageSelector:
    def __init__(
        self,
        *,
        preferred_paths: Iterable[Path],
        fallback_path: Path,
    ) -> None:
        self.preferred_paths = list(preferred_paths)
        self.fallback_path = fallback_path

    def select_recordings_dir(self) -> Path:
        for path in self.preferred_paths:
            if self._is_usable(path):
                return path
        self.fallback_path.mkdir(parents=True, exist_ok=True)
        return self.fallback_path

    def _is_usable(self, path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".ghost_dvr_write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            return True
        except OSError:
            return False


def _bytes_to_gb(value: int) -> float:
    return round(value / (1024**3), 2)
