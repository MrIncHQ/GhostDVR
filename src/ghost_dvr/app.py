from __future__ import annotations

import json
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

from ghost_dvr.api import GhostDvrApiServer
from ghost_dvr.config import load_or_create_config, save_config
from ghost_dvr.diagnostics import run_diagnostics
from ghost_dvr.engine import DvrEngine
from ghost_dvr.health import HealthMonitor
from ghost_dvr.identity import load_or_create_identity
from ghost_dvr.logging_setup import configure_event_logger
from ghost_dvr.paths import RuntimePaths
from ghost_dvr.preview import PreviewFrameGrabber
from ghost_dvr.recording_library import (
    cleanup_attention_recordings,
    cleanup_plan,
    recordings_report,
)
from ghost_dvr.recording import FfmpegRecorder
from ghost_dvr.setup_wizard import run_setup_prompt
from ghost_dvr.source_probe import probe_stream
from ghost_dvr.storage import StorageMonitor, StorageSelector
from ghost_dvr.ui.main_window import MainWindow


@dataclass(frozen=True)
class RuntimeContext:
    paths: RuntimePaths
    identity: object
    config: dict[str, object]
    engine: DvrEngine


def create_runtime_context(paths: RuntimePaths | None = None) -> RuntimeContext:
    runtime_paths = paths or RuntimePaths.default()
    runtime_paths.ensure()

    identity = load_or_create_identity(runtime_paths.identity_file)
    config = load_or_create_config(runtime_paths.config_file, identity)
    logger = configure_event_logger(runtime_paths.log_file)
    recording_config = config.get("recording", {})
    storage_config = config.get("storage", {})
    recordings_dir = StorageSelector(
        preferred_paths=[
            runtime_paths.root / path
            if not Path(path).is_absolute()
            else Path(path)
            for path in storage_config.get("preferred_paths", [])
        ],
        fallback_path=runtime_paths.recordings_dir,
    ).select_recordings_dir()
    engine = DvrEngine(
        identity=identity,
        config=config,
        status_file=runtime_paths.status_file,
        logger=logger,
        recorder=FfmpegRecorder(
            recordings_dir,
            segment_minutes=int(recording_config.get("segment_minutes", 15)),
        ),
        storage_monitor=StorageMonitor(
            recordings_dir,
            warning_percent=int(recording_config.get("storage_warning_percent", 10)),
        ),
    )
    return RuntimeContext(
        paths=runtime_paths,
        identity=identity,
        config=config,
        engine=engine,
    )


def bootstrap(paths: RuntimePaths | None = None) -> dict[str, object]:
    context = create_runtime_context(paths)

    context.engine.logger.info("System Boot")
    status = context.engine.snapshot()

    return {
        "identity": context.identity.to_dict(),
        "config": sanitized_config(context.config),
        "status": status,
        "runtime_dir": str(context.paths.root),
    }


def sanitized_config(config: dict[str, object]) -> dict[str, object]:
    sanitized = json.loads(json.dumps(config))
    for source in sanitized.get("sources", []):
        if isinstance(source, dict) and source.get("password"):
            source["password"] = "<redacted>"
    web_config = sanitized.get("web", {})
    if isinstance(web_config, dict) and web_config.get("admin_token"):
        web_config["admin_token"] = "<redacted>"
    return sanitized


def main() -> None:
    if "--diagnostics" in sys.argv:
        print(json.dumps([item.to_dict() for item in run_diagnostics()], indent=2))
        return

    if "--probe-source" in sys.argv:
        context = create_runtime_context()
        source_statuses = context.engine.refresh_sources()
        if not source_statuses or not source_statuses[0].stream:
            print(json.dumps({"ok": False, "error": "No source stream configured"}, indent=2))
            return
        result = probe_stream(source_statuses[0].stream)
        print(json.dumps(result.to_dict(), indent=2))
        return

    if "--recordings-report" in sys.argv:
        paths = RuntimePaths.default()
        print(json.dumps(recordings_report(paths.recordings_dir), indent=2))
        return

    if "--cleanup-recordings" in sys.argv:
        paths = RuntimePaths.default()
        if "--yes" in sys.argv:
            print(json.dumps(cleanup_attention_recordings(paths.recordings_dir), indent=2))
        else:
            print(json.dumps(cleanup_plan(paths.recordings_dir), indent=2))
            print("Preview only. Re-run with --yes to delete listed files.")
        return

    if "--setup" in sys.argv:
        paths = RuntimePaths.default()
        paths.ensure()
        identity = load_or_create_identity(paths.identity_file)
        config = load_or_create_config(paths.config_file, identity)
        config["sources"] = [run_setup_prompt()]
        save_config(paths.config_file, config)
        print(f"Configuration saved to {paths.config_file}")
        return

    if "--ui" in sys.argv:
        context = create_runtime_context()
        context.engine.logger.info("System Boot")
        monitor = HealthMonitor(context.engine)
        monitor.start()
        try:
            MainWindow(
                context.engine,
                config_file=context.paths.config_file,
                default_recordings_dir=context.paths.recordings_dir,
                preview_grabber=PreviewFrameGrabber(context.paths.preview_dir),
            ).run()
        finally:
            monitor.stop()
            context.engine.close()
        return

    if "--api" in sys.argv:
        context = create_runtime_context()
        context.engine.logger.info("System Boot")
        monitor = HealthMonitor(context.engine)
        monitor.start()
        web_config = context.config.get("web", {})
        host = str(web_config.get("host", "0.0.0.0"))
        port = int(web_config.get("port", 8080))
        server = GhostDvrApiServer(
            engine=context.engine,
            events_log=context.paths.log_file,
            config=context.config,
            config_file=context.paths.config_file,
            recordings_dir=context.engine.recorder.recordings_dir,
            preview_grabber=PreviewFrameGrabber(context.paths.preview_dir),
            host=host,
            port=port,
        )
        print(f"Ghost DVR API listening on {host}:{port}")
        if host in ("0.0.0.0", "::"):
            print(f"Open http://{_local_lan_ip()}:{port} from another device on the same network")
        else:
            print(f"Open http://{host}:{port}")
        try:
            server.serve_forever()
        finally:
            monitor.stop()
            context.engine.close()
        return

    result = bootstrap()
    print(json.dumps(result, indent=2))


def _local_lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return "PI_IP_ADDRESS"


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Ghost DVR could not start: {exc}")
        raise SystemExit(1) from exc
