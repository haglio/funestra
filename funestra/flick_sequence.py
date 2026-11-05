from __future__ import annotations

from pathlib import Path

from .up_next import put_up_next


def _index_of(flicks: list[Path], wanted: Path | None) -> int | None:
    if wanted is None:
        return None
    # Windows paths that differ by case alone name one file, and this one comes back from
    # another process.
    key = str(wanted).lower()
    for index, flick in enumerate(flicks):
        if str(flick).lower() == key:
            return index
    return None


class FlickSequenceController:
    def __init__(self, flicks: list[Path], *, start_at: Path | None = None):
        if not flicks:
            raise ValueError("FlickSequenceController requires at least one flick")
        self._flicks = list(flicks)
        self._index = _index_of(self._flicks, start_at) or 0

    @property
    def count(self) -> int:
        return len(self._flicks)

    @property
    def current_number(self) -> int:
        return self._index + 1

    @property
    def current_path(self) -> Path:
        return self._flicks[self._index]

    def take_up(self, flicks: list[Path], *, holding: Path | None = None) -> Path:
        if not flicks:
            raise ValueError("FlickSequenceController requires at least one flick")
        self._flicks = list(flicks)
        self._index = _index_of(self._flicks, holding) or 0
        return self.current_path

    def move_to(self, flick: Path) -> bool:
        index = _index_of(self._flicks, flick)
        if index is None:
            return False
        self._index = index
        return True

    def play(self, flick: Path) -> Path:
        if not self.move_to(flick):
            self._index = put_up_next(self._flicks, self._index, flick, None) + 1
        return self.current_path

    def play_next(self, flick: Path) -> None:
        self._index = put_up_next(self._flicks, self._index, flick, _index_of(self._flicks, flick))

    def step(self, delta: int) -> Path:
        self._index = (self._index + delta) % len(self._flicks)
        return self.current_path

    def remove_current(self) -> Path | None:
        if len(self._flicks) <= 1:
            return None
        del self._flicks[self._index]
        self._index %= len(self._flicks)
        return self.current_path

    def nearby_candidates(self) -> list[Path]:
        if len(self._flicks) <= 1:
            return []
        return [self._flicks[(self._index + delta) % len(self._flicks)] for delta in (1, -1)]
