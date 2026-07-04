from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from ghost_dvr.auth import default_auth_config
from ghost_dvr.identity import DeviceIdentity


def default_source() -> dict[str, Any]:
    return {
        "_notes": "source_type must be mock, rtsp, or usb. For mock, address is a local video file path. For rtsp, address must be a full rtsp:// URL. For usb, use /dev/video0 on Linux/Pi or video=Camera Name on Windows.",
        "source_id": "source-1",
        "name": "Mock Video",
        "source_type": "mock",
        "address": "test_video.mp4",
    }


def default_config(identity: DeviceIdentity) -> dict[str, Any]:
    return {
        "_notes": "Ghost DVR config file. JSON does not support comments, so _notes fields are informational and ignored by the app.",
        "device": {
            "_notes": "Generated on first launch. Do not edit uuid, device_id, or hostname while recording. Change only for deliberate device identity reset or rename.",
            "uuid": identity.uuid,
            "device_id": identity.device_id,
            "hostname": identity.hostname,
        },
        "hardware": {
            "_notes": "Hardware recommendations are advisory. gpio_led_pin is used by real GPIO on Raspberry Pi and mock GPIO on Windows. gpio_led_backend supports auto, gpio, or mock.",
            "auto_detect": True,
            "max_sources": 1,
            "hardware_profile_override": False,
            "gpio_led_pin": 18,
            "gpio_led_backend": "auto",
        },
        "recording": {
            "_notes": "segment_minutes controls output file splitting. max_duration_minutes controls how long a recording session runs; use 0 for infinite. stop_when_free_gb_below stops recording when free disk space falls to that GB floor. storage_mode supports stop now; overwrite_oldest is reserved for later. auto_reconnect restarts failed recordings.",
            "segment_minutes": 15,
            "max_duration_minutes": 0,
            "stop_when_free_gb_below": 2.0,
            "storage_warning_percent": 10,
            "storage_mode": "stop",
            "auto_reconnect": True,
        },
        "storage": {
            "_notes": "preferred_paths can list external recording folders. First usable path wins. Leave empty to use runtime/recordings.",
            "preferred_paths": [],
        },
        "web": {
            "_notes": "Local web/API server settings. host 0.0.0.0 allows access from other devices on the same network. Use 127.0.0.1 for local-only access. Do not port-forward this dashboard to the internet.",
            "enabled": False,
            "host": "0.0.0.0",
            "port": 8080,
        },
        "web_auth": default_auth_config(),
        "time": {
            "_notes": "Use local for the computer timezone, UTC for UTC, or an IANA timezone when available.",
            "timezone": "local",
        },
        "features": {
            "_notes": "Feature flags for current and future capabilities. Disabled future features may not be implemented yet.",
            "web_ui": False,
            "gpio_led": True,
            "gpio_buzzer": False,
            "multi_source": False,
            "plugins": False,
        },
        "sources": [default_source()],
    }


def load_or_create_config(path: Path, identity: DeviceIdentity) -> dict[str, Any]:
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as file:
                config = json.load(file)
        except JSONDecodeError as exc:
            raise ValueError(
                f"Invalid JSON in {path} at line {exc.lineno}, column {exc.colno}: {exc.msg}"
            ) from exc
        migrated = merge_missing_defaults(config, default_config(identity))
        web_config = migrated.get("web", {})
        if isinstance(web_config, dict):
            web_config.pop("admin_token", None)
        if migrated != config:
            config = migrated
            save_config(path, config)
        return config

    config = default_config(identity)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)
        file.write("\n")
    return config


def save_config(path: Path, config: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(config, file, indent=2)
        file.write("\n")


def merge_missing_defaults(
    config: dict[str, Any],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    merged = dict(config)
    for key, default_value in defaults.items():
        if key not in merged:
            merged[key] = default_value
            continue
        if isinstance(default_value, dict) and isinstance(merged[key], dict):
            merged[key] = merge_missing_defaults(merged[key], default_value)
        elif key == "sources" and not merged[key]:
            merged[key] = default_value
    return merged
