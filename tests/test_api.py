from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from ghost_dvr.api import GhostDvrApiServer
from ghost_dvr.preview import PreviewResult


class ApiTests(unittest.TestCase):
    def test_default_host_accepts_lan_connections(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = GhostDvrApiServer(
                engine=FakeApiEngine(),
                events_log=Path(temp_dir) / "events.log",
                port=0,
            )
            try:
                self.assertEqual(server.host, "0.0.0.0")
            finally:
                server.httpd.server_close()

    def test_status_sources_and_events_endpoints(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            events_log = Path(temp_dir) / "events.log"
            events_log.write_text("one\ntwo\n", encoding="utf-8")
            server = GhostDvrApiServer(
                engine=FakeApiEngine(),
                events_log=events_log,
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                self.assertIn("Ghost DVR", _request_text("GET", port, "/"))
                self.assertEqual(_request("GET", port, "/status")["device_id"], "TEST")
                self.assertEqual(_request("GET", port, "/sources")[0]["name"], "Mock")
                self.assertEqual(
                    _request("GET", port, "/events")["events"],
                    ["one", "two"],
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_recording_endpoints_delegate_to_engine(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            engine = FakeApiEngine()
            server = GhostDvrApiServer(
                engine=engine,
                events_log=Path(temp_dir) / "events.log",
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                self.assertTrue(_request("POST", port, "/record/start")["recording"])
                self.assertTrue(engine.started)
                self.assertFalse(_request("POST", port, "/record/stop")["recording"])
                self.assertTrue(engine.stopped)
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_preview_endpoint_returns_image_for_online_stream(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.png"
            preview_path.write_bytes(b"png")
            grabber = FakePreviewGrabber(preview_path)
            server = GhostDvrApiServer(
                engine=FakeApiEngine(),
                events_log=Path(temp_dir) / "events.log",
                preview_grabber=grabber,
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                body, content_type = _request_raw("GET", port, "/preview")

                self.assertEqual(body, b"png")
                self.assertEqual(content_type, "image/png")
                self.assertEqual(grabber.stream, "rtsp://example.test/stream")
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_preview_endpoint_reports_when_no_stream_is_online(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = GhostDvrApiServer(
                engine=FakeApiEngine(source_online=False),
                events_log=Path(temp_dir) / "events.log",
                preview_grabber=FakePreviewGrabber(Path(temp_dir) / "preview.png"),
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                response = _request("GET", port, "/preview")

                self.assertEqual(response["error"], "No online source stream available")
            finally:
                server.shutdown()
                thread.join(timeout=5)


class FakeApiSource:
    source_id = "source-1"
    name = "Mock"
    source_type = "rtsp"
    stream = "rtsp://example.test/stream"

    def __init__(self, online: bool = True) -> None:
        self.online = online

    def to_dict(self):
        return {
            "source_id": self.source_id,
            "name": self.name,
            "source_type": self.source_type,
            "online": self.online,
            "stream": self.stream if self.online else None,
        }


class FakeApiEngine:
    def __init__(self, source_online: bool = True) -> None:
        self.started = False
        self.stopped = False
        self.source_online = source_online

    def snapshot(self):
        return {
            "device_id": "TEST",
            "recording": self.started and not self.stopped,
            "sources": [FakeApiSource(self.source_online).to_dict()],
        }

    def refresh_sources(self):
        return [FakeApiSource(self.source_online)]

    def start_recording(self):
        self.started = True
        return self.snapshot()

    def stop_recording(self):
        self.stopped = True
        return self.snapshot()


class FakePreviewGrabber:
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path
        self.stream: str | None = None

    def grab(self, stream: str, source_id: str = "source") -> PreviewResult:
        self.stream = stream
        return PreviewResult(self.image_path)


def _request(method: str, port: int, path: str):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        return json.loads(body)
    finally:
        connection.close()


def _request_text(method: str, port: int, path: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.read().decode("utf-8")
    finally:
        connection.close()


def _request_raw(method: str, port: int, path: str) -> tuple[bytes, str]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        connection.request(method, path)
        response = connection.getresponse()
        return response.read(), response.getheader("Content-Type") or ""
    finally:
        connection.close()


if __name__ == "__main__":
    unittest.main()
