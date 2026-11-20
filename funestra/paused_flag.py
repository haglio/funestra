from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from app_support.file_channel import read_whole
from app_support.written_file import WrittenFile


class PausedFlag:
    def __init__(self, path: Path, *, now_ns: Callable[[], int] = time.time_ns) -> None:
        self._file = WrittenFile(path, now_ns=now_ns)
        self._paused = False

    def read(self) -> bool:
        if not self._file.may_have_been_written():
            return self._paused
        if not self._file.holds_something:
            self._file.was_read()
            self._paused = False
            return self._paused
        try:
            text = read_whole(self._file.path)
        except OSError:
            return self._paused
        self._file.was_read()
        self._paused = text.replace("\ufeff", "").strip() == "1"
        return self._paused
