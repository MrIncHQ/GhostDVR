from __future__ import annotations

import json
import platform
import subprocess
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, quote, unquote, urlparse

from ghost_dvr.auth import (
    AUTH_COOKIE_NAME,
    auth_required,
    auth_status,
    configure_password,
    disable_auth,
    new_session_token,
    setup_required,
    verify_password,
)
from ghost_dvr.autostart import api_autostart_status, set_api_autostart
from ghost_dvr.config import save_config
from ghost_dvr.discovery import discover_onvif_cameras
from ghost_dvr.engine import DvrEngine
from ghost_dvr.ffmpeg import find_ffmpeg
from ghost_dvr.preview import PreviewFrameGrabber
from ghost_dvr.recording_library import list_recordings
from ghost_dvr.source_probe import friendly_probe_error, probe_stream
from ghost_dvr.sources.factory import create_source
from ghost_dvr.sources.base import SourceConfig
from ghost_dvr.storage import StorageMonitor
from ghost_dvr.system_metrics import system_metrics
from ghost_dvr.updater import check_update_status, restart_current_process, run_update, update_applied


UPDATE_CHECK_INTERVAL_SECONDS = 3 * 60 * 60


class PreviewGrabber(Protocol):
    def grab(self, stream: str, source_id: str = "source"):
        raise NotImplementedError


class GhostDvrApiServer:
    def __init__(
        self,
        *,
        engine: DvrEngine,
        events_log: Path,
        config: dict[str, Any] | None = None,
        config_file: Path | None = None,
        recordings_dir: Path | None = None,
        preview_grabber: PreviewGrabber | None = None,
        host: str = "0.0.0.0",
        port: int = 8080,
    ) -> None:
        self.engine = engine
        self.events_log = events_log
        self.config = config if config is not None else engine.config
        self.config_file = config_file
        self.recordings_dir = recordings_dir or events_log.parent.parent / "recordings"
        self.preview_grabber = preview_grabber or PreviewFrameGrabber(
            events_log.parent.parent / "preview"
        )
        self.host = host
        self.port = port
        self.httpd = ThreadingHTTPServer((host, port), self._handler_class())

    def serve_forever(self) -> None:
        self.httpd.serve_forever()

    def shutdown(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()

    def _handler_class(self) -> type[BaseHTTPRequestHandler]:
        engine = self.engine
        events_log = self.events_log
        config = self.config
        config_file = self.config_file
        recordings_dir = self.recordings_dir
        preview_grabber = self.preview_grabber
        update_cache: dict[str, Any] = {"checked_at": 0.0, "payload": None}
        sessions: set[str] = set()

        def cached_update_status(force: bool = False) -> dict[str, object]:
            now = time.monotonic()
            should_fetch = force or (
                update_cache["payload"] is not None
                and now - float(update_cache["checked_at"]) >= UPDATE_CHECK_INTERVAL_SECONDS
            )
            if (
                update_cache["payload"] is None
                or should_fetch
            ):
                update_cache["payload"] = check_update_status(fetch=should_fetch).to_dict()
                update_cache["checked_at"] = now
            return dict(update_cache["payload"])

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed_path = urlparse(self.path)
                if parsed_path.path == "/":
                    self._send_html(_web_page())
                    return
                if parsed_path.path == "/auth/status":
                    self._send_json(
                        auth_status(
                            config,
                            authenticated=self._is_authenticated(),
                        ).to_dict()
                    )
                    return
                if not self._authorize_request():
                    return
                if parsed_path.path == "/status":
                    self._send_json(engine.snapshot())
                    return
                if parsed_path.path == "/system":
                    self._send_json(system_metrics())
                    return
                if parsed_path.path == "/startup/api":
                    self._send_json(api_autostart_status(_app_root(config_file)).to_dict())
                    return
                if parsed_path.path == "/update/status":
                    query = parse_qs(parsed_path.query)
                    self._send_json(
                        cached_update_status(force=query.get("force", ["0"])[0] == "1")
                    )
                    return
                if parsed_path.path == "/sources":
                    self._send_json(
                        [source.to_dict() for source in engine.refresh_sources()]
                    )
                    return
                if parsed_path.path == "/discover/cameras":
                    self._send_json(
                        {
                            "cameras": [
                                camera.to_dict()
                                for camera in discover_onvif_cameras(timeout_seconds=3.0)
                            ]
                        }
                    )
                    return
                if parsed_path.path == "/config/sources":
                    self._send_json(_source_config_payload(config, engine))
                    return
                if parsed_path.path == "/config/recording":
                    self._send_json(_recording_config_payload(config))
                    return
                if parsed_path.path == "/config/storage":
                    self._send_json(_storage_config_payload(config, engine, recordings_dir))
                    return
                if parsed_path.path == "/events":
                    self._send_json({"events": _read_events(events_log)})
                    return
                if parsed_path.path == "/recordings":
                    active_recordings_dir = _active_recordings_dir(engine, recordings_dir)
                    self._send_json(
                        {"recordings": [item.to_dict() for item in list_recordings(active_recordings_dir)]}
                    )
                    return
                if parsed_path.path == "/recordings/download":
                    self._send_recording_download(
                        _active_recordings_dir(engine, recordings_dir),
                        parsed_path.query,
                    )
                    return
                if parsed_path.path == "/recordings/download-mp4":
                    self._send_recording_mp4_download(
                        _active_recordings_dir(engine, recordings_dir),
                        parsed_path.query,
                    )
                    return
                if parsed_path.path == "/preview":
                    self._send_preview(engine, preview_grabber, parsed_path.query)
                    return
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                parsed_path = urlparse(self.path)
                if parsed_path.path == "/auth/setup":
                    self._handle_auth_setup(config, config_file)
                    return
                if parsed_path.path == "/auth/login":
                    self._handle_auth_login(config, sessions)
                    return
                if parsed_path.path == "/auth/logout":
                    self._handle_auth_logout(sessions)
                    return
                if not self._authorize_request():
                    return
                if parsed_path.path == "/auth/password":
                    self._handle_auth_password(config, config_file, sessions)
                    return
                if parsed_path.path == "/auth/disable":
                    self._handle_auth_disable(config, config_file, sessions)
                    return
                if parsed_path.path == "/record/start":
                    self._handle_engine_action(engine.start_recording)
                    return
                if parsed_path.path == "/record/test":
                    self._handle_test_recording(
                        engine,
                        _active_recordings_dir(engine, recordings_dir),
                    )
                    return
                if parsed_path.path == "/record/stop":
                    self._handle_engine_action(engine.stop_recording)
                    return
                if parsed_path.path == "/recordings/delete":
                    self._handle_recording_delete(
                        engine,
                        config,
                        _active_recordings_dir(engine, recordings_dir),
                    )
                    return
                if parsed_path.path == "/config/sources":
                    self._handle_source_config_save(engine, config, config_file)
                    return
                if parsed_path.path == "/config/sources/probe":
                    self._handle_source_probe(config)
                    return
                if parsed_path.path == "/config/recording":
                    self._handle_recording_config_save(engine, config, config_file)
                    return
                if parsed_path.path == "/config/storage":
                    self._handle_storage_config_save(
                        engine,
                        config,
                        config_file,
                        recordings_dir,
                    )
                    return
                if parsed_path.path == "/startup/api":
                    self._handle_api_autostart(config_file)
                    return
                if parsed_path.path == "/update/run":
                    if engine.recorder.is_recording():
                        self._send_json(
                            {"error": "Stop recording before updating Ghost DVR"},
                            HTTPStatus.CONFLICT,
                        )
                        return
                    update_status = run_update()
                    payload = update_status.to_dict()
                    update_cache["payload"] = payload
                    update_cache["checked_at"] = time.monotonic()
                    self._send_json(payload)
                    if update_applied(update_status):
                        restart_current_process(delay_seconds=1.0)
                    return
                if parsed_path.path == "/device/shutdown":
                    self._handle_device_power(engine, "shutdown")
                    return
                if parsed_path.path == "/device/restart":
                    self._handle_device_power(engine, "restart")
                    return
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

            def log_message(self, format: str, *args: Any) -> None:
                return

            def _handle_engine_action(self, action) -> None:
                try:
                    self._send_json(action())
                except Exception as exc:
                    self._send_json(
                        {"error": str(exc)},
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )

            def _authorize_request(self) -> bool:
                if setup_required(config):
                    self._send_json(
                        {"error": "Dashboard auth setup is required"},
                        HTTPStatus.FORBIDDEN,
                    )
                    return False
                if not auth_required(config):
                    return True
                if self._is_authenticated():
                    return True
                self._send_json({"error": "Login required"}, HTTPStatus.UNAUTHORIZED)
                return False

            def _is_authenticated(self) -> bool:
                if not auth_required(config):
                    return not setup_required(config)
                token = self._session_cookie()
                return bool(token and token in sessions)

            def _session_cookie(self) -> str:
                cookie_header = self.headers.get("Cookie", "")
                for item in cookie_header.split(";"):
                    name, _, value = item.strip().partition("=")
                    if name == AUTH_COOKIE_NAME:
                        return value
                return ""

            def _set_session_cookie(self, token: str, *, clear: bool = False) -> None:
                max_age = "0" if clear else str(60 * 60 * 24 * 30)
                value = "" if clear else token
                self.send_header(
                    "Set-Cookie",
                    f"{AUTH_COOKIE_NAME}={value}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax",
                )

            def _handle_auth_setup(
                self,
                config: dict[str, Any],
                config_file: Path | None,
            ) -> None:
                if not setup_required(config):
                    self._send_json({"error": "Dashboard auth setup is already complete"}, HTTPStatus.CONFLICT)
                    return
                if config_file is None:
                    self._send_json({"error": "Config file is not available"}, HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                try:
                    payload = self._read_json_body()
                    action = str(payload.get("action") or "password")
                    token = ""
                    clear_cookie = False
                    if action == "skip":
                        disable_auth(config)
                        clear_cookie = True
                    elif action == "password":
                        password = str(payload.get("password") or "")
                        confirm = str(payload.get("confirm_password") or "")
                        if password != confirm:
                            raise ValueError("Dashboard passwords do not match")
                        configure_password(config, password)
                        token = new_session_token()
                        sessions.add(token)
                    else:
                        raise ValueError("Unsupported auth setup action")
                    save_config(config_file, config)
                    self._send_auth_response(config, token=token, clear=clear_cookie)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

            def _handle_auth_login(
                self,
                config: dict[str, Any],
                sessions: set[str],
            ) -> None:
                if setup_required(config):
                    self._send_json({"error": "Dashboard auth setup is required"}, HTTPStatus.FORBIDDEN)
                    return
                if not auth_required(config):
                    self._send_json(auth_status(config, authenticated=True).to_dict())
                    return
                payload = self._read_json_body()
                password = str(payload.get("password") or "")
                if not verify_password(config, password):
                    self._send_json({"error": "Invalid dashboard password"}, HTTPStatus.UNAUTHORIZED)
                    return
                token = new_session_token()
                sessions.add(token)
                self._send_auth_response(config, token=token)

            def _handle_auth_logout(self, sessions: set[str]) -> None:
                token = self._session_cookie()
                if token:
                    sessions.discard(token)
                self._send_auth_response(config, token="", clear=True)

            def _handle_auth_password(
                self,
                config: dict[str, Any],
                config_file: Path | None,
                sessions: set[str],
            ) -> None:
                if config_file is None:
                    self._send_json({"error": "Config file is not available"}, HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                try:
                    payload = self._read_json_body()
                    password = str(payload.get("password") or "")
                    confirm = str(payload.get("confirm_password") or "")
                    if password != confirm:
                        raise ValueError("Dashboard passwords do not match")
                    configure_password(config, password)
                    token = new_session_token()
                    sessions.add(token)
                    save_config(config_file, config)
                    self._send_auth_response(config, token=token)
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

            def _handle_auth_disable(
                self,
                config: dict[str, Any],
                config_file: Path | None,
                sessions: set[str],
            ) -> None:
                if config_file is None:
                    self._send_json({"error": "Config file is not available"}, HTTPStatus.INTERNAL_SERVER_ERROR)
                    return
                disable_auth(config)
                sessions.clear()
                save_config(config_file, config)
                self._send_auth_response(config, token="", clear=True)

            def _send_auth_response(
                self,
                config: dict[str, Any],
                *,
                token: str,
                clear: bool = False,
            ) -> None:
                payload = auth_status(
                    config,
                    authenticated=bool(token) or not auth_required(config),
                ).to_dict()
                body = json.dumps(payload, indent=2).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self._set_session_cookie(token, clear=clear)
                self.end_headers()
                self.wfile.write(body)

            def _handle_device_power(self, engine: DvrEngine, action: str) -> None:
                if engine.recorder.is_recording():
                    self._send_json(
                        {"error": f"Stop recording before device {action}"},
                        HTTPStatus.CONFLICT,
                    )
                    return
                try:
                    logger = getattr(engine, "logger", None)
                    if logger:
                        logger.warning("Device %s requested from web dashboard", action)
                    _schedule_device_power(action, delay_seconds=1.0)
                    self._send_json(
                        {
                            "ok": True,
                            "action": action,
                            "message": f"Device {action} scheduled.",
                        }
                    )
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

            def _send_json(
                self,
                payload: Any,
                status: HTTPStatus = HTTPStatus.OK,
            ) -> None:
                body = json.dumps(payload, indent=2).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_html(
                self,
                payload: str,
                status: HTTPStatus = HTTPStatus.OK,
            ) -> None:
                body = payload.encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _read_json_body(self) -> dict[str, Any]:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0:
                    return {}
                body = self.rfile.read(length).decode("utf-8")
                return json.loads(body)

            def _handle_source_config_save(
                self,
                engine: DvrEngine,
                config: dict[str, Any],
                config_file: Path | None,
            ) -> None:
                if config_file is None:
                    self._send_json(
                        {"error": "Config file is not available"},
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                try:
                    payload = self._read_json_body()
                    sources = _normalize_source_configs(
                        payload.get("sources", []),
                        existing_sources=config.get("sources", []),
                    )
                    engine.replace_sources(sources)
                    config["sources"] = sources
                    save_config(config_file, config)
                    self._send_json(_source_config_payload(config, engine))
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

            def _handle_source_probe(self, config: dict[str, Any]) -> None:
                try:
                    payload = self._read_json_body()
                    source_config = _normalize_single_source(
                        payload,
                        existing_sources=config.get("sources", []),
                    )
                    source = create_source(SourceConfig(**_source_config_for_factory(source_config)))
                    error = engine.recording_source_validator.validate(source)
                    self._send_json({"ok": error is None, "error": error})
                except Exception as exc:
                    self._send_json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)

            def _handle_recording_delete(
                self,
                engine: DvrEngine,
                config: dict[str, Any],
                recordings_dir: Path,
            ) -> None:
                if engine.recorder.is_recording():
                    self._send_json(
                        {"error": "Stop recording before deleting files"},
                        HTTPStatus.CONFLICT,
                    )
                    return
                try:
                    payload = self._read_json_body()
                    requested_file = str(payload.get("file", ""))
                    path = _safe_recording_path(recordings_dir, requested_file)
                    if path is None:
                        self._send_json(
                            {"error": "Recording not found"},
                            HTTPStatus.NOT_FOUND,
                        )
                        return
                    deleted = _delete_recording_files(recordings_dir, path)
                    self._send_json({"deleted": deleted})
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

            def _handle_test_recording(
                self,
                engine: DvrEngine,
                recordings_dir: Path,
            ) -> None:
                if engine.recorder.is_recording():
                    self._send_json(
                        {"ok": False, "error": "Stop recording before running a test recording"},
                        HTTPStatus.CONFLICT,
                    )
                    return
                try:
                    payload = self._read_json_body()
                    source_id = str(payload.get("source_id") or "").strip() or None
                    duration_seconds = int(payload.get("duration_seconds", 10) or 10)
                    result = _run_test_recording(
                        engine,
                        recordings_dir,
                        source_id=source_id,
                        duration_seconds=duration_seconds,
                    )
                    self._send_json(result)
                except Exception as exc:
                    self._send_json(
                        {"ok": False, "error": str(exc)},
                        HTTPStatus.BAD_REQUEST,
                    )

            def _handle_recording_config_save(
                self,
                engine: DvrEngine,
                config: dict[str, Any],
                config_file: Path | None,
            ) -> None:
                if config_file is None:
                    self._send_json(
                        {"error": "Config file is not available"},
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                try:
                    payload = self._read_json_body()
                    recording_config = _normalize_recording_config(
                        payload,
                        existing_recording=config.get("recording", {}),
                    )
                    config["recording"] = recording_config
                    engine.config["recording"] = recording_config
                    save_config(config_file, config)
                    self._send_json(_recording_config_payload(config))
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

            def _handle_storage_config_save(
                self,
                engine: DvrEngine,
                config: dict[str, Any],
                config_file: Path | None,
                fallback_recordings_dir: Path,
            ) -> None:
                if engine.recorder.is_recording():
                    self._send_json(
                        {"error": "Stop recording before changing storage settings"},
                        HTTPStatus.CONFLICT,
                    )
                    return
                if config_file is None:
                    self._send_json(
                        {"error": "Config file is not available"},
                        HTTPStatus.INTERNAL_SERVER_ERROR,
                    )
                    return
                try:
                    payload = self._read_json_body()
                    storage_config = _normalize_storage_config(payload)
                    active_path = _select_recordings_dir(
                        storage_config.get("preferred_paths", []),
                        config_file.parent,
                        fallback_recordings_dir,
                    )
                    config["storage"] = storage_config
                    engine.config["storage"] = storage_config
                    engine.recorder.recordings_dir = active_path
                    engine.storage_monitor = StorageMonitor(
                        active_path,
                        warning_percent=int(
                            config.get("recording", {}).get("storage_warning_percent", 10)
                        ),
                    )
                    save_config(config_file, config)
                    self._send_json(_storage_config_payload(config, engine, fallback_recordings_dir))
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

            def _handle_api_autostart(self, config_file: Path | None) -> None:
                try:
                    payload = self._read_json_body()
                    status = set_api_autostart(
                        _app_root(config_file),
                        enabled=bool(payload.get("enabled", False)),
                    )
                    self._send_json(status.to_dict())
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

            def _send_recording_download(
                self,
                recordings_dir: Path,
                query: str,
            ) -> None:
                requested_file = parse_qs(query).get("file", [""])[0]
                path = _safe_recording_path(recordings_dir, requested_file)
                if path is None:
                    self._send_json(
                        {"error": "Recording not found"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return

                self._send_file_download(path)

            def _send_recording_mp4_download(
                self,
                recordings_dir: Path,
                query: str,
            ) -> None:
                requested_file = parse_qs(query).get("file", [""])[0]
                path = _safe_recording_path(recordings_dir, requested_file)
                if path is None or path.suffix.lower() not in {".mkv", ".mp4"}:
                    self._send_json(
                        {"error": "Recording not found"},
                        HTTPStatus.NOT_FOUND,
                    )
                    return
                try:
                    mp4_path = _mp4_export_for_recording(path)
                    self._send_file_download(mp4_path, content_type="video/mp4")
                except Exception as exc:
                    self._send_json({"error": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

            def _send_file_download(
                self,
                path: Path,
                content_type: str | None = None,
            ) -> None:
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type or _content_type_for(path))
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename*=UTF-8''{quote(path.name)}",
                )
                self.send_header("Content-Length", str(path.stat().st_size))
                self.end_headers()
                with path.open("rb") as file:
                    while chunk := file.read(1024 * 1024):
                        self.wfile.write(chunk)

            def _send_preview(
                self,
                engine: DvrEngine,
                preview_grabber: PreviewGrabber,
                query: str,
            ) -> None:
                requested_source_id = parse_qs(query).get("source_id", [None])[0]
                source = _active_preview_source(engine, requested_source_id)
                if not source:
                    self._send_json(
                        {"error": "No online source stream available"},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return

                result = preview_grabber.grab(source["stream"], source["source_id"])
                if result.error or not result.image_path:
                    self._send_json(
                        {"error": result.error or "Preview unavailable"},
                        HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return

                body = Path(result.image_path).read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        return Handler


def _safe_recording_path(recordings_dir: Path, requested_file: str) -> Path | None:
    if not requested_file:
        return None
    candidate = (recordings_dir / unquote(requested_file)).resolve()
    root = recordings_dir.resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    if not candidate.is_file() or candidate.suffix.lower() not in {".mkv", ".mp4", ".json"}:
        return None
    return candidate


def _delete_recording_files(recordings_dir: Path, path: Path) -> list[str]:
    targets = [path]
    if path.suffix.lower() in {".mkv", ".mp4"}:
        metadata = _metadata_file_for_recording(path)
        if metadata.exists():
            targets.append(metadata)

    deleted: list[str] = []
    for target in targets:
        safe_target = _safe_recording_path(recordings_dir, target.name)
        if safe_target is None:
            continue
        safe_target.unlink()
        deleted.append(safe_target.name)
    return deleted


def _metadata_file_for_recording(video_file: Path) -> Path:
    stem = video_file.stem
    if stem.endswith("_000"):
        stem = stem.removesuffix("_000")
    return video_file.with_name(f"{stem}.json")


def _mp4_export_for_recording(video_file: Path) -> Path:
    if video_file.suffix.lower() == ".mp4":
        return video_file

    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required to export MP4")

    export_dir = video_file.parent / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    output = export_dir / f"{video_file.stem}.mp4"
    if output.exists() and output.stat().st_mtime >= video_file.stat().st_mtime:
        return output

    temp_output = output.with_suffix(".tmp.mp4")
    if temp_output.exists():
        temp_output.unlink()
    result = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(video_file),
            "-map",
            "0:v:0",
            "-map",
            "0:a?",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(temp_output),
        ],
        capture_output=True,
        text=True,
        timeout=300,
    )
    if result.returncode != 0:
        if temp_output.exists():
            temp_output.unlink()
        detail = (result.stderr or result.stdout or "MP4 export failed").strip()
        raise RuntimeError(detail.splitlines()[-1])
    temp_output.replace(output)
    return output


def _run_test_recording(
    engine: DvrEngine,
    recordings_dir: Path,
    *,
    source_id: str | None = None,
    duration_seconds: int = 10,
) -> dict[str, Any]:
    if duration_seconds < 3 or duration_seconds > 30:
        raise ValueError("Test recording duration must be between 3 and 30 seconds")

    source = _select_test_recording_source(engine, source_id)
    ffmpeg = find_ffmpeg()
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required to run a test recording")

    recordings_dir.mkdir(parents=True, exist_ok=True)
    source_name = str(getattr(source, "name", None) or getattr(source, "source_id", "camera"))
    started = time.strftime("%Y-%m-%d_%H-%M-%S")
    output = recordings_dir / f"Test_{_safe_filename_part(source_name)}_{started}.mkv"
    command = _test_recording_command(ffmpeg, source, output, duration_seconds)
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=duration_seconds + 20,
    )
    if result.returncode != 0:
        if output.exists():
            output.unlink()
        detail = (result.stderr or result.stdout or "Test recording failed").strip()
        raise RuntimeError(friendly_probe_error(detail))
    if not output.exists() or output.stat().st_size == 0:
        raise RuntimeError("Test recording did not create a playable video file")

    probe = probe_stream(str(output), timeout_seconds=15)
    if not probe.ok:
        raise RuntimeError(probe.error or "Test recording file has no readable video stream")

    return {
        "ok": True,
        "file": output.name,
        "source_id": str(getattr(source, "source_id", "")),
        "source_name": source_name,
        "duration_seconds": duration_seconds,
        "size_bytes": output.stat().st_size,
        "codec_name": probe.codec_name,
        "width": probe.width,
        "height": probe.height,
    }


def _select_test_recording_source(engine: DvrEngine, source_id: str | None):
    candidates = []
    for source in engine.refresh_sources():
        current_source_id = str(getattr(source, "source_id", ""))
        if source_id and current_source_id != source_id:
            continue
        if bool(getattr(source, "online", False)) and getattr(source, "stream", None):
            candidates.append(source)
    if not candidates:
        if source_id:
            raise RuntimeError("Selected camera is not online or has no stream")
        raise RuntimeError("No online camera is available for a test recording")
    return candidates[0]


def _test_recording_command(
    ffmpeg: str,
    source,
    output: Path,
    duration_seconds: int,
) -> list[str]:
    source_type = str(getattr(source, "source_type", "rtsp") or "rtsp").lower()
    stream = str(getattr(source, "stream", "") or "")
    input_args: list[str] = []
    if source_type == "mock":
        input_args = ["-re", "-stream_loop", "-1"]
    elif source_type == "rtsp":
        input_args = [
            "-rtsp_transport",
            "tcp",
            "-fflags",
            "+genpts+discardcorrupt",
            "-use_wallclock_as_timestamps",
            "1",
        ]
    elif source_type == "usb":
        input_args = ["-f", "dshow"] if platform.system().lower() == "windows" else ["-f", "v4l2"]

    stream_args = ["-map", "0:v:0", "-map", "0:a?", "-dn", "-sn"]
    codec_args = ["-c", "copy"]
    if source_type == "usb":
        stream_args = ["-map", "0:v:0", "-dn", "-sn"]
        codec_args = ["-c:v", "libx264", "-preset", "ultrafast", "-an"]

    return [
        ffmpeg,
        "-hide_banner",
        "-loglevel",
        "error",
        *input_args,
        "-i",
        stream,
        "-t",
        str(duration_seconds),
        *stream_args,
        *codec_args,
        "-avoid_negative_ts",
        "make_zero",
        "-y",
        str(output),
    ]


def _safe_filename_part(value: str) -> str:
    cleaned = "".join(char if char.isalnum() or char in "._-" else "_" for char in value.strip())
    cleaned = cleaned.strip("._-")
    return cleaned[:40] or "camera"


def _content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".mp4":
        return "video/mp4"
    if suffix == ".mkv":
        return "video/x-matroska"
    if suffix == ".json":
        return "application/json"
    return "application/octet-stream"


def _active_recordings_dir(engine: DvrEngine, fallback_recordings_dir: Path) -> Path:
    recordings_dir = getattr(engine.recorder, "recordings_dir", None)
    if isinstance(recordings_dir, Path) and recordings_dir.is_absolute():
        return recordings_dir
    return fallback_recordings_dir


def _source_config_payload(config: dict[str, Any], engine: DvrEngine) -> dict[str, Any]:
    return {
        "sources": [_public_source_config(source) for source in config.get("sources", [])],
        "hardware_profile": engine.hardware_profile.to_dict(),
        "recommended_sources": engine.hardware_profile.recommended_sources,
        "recording": bool(engine.recorder.is_recording()),
        "admin_required": False,
    }


def _recording_config_payload(config: dict[str, Any]) -> dict[str, Any]:
    recording = config.get("recording", {})
    return {
        "max_duration_minutes": int(recording.get("max_duration_minutes", 0) or 0),
        "stop_when_free_gb_below": float(
            recording.get("stop_when_free_gb_below", 2.0) or 0
        ),
        "segment_minutes": int(recording.get("segment_minutes", 15) or 15),
        "duration_options": [15, 25, 30, 40, 60, 0],
    }


def _storage_config_payload(
    config: dict[str, Any],
    engine: DvrEngine,
    fallback_recordings_dir: Path,
) -> dict[str, Any]:
    storage = config.get("storage", {})
    preferred_paths = storage.get("preferred_paths", [])
    if not isinstance(preferred_paths, list):
        preferred_paths = []
    return {
        "preferred_path": str(preferred_paths[0]) if preferred_paths else "",
        "preferred_paths": [str(path) for path in preferred_paths],
        "active_recordings_dir": str(_active_recordings_dir(engine, fallback_recordings_dir)),
        "fallback_recordings_dir": str(fallback_recordings_dir),
    }


def _normalize_storage_config(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("storage config must be an object")
    raw_path = str(payload.get("preferred_path", "")).strip()
    return {
        "_notes": "preferred_paths can list external recording folders. First usable path wins. Leave empty to use runtime/recordings.",
        "preferred_paths": [raw_path] if raw_path else [],
    }


def _select_recordings_dir(
    preferred_paths: list[str],
    runtime_dir: Path,
    fallback_recordings_dir: Path,
) -> Path:
    for raw_path in preferred_paths:
        path = Path(str(raw_path))
        candidate = path if path.is_absolute() else runtime_dir / path
        if _is_writable_directory(candidate):
            return candidate
    fallback_recordings_dir.mkdir(parents=True, exist_ok=True)
    return fallback_recordings_dir


def _is_writable_directory(path: Path) -> bool:
    path.mkdir(parents=True, exist_ok=True)
    probe = path / ".ghost_dvr_write_test"
    probe.write_text("ok", encoding="utf-8")
    probe.unlink()
    return True


def _normalize_recording_config(
    payload: dict[str, Any],
    *,
    existing_recording: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("recording config must be an object")

    recording = dict(existing_recording)
    duration = int(payload.get("max_duration_minutes", 0) or 0)
    if duration not in {0, 15, 25, 30, 40, 60}:
        raise ValueError("max_duration_minutes must be 15, 25, 30, 40, 60, or 0")

    free_gb_floor = float(payload.get("stop_when_free_gb_below", 0) or 0)
    if free_gb_floor < 0:
        raise ValueError("stop_when_free_gb_below cannot be negative")

    recording["max_duration_minutes"] = duration
    recording["stop_when_free_gb_below"] = round(free_gb_floor, 2)
    return recording


def _public_source_config(source: dict[str, Any]) -> dict[str, Any]:
    public = {
        "source_id": source.get("source_id"),
        "name": source.get("name", ""),
        "source_type": source.get("source_type", "rtsp"),
        "address": source.get("address", ""),
        "username": source.get("username") or "",
        "password": "",
        "has_password": bool(source.get("password")),
    }
    return public


def _normalize_source_configs(
    sources: list[dict[str, Any]],
    *,
    existing_sources: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not isinstance(sources, list):
        raise ValueError("sources must be a list")
    normalized = [
        _normalize_single_source(source, existing_sources=existing_sources, index=index)
        for index, source in enumerate(sources)
    ]
    return normalized


def _normalize_single_source(
    source: dict[str, Any],
    *,
    existing_sources: list[dict[str, Any]],
    index: int = 0,
) -> dict[str, Any]:
    if not isinstance(source, dict):
        raise ValueError("source must be an object")
    source_id = str(source.get("source_id") or f"source-{uuid.uuid4().hex[:8]}")
    name = str(source.get("name") or f"Camera {index + 1}").strip()
    source_type = str(source.get("source_type") or "rtsp").strip().lower()
    address = str(source.get("address") or "").strip()
    username = str(source.get("username") or "").strip()
    password = str(source.get("password") or "")
    existing = _existing_source(existing_sources, source_id)

    if source_type not in {"mock", "rtsp", "usb"}:
        raise ValueError("source_type must be mock, rtsp, or usb")
    if not address:
        raise ValueError(f"{name} address is required")
    if source_type == "rtsp" and not address.startswith("rtsp://"):
        raise ValueError(f"{name} RTSP address must start with rtsp://")

    if not password and existing and existing.get("password"):
        password = str(existing.get("password") or "")

    normalized: dict[str, Any] = {
        "source_id": source_id,
        "name": name,
        "source_type": source_type,
        "address": address,
    }
    if username:
        normalized["username"] = username
    if password:
        normalized["password"] = password
    return normalized


def _existing_source(
    existing_sources: list[dict[str, Any]],
    source_id: str,
) -> dict[str, Any] | None:
    for source in existing_sources:
        if str(source.get("source_id")) == source_id:
            return source
    return None


def _source_config_for_factory(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_id": source.get("source_id"),
        "name": source.get("name"),
        "source_type": source.get("source_type"),
        "address": source.get("address"),
        "username": source.get("username"),
        "password": source.get("password"),
    }


def _active_preview_source(
    engine: DvrEngine,
    source_id: str | None = None,
) -> dict[str, str] | None:
    for status in engine.refresh_sources():
        stream = getattr(status, "stream", None)
        online = bool(getattr(status, "online", False))
        current_source_id = str(getattr(status, "source_id", "source"))
        if source_id and current_source_id != source_id:
            continue
        if online and stream:
            return {"source_id": current_source_id, "stream": str(stream)}
    return None


def _read_events(path: Path, limit: int = 100) -> list[str]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return lines[-limit:]


def _app_root(config_file: Path | None) -> Path:
    if config_file is not None:
        return config_file.parent.parent.resolve()
    return Path.cwd().resolve()


def _schedule_device_power(action: str, delay_seconds: float = 1.0) -> list[str]:
    command = _device_power_command(action)

    def run_command() -> None:
        subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    timer = threading.Timer(delay_seconds, run_command)
    timer.daemon = True
    timer.start()
    return command


def _device_power_command(action: str) -> list[str]:
    system = platform.system().lower()
    if action not in {"shutdown", "restart"}:
        raise ValueError(f"Unsupported device power action: {action}")

    if system == "windows":
        return ["shutdown", "/s" if action == "shutdown" else "/r", "/t", "5"]
    if system == "linux":
        return ["systemctl", "poweroff" if action == "shutdown" else "reboot"]
    return ["shutdown", "-h" if action == "shutdown" else "-r", "now"]


def _web_page() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Ghost DVR</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Segoe UI, system-ui, sans-serif;
      --page-bg: #f4f6f8;
      --panel-bg: #ffffff;
      --panel-border: #d7dde5;
      --text: #111827;
      --muted: #5b6472;
      --button-bg: #1f2937;
      --button-text: #ffffff;
      --secondary-bg: #ffffff;
      --secondary-text: #1f2937;
      --secondary-hover: #eef2f7;
      --input-bg: #ffffff;
      --input-readonly-bg: #f8fafc;
      --table-border: #e5e9ef;
      --preview-bg: #101820;
      --preview-border: #27313d;
      background: var(--page-bg);
      color: var(--text);
    }
    :root[data-theme="dark"] {
      color-scheme: dark;
      --page-bg: #101317;
      --panel-bg: #181d23;
      --panel-border: #2b3440;
      --text: #f3f6fa;
      --muted: #a8b3c2;
      --button-bg: #e5edf7;
      --button-text: #111827;
      --secondary-bg: #202731;
      --secondary-text: #f3f6fa;
      --secondary-hover: #2a3340;
      --input-bg: #11161c;
      --input-readonly-bg: #151b22;
      --table-border: #2b3440;
      --preview-bg: #05070a;
      --preview-border: #2b3440;
    }
    body {
      margin: 0;
      background: var(--page-bg);
      color: var(--text);
    }
    [hidden] {
      display: none !important;
    }
    .auth-screen {
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
    }
    .auth-card {
      width: min(520px, 100%);
      border: 1px solid var(--panel-border);
      border-radius: 8px;
      background: var(--panel-bg);
      padding: 24px;
    }
    .auth-card h1 {
      margin-bottom: 10px;
    }
    .auth-card label {
      display: block;
      margin: 12px 0;
    }
    .auth-card .actions {
      margin-bottom: 8px;
    }
    main {
      max-width: 980px;
      margin: 0 auto;
      padding: 24px;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 20px;
    }
    h1 {
      font-size: 28px;
      margin: 0;
    }
    .tabs {
      display: flex;
      gap: 8px;
      margin: 0 0 16px;
      border-bottom: 1px solid var(--panel-border);
    }
    .tab-button {
      min-width: 96px;
      min-height: 38px;
      border: 0;
      border-bottom: 3px solid transparent;
      border-radius: 0;
      background: transparent;
      color: var(--muted);
    }
    .tab-button.active {
      border-bottom-color: var(--text);
      color: var(--text);
      font-weight: 650;
    }
    .tab-panel[hidden] {
      display: none;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
    }
    .panel {
      background: var(--panel-bg);
      border: 1px solid var(--panel-border);
      border-radius: 6px;
      padding: 14px;
    }
    .panel h3 {
      margin: 0 0 12px;
      font-size: 18px;
    }
    .label {
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 6px;
    }
    .value {
      font-size: 18px;
      font-weight: 650;
      overflow-wrap: anywhere;
    }
    .preview {
      display: grid;
      min-height: 220px;
      margin: 16px 0;
      place-items: center;
      background: var(--preview-bg);
      color: #e5e7eb;
      border-radius: 6px;
      border: 1px solid var(--preview-border);
      overflow: hidden;
    }
    .preview-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
      margin: 16px 0;
    }
    .preview-card {
      background: var(--panel-bg);
      border: 1px solid var(--panel-border);
      border-radius: 6px;
      overflow: hidden;
    }
    .preview-title {
      padding: 10px 12px;
      border-bottom: 1px solid var(--panel-border);
      font-weight: 650;
    }
    .preview img {
      display: block;
      max-width: 100%;
      width: 100%;
      height: auto;
    }
    button {
      min-width: 148px;
      min-height: 40px;
      border: 1px solid var(--button-bg);
      border-radius: 6px;
      background: var(--button-bg);
      color: var(--button-text);
      font: inherit;
      cursor: pointer;
    }
    button + button {
      margin-left: 8px;
    }
    input, select {
      box-sizing: border-box;
      width: 100%;
      min-height: 36px;
      border: 1px solid var(--panel-border);
      border-radius: 4px;
      padding: 6px 8px;
      font: inherit;
      background: var(--input-bg);
      color: var(--text);
    }
    input[readonly] {
      background: var(--input-readonly-bg);
      color: var(--muted);
    }
    .actions {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 16px 0;
    }
    .actions button {
      min-width: 120px;
    }
    .secondary {
      background: var(--secondary-bg);
      color: var(--secondary-text);
    }
    .danger {
      background: #8a1f1f;
      border-color: #8a1f1f;
    }
    .message {
      min-height: 20px;
      color: var(--muted);
    }
    .warning-message {
      color: #b45309;
      font-weight: 650;
    }
    :root[data-theme="dark"] .warning-message {
      color: #fbbf24;
    }
    pre {
      max-height: 220px;
      overflow: auto;
      background: var(--panel-bg);
      border: 1px solid var(--panel-border);
      border-radius: 6px;
      padding: 12px;
      white-space: pre-wrap;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 16px 0;
      background: var(--panel-bg);
      border: 1px solid var(--panel-border);
      border-radius: 6px;
      overflow: hidden;
    }
    th, td {
      border-bottom: 1px solid var(--table-border);
      padding: 10px;
      text-align: left;
      vertical-align: middle;
    }
    th {
      color: var(--muted);
      font-size: 13px;
      font-weight: 650;
    }
    tr:last-child td {
      border-bottom: 0;
    }
    a.download {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 82px;
      min-height: 36px;
      border: 1px solid var(--button-bg);
      border-radius: 6px;
      background: var(--secondary-bg);
      color: var(--secondary-text);
      font-weight: 650;
      text-decoration: none;
    }
    a.download:hover {
      background: var(--secondary-hover);
    }
    .camera-table {
      table-layout: fixed;
    }
    .camera-table th:nth-child(1) { width: 15%; }
    .camera-table th:nth-child(2) { width: 90px; }
    .camera-table th:nth-child(3) { width: 28%; }
    .camera-table th:nth-child(4) { width: 16%; }
    .camera-table th:nth-child(5) { width: 18%; }
    .camera-table th:nth-child(6) { width: 190px; }
    .row-actions {
      display: flex;
      gap: 8px;
      align-items: center;
      justify-content: flex-start;
    }
    .row-actions button {
      min-width: 82px;
      min-height: 36px;
      margin: 0;
    }
    .discovery-list {
      display: grid;
      gap: 10px;
      margin: 12px 0 0;
    }
    .discovery-item {
      display: grid;
      grid-template-columns: minmax(160px, 1fr) minmax(260px, 2fr) minmax(120px, auto);
      gap: 10px;
      align-items: center;
      padding: 10px;
      border: 1px solid var(--panel-border);
      border-radius: 6px;
      background: var(--input-readonly-bg);
    }
    .discovery-address {
      overflow-wrap: anywhere;
      color: var(--muted);
      font-size: 13px;
    }
    .camera-table td {
      vertical-align: top;
    }
    .settings-row {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      align-items: end;
      margin: 14px 0;
    }
    .settings-row button {
      width: 100%;
    }
    .update-row {
      display: grid;
      grid-template-columns: minmax(140px, 1fr) minmax(140px, 1fr) minmax(160px, auto);
      gap: 12px;
      align-items: end;
      margin: 12px 0;
    }
    .power-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 12px 0;
    }
    .power-row button {
      margin: 0;
    }
    .inline-toggle {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin: 8px 0;
    }
    .inline-toggle input {
      width: auto;
      min-height: auto;
    }
  </style>
</head>
<body>
  <section id="authScreen" class="auth-screen" hidden>
    <div class="auth-card">
      <h1>Ghost DVR</h1>
      <div id="authSetup" hidden>
        <p class="message">Create a local dashboard password, or skip login protection for trusted local-only use.</p>
        <label>
          <span class="label">Dashboard Password</span>
          <input id="setupPassword" type="password" autocomplete="new-password">
        </label>
        <label>
          <span class="label">Confirm Password</span>
          <input id="setupConfirmPassword" type="password" autocomplete="new-password">
        </label>
        <div class="actions">
          <button id="createPasswordButton" type="button">Create Password</button>
          <button id="skipAuthButton" type="button" class="secondary">Skip Login</button>
        </div>
      </div>
      <div id="authLogin" hidden>
        <p class="message">Enter the local dashboard password for this Ghost DVR device.</p>
        <label>
          <span class="label">Dashboard Password</span>
          <input id="loginPassword" type="password" autocomplete="current-password">
        </label>
        <div class="actions">
          <button id="loginButton" type="button">Log In</button>
        </div>
      </div>
      <div id="authMessage" class="message"></div>
    </div>
  </section>
  <main id="appShell" hidden>
    <header>
      <h1>Ghost DVR</h1>
      <div>
        <button id="logoutButton" type="button" class="secondary" hidden>Logout</button>
        <button id="themeToggleButton" type="button" class="secondary">Dark Mode</button>
        <button id="recordButton" type="button">Start Recording</button>
      </div>
    </header>
    <nav class="tabs" aria-label="Dashboard tabs">
      <button class="tab-button active" type="button" data-tab="dashboard">Dashboard</button>
      <button class="tab-button" type="button" data-tab="cameras">Cameras</button>
      <button class="tab-button" type="button" data-tab="recordings">Recordings</button>
      <button class="tab-button" type="button" data-tab="settings">Settings</button>
      <button class="tab-button" type="button" data-tab="status">Status</button>
    </nav>
    <section id="dashboardTab" class="tab-panel">
      <section class="preview-grid" id="previewGrid"></section>
      <section class="grid">
        <div class="panel"><div class="label">Device ID</div><div id="device" class="value">-</div></div>
        <div class="panel"><div class="label">Source</div><div id="source" class="value">-</div></div>
        <div class="panel"><div class="label">Recording</div><div id="recording" class="value">-</div></div>
        <div class="panel"><div class="label">Storage</div><div id="storage" class="value">-</div></div>
        <div class="panel"><div class="label">CPU Load</div><div id="load" class="value">-</div></div>
        <div class="panel"><div class="label">Memory</div><div id="memory" class="value">-</div></div>
        <div class="panel"><div class="label">Temperature</div><div id="temperature" class="value">-</div></div>
        <div class="panel"><div class="label">Uptime</div><div id="uptime" class="value">-</div></div>
      </section>
      <div id="storageWarning" class="message warning-message"></div>
    </section>
    <section id="camerasTab" class="tab-panel" hidden>
        <h2>Cameras</h2>
        <div class="grid">
          <div class="panel"><div class="label">Detected Platform</div><div id="profile" class="value">-</div></div>
          <div class="panel"><div class="label">Recommended Cameras</div><div id="recommendedSources" class="value">-</div></div>
        </div>
        <div id="cameraLimitWarning" class="message warning-message"></div>
        <p class="message">Camera changes apply to this local Ghost DVR dashboard.</p>
        <section class="panel">
          <h3>Camera Discovery</h3>
          <div class="actions">
            <button id="discoverCamerasButton" type="button" class="secondary">Discover Cameras</button>
          </div>
          <div id="discoveryMessage" class="message"></div>
          <div id="discoveryResults" class="discovery-list"></div>
        </section>
        <table class="camera-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Address</th>
              <th>Username</th>
              <th>Password</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id="sourcesConfig">
            <tr><td colspan="6">No cameras loaded</td></tr>
          </tbody>
        </table>
        <div class="actions">
          <button id="addSourceButton" type="button" class="secondary">+ Add Camera</button>
          <button id="saveSourcesButton" type="button">Save Cameras</button>
        </div>
        <div id="configMessage" class="message"></div>
    </section>
    <section id="recordingsTab" class="tab-panel" hidden>
      <h2>Recordings</h2>
      <p class="message">Download or delete completed recordings from the Pi remotely.</p>
      <div id="recordingsMessage" class="message"></div>
      <table>
        <thead>
          <tr>
            <th>Recording</th>
            <th>Source</th>
            <th>Duration</th>
            <th>Size</th>
            <th>Status</th>
            <th>Download MKV</th>
            <th>Download MP4</th>
            <th>Delete</th>
          </tr>
        </thead>
        <tbody id="recordings">
          <tr><td colspan="8">No recordings loaded</td></tr>
        </tbody>
      </table>
    </section>
    <section id="settingsTab" class="tab-panel" hidden>
      <h2>Settings</h2>
      <section class="panel">
        <h3>Storage</h3>
        <div class="settings-row">
          <label>
            <span class="label">Active Recording Folder</span>
            <input id="activeRecordingsDir" type="text" readonly>
          </label>
          <label>
            <span class="label">Preferred Save Folder</span>
            <input id="preferredRecordingsDir" type="text" placeholder="/media/pi/GhostDVR">
          </label>
          <button id="saveStorageConfigButton" type="button">Save Storage</button>
        </div>
        <p class="message">Leave preferred folder blank to use the default runtime recordings folder. Stop recording before changing storage.</p>
        <div id="storageConfigMessage" class="message"></div>
      </section>
      <section class="panel">
        <h3>Recording Limits</h3>
        <div class="settings-row">
          <label>
            <span class="label">Session Duration</span>
            <select id="recordingDuration">
              <option value="15">15 minutes</option>
              <option value="25">25 minutes</option>
              <option value="30">30 minutes</option>
              <option value="40">40 minutes</option>
              <option value="60">1 hour</option>
              <option value="0">Infinite</option>
            </select>
          </label>
          <label>
            <span class="label">Stop When Free Space Hits</span>
            <input id="freeGbFloor" type="number" min="0" step="0.5" placeholder="2">
          </label>
          <button id="saveRecordingConfigButton" type="button">Save Limits</button>
        </div>
        <p class="message">Infinite keeps recording until stopped or until free disk space reaches the GB floor.</p>
        <div id="recordingStorageWarning" class="message warning-message"></div>
        <div id="recordingConfigMessage" class="message"></div>
      </section>
      <section class="panel">
        <h3>Test Recording</h3>
        <p class="message">Create a short test clip to verify the selected camera, save folder, and video stream before field use.</p>
        <div class="settings-row">
          <label>
            <span class="label">Camera</span>
            <select id="testRecordingSource"></select>
          </label>
          <label>
            <span class="label">Duration</span>
            <select id="testRecordingDuration">
              <option value="10">10 seconds</option>
              <option value="15">15 seconds</option>
              <option value="20">20 seconds</option>
            </select>
          </label>
          <button id="testRecordingButton" type="button">Test Recording</button>
        </div>
        <div id="testRecordingMessage" class="message"></div>
      </section>
    </section>
    <section id="statusTab" class="tab-panel" hidden>
      <h2>Status</h2>
      <section class="panel">
        <h3>Updates</h3>
        <div class="update-row">
          <div>
            <div class="label">Version</div>
            <div id="updateVersion" class="value">-</div>
          </div>
          <div>
            <div class="label">Update Status</div>
            <div id="updateStatus" class="value">Checking...</div>
          </div>
          <button id="checkUpdateButton" type="button">Check Updates</button>
        </div>
        <div id="updateMessage" class="message"></div>
      </section>
      <section class="panel">
        <h3>Device Power</h3>
        <label class="inline-toggle">
          <input id="apiAutostartToggle" type="checkbox">
          <span>Start web dashboard on device boot</span>
        </label>
        <div class="power-row">
          <button id="restartDeviceButton" type="button" class="secondary">Restart Device</button>
          <button id="shutdownDeviceButton" type="button" class="danger">Shutdown Device</button>
        </div>
        <div id="powerMessage" class="message"></div>
      </section>
      <section class="panel">
        <h3>Dashboard Login</h3>
        <p id="dashboardLoginStatus" class="message">Checking dashboard login status...</p>
        <div class="settings-row">
          <label>
            <span class="label">New Dashboard Password</span>
            <input id="dashboardPassword" type="password" autocomplete="new-password">
          </label>
          <label>
            <span class="label">Confirm Password</span>
            <input id="dashboardConfirmPassword" type="password" autocomplete="new-password">
          </label>
          <button id="saveDashboardPasswordButton" type="button">Enable Login</button>
        </div>
        <div class="power-row">
          <button id="disableDashboardLoginButton" type="button" class="secondary">Disable Dashboard Login</button>
        </div>
        <div id="dashboardLoginMessage" class="message"></div>
      </section>
      <h2>Status Log</h2>
      <pre id="events"></pre>
    </section>
  </main>
  <script>
    let isRecording = false;
    let sourceConfigs = [];
    let sourceConfigLoaded = false;
    let recordingConfigLoaded = false;
    let storageConfigLoaded = false;
    let refreshTimer = null;
    let previewTimer = null;
    let currentAuthStatus = null;

    async function requestJson(path, options) {
      const response = await fetch(path, options);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }

    function applyTheme(theme) {
      document.documentElement.dataset.theme = theme;
      localStorage.setItem('ghostTheme', theme);
      document.getElementById('themeToggleButton').textContent = theme === 'dark'
        ? 'Light Mode'
        : 'Dark Mode';
    }

    function initTheme() {
      const savedTheme = localStorage.getItem('ghostTheme');
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      applyTheme(savedTheme || (prefersDark ? 'dark' : 'light'));
    }

    function toggleTheme() {
      const current = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
      applyTheme(current === 'dark' ? 'light' : 'dark');
    }

    async function initAuth() {
      try {
        const status = await requestJson('/auth/status');
        renderAuthState(status);
      } catch (error) {
        showAuthMessage(`Auth check failed: ${error.message}`);
      }
    }

    function renderAuthState(status) {
      currentAuthStatus = status;
      renderDashboardLoginStatus(status);
      const authScreen = document.getElementById('authScreen');
      const appShell = document.getElementById('appShell');
      const setup = document.getElementById('authSetup');
      const login = document.getElementById('authLogin');
      document.getElementById('logoutButton').hidden = !status.auth_enabled;

      if (status.setup_required) {
        authScreen.hidden = false;
        appShell.hidden = true;
        setup.hidden = false;
        login.hidden = true;
        return;
      }
      if (status.auth_enabled && !status.authenticated) {
        authScreen.hidden = false;
        appShell.hidden = true;
        setup.hidden = true;
        login.hidden = false;
        return;
      }
      authScreen.hidden = true;
      appShell.hidden = false;
      setup.hidden = true;
      login.hidden = true;
      startDashboard();
    }

    function renderDashboardLoginStatus(status) {
      const statusElement = document.getElementById('dashboardLoginStatus');
      const saveButton = document.getElementById('saveDashboardPasswordButton');
      const disableButton = document.getElementById('disableDashboardLoginButton');
      if (!statusElement || !saveButton || !disableButton) return;
      if (status.setup_required) {
        statusElement.textContent = 'Choose a login option before using the dashboard.';
        saveButton.textContent = 'Enable Login';
        disableButton.hidden = true;
        return;
      }
      if (status.auth_enabled) {
        statusElement.textContent = 'Dashboard login is enabled.';
        saveButton.textContent = 'Update Password';
        disableButton.hidden = false;
        return;
      }
      statusElement.textContent = 'Dashboard login is disabled. Anyone on the local network who can reach this device can open the dashboard.';
      saveButton.textContent = 'Enable Login';
      disableButton.hidden = true;
    }

    async function setupDashboardAuth(action) {
      const body = { action };
      if (action === 'password') {
        body.password = document.getElementById('setupPassword').value;
        body.confirm_password = document.getElementById('setupConfirmPassword').value;
      }
      const status = await requestJson('/auth/setup', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(body)
      });
      showAuthMessage('');
      renderAuthState(status);
    }

    async function loginDashboard() {
      const status = await requestJson('/auth/login', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          password: document.getElementById('loginPassword').value
        })
      });
      showAuthMessage('');
      renderAuthState(status);
    }

    async function logoutDashboard() {
      const status = await requestJson('/auth/logout', { method: 'POST' });
      stopDashboard();
      renderAuthState(status);
    }

    async function saveDashboardPassword() {
      const status = await requestJson('/auth/password', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          password: document.getElementById('dashboardPassword').value,
          confirm_password: document.getElementById('dashboardConfirmPassword').value
        })
      });
      document.getElementById('dashboardPassword').value = '';
      document.getElementById('dashboardConfirmPassword').value = '';
      renderAuthState(status);
      setDashboardLoginMessage(status.auth_enabled ? 'Dashboard login password saved.' : 'Dashboard login updated.');
    }

    async function disableDashboardLogin() {
      if (!confirm('Disable dashboard login? Anyone on this local network who can reach the device IP can open the dashboard.')) {
        return;
      }
      const status = await requestJson('/auth/disable', { method: 'POST' });
      renderAuthState(status);
      setDashboardLoginMessage('Dashboard login disabled.');
    }

    function setDashboardLoginMessage(message) {
      document.getElementById('dashboardLoginMessage').textContent = message;
    }

    function showAuthMessage(message) {
      document.getElementById('authMessage').textContent = message;
    }

    function startDashboard() {
      if (refreshTimer || previewTimer) return;
      refresh();
      refreshPreview();
      refreshTimer = setInterval(refresh, 5000);
      previewTimer = setInterval(refreshPreview, 5000);
    }

    function stopDashboard() {
      if (refreshTimer) clearInterval(refreshTimer);
      if (previewTimer) clearInterval(previewTimer);
      refreshTimer = null;
      previewTimer = null;
    }

    async function refresh() {
      const status = await requestJson('/status');
      const system = await requestJson('/system');
      const auth = await requestJson('/auth/status');
      const updateStatus = await requestJson('/update/status');
      const apiAutostart = await requestJson('/startup/api');
      const sourceConfig = await requestJson('/config/sources');
      const recordingConfig = await requestJson('/config/recording');
      const storageConfig = await requestJson('/config/storage');
      const recordings = await requestJson('/recordings');
      const events = await requestJson('/events');
      const sources = status.sources || [];
      const sourceText = sources.length
        ? sources.map(source => `${source.name} (${source.online ? 'online' : 'offline'})`).join(', ')
        : 'No sources';
      const storage = status.storage || {};

      isRecording = Boolean(status.recording);
      document.getElementById('device').textContent = status.device_id || '-';
      document.getElementById('source').textContent = sourceText;
      document.getElementById('recording').textContent = isRecording ? 'Recording' : 'Idle';
      document.getElementById('recordButton').textContent = isRecording ? 'Stop Recording' : 'Start Recording';
      document.getElementById('storage').textContent = storage.free_gb === undefined
        ? 'Unknown'
        : `${storage.free_gb} GB free of ${storage.total_gb} GB (${storage.free_percent}%)`;
      renderStorageWarnings(storage, recordingConfig);
      document.getElementById('load').textContent = formatLoad(system);
      document.getElementById('memory').textContent = formatMemory(system.memory);
      document.getElementById('temperature').textContent = system.temperature_c === null || system.temperature_c === undefined
        ? 'Unknown'
        : `${system.temperature_c} C`;
      document.getElementById('uptime').textContent = formatUptime(system.uptime_seconds);
      renderUpdateStatus(updateStatus);
      renderDashboardLoginStatus(auth);
      renderApiAutostart(apiAutostart);
      document.getElementById('profile').textContent = sourceConfig.hardware_profile?.name || '-';
      document.getElementById('recommendedSources').textContent = sourceConfig.recommended_sources || '-';
      renderCameraLimitWarning(sourceConfig.sources || [], sourceConfig.recommended_sources, sourceConfig.hardware_profile);
      if (!sourceConfigLoaded) {
        sourceConfigs = sourceConfig.sources || [];
        renderSourceConfig(sourceConfigs);
        renderPreviewSlots(sourceConfigs);
        renderTestRecordingSources(sourceConfigs);
        sourceConfigLoaded = true;
      }
      if (!recordingConfigLoaded) {
        renderRecordingConfig(recordingConfig);
        recordingConfigLoaded = true;
      }
      if (!storageConfigLoaded) {
        renderStorageConfig(storageConfig);
        storageConfigLoaded = true;
      }
      renderRecordings(recordings.recordings || []);
      document.getElementById('events').textContent = (events.events || []).join('\\n');
    }

    function renderSourceConfig(sources) {
      const tbody = document.getElementById('sourcesConfig');
      tbody.replaceChildren();
      if (!sources.length) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 6;
        cell.textContent = 'No cameras configured. Use Discover Cameras or + Add Camera to add the first one.';
        row.appendChild(cell);
        tbody.appendChild(row);
        return;
      }
      sources.forEach((source, index) => {
        const row = document.createElement('tr');
        row.dataset.index = String(index);
        appendInputCell(row, 'name', source.name || '');
        appendSelectCell(row, 'source_type', source.source_type || 'rtsp');
        appendInputCell(row, 'address', source.address || '');
        appendInputCell(row, 'username', source.username || '');
        appendInputCell(row, 'password', '', source.has_password ? 'Saved; leave blank to keep' : '');
        const actions = document.createElement('td');
        const actionGroup = document.createElement('div');
        actionGroup.className = 'row-actions';
        const test = document.createElement('button');
        test.type = 'button';
        test.className = 'secondary';
        test.textContent = 'Test';
        test.addEventListener('click', () => testSource(row));
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'danger';
        remove.textContent = 'Remove';
        remove.addEventListener('click', () => {
          const currentIndex = Number(row.dataset.index);
          sourceConfigs.splice(currentIndex, 1);
          renderSourceConfig(sourceConfigs);
          renderTestRecordingSources(sourceConfigs);
          setConfigMessage('Camera removed from the edit list. Save Cameras to apply.');
        });
        actionGroup.appendChild(test);
        actionGroup.appendChild(remove);
        actions.appendChild(actionGroup);
        row.appendChild(actions);
        tbody.appendChild(row);
      });
    }

    function appendInputCell(row, field, value, placeholder = '') {
      const cell = document.createElement('td');
      const input = document.createElement('input');
      input.dataset.field = field;
      input.value = value;
      input.placeholder = placeholder;
      if (field === 'password') input.type = 'password';
      cell.appendChild(input);
      row.appendChild(cell);
    }

    function appendSelectCell(row, field, value) {
      const cell = document.createElement('td');
      const select = document.createElement('select');
      select.dataset.field = field;
      for (const optionValue of ['rtsp', 'usb', 'mock']) {
        const option = document.createElement('option');
        option.value = optionValue;
        option.textContent = optionValue;
        option.selected = value === optionValue;
        select.appendChild(option);
      }
      cell.appendChild(select);
      row.appendChild(cell);
    }

    function collectSources() {
      return Array.from(document.querySelectorAll('#sourcesConfig tr[data-index]')).map(row => sourceFromRow(row));
    }

    async function saveSources() {
      setConfigMessage('Saving cameras...');
      const response = await requestJson('/config/sources', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ sources: collectSources() })
      });
      sourceConfigs = response.sources || [];
      renderSourceConfig(sourceConfigs);
      renderPreviewSlots(sourceConfigs);
      renderTestRecordingSources(sourceConfigs);
      renderCameraLimitWarning(sourceConfigs, response.recommended_sources, response.hardware_profile);
      sourceConfigLoaded = true;
      setConfigMessage(sourceConfigs.length
        ? 'Camera settings saved. Recording must be stopped before changes are allowed.'
        : 'No cameras are configured. Use Discover Cameras or + Add Camera to add one.'
      );
    }

    async function discoverCameras() {
      setDiscoveryMessage('Searching for ONVIF cameras...');
      const result = await requestJson('/discover/cameras');
      renderDiscoveryResults(result.cameras || []);
    }

    function renderDiscoveryResults(cameras) {
      const results = document.getElementById('discoveryResults');
      results.replaceChildren();
      const newCameras = cameras.filter(camera => !isDiscoveredCameraAlreadyListed(camera));
      if (!newCameras.length) {
        setDiscoveryMessage(cameras.length ? 'No new ONVIF cameras found.' : 'No ONVIF cameras found.');
        return;
      }
      setDiscoveryMessage(`Found ${newCameras.length} new camera(s). Click Add to place one in the edit list.`);
      for (const camera of newCameras) {
        const item = document.createElement('div');
        item.className = 'discovery-item';
        const title = document.createElement('div');
        title.innerHTML = `<strong>${camera.name || 'Camera'}</strong><div class="discovery-address">${camera.host || ''}</div>`;
        const select = document.createElement('select');
        for (const address of camera.rtsp_suggestions || []) {
          const option = document.createElement('option');
          option.value = address;
          option.textContent = address;
          select.appendChild(option);
        }
        const add = document.createElement('button');
        add.type = 'button';
        add.className = 'secondary';
        add.textContent = 'Add to List';
        add.addEventListener('click', () => addDiscoveredCamera(camera, select.value));
        item.appendChild(title);
        item.appendChild(select);
        item.appendChild(add);
        results.appendChild(item);
      }
    }

    function isDiscoveredCameraAlreadyListed(camera) {
      const discoveredHost = String(camera.host || '').toLowerCase();
      const discoveredAddresses = new Set((camera.rtsp_suggestions || []).map(address => normalizeAddress(address)));
      for (const source of collectSources()) {
        const sourceAddress = normalizeAddress(source.address || '');
        const sourceHost = hostFromAddress(source.address || '');
        if (sourceAddress && discoveredAddresses.has(sourceAddress)) return true;
        if (discoveredHost && sourceHost && discoveredHost === sourceHost) return true;
      }
      return false;
    }

    function normalizeAddress(address) {
      return String(address || '').trim().toLowerCase();
    }

    function hostFromAddress(address) {
      try {
        return new URL(String(address || '').trim()).hostname.toLowerCase();
      } catch (error) {
        return '';
      }
    }

    function addDiscoveredCamera(camera, address) {
      sourceConfigs.push({
        source_id: '',
        name: camera.name || `Camera ${sourceConfigs.length + 1}`,
        source_type: 'rtsp',
        address: address || '',
        username: '',
        has_password: false
      });
      renderSourceConfig(sourceConfigs);
      renderTestRecordingSources(sourceConfigs);
      setConfigMessage('Discovered camera added to the edit list. Add username/password if needed, then Save Cameras.');
    }

    function setDiscoveryMessage(message) {
      document.getElementById('discoveryMessage').textContent = message;
    }

    function renderPreviewSlots(sources) {
      const grid = document.getElementById('previewGrid');
      grid.replaceChildren();
      if (!sources.length) {
        const empty = document.createElement('section');
        empty.className = 'preview';
        empty.textContent = 'No cameras configured';
        grid.appendChild(empty);
        return;
      }
      for (const source of sources) {
        const card = document.createElement('section');
        card.className = 'preview-card';
        card.dataset.sourceId = source.source_id || '';
        const title = document.createElement('div');
        title.className = 'preview-title';
        title.textContent = source.name || source.source_id || 'Camera';
        const preview = document.createElement('div');
        preview.className = 'preview';
        const text = document.createElement('span');
        text.className = 'preview-text';
        text.textContent = 'Live Preview';
        preview.appendChild(text);
        card.appendChild(title);
        card.appendChild(preview);
        grid.appendChild(card);
      }
    }

    function renderTestRecordingSources(sources) {
      const select = document.getElementById('testRecordingSource');
      select.replaceChildren();
      if (!sources.length) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = 'No cameras configured';
        select.appendChild(option);
        return;
      }
      for (const source of sources) {
        const option = document.createElement('option');
        option.value = source.source_id || '';
        option.textContent = source.name || source.source_id || 'Camera';
        select.appendChild(option);
      }
    }

    function renderCameraLimitWarning(sources, recommended, profile) {
      const count = (sources || []).length;
      const limit = Number(recommended || 0);
      const name = profile?.name || 'this hardware';
      const message = limit > 0 && count > limit
        ? `${name} is recommended for ${limit} camera(s). ${count} are configured, so recording or preview may be unstable.`
        : '';
      document.getElementById('cameraLimitWarning').textContent = message;
    }

    function renderStorageWarnings(storage, recordingConfig) {
      const warning = storageWarningMessage(storage, recordingConfig);
      document.getElementById('storageWarning').textContent = warning;
      document.getElementById('recordingStorageWarning').textContent = warning;
    }

    function storageWarningMessage(storage, recordingConfig) {
      if (!storage || storage.free_gb === undefined) return '';
      const floor = Number(recordingConfig?.stop_when_free_gb_below ?? 0);
      if (floor > 0 && Number(storage.free_gb) <= floor) {
        return `Storage is at or below the configured ${floor} GB floor. Long or infinite recordings will stop.`;
      }
      if (floor > 0 && Number(storage.free_gb) <= floor + 2) {
        return `Storage is close to the configured ${floor} GB floor.`;
      }
      if (storage.warning) {
        return `Storage is low: ${storage.free_percent}% free.`;
      }
      return '';
    }

    async function testSource(row) {
      setConfigMessage('Testing camera...');
      const source = sourceFromRow(row);
      const result = await requestJson('/config/sources/probe', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(source)
      });
      setConfigMessage(result.ok ? 'Camera test passed.' : `Camera test failed: ${result.error || 'Unknown error'}`);
    }

    async function testRecording() {
      if (isRecording) {
        setTestRecordingMessage('Stop recording before running a test recording.');
        return;
      }
      const sourceId = document.getElementById('testRecordingSource').value;
      if (!sourceId) {
        setTestRecordingMessage('Add and save a camera before running a test recording.');
        return;
      }
      setTestRecordingMessage('Running test recording...');
      const result = await requestJson('/record/test', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          source_id: sourceId,
          duration_seconds: Number(document.getElementById('testRecordingDuration').value)
        })
      });
      setTestRecordingMessage(
        `Test recording passed: ${result.file} (${formatBytes(result.size_bytes)}, ${result.codec_name || 'video'}${result.width && result.height ? `, ${result.width}x${result.height}` : ''}).`
      );
      const recordings = await requestJson('/recordings');
      renderRecordings(recordings.recordings || []);
    }

    function setTestRecordingMessage(message) {
      document.getElementById('testRecordingMessage').textContent = message;
    }

    function sourceFromRow(row) {
      const index = Number(row.dataset.index);
      const existing = sourceConfigs[index] || {};
      const source = { source_id: existing.source_id };
      row.querySelectorAll('input, select').forEach(input => {
        source[input.dataset.field] = input.value;
      });
      return source;
    }

    function setConfigMessage(message) {
      document.getElementById('configMessage').textContent = message;
    }

    function renderRecordings(recordings) {
      const tbody = document.getElementById('recordings');
      tbody.replaceChildren();
      if (!recordings.length) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 8;
        cell.textContent = 'No recordings yet';
        row.appendChild(cell);
        tbody.appendChild(row);
        return;
      }

      for (const recording of recordings.slice().reverse()) {
        const row = document.createElement('tr');
        appendCell(row, recording.video_file || '-');
        appendCell(row, recording.source_name || '-');
        appendCell(row, formatDuration(recording.duration_seconds));
        appendCell(row, formatBytes(recording.size_bytes));
        appendCell(row, recording.status || '-');
        row.appendChild(downloadLinkCell(
          `/recordings/download?file=${encodeURIComponent(recording.video_file)}`,
          'MKV'
        ));
        row.appendChild(downloadLinkCell(
          `/recordings/download-mp4?file=${encodeURIComponent(recording.video_file)}`,
          'MP4'
        ));
        const deleteCell = document.createElement('td');
        const deleteButton = document.createElement('button');
        deleteButton.type = 'button';
        deleteButton.className = 'danger';
        deleteButton.textContent = 'Delete';
        deleteButton.addEventListener('click', () => deleteRecording(recording.video_file));
        deleteCell.appendChild(deleteButton);
        row.appendChild(deleteCell);
        tbody.appendChild(row);
      }
    }

    function downloadLinkCell(href, label) {
      const cell = document.createElement('td');
      const link = document.createElement('a');
      link.className = 'download';
      link.href = href;
      link.textContent = label;
      cell.appendChild(link);
      return cell;
    }

    async function deleteRecording(file) {
      if (!file) return;
      if (!confirm(`Delete ${file}?`)) return;
      setRecordingsMessage('Deleting recording...');
      try {
        const result = await requestJson('/recordings/delete', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ file })
        });
        setRecordingsMessage(`Deleted: ${(result.deleted || []).join(', ')}`);
        const recordings = await requestJson('/recordings');
        renderRecordings(recordings.recordings || []);
      } catch (error) {
        setRecordingsMessage(`Delete failed: ${error.message}`);
      }
    }

    function setRecordingsMessage(message) {
      document.getElementById('recordingsMessage').textContent = message;
    }

    function renderStorageConfig(config) {
      document.getElementById('activeRecordingsDir').value = config.active_recordings_dir || '';
      document.getElementById('preferredRecordingsDir').value = config.preferred_path || '';
    }

    function renderUpdateStatus(status) {
      const version = status.commit && status.commit !== '-'
        ? `${status.version || '-'} (${status.commit})`
        : status.version || '-';
      document.getElementById('updateVersion').textContent = version;
      document.getElementById('updateStatus').textContent = status.update_available
        ? 'Out of date'
        : 'Current';
    }

    async function checkUpdates() {
      setUpdateMessage('Checking for updates...');
      const status = await requestJson('/update/status?force=1');
      renderUpdateStatus(status);
      if (!status.update_available) {
        setUpdateMessage('');
        return;
      }
      if (isRecording) {
        setUpdateMessage('Update found. Stop recording before updating.');
        return;
      }
      if (!confirm('Update found. Update Ghost DVR now? Restart after the update finishes.')) {
        setUpdateMessage('Update available.');
        return;
      }
      await runUpdate();
    }

    async function runUpdate() {
      if (isRecording) {
        setUpdateMessage('Stop recording before updating Ghost DVR.');
        return;
      }
      setUpdateMessage('Updating Ghost DVR...');
      const status = await requestJson('/update/run', { method: 'POST' });
      renderUpdateStatus(status);
      setUpdateMessage(status.message || 'Update finished. Restart Ghost DVR.');
      if ((status.message || '').startsWith('Update applied.')) {
        setTimeout(() => window.location.reload(), 6000);
      }
    }

    function setUpdateMessage(message) {
      document.getElementById('updateMessage').textContent = message;
    }

    function renderApiAutostart(status) {
      const toggle = document.getElementById('apiAutostartToggle');
      toggle.checked = Boolean(status.enabled);
      toggle.disabled = !status.supported;
      if (!status.supported && status.message) {
        setPowerMessage(status.message);
      }
    }

    async function saveApiAutostart(enabled) {
      setPowerMessage(enabled ? 'Enabling API autostart...' : 'Disabling API autostart...');
      const status = await requestJson('/startup/api', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ enabled })
      });
      renderApiAutostart(status);
      const state = status.enabled ? 'enabled' : 'disabled';
      setPowerMessage(`Web dashboard autostart ${state}.`);
    }

    async function requestDevicePower(action) {
      if (isRecording) {
        setPowerMessage(`Stop recording before device ${action}.`);
        return;
      }
      const label = action === 'shutdown' ? 'shut down' : 'restart';
      if (!confirm(`${label.charAt(0).toUpperCase() + label.slice(1)} this device? The web panel will disconnect.`)) {
        return;
      }
      setPowerMessage(`Scheduling device ${action}...`);
      const result = await requestJson(`/device/${action}`, { method: 'POST' });
      setPowerMessage(result.message || `Device ${action} scheduled.`);
    }

    function setPowerMessage(message) {
      document.getElementById('powerMessage').textContent = message;
    }

    async function saveStorageConfig() {
      setStorageConfigMessage('Saving storage settings...');
      const response = await requestJson('/config/storage', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          preferred_path: document.getElementById('preferredRecordingsDir').value
        })
      });
      renderStorageConfig(response);
      storageConfigLoaded = true;
      setStorageConfigMessage('Storage settings saved.');
      const recordings = await requestJson('/recordings');
      renderRecordings(recordings.recordings || []);
    }

    function setStorageConfigMessage(message) {
      document.getElementById('storageConfigMessage').textContent = message;
    }

    function renderRecordingConfig(config) {
      document.getElementById('recordingDuration').value = String(config.max_duration_minutes ?? 0);
      document.getElementById('freeGbFloor').value = String(config.stop_when_free_gb_below ?? 2);
    }

    async function saveRecordingConfig() {
      setRecordingConfigMessage('Saving recording limits...');
      const response = await requestJson('/config/recording', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          max_duration_minutes: Number(document.getElementById('recordingDuration').value),
          stop_when_free_gb_below: Number(document.getElementById('freeGbFloor').value)
        })
      });
      renderRecordingConfig(response);
      recordingConfigLoaded = true;
      setRecordingConfigMessage('Recording limits saved.');
    }

    function setRecordingConfigMessage(message) {
      document.getElementById('recordingConfigMessage').textContent = message;
    }

    function appendCell(row, value) {
      const cell = document.createElement('td');
      cell.textContent = value;
      row.appendChild(cell);
    }

    function formatDuration(seconds) {
      if (seconds === null || seconds === undefined) return '-';
      const minutes = Math.floor(seconds / 60);
      const remaining = seconds % 60;
      return `${minutes}:${String(remaining).padStart(2, '0')}`;
    }

    function formatBytes(bytes) {
      if (bytes === null || bytes === undefined) return '-';
      if (bytes >= 1073741824) return `${(bytes / 1073741824).toFixed(2)} GB`;
      if (bytes >= 1048576) return `${(bytes / 1048576).toFixed(1)} MB`;
      if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
      return `${bytes} B`;
    }

    function formatLoad(system) {
      if (!system.load) return 'Unknown';
      const cores = system.cpu_count ? ` / ${system.cpu_count} cores` : '';
      return `${system.load['1m']} / ${system.load['5m']} / ${system.load['15m']}${cores}`;
    }

    function formatMemory(memory) {
      if (!memory) return 'Unknown';
      return `${memory.used_mb} MB used (${memory.used_percent}%)`;
    }

    function formatUptime(seconds) {
      if (seconds === null || seconds === undefined) return 'Unknown';
      const days = Math.floor(seconds / 86400);
      const hours = Math.floor((seconds % 86400) / 3600);
      const minutes = Math.floor((seconds % 3600) / 60);
      if (days > 0) return `${days}d ${hours}h ${minutes}m`;
      if (hours > 0) return `${hours}h ${minutes}m`;
      return `${minutes}m`;
    }

    async function refreshPreview() {
      for (const card of document.querySelectorAll('.preview-card')) {
        const sourceId = card.dataset.sourceId;
        const preview = card.querySelector('.preview');
        const previewText = card.querySelector('.preview-text');
        try {
          const response = await fetch(`/preview?source_id=${encodeURIComponent(sourceId)}&ts=${Date.now()}`, { cache: 'no-store' });
          if (!response.ok) throw new Error('Preview unavailable');
          const blob = await response.blob();
          const url = URL.createObjectURL(blob);
          let image = card.querySelector('img');
          if (!image) {
            image = document.createElement('img');
            image.alt = 'Live Preview';
            preview.appendChild(image);
          }
          const oldUrl = image.dataset.url;
          image.onload = () => {
            if (oldUrl) URL.revokeObjectURL(oldUrl);
          };
          image.src = url;
          image.dataset.url = url;
          previewText.hidden = true;
        } catch (error) {
          previewText.hidden = false;
        }
      }
    }

    document.getElementById('recordButton').addEventListener('click', async () => {
      const path = isRecording ? '/record/stop' : '/record/start';
      try {
        await requestJson(path, { method: 'POST' });
      } finally {
        await refresh();
      }
    });

    document.getElementById('themeToggleButton').addEventListener('click', toggleTheme);

    document.getElementById('createPasswordButton').addEventListener('click', async () => {
      try {
        await setupDashboardAuth('password');
      } catch (error) {
        showAuthMessage(`Setup failed: ${error.message}`);
      }
    });

    document.getElementById('skipAuthButton').addEventListener('click', async () => {
      if (!confirm('Skip dashboard login? Anyone on this local network who can reach the device IP can open the dashboard.')) {
        return;
      }
      try {
        await setupDashboardAuth('skip');
      } catch (error) {
        showAuthMessage(`Setup failed: ${error.message}`);
      }
    });

    document.getElementById('loginButton').addEventListener('click', async () => {
      try {
        await loginDashboard();
      } catch (error) {
        showAuthMessage(`Login failed: ${error.message}`);
      }
    });

    document.getElementById('loginPassword').addEventListener('keydown', async event => {
      if (event.key !== 'Enter') return;
      try {
        await loginDashboard();
      } catch (error) {
        showAuthMessage(`Login failed: ${error.message}`);
      }
    });

    document.getElementById('logoutButton').addEventListener('click', async () => {
      try {
        await logoutDashboard();
      } catch (error) {
        showAuthMessage(`Logout failed: ${error.message}`);
      }
    });

    document.getElementById('saveDashboardPasswordButton').addEventListener('click', async () => {
      try {
        await saveDashboardPassword();
      } catch (error) {
        setDashboardLoginMessage(`Save failed: ${error.message}`);
      }
    });

    document.getElementById('disableDashboardLoginButton').addEventListener('click', async () => {
      try {
        await disableDashboardLogin();
      } catch (error) {
        setDashboardLoginMessage(`Disable failed: ${error.message}`);
      }
    });

    document.getElementById('checkUpdateButton').addEventListener('click', async () => {
      try {
        await checkUpdates();
      } catch (error) {
        setUpdateMessage(`Update check failed: ${error.message}`);
      }
    });

    document.getElementById('apiAutostartToggle').addEventListener('change', async event => {
      try {
        await saveApiAutostart(event.target.checked);
      } catch (error) {
        event.target.checked = !event.target.checked;
        setPowerMessage(`Autostart change failed: ${error.message}`);
      }
    });

    document.getElementById('restartDeviceButton').addEventListener('click', async () => {
      try {
        await requestDevicePower('restart');
      } catch (error) {
        setPowerMessage(`Restart failed: ${error.message}`);
      }
    });

    document.getElementById('shutdownDeviceButton').addEventListener('click', async () => {
      try {
        await requestDevicePower('shutdown');
      } catch (error) {
        setPowerMessage(`Shutdown failed: ${error.message}`);
      }
    });

    document.getElementById('addSourceButton').addEventListener('click', () => {
      sourceConfigs.push({
        source_id: '',
        name: `Camera ${sourceConfigs.length + 1}`,
        source_type: 'rtsp',
        address: '',
        username: '',
        has_password: false
      });
      renderSourceConfig(sourceConfigs);
      renderTestRecordingSources(sourceConfigs);
    });

    document.getElementById('discoverCamerasButton').addEventListener('click', async () => {
      try {
        await discoverCameras();
      } catch (error) {
        setDiscoveryMessage(`Discovery failed: ${error.message}`);
      }
    });

    document.getElementById('saveSourcesButton').addEventListener('click', async () => {
      try {
        await saveSources();
      } catch (error) {
        setConfigMessage(`Save failed: ${error.message}`);
      }
    });

    document.getElementById('saveStorageConfigButton').addEventListener('click', async () => {
      try {
        await saveStorageConfig();
      } catch (error) {
        setStorageConfigMessage(`Save failed: ${error.message}`);
      }
    });

    document.getElementById('saveRecordingConfigButton').addEventListener('click', async () => {
      try {
        await saveRecordingConfig();
      } catch (error) {
        setRecordingConfigMessage(`Save failed: ${error.message}`);
      }
    });

    document.getElementById('testRecordingButton').addEventListener('click', async () => {
      try {
        await testRecording();
      } catch (error) {
        setTestRecordingMessage(`Test recording failed: ${error.message}`);
      }
    });

    document.querySelectorAll('.tab-button').forEach(button => {
      button.addEventListener('click', () => {
        const tab = button.dataset.tab;
        document.querySelectorAll('.tab-button').forEach(item => {
          item.classList.toggle('active', item === button);
        });
        document.getElementById('dashboardTab').hidden = tab !== 'dashboard';
        document.getElementById('camerasTab').hidden = tab !== 'cameras';
        document.getElementById('recordingsTab').hidden = tab !== 'recordings';
        document.getElementById('settingsTab').hidden = tab !== 'settings';
        document.getElementById('statusTab').hidden = tab !== 'status';
      });
    });

    initTheme();
    initAuth();
  </script>
</body>
</html>
"""
