from __future__ import annotations

import functools
import itertools
import subprocess
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from app_support.pcloud.fetching import Entry
from app_support.pcloud.library import PCloudLibrary, Wish, from_settings

WHOLE_BELOW_BYTES = 25 * 1024 * 1024
LOOKED_AHEAD = 12
LOOKED_BACK = 3
OPENING_S = 20
UNTIMED_OPENING_BYTES = 64 * 1024 * 1024
_LOOK_AHEADS = itertools.count(1)


def opening_spans(start_ms: int | None) -> Callable[[Entry], list[tuple[int, int]]]:
    def spans(entry: Entry) -> list[tuple[int, int]]:
        if entry.size <= WHOLE_BELOW_BYTES:
            return [(0, entry.size)]
        tail = (entry.size - 1, entry.size)
        if not entry.duration_s:
            return [(0, min(entry.size, UNTIMED_OPENING_BYTES)), tail]
        per_second = entry.size / entry.duration_s
        opening = int(per_second * OPENING_S)
        if not start_ms:
            return [(0, min(entry.size, opening)), tail]
        at = int(per_second * start_ms / 1000)
        return [(0, 1), (at, min(entry.size, at + opening)), tail]

    return spans


class LooksAhead(Protocol):
    def see(self, coming: Sequence[tuple[Path, int | None]]) -> None: ...


class _LooksAheadForNothing:
    def see(self, coming: Sequence[tuple[Path, int | None]]) -> None:
        pass


LOOKS_AHEAD_FOR_NOTHING = _LooksAheadForNothing()


class _Prefetches(Protocol):
    def prefetch(self, owner: str, wishes: Sequence[Wish]) -> None: ...


class LookAhead:
    def __init__(self, library: _Prefetches) -> None:
        self._library = library
        self._owner = f"look ahead {next(_LOOK_AHEADS)}"

    def see(self, coming: Sequence[tuple[Path, int | None]]) -> None:
        self._library.prefetch(self._owner, [Wish(path, opening_spans(start_ms)) for path, start_ms in coming])



class _PlaysFromDisk:
    @staticmethod
    def playable(path: Path) -> str:
        return str(path)

    @staticmethod
    def local_copy(path: Path) -> Path:
        return path

    def prefetch(self, owner: str, wishes: Sequence[Wish]) -> None:
        pass


PLAYS_FROM_DISK = _PlaysFromDisk()


def open_the_sign_in_window(*, popen: Callable[..., object] = subprocess.Popen) -> None:
    beside = Path(sys.executable).with_name("pythonw.exe")
    windowless = beside if beside.is_file() else Path(sys.executable)
    popen([str(windowless), "-m", "shared_ui.pcloud_sign_in"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


@functools.cache
def the_library() -> PCloudLibrary | _PlaysFromDisk:
    library = from_settings(when_not_signed_in=open_the_sign_in_window)
    return PLAYS_FROM_DISK if library is None else library.__enter__()


def on_this_disk(path: Path) -> Path:
    return the_library().local_copy(path)
