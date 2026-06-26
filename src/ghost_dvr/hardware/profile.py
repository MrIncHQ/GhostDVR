from __future__ import annotations

import platform
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class HardwareProfile:
    name: str
    recommended_sources: int
    web_ui_enabled: bool
    playback_enabled: bool
    advanced_features_enabled: bool

    def to_dict(self) -> dict[str, str | int | bool]:
        return asdict(self)

    @property
    def is_raspberry_pi(self) -> bool:
        return self.name.startswith("Raspberry Pi")


WINDOWS_PC_PROFILE = HardwareProfile(
    name="Windows PC",
    recommended_sources=8,
    web_ui_enabled=True,
    playback_enabled=True,
    advanced_features_enabled=True,
)

WINDOWS_DEV_PROFILE = WINDOWS_PC_PROFILE

UNKNOWN_LINUX_PROFILE = HardwareProfile(
    name="Generic Linux SBC",
    recommended_sources=1,
    web_ui_enabled=True,
    playback_enabled=False,
    advanced_features_enabled=False,
)

PI_ZERO_2_W_PROFILE = HardwareProfile(
    name="Raspberry Pi Zero 2 W",
    recommended_sources=1,
    web_ui_enabled=False,
    playback_enabled=False,
    advanced_features_enabled=False,
)

PI_4_PROFILE = HardwareProfile(
    name="Raspberry Pi 4",
    recommended_sources=4,
    web_ui_enabled=True,
    playback_enabled=False,
    advanced_features_enabled=False,
)

PI_5_PROFILE = HardwareProfile(
    name="Raspberry Pi 5",
    recommended_sources=4,
    web_ui_enabled=True,
    playback_enabled=True,
    advanced_features_enabled=True,
)


def detect_hardware_profile(cpuinfo_path: Path = Path("/proc/cpuinfo")) -> HardwareProfile:
    if cpuinfo_path.exists():
        cpuinfo = cpuinfo_path.read_text(encoding="utf-8", errors="ignore").lower()
        if "raspberry pi zero 2" in cpuinfo:
            return PI_ZERO_2_W_PROFILE
        if "raspberry pi 5" in cpuinfo:
            return PI_5_PROFILE
        if "raspberry pi 4" in cpuinfo:
            return PI_4_PROFILE
    system = platform.system().lower()
    if system == "windows":
        return WINDOWS_PC_PROFILE
    return UNKNOWN_LINUX_PROFILE
