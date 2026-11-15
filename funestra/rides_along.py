from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterable, Mapping
from pathlib import Path

from .funscript import Funscript
from .funscript import load as load_funscript
from .playlist import PlaylistItem

_SCRIPTS_HELD = 8


def _by_path(items: Iterable[PlaylistItem], field: str) -> dict:
    return {item.path: getattr(item, field) for item in items if getattr(item, field)}


def funscripts_of(items: Iterable[PlaylistItem]) -> dict[Path, Path]:
    return _by_path(items, "funscript")


def points_of_interest_of(items: Iterable[PlaylistItem]) -> dict[Path, tuple]:
    return _by_path(items, "points_of_interest")


class RidesAlong:
    def __init__(self, funscripts: Mapping[Path, Path] | None = None,
                 points_of_interest: Mapping[Path, tuple] | None = None) -> None:
        self._funscripts = dict(funscripts or {})
        self._points_of_interest = dict(points_of_interest or {})
        self._read: OrderedDict[Path, Funscript] = OrderedDict()

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
            self._read[path] = load_funscript(path)
            while len(self._read) > _SCRIPTS_HELD:
                self._read.popitem(last=False)
        self._read.move_to_end(path)
        return self._read[path]

    def points(self, video: Path) -> tuple:
        return self._points_of_interest.get(video, ())
