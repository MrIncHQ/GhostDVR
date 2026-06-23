from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from ghost_dvr.engine import DvrEngine


class GhostDvrApiServer:
    def __init__(
        self,
        *,
        engine: DvrEngine,
        events_log: Path,
        host: str = "127.0.0.1",
        port: int = 8080,
    ) -> None:
        self.engine = engine
        self.events_log = events_log
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

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/":
                    self._send_html(_web_page())
                    return
                if self.path == "/status":
                    self._send_json(engine.snapshot())
                    return
                if self.path == "/sources":
                    self._send_json(
                        [source.to_dict() for source in engine.refresh_sources()]
                    )
                    return
                if self.path == "/events":
                    self._send_json({"events": _read_events(events_log)})
                    return
                self._send_json({"error": "Not found"}, HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                if self.path == "/record/start":
                    self._handle_engine_action(engine.start_recording)
                    return
                if self.path == "/record/stop":
                    self._handle_engine_action(engine.stop_recording)
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

        return Handler


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
    pre {
      max-height: 220px;
      overflow: auto;
      background: #ffffff;
      border: 1px solid #d7dde5;
      border-radius: 6px;
      padding: 12px;
      white-space: pre-wrap;
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
    <section class="grid">
      <div class="panel"><div class="label">Device ID</div><div id="device" class="value">-</div></div>
      <div class="panel"><div class="label">Source</div><div id="source" class="value">-</div></div>
      <div class="panel"><div class="label">Recording</div><div id="recording" class="value">-</div></div>
      <div class="panel"><div class="label">Storage</div><div id="storage" class="value">-</div></div>
    </section>
    <section class="preview" id="preview">Live Preview</section>
    <pre id="events"></pre>
  </main>
  <script>
    let isRecording = false;

    async function requestJson(path, options) {
      const response = await fetch(path, options);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || response.statusText);
      return data;
    }

    async function refresh() {
      const status = await requestJson('/status');
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
      document.getElementById('events').textContent = (events.events || []).join('\\n');
    }

    document.getElementById('recordButton').addEventListener('click', async () => {
      const path = isRecording ? '/record/stop' : '/record/start';
      try {
        await requestJson(path, { method: 'POST' });
      } finally {
        await refresh();
      }
    });

    refresh();
    setInterval(refresh, 5000);
  </script>
</body>
</html>
"""
