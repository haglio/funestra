from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol

from app_support.file_channel import write_whole

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
        self._path = path
        self._seen: tuple[int, int] | None = None

    def changed(self) -> list[list[Path]] | None:
        try:
            stat = self._path.stat()
        except OSError:
            seen = None
        else:
            seen = (stat.st_mtime_ns, stat.st_size)
        if seen == self._seen:
            return None
        self._seen = seen
        return [] if seen is None else read_radio(self._path)


class Radio:
    def __init__(self, open_station: Callable[[list[Path]], Station | None], *,
                 dealt_in: RadioFile | None = None, together: bool = False) -> None:
        self._open_station = open_station
        self._dealt_in = dealt_in
        self._together = together
        self._dealt: list[list[Path]] = []
        self._stations: list[Station] = []
        self._tuned = -1
        self._on_an_image = False

    def take(self, stations: list[list[Path]]) -> None:
        self.close()
        self._dealt = stations
        self._tuned = -1

    def close(self) -> None:
        for station in self._stations:
            station.close()
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
        if self._stations or not self._dealt:
            return
        opened: list[Station | None] = []
        try:
            opened.extend(self._open_station(videos) for videos in self._dealt)
        except Exception:
            logger.exception("A radio station would not open, so this radio stays off")
            self._dealt = []
            opened.append(None)
        if None in opened:
            for station in opened:
                if station is not None:
                    station.close()
            return
        self._stations = opened
