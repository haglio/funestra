from __future__ import annotations

import time
from pathlib import Path

from .file_channel import publish_whole
from .modes import MessageLevel

__all__: list[str] = []


class MessageWriter:
    def __init__(self, path: Path | None, *, clock=time.time) -> None:
        self._path = path
        self._clock = clock

    def say(self, message: str, *, level: MessageLevel) -> None:
        if self._path is None:
            return
        publish_whole(
            self._path,
            f"seq={self._clock():.3f}\nlevel={level}\nmessage={message}\n")
