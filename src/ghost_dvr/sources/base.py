from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SourceConfig:
    source_id: str
    name: str
    source_type: str
    address: str
    username: str | None = None
    password: str | None = None
    stream_path: str | None = None


class Source(ABC):
    def __init__(self, config: SourceConfig) -> None:
        self.config = config
        self._online = False

    @abstractmethod
    def connect(self) -> None:
        raise NotImplementedError

    def disconnect(self) -> None:
        self._online = False

    def is_online(self) -> bool:
        return self._online

    @abstractmethod
    def get_stream(self) -> Any:
        raise NotImplementedError

    def get_source_name(self) -> str:
        return self.config.name

    def get_source_type(self) -> str:
        return self.config.source_type

    def get_source_id(self) -> str:
        return self.config.source_id
