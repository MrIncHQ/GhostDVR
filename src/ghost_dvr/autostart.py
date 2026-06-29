from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


SERVICE_NAME = "ghost-dvr-api.service"
WINDOWS_STARTUP_FILE = "Ghost DVR API.bat"


@dataclass(frozen=True)
class ApiAutostartStatus:
    supported: bool
    enabled: bool
    method: str
    target: str
    message: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def api_autostart_status(app_root: Path) -> ApiAutostartStatus:
    method = _method()
    target = _target_path(app_root, method)
    if method == "unsupported":
        return ApiAutostartStatus(
            supported=False,
            enabled=False,
            method=method,
            target="",
            message="API autostart is only supported on Windows and Linux.",
        )
    return ApiAutostartStatus(
        supported=True,
        enabled=target.exists(),
        method=method,
        target=str(target),
    )


def set_api_autostart(app_root: Path, enabled: bool) -> ApiAutostartStatus:
    method = _method()
    if method == "windows-startup":
        return _set_windows_startup(app_root, enabled)
    if method == "systemd-user":
        return _set_systemd_user_service(app_root, enabled)
    raise RuntimeError("API autostart is only supported on Windows and Linux")


def _method() -> str:
    system = platform.system().lower()
    if system == "windows":
        return "windows-startup"
    if system == "linux":
        return "systemd-user"
    return "unsupported"


def _target_path(app_root: Path, method: str) -> Path:
    if method == "windows-startup":
        startup = os.environ.get("APPDATA")
        if startup:
            return (
                Path(startup)
                / "Microsoft"
                / "Windows"
                / "Start Menu"
                / "Programs"
                / "Startup"
                / WINDOWS_STARTUP_FILE
            )
        return Path.home() / "AppData" / "Roaming" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / WINDOWS_STARTUP_FILE
    if method == "systemd-user":
        return Path.home() / ".config" / "systemd" / "user" / SERVICE_NAME
    return Path()


def _set_windows_startup(app_root: Path, enabled: bool) -> ApiAutostartStatus:
    target = _target_path(app_root, "windows-startup")
    launcher = app_root / "Run_Ghost_DVR_API.bat"
    if enabled:
        if not launcher.exists():
            raise FileNotFoundError(f"Missing launcher: {launcher}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "@echo off\n"
            f'cd /d "{app_root}"\n'
            f'call "{launcher}"\n',
            encoding="utf-8",
        )
    else:
        target.unlink(missing_ok=True)
    return api_autostart_status(app_root)


def _set_systemd_user_service(app_root: Path, enabled: bool) -> ApiAutostartStatus:
    target = _target_path(app_root, "systemd-user")
    launcher = app_root / "Run_Ghost_DVR_API_Pi.sh"
    if enabled:
        if not launcher.exists():
            raise FileNotFoundError(f"Missing launcher: {launcher}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            "[Unit]\n"
            "Description=Ghost DVR API\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n"
            "\n"
            "[Service]\n"
            "Type=simple\n"
            f"WorkingDirectory={app_root}\n"
            f"ExecStart=/bin/sh {launcher}\n"
            "Restart=on-failure\n"
            "RestartSec=5\n"
            "\n"
            "[Install]\n"
            "WantedBy=default.target\n",
            encoding="utf-8",
        )
        _run_systemctl(["daemon-reload"])
        _run_systemctl(["enable", SERVICE_NAME])
    else:
        _run_systemctl(["disable", SERVICE_NAME], check=False)
        target.unlink(missing_ok=True)
        _run_systemctl(["daemon-reload"], check=False)
    return api_autostart_status(app_root)


def _run_systemctl(args: list[str], *, check: bool = True) -> None:
    subprocess.run(
        ["systemctl", "--user", *args],
        check=check,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
