from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from ghost_dvr.api import GhostDvrApiServer


class ApiTests(unittest.TestCase):
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


class FakeApiSource:
    def to_dict(self):
        return {
            "source_id": "source-1",
            "name": "Mock",
            "source_type": "mock",
            "online": True,
        }


class FakeApiEngine:
    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    def snapshot(self):
        return {
            "device_id": "TEST",
            "recording": self.started and not self.stopped,
            "sources": [FakeApiSource().to_dict()],
        }

    def refresh_sources(self):
        return [FakeApiSource()]

    def start_recording(self):
        self.started = True
        return self.snapshot()

    def stop_recording(self):
        self.stopped = True
        return self.snapshot()


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


if __name__ == "__main__":
    unittest.main()
