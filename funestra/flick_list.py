from __future__ import annotations

import random
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from pathlib import Path

from .flick_overlay import FlickFrame
from .genau import Genau, Narrow, Opening, a_step_shown_genau_takes
from .main_hud import ModeHud
from .playlist import PlaylistItem, read_playlist, write_playlist
from .runs_here import AddsNothing

RELOAD_FLICKS = "RELOAD_FLICKS"


def flips_file_for(flicks: Path) -> Path:
    return flicks.with_name(f"{flicks.stem}.flipped{flicks.suffix}")


def write_flicks(file: Path, flicks: Sequence[Path], *, flipped: Collection[Path] = ()) -> None:
    write_playlist(flips_file_for(file), [PlaylistItem(flick) for flick in flicks if flick in flipped])
    write_playlist(file, [PlaylistItem(flick) for flick in flicks])


class _FlipsOnTheList:
    def __init__(self) -> None:
        self._flipped: frozenset[Path] = frozenset()

    def take(self, flipped: Iterable[Path]) -> None:
        self._flipped = frozenset(flipped)

    def keeps(self, _flick: Path) -> bool:
        return True

    def is_flipped(self, flick: Path) -> bool:
        return flick in self._flipped

    def keep(self, flick: Path, flipped: bool) -> None:
        self._flipped = self._flipped | {flick} if flipped else self._flipped - {flick}


class FlickList:
    metadata_root = None
    keep_shapes = None
    trash = None
    up_next = None

    def __init__(self, file: Path, *, shuffle: Callable[[list[Path]], None] = random.shuffle) -> None:
        self._file = Path(file)
        self._shuffle = shuffle
        self.flips = _FlipsOnTheList()

    def opening(self, *, recent: bool, shuffled: bool) -> Opening:
        return Opening(self.listed(recent=recent, shuffled=shuffled))

    def listed(self, *, recent: bool, shuffled: bool) -> list[Path]:
        self.flips.take(item.path for item in read_playlist(flips_file_for(self._file)))
        flicks = [item.path for item in read_playlist(self._file)]
        if shuffled and not recent:
            self._shuffle(flicks)
        return flicks

    def name_of(self, flick: Path) -> str:
        return flick.stem

    def apply_command(self, command: str, narrow: Narrow) -> bool:
        verb, _, says = command.partition(" ")
        if verb != RELOAD_FLICKS:
            return False
        narrow(says.strip())
        return True


class _NoFlicksYet(AddsNothing):
    def own_frame(self) -> FlickFrame:
        return FlickFrame(frame=None)


_NO_FLICKS_YET = _NoFlicksYet()


class GenauOnAList:
    def __init__(self, flicks: FlickList, start: Callable[[FlickList], Genau]) -> None:
        self._flicks = flicks
        self._start = start
        self._genau: Genau | _NoFlicksYet = _NO_FLICKS_YET
        self._showing = False
        self._start_once_listed()

    def apply_command(self, command: str) -> bool:
        if self._genau is _NO_FLICKS_YET:
            return (a_step_shown_genau_takes(command, showing=self._showing)
                    or self._flicks.apply_command(command, lambda _says: self._start_once_listed()))
        return self._genau.apply_command(command)

    def tick(self) -> None:
        self._genau.tick()

    def status_fields(self) -> Mapping[str, str]:
        return self._genau.status_fields()

    def top_block(self) -> ModeHud:
        return self._genau.top_block()

    def set_showing(self, showing: bool) -> None:
        self._showing = showing
        self._genau.set_showing(showing)

    def own_frame(self) -> FlickFrame:
        return self._genau.own_frame()

    def close(self) -> None:
        self._genau.close()

    def _start_once_listed(self) -> None:
        if self._flicks.listed(recent=True, shuffled=False):
            self._genau = self._start(self._flicks)
            self._genau.set_showing(self._showing)
