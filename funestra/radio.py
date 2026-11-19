from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from functools import partial
from pathlib import Path
from typing import NamedTuple, Protocol

from app_support.file_channel import write_whole

from .off_the_loop import at_once
from .written_file import WrittenFile

logger = logging.getLogger(__name__)


class Station(Protocol):
    def tune(self, level: int | None) -> None: ...

    def set_paused(self, paused: bool) -> None: ...

    def close(self) -> None: ...


class Tuner(Protocol):
    def tick(self, *, image: bool | None, level: int | None, paused: bool) -> None: ...

    def close(self) -> None: ...


READER_HOLD_BUDGET_S = 1.0
_RETRY_SPACING_S = 0.005


def radio_file_for(playlist: Path) -> Path:
    return playlist.with_name(f"{playlist.stem}.radio{playlist.suffix}")


def write_radio(path: Path, stations: Sequence[Sequence[Path]]) -> None:
    write_whole(path, "".join(f"{number}\t{video}\n" for number, videos in enumerate(stations)
                              for video in videos),
                attempts=round(READER_HOLD_BUDGET_S / _RETRY_SPACING_S), delay_s=_RETRY_SPACING_S)


def read_radio(path: Path) -> list[list[Path]]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    stations: dict[int, list[Path]] = {}
    for line in text.splitlines():
        number, _, video = line.partition("\t")
        if number.strip().isdigit() and video.strip():
            stations.setdefault(int(number), []).append(Path(video.strip()))
    return [stations[number] for number in sorted(stations)]


class RadioFile:
    def __init__(self, path: Path) -> None:
        self._file = WrittenFile(path)
        self._handed_on: list[list[Path]] | None = None

    def changed(self) -> list[list[Path]] | None:
        if not self._file.may_have_been_written():
            return None
        there = self._file.holds_something
        stations = read_radio(self._file.path) if there else []
        self._file.was_read()
        if stations == (self._handed_on or []) and (there or self._handed_on is None):
            return None
        self._handed_on = stations
        return stations


class _Opened(NamedTuple):
    stations: list[Station] | None
    will_never_open: bool = False


def _open_every_station(open_station: Callable[[list[Path]], Station | None],
                        dealt: list[list[Path]]) -> _Opened:
    opened: list[Station | None] = []
    will_never_open = False
    try:
        opened.extend(open_station(videos) for videos in dealt)
    except Exception:
        logger.exception("A radio station would not open, so this radio stays off")
        will_never_open = True
        opened.append(None)
    if None not in opened:
        return _Opened(opened)
    for station in opened:
        if station is not None:
            station.close()
    return _Opened(None, will_never_open)


class Radio:
    def __init__(self, open_station: Callable[[list[Path]], Station | None], *,
                 dealt_in: RadioFile | None = None, together: bool = False,
                 behind: Callable = at_once) -> None:
        self._open_station = open_station
        self._dealt_in = dealt_in
        self._together = together
        self._behind = behind
        self._dealt: list[list[Path]] = []
        self._opening: list[list[Path]] | None = None
        self._stations: list[Station] = []
        self._tuned = -1
        self._on_an_image = False

    def take(self, stations: list[list[Path]]) -> None:
        self.close()
        self._dealt = stations
        self._tuned = -1

    def close(self) -> None:
        for station in self._stations:
            self._behind(station.close)
        self._stations, self._dealt = [], []

    def tick(self, *, image: bool | None, level: int | None, paused: bool) -> None:
        dealt = None if self._dealt_in is None else self._dealt_in.changed()
        if dealt is not None:
            self.take(dealt)
        self._open_what_was_dealt()
        if image is not None:
            arriving = image and not self._on_an_image
            self._on_an_image = image
            if self._stations and (arriving or (image and self._tuned < 0)):
                self._tuned = (self._tuned + 1) % len(self._stations)
        for index, station in enumerate(self._stations):
            station.set_paused(paused)
            heard = self._together or index == self._tuned
            station.tune(level if self._on_an_image and heard else None)

    def _open_what_was_dealt(self) -> None:
        if self._stations or not self._dealt or self._opening is self._dealt:
            return
        dealt = self._opening = self._dealt
        self._behind(partial(_open_every_station, self._open_station, dealt),
                     partial(self._tune_in, dealt))

    def _tune_in(self, dealt: list[list[Path]], opened: _Opened) -> None:
        if self._opening is dealt:
            self._opening = None
        if dealt is not self._dealt:
            for station in opened.stations or []:
                self._behind(station.close)
            return
        if opened.will_never_open:
            self._dealt = []
        if opened.stations is not None:
            self._stations = opened.stations
