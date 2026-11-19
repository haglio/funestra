from __future__ import annotations

import os
from pathlib import Path

from app_support.file_channel import read_whole

_Written = tuple[int, int, int]
_NEVER_READ = (-1, -1, -1)


class ReplacedFile:
    # The family's channel files are replaced, never rewritten in place, so each write is a new
    # file with an identity of its own, though Windows can stamp two writes with one time.

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._read_as: _Written | None = _NEVER_READ
        self._found: _Written | None = None

    @property
    def path(self) -> Path:
        return self._path

    def replaced(self) -> bool:
        try:
            found = os.stat(self._path)
        except OSError:
            self._found = None
        else:
            self._found = (found.st_ino, found.st_size, found.st_mtime_ns)
        return self._found != self._read_as

    @property
    def holds_something(self) -> bool:
        return self._found is not None and self._found[1] > 0

    def was_read(self) -> None:
        self._read_as = self._found


class PausedFlag:
    def __init__(self, path: Path) -> None:
        self._file = ReplacedFile(path)
        self._paused = False

    def read(self) -> bool:
        if not self._file.replaced():
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
