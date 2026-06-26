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
                self.assertEqual(_request("GET", port, "/sources")[0]["name"], "source-1")
                self.assertEqual(
                    _request("GET", port, "/events")["events"],
                    ["one", "two"],
                )
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_config_sources_endpoint_redacts_password_and_reports_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _api_config()
            server = GhostDvrApiServer(
                engine=FakeApiEngine(),
                events_log=Path(temp_dir) / "events.log",
                config=config,
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                response = _request("GET", port, "/config/sources")

                self.assertEqual(response["sources"][0]["password"], "")
                self.assertTrue(response["sources"][0]["has_password"])
                self.assertEqual(response["hardware_profile"]["name"], "Test Profile")
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_config_sources_save_requires_admin_token(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_file = Path(temp_dir) / "config.json"
            server = GhostDvrApiServer(
                engine=FakeApiEngine(),
                events_log=Path(temp_dir) / "events.log",
                config=_api_config(),
                config_file=config_file,
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                response = _request(
                    "POST",
                    port,
                    "/config/sources",
                    body={"sources": []},
                )

                self.assertEqual(response["error"], "Unauthorized")
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_config_sources_save_updates_config_and_preserves_blank_password(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _api_config()
            config_file = Path(temp_dir) / "config.json"
            engine = FakeApiEngine()
            server = GhostDvrApiServer(
                engine=engine,
                events_log=Path(temp_dir) / "events.log",
                config=config,
                config_file=config_file,
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                response = _request(
                    "POST",
                    port,
                    "/config/sources",
                    headers={"X-Ghost-Admin-Token": "test-token"},
                    body={
                        "sources": [
                            {
                                "source_id": "source-1",
                                "name": "Updated",
                                "source_type": "rtsp",
                                "address": "rtsp://example.test/updated",
                                "username": "camera-user",
                                "password": "",
                            }
                        ]
                    },
                )

                self.assertEqual(response["sources"][0]["name"], "Updated")
                self.assertEqual(config["sources"][0]["password"], "camera-pass")
                self.assertEqual(engine.replaced_sources[0]["name"], "Updated")
                self.assertTrue(config_file.exists())
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_config_sources_save_accepts_usb_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = _api_config()
            config_file = Path(temp_dir) / "config.json"
            engine = FakeApiEngine()
            server = GhostDvrApiServer(
                engine=engine,
                events_log=Path(temp_dir) / "events.log",
                config=config,
                config_file=config_file,
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                response = _request(
                    "POST",
                    port,
                    "/config/sources",
                    headers={"X-Ghost-Admin-Token": "test-token"},
                    body={
                        "sources": [
                            {
                                "source_id": "usb-1",
                                "name": "USB Camera",
                                "source_type": "usb",
                                "address": "video=Integrated Camera",
                            }
                        ]
                    },
                )

                self.assertEqual(response["sources"][0]["source_type"], "usb")
                self.assertEqual(engine.replaced_sources[0]["address"], "video=Integrated Camera")
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_system_endpoint_returns_remote_metrics(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            server = GhostDvrApiServer(
                engine=FakeApiEngine(),
                events_log=Path(temp_dir) / "events.log",
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                system = _request("GET", port, "/system")

                self.assertIn("hostname", system)
                self.assertIn("memory", system)
                self.assertIn("uptime_seconds", system)
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
                self.assertEqual(grabber.stream, "rtsp://example.test/source-1")
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_preview_endpoint_uses_requested_source_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            preview_path = Path(temp_dir) / "preview.png"
            preview_path.write_bytes(b"png")
            grabber = FakePreviewGrabber(preview_path)
            server = GhostDvrApiServer(
                engine=FakeApiEngine(source_count=2),
                events_log=Path(temp_dir) / "events.log",
                preview_grabber=grabber,
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                _request_raw("GET", port, "/preview?source_id=source-2")

                self.assertEqual(grabber.source_id, "source-2")
                self.assertEqual(grabber.stream, "rtsp://example.test/source-2")
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

    def test_recordings_endpoint_lists_recording_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recordings_dir = Path(temp_dir) / "recordings"
            recordings_dir.mkdir()
            video = recordings_dir / "2026-06-26_12-00-00_000.mkv"
            video.write_bytes(b"video")
            (recordings_dir / "2026-06-26_12-00-00.json").write_text(
                '{"duration_seconds":5,"source_name":"Camera"}',
                encoding="utf-8",
            )
            server = GhostDvrApiServer(
                engine=FakeApiEngine(),
                events_log=Path(temp_dir) / "events.log",
                recordings_dir=recordings_dir,
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                response = _request("GET", port, "/recordings")

                self.assertEqual(response["recordings"][0]["video_file"], video.name)
                self.assertEqual(response["recordings"][0]["source_name"], "Camera")
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_recordings_download_serves_file_from_recordings_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            recordings_dir = Path(temp_dir) / "recordings"
            recordings_dir.mkdir()
            video = recordings_dir / "clip_000.mkv"
            video.write_bytes(b"video")
            server = GhostDvrApiServer(
                engine=FakeApiEngine(),
                events_log=Path(temp_dir) / "events.log",
                recordings_dir=recordings_dir,
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                body, content_type = _request_raw(
                    "GET",
                    port,
                    "/recordings/download?file=clip_000.mkv",
                )

                self.assertEqual(body, b"video")
                self.assertEqual(content_type, "application/octet-stream")
            finally:
                server.shutdown()
                thread.join(timeout=5)

    def test_recordings_download_blocks_paths_outside_recordings_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            recordings_dir = root / "recordings"
            recordings_dir.mkdir()
            (root / "private.mkv").write_bytes(b"private")
            server = GhostDvrApiServer(
                engine=FakeApiEngine(),
                events_log=root / "events.log",
                recordings_dir=recordings_dir,
                port=0,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.httpd.server_address[1]
            try:
                response = _request(
                    "GET",
                    port,
                    "/recordings/download?file=../private.mkv",
                )

                self.assertEqual(response["error"], "Recording not found")
            finally:
                server.shutdown()
                thread.join(timeout=5)


class FakeApiSource:
    source_type = "rtsp"

    def __init__(self, source_id: str = "source-1", online: bool = True) -> None:
        self.source_id = source_id
        self.name = source_id
        self.stream = f"rtsp://example.test/{source_id}"
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
    def __init__(self, source_online: bool = True, source_count: int = 1) -> None:
        self.started = False
        self.stopped = False
        self.source_online = source_online
        self.source_count = source_count
        self.config = {"sources": []}
        self.recorder = FakeApiRecorder()
        self.hardware_profile = FakeHardwareProfile()
        self.recording_source_validator = FakeSourceValidator()
        self.replaced_sources = []

    def snapshot(self):
        return {
            "device_id": "TEST",
            "recording": self.started and not self.stopped,
            "sources": [
                FakeApiSource(f"source-{index}", self.source_online).to_dict()
                for index in range(1, self.source_count + 1)
            ],
        }

    def refresh_sources(self):
        return [
            FakeApiSource(f"source-{index}", self.source_online)
            for index in range(1, self.source_count + 1)
        ]

    def start_recording(self):
        self.started = True
        return self.snapshot()

    def stop_recording(self):
        self.stopped = True
        return self.snapshot()

    def replace_sources(self, sources):
        self.replaced_sources = sources
        self.config["sources"] = sources


class FakeApiRecorder:
    def is_recording(self):
        return False


class FakeHardwareProfile:
    name = "Test Profile"
    recommended_sources = 2

    def to_dict(self):
        return {
            "name": self.name,
            "recommended_sources": self.recommended_sources,
            "web_ui_enabled": True,
            "playback_enabled": False,
            "advanced_features_enabled": False,
        }


class FakeSourceValidator:
    def validate(self, source):
        source.connect()
        return None


class FakePreviewGrabber:
    def __init__(self, image_path: Path) -> None:
        self.image_path = image_path
        self.stream: str | None = None
        self.source_id: str | None = None

    def grab(self, stream: str, source_id: str = "source") -> PreviewResult:
        self.stream = stream
        self.source_id = source_id
        return PreviewResult(self.image_path)


def _request(method: str, port: int, path: str, headers=None, body=None):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        payload = None if body is None else json.dumps(body)
        request_headers = headers or {}
        if body is not None:
            request_headers = {"Content-Type": "application/json", **request_headers}
        connection.request(method, path, body=payload, headers=request_headers)
        response = connection.getresponse()
        body = response.read().decode("utf-8")
        return json.loads(body)
    finally:
        connection.close()


def _api_config():
    return {
        "web": {"admin_token": "test-token"},
        "sources": [
            {
                "source_id": "source-1",
                "name": "Camera",
                "source_type": "rtsp",
                "address": "rtsp://example.test/stream",
                "username": "camera-user",
                "password": "camera-pass",
            }
        ],
    }


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
