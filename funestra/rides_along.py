from __future__ import annotations

import os
from collections import OrderedDict
from collections.abc import Callable, Iterable, Mapping
from functools import partial
from pathlib import Path
from typing import NamedTuple

from .funscript import Funscript
from .funscript import load as load_funscript
from .off_the_loop import at_once
from .playlist import PlaylistItem

_SCRIPTS_HELD = 8

_Written = tuple[int, int, int] | None


class _Read(NamedTuple):
    written: _Written
    script: Funscript


def _written(path: Path) -> _Written:
    try:
        found = os.stat(path)
    except OSError:
        return None
    return (found.st_ino, found.st_size, found.st_mtime_ns)


def _read(path: Path) -> _Read:
    return _Read(_written(path), load_funscript(path))


def _by_path(items: Iterable[PlaylistItem], field: str) -> dict:
    return {item.path: getattr(item, field) for item in items if getattr(item, field)}


def funscripts_of(items: Iterable[PlaylistItem]) -> dict[Path, Path]:
    return _by_path(items, "funscript")


def points_of_interest_of(items: Iterable[PlaylistItem]) -> dict[Path, tuple]:
    return _by_path(items, "points_of_interest")


class RidesAlong:
    def __init__(self, funscripts: Mapping[Path, Path] | None = None,
                 points_of_interest: Mapping[Path, tuple] | None = None, *,
                 read_before: RidesAlong | None = None) -> None:
        self._funscripts = dict(funscripts or {})
        self._points_of_interest = dict(points_of_interest or {})
        self._read: OrderedDict[Path, _Read] = OrderedDict()
        self._asked_for: set[Path] = set()
        if read_before is not None:
            self._read.update(read_before.read_and_not_written_since())

    def read_and_not_written_since(self) -> list[tuple[Path, _Read]]:
        return [(path, read) for path, read in self._read.items()
                if _written(path) == read.written]

    @classmethod
    def of(cls, items: Iterable[PlaylistItem]) -> RidesAlong:
        items = list(items)
        return cls(funscripts_of(items), points_of_interest_of(items))

    def take(self, video: Path, funscript: Path | None, points_of_interest: Iterable) -> None:
        if funscript is not None:
            self._funscripts[video] = funscript
        if points_of_interest:
            self._points_of_interest[video] = tuple(points_of_interest)

    def funscript_path(self, video: Path) -> Path | None:
        return self._funscripts.get(video)

    def funscript(self, *videos: Path) -> Funscript | None:
        path = next(filter(None, map(self.funscript_path, videos)), None)
        if path is None:
            return None
        if path not in self._read:
            self._keep(path, _read(path))
        self._read.move_to_end(path)
        return self._read[path].script

    def funscript_once_read(self, video: Path, behind: Callable = at_once) -> Funscript | None:
        path = self.funscript_path(video)
        if path is None:
            return None
        if path not in self._read and path not in self._asked_for:
            self._asked_for.add(path)
            behind(partial(_read, path), partial(self._keep, path))
        read = self._read.get(path)
        return None if read is None else read.script

    def _keep(self, path: Path, read: _Read) -> None:
        self._asked_for.discard(path)
        self._read[path] = read
        while len(self._read) > _SCRIPTS_HELD:
            self._read.popitem(last=False)

    def points(self, video: Path) -> tuple:
        return self._points_of_interest.get(video, ())
