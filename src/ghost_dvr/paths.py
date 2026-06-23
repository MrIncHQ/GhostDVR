from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    root: Path

    @classmethod
    def default(cls) -> "RuntimePaths":
        return cls(Path.cwd() / "runtime")

    @property
    def config_file(self) -> Path:
        return self.root / "config.json"

    @property
    def identity_file(self) -> Path:
        return self.root / "identity.json"

    @property
    def log_file(self) -> Path:
        return self.root / "logs" / "events.log"

    @property
    def status_file(self) -> Path:
        return self.root / "status.json"

    @property
    def recordings_dir(self) -> Path:
        return self.root / "recordings"

    @property
    def preview_dir(self) -> Path:
        return self.root / "preview"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
