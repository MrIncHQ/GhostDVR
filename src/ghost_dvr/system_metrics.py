from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any


def system_metrics(
    *,
    meminfo_path: Path = Path("/proc/meminfo"),
    uptime_path: Path = Path("/proc/uptime"),
    temperature_path: Path = Path("/sys/class/thermal/thermal_zone0/temp"),
) -> dict[str, Any]:
    return {
        "hostname": platform.node(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "load": _load_average(),
        "memory": _memory_status(meminfo_path),
        "temperature_c": _temperature_c(temperature_path),
        "uptime_seconds": _uptime_seconds(uptime_path),
    }


def _load_average() -> dict[str, float] | None:
    try:
        one, five, fifteen = os.getloadavg()
    except (AttributeError, OSError):
        return None
    return {
        "1m": round(one, 2),
        "5m": round(five, 2),
        "15m": round(fifteen, 2),
    }


def _memory_status(path: Path) -> dict[str, float] | None:
    if not path.exists():
        return None

    values: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        key, _, remainder = line.partition(":")
        parts = remainder.strip().split()
        if parts and parts[0].isdigit():
            values[key] = int(parts[0])

    total_kb = values.get("MemTotal")
    available_kb = values.get("MemAvailable")
    if not total_kb or available_kb is None:
        return None

    used_kb = max(total_kb - available_kb, 0)
    used_percent = (used_kb / total_kb) * 100
    return {
        "total_mb": round(total_kb / 1024, 1),
        "available_mb": round(available_kb / 1024, 1),
        "used_mb": round(used_kb / 1024, 1),
        "used_percent": round(used_percent, 1),
    }


def _temperature_c(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore").strip()
        return round(int(raw) / 1000, 1)
    except (OSError, ValueError):
        return None


def _uptime_seconds(path: Path) -> int | None:
    if not path.exists():
        return None
    try:
        raw = path.read_text(encoding="utf-8", errors="ignore").split()[0]
        return int(float(raw))
    except (IndexError, OSError, ValueError):
        return None
