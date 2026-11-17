from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from .file_channel import publish_whole
from .modes import MessageLevel, read_mode

__all__: list[str] = []


@dataclass(frozen=True)
class SaidMessage:
    seq: float = 0.0
    level: MessageLevel = MessageLevel.NORMAL
    message: str = ""
    mark: str = ""


class MessageWriter:
    def __init__(self, path: Path | None, *, clock=time.time) -> None:
        self._path = path
        self._clock = clock

    def say(self, message: str, *, level: MessageLevel, mark: str = "") -> None:
        if self._path is None:
            return
        marked = f"mark={mark}\n" if mark else ""
        publish_whole(
            self._path,
            f"seq={self._clock():.3f}\nlevel={level}\nmessage={message}\n{marked}")


def read_message(path: Path) -> SaidMessage:
    try:
        values = dict(
            line.split("=", 1)
            for line in path.read_text(encoding="utf-8").splitlines()
            if "=" in line
        )
        return SaidMessage(float(values.get("seq", "0")),
                           read_mode(MessageLevel, values.get("level", ""), MessageLevel.NORMAL),
                           values.get("message", ""), values.get("mark", ""))
    except (OSError, ValueError):
        return SaidMessage()


class MessageReader:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._seen = read_message(path).seq

    def take_new(self) -> SaidMessage | None:
        said = read_message(self._path)
        if said.seq <= self._seen:
            return None
        self._seen = said.seq
        return said if said.message else None
