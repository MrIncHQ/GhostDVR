from __future__ import annotations

import json
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import parse_qs, quote, unquote, urlparse

from ghost_dvr.config import save_config
from ghost_dvr.engine import DvrEngine
from ghost_dvr.preview import PreviewFrameGrabber
from ghost_dvr.recording_library import list_recordings
from ghost_dvr.sources.factory import create_source
from ghost_dvr.sources.base import SourceConfig
from ghost_dvr.system_metrics import system_metrics


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

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed_path = urlparse(self.path)
                if parsed_path.path == "/":
                    self._send_html(_web_page())
                    return
                if parsed_path.path == "/status":
                    self._send_json(engine.snapshot())
                    return
                if parsed_path.path == "/system":
                    self._send_json(system_metrics())
                    return
                if parsed_path.path == "/sources":
                    self._send_json(
                        [source.to_dict() for source in engine.refresh_sources()]
                    )
                    return
                if parsed_path.path == "/config/sources":
                    self._send_json(_source_config_payload(config, engine))
                    return
                if parsed_path.path == "/events":
                    self._send_json({"events": _read_events(events_log)})
                    return
                if parsed_path.path == "/recordings":
                    self._send_json(
                        {"recordings": [item.to_dict() for item in list_recordings(recordings_dir)]}
                    )
                    return
                if parsed_path.path == "/recordings/download":
                    self._send_recording_download(recordings_dir, parsed_path.query)
                    return
                if parsed_path.path == "/preview":
                    self._send_preview(engine, preview_grabber, parsed_path.query)
                    return
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                parsed_path = urlparse(self.path)
                if parsed_path.path == "/record/start":
                    self._handle_engine_action(engine.start_recording)
                    return
                if parsed_path.path == "/record/stop":
                    self._handle_engine_action(engine.stop_recording)
                    return
                if parsed_path.path == "/config/sources":
                    self._handle_source_config_save(engine, config, config_file)
                    return
                if parsed_path.path == "/config/sources/probe":
                    self._handle_source_probe(config)
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

            def _is_authorized(self, config: dict[str, Any]) -> bool:
                expected = str(config.get("web", {}).get("admin_token", ""))
                supplied = self.headers.get("X-Ghost-Admin-Token", "")
                return bool(expected) and supplied == expected

            def _handle_source_config_save(
                self,
                engine: DvrEngine,
                config: dict[str, Any],
                config_file: Path | None,
            ) -> None:
                if not self._is_authorized(config):
                    self._send_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
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
                if not self._is_authorized(config):
                    self._send_json({"error": "Unauthorized"}, HTTPStatus.UNAUTHORIZED)
                    return
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

                body = path.read_bytes()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename*=UTF-8''{quote(path.name)}",
                )
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

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


def _source_config_payload(config: dict[str, Any], engine: DvrEngine) -> dict[str, Any]:
    return {
        "sources": [_public_source_config(source) for source in config.get("sources", [])],
        "hardware_profile": engine.hardware_profile.to_dict(),
        "recommended_sources": engine.hardware_profile.recommended_sources,
        "recording": bool(engine.recorder.is_recording()),
        "admin_required": True,
    }


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
    if not normalized:
        raise ValueError("At least one camera source is required")
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
      background: #f4f6f8;
      color: #111827;
    }
    body {
      margin: 0;
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
      border-bottom: 1px solid #d7dde5;
    }
    .tab-button {
      min-width: 96px;
      min-height: 38px;
      border: 0;
      border-bottom: 3px solid transparent;
      border-radius: 0;
      background: transparent;
      color: #374151;
    }
    .tab-button.active {
      border-bottom-color: #1f2937;
      color: #111827;
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
      background: #ffffff;
      border: 1px solid #d7dde5;
      border-radius: 6px;
      padding: 14px;
    }
    .label {
      color: #5b6472;
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
      background: #101820;
      color: #e5e7eb;
      border-radius: 6px;
      border: 1px solid #27313d;
      overflow: hidden;
    }
    .preview-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
      margin: 16px 0;
    }
    .preview-card {
      background: #ffffff;
      border: 1px solid #d7dde5;
      border-radius: 6px;
      overflow: hidden;
    }
    .preview-title {
      padding: 10px 12px;
      border-bottom: 1px solid #d7dde5;
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
      border: 1px solid #1f2937;
      border-radius: 6px;
      background: #1f2937;
      color: white;
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
      border: 1px solid #cbd5e1;
      border-radius: 4px;
      padding: 6px 8px;
      font: inherit;
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
      background: #ffffff;
      color: #1f2937;
    }
    .danger {
      background: #8a1f1f;
      border-color: #8a1f1f;
    }
    .message {
      min-height: 20px;
      color: #374151;
    }
    pre {
      max-height: 220px;
      overflow: auto;
      background: #ffffff;
      border: 1px solid #d7dde5;
      border-radius: 6px;
      padding: 12px;
      white-space: pre-wrap;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      margin: 16px 0;
      background: #ffffff;
      border: 1px solid #d7dde5;
      border-radius: 6px;
      overflow: hidden;
    }
    th, td {
      border-bottom: 1px solid #e5e9ef;
      padding: 10px;
      text-align: left;
      vertical-align: middle;
    }
    th {
      color: #5b6472;
      font-size: 13px;
      font-weight: 650;
    }
    tr:last-child td {
      border-bottom: 0;
    }
    a.download {
      color: #0f4c81;
      font-weight: 650;
      text-decoration: none;
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
    .camera-table td {
      vertical-align: top;
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>Ghost DVR</h1>
      <div>
        <button id="recordButton" type="button">Start Recording</button>
      </div>
    </header>
    <nav class="tabs" aria-label="Dashboard tabs">
      <button class="tab-button active" type="button" data-tab="dashboard">Dashboard</button>
      <button class="tab-button" type="button" data-tab="cameras">Cameras</button>
      <button class="tab-button" type="button" data-tab="recordings">Recordings</button>
      <button class="tab-button" type="button" data-tab="status">Status</button>
    </nav>
    <section id="dashboardTab" class="tab-panel">
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
      <section class="preview-grid" id="previewGrid"></section>
    </section>
    <section id="camerasTab" class="tab-panel" hidden>
        <h2>Cameras</h2>
        <div class="grid">
          <div class="panel"><div class="label">Detected Platform</div><div id="profile" class="value">-</div></div>
          <div class="panel"><div class="label">Recommended Cameras</div><div id="recommendedSources" class="value">-</div></div>
        </div>
        <p class="message">The admin token unlocks camera changes. Viewing and recording controls do not need it.</p>
        <div class="actions">
          <input id="adminToken" type="password" autocomplete="current-password" placeholder="Admin token from runtime/config.json">
          <button id="rememberTokenButton" type="button" class="secondary">Remember Token</button>
        </div>
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
      <table>
        <thead>
          <tr>
            <th>Recording</th>
            <th>Source</th>
            <th>Duration</th>
            <th>Size</th>
            <th>Status</th>
            <th>Download</th>
          </tr>
        </thead>
        <tbody id="recordings">
          <tr><td colspan="6">No recordings loaded</td></tr>
        </tbody>
      </table>
    </section>
    <section id="statusTab" class="tab-panel" hidden>
      <h2>Status Log</h2>
      <pre id="events"></pre>
    </section>
  </main>
  <script>
    let isRecording = false;
    let sourceConfigs = [];
    let sourceConfigLoaded = false;

    async function requestJson(path, options) {
      const response = await fetch(path, options);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }

    function adminToken() {
      return document.getElementById('adminToken').value || localStorage.getItem('ghostAdminToken') || '';
    }

    async function refresh() {
      const status = await requestJson('/status');
      const system = await requestJson('/system');
      const sourceConfig = await requestJson('/config/sources');
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
      document.getElementById('load').textContent = formatLoad(system);
      document.getElementById('memory').textContent = formatMemory(system.memory);
      document.getElementById('temperature').textContent = system.temperature_c === null || system.temperature_c === undefined
        ? 'Unknown'
        : `${system.temperature_c} C`;
      document.getElementById('uptime').textContent = formatUptime(system.uptime_seconds);
      document.getElementById('profile').textContent = sourceConfig.hardware_profile?.name || '-';
      document.getElementById('recommendedSources').textContent = sourceConfig.recommended_sources || '-';
      if (!sourceConfigLoaded) {
        sourceConfigs = sourceConfig.sources || [];
        renderSourceConfig(sourceConfigs);
        renderPreviewSlots(sourceConfigs);
        sourceConfigLoaded = true;
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
        cell.textContent = 'No cameras configured';
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
          'Content-Type': 'application/json',
          'X-Ghost-Admin-Token': adminToken()
        },
        body: JSON.stringify({ sources: collectSources() })
      });
      sourceConfigs = response.sources || [];
      renderSourceConfig(sourceConfigs);
      renderPreviewSlots(sourceConfigs);
      sourceConfigLoaded = true;
      setConfigMessage('Camera settings saved. Recording must be stopped before changes are allowed.');
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

    async function testSource(row) {
      setConfigMessage('Testing camera...');
      const source = sourceFromRow(row);
      const result = await requestJson('/config/sources/probe', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Ghost-Admin-Token': adminToken()
        },
        body: JSON.stringify(source)
      });
      setConfigMessage(result.ok ? 'Camera test passed.' : `Camera test failed: ${result.error || 'Unknown error'}`);
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
        cell.colSpan = 6;
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
        const downloadCell = document.createElement('td');
        const link = document.createElement('a');
        link.className = 'download';
        link.href = `/recordings/download?file=${encodeURIComponent(recording.video_file)}`;
        link.textContent = 'Download';
        downloadCell.appendChild(link);
        row.appendChild(downloadCell);
        tbody.appendChild(row);
      }
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

    document.getElementById('rememberTokenButton').addEventListener('click', () => {
      localStorage.setItem('ghostAdminToken', document.getElementById('adminToken').value);
      setConfigMessage('Admin token saved in this browser.');
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
    });

    document.getElementById('saveSourcesButton').addEventListener('click', async () => {
      try {
        await saveSources();
      } catch (error) {
        setConfigMessage(`Save failed: ${error.message}`);
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
        document.getElementById('statusTab').hidden = tab !== 'status';
      });
    });

    refresh();
    refreshPreview();
    setInterval(refresh, 5000);
    setInterval(refreshPreview, 5000);
  </script>
</body>
</html>
"""
