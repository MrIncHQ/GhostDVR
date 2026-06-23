from __future__ import annotations

from getpass import getpass
from typing import Callable


InputFn = Callable[[str], str]
SUPPORTED_SOURCE_TYPES = {"mock", "rtsp"}


def build_source_config(
    *,
    source_type: str,
    name: str,
    address: str,
    username: str = "",
    password: str = "",
    stream_path: str = "",
    source_id: str = "source-1",
) -> dict[str, str | None]:
    normalized_source_type = source_type.strip().lower() or "mock"
    if normalized_source_type not in SUPPORTED_SOURCE_TYPES:
        raise ValueError(
            f"Unsupported source type: {normalized_source_type}. Use mock or rtsp."
        )

    return {
        "source_id": source_id,
        "name": name.strip() or "Source 1",
        "source_type": normalized_source_type,
        "address": address.strip() or "test_video.mp4",
        "username": username.strip() or None,
        "password": password or None,
        "stream_path": stream_path.strip() or None,
    }


def run_setup_prompt(input_fn: InputFn = input) -> dict[str, str | None]:
    print("Ghost DVR First Time Setup")
    print()
    while True:
        source_type = input_fn("Source Type [mock/rtsp] (mock): ") or "mock"
        if source_type.strip().lower() in SUPPORTED_SOURCE_TYPES:
            break
        print("Unsupported source type. Use mock or rtsp.")
    name = input_fn("Source Name (Mock Video): ") or "Mock Video"
    address = input_fn("Source Address or File (test_video.mp4): ") or "test_video.mp4"
    username = input_fn("Username (optional): ")
    password = getpass("Password (optional): ") if username else ""
    stream_path = input_fn("Stream Path (optional): ")
    return build_source_config(
        source_type=source_type,
        name=name,
        address=address,
        username=username,
        password=password,
        stream_path=stream_path,
    )
