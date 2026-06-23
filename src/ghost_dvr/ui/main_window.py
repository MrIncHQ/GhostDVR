from __future__ import annotations

import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from tkinter import ttk

from ghost_dvr.engine import DvrEngine
from ghost_dvr.preview import PreviewFrameGrabber
from ghost_dvr.stream_profile import describe_stream_profile


class MainWindow:
    def __init__(
        self,
        engine: DvrEngine,
        *,
        preview_grabber: PreviewFrameGrabber | None = None,
        refresh_ms: int = 1000,
        preview_refresh_ms: int = 5000,
    ) -> None:
        self.engine = engine
        self.preview_grabber = preview_grabber
        self.refresh_ms = refresh_ms
        self.preview_refresh_ms = preview_refresh_ms
        self.root = tk.Tk()
        self.root.title("Ghost DVR")
        self.root.geometry("720x420")
        self.root.minsize(560, 360)

        self.device_var = tk.StringVar()
        self.source_var = tk.StringVar()
        self.recording_var = tk.StringVar()
        self.storage_var = tk.StringVar()
        self.stream_profile_var = tk.StringVar(value="-")
        self.duration_var = tk.StringVar(value="00:00:00")
        self.message_var = tk.StringVar(value="")
        self.recording_button_var = tk.StringVar(value="Start Recording")
        self.is_recording = False
        self.preview_image: tk.PhotoImage | None = None
        self.preview_in_progress = False
        self.last_preview_refresh = 0.0
        self.preview_paused = False

        self._build()

    def _build(self) -> None:
        frame = ttk.Frame(self.root, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Ghost DVR", font=("Segoe UI", 22, "bold")).grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 16),
        )

        rows = [
            ("Device ID", self.device_var),
            ("Source Status", self.source_var),
            ("Recording Status", self.recording_var),
            ("Storage Status", self.storage_var),
            ("Stream Profile", self.stream_profile_var),
            ("Recording Duration", self.duration_var),
            ("System Message", self.message_var),
        ]
        for index, (label, variable) in enumerate(rows, start=1):
            ttk.Label(frame, text=label).grid(row=index, column=0, sticky="w", pady=4)
            ttk.Label(frame, textvariable=variable).grid(
                row=index,
                column=1,
                sticky="ew",
                pady=4,
            )

        self.preview = ttk.Label(
            frame,
            text="Live Preview",
            anchor="center",
            relief="solid",
            padding=32,
        )
        self.preview.grid(row=7, column=0, columnspan=2, sticky="nsew", pady=16)
        frame.rowconfigure(7, weight=1)

        buttons = ttk.Frame(frame)
        buttons.grid(row=8, column=0, columnspan=2, sticky="ew")
        ttk.Button(
            buttons,
            textvariable=self.recording_button_var,
            command=self.toggle_recording,
        ).pack(
            side="left",
        )
        ttk.Button(buttons, text="Exit", command=self.root.destroy).pack(side="right")

    def refresh(self) -> None:
        status = self.engine.snapshot()
        source_names = [
            f"{source['name']} ({'online' if source['online'] else 'offline'})"
            for source in status["sources"]
        ]

        self.device_var.set(status["device_id"])
        self.source_var.set(", ".join(source_names) if source_names else "No sources")
        self.stream_profile_var.set(stream_profile_from_status(status))
        self.recording_var.set("Recording" if status["recording"] else "Idle")
        self.duration_var.set(
            format_duration(int(status.get("recording_duration_seconds", 0)))
        )
        self.is_recording = status["recording"]
        self.recording_button_var.set(
            "Stop Recording" if self.is_recording else "Start Recording"
        )
        storage = status.get("storage", {})
        if storage:
            warning = " WARNING" if storage.get("warning") else ""
            self.storage_var.set(
                f"{storage['free_gb']} GB free of {storage['total_gb']} GB"
                f" ({storage['free_percent']}%){warning}"
            )
        else:
            self.storage_var.set("Unknown")
        self._refresh_preview(status)
        self.root.after(self.refresh_ms, self.refresh)

    def run(self) -> None:
        self.refresh()
        self.root.mainloop()

    def toggle_recording(self) -> None:
        try:
            self.preview_paused = True
            if self.is_recording:
                self.engine.stop_recording()
            else:
                self.engine.start_recording()
            self.message_var.set("")
        except Exception as exc:
            self.message_var.set(str(exc))
            messagebox.showerror("Ghost DVR", str(exc))
        finally:
            self.preview_paused = False
            self.last_preview_refresh = time.monotonic()
            self.refresh()

    def _refresh_preview(self, status: dict[str, object]) -> None:
        if self.preview_grabber is None:
            self.preview.configure(text="Live Preview", image="")
            return
        if self.preview_paused:
            return

        sources = status.get("sources", [])
        if not isinstance(sources, list):
            self.preview.configure(text="Live Preview", image="")
            return

        source = next(
            (
                item
                for item in sources
                if isinstance(item, dict) and item.get("online") and item.get("stream")
            ),
            None,
        )
        if source is None:
            self.preview.configure(text="No preview source", image="")
            return

        now = time.monotonic()
        if self.preview_in_progress:
            return
        if now - self.last_preview_refresh < self.preview_refresh_ms / 1000:
            return

        source_id = str(source.get("source_id", "source"))
        stream = self.engine.stream_for_source(source_id)
        if stream is None:
            self.preview.configure(text="No preview stream", image="")
            return

        self.preview_in_progress = True
        threading.Thread(
            target=self._grab_preview_in_background,
            args=(stream, source_id),
            daemon=True,
            name="ghost-dvr-preview-grab",
        ).start()

    def _grab_preview_in_background(self, stream: str, source_id: str) -> None:
        assert self.preview_grabber is not None
        result = self.preview_grabber.grab(stream, source_id=source_id)
        self.root.after(0, lambda: self._apply_preview_result(result))

    def _apply_preview_result(self, result) -> None:
        self.preview_in_progress = False
        self.last_preview_refresh = time.monotonic()
        if result.error or result.image_path is None:
            self.message_var.set(result.error or "Preview unavailable")
            self.preview.configure(text=result.error or "Preview unavailable", image="")
            return

        self._show_preview_image(result.image_path)

    def _show_preview_image(self, image_path: Path) -> None:
        try:
            self.preview_image = tk.PhotoImage(file=str(image_path))
        except tk.TclError as exc:
            self.preview.configure(text=f"Preview image error: {exc}", image="")
            return
        self.preview.configure(image=self.preview_image, text="")


def format_duration(total_seconds: int) -> str:
    hours, remainder = divmod(max(0, total_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def stream_profile_from_status(status: dict[str, object]) -> str:
    sources = status.get("sources", [])
    if not isinstance(sources, list):
        return "-"
    for source in sources:
        if not isinstance(source, dict):
            continue
        stream = source.get("stream")
        source_type = source.get("source_type")
        if isinstance(stream, str) and isinstance(source_type, str):
            return describe_stream_profile(stream, source_type)
    return "-"
