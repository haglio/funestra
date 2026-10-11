"""The order Genau browses its flicks in, and where it is in that order."""
from __future__ import annotations

from pathlib import Path

from .renamed import answers_to_old_names

__all__ = [
    "FlickSequenceController",
]

def _index_of(flicks: list[Path], wanted: Path | None) -> int | None:
    """Where *wanted* sits in *flicks*, or None for "not among them".

    Compared case-insensitively: the path comes back through a status file
    another process wrote, and Windows hands the same file back in either case.
    """
    if wanted is None:
        return None
    key = str(wanted).lower()
    for index, flick in enumerate(flicks):
        if str(flick).lower() == key:
            return index
    return None


@answers_to_old_names({"clips": "flicks"})
class FlickSequenceController:
    def __init__(self, flicks: list[Path], *, start_at: Path | None = None):
        """*start_at* is the flick to open on — where a reopened session picks up,
        in whatever order *flicks* were scanned in.  A flick that is no longer in
        it (deleted, or condemned as weird since) simply is not found, and the
        scan order stands from its top.
        """
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
        """Browse a freshly scanned list, from its top or from *holding* where
        it is among them.

        A reorder takes it from the top: it is asked for to see what the new
        order puts first — the arrivals, under Latest — and holding position
        would apply the order only *after* the flick that is up, so those
        arrivals would never come round.

        Refuses an empty list for the same reason building one does: Genau has to
        keep something on screen.
        """
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
            self._index += 1
            self._flicks.insert(self._index, flick)
        return self.current_path

    def step(self, delta: int) -> Path:
        self._index = (self._index + delta) % len(self._flicks)
        return self.current_path

    def remove_current(self) -> Path | None:
        """Remove the current flick and return whichever one takes its place.

        Returns None — and keeps the flick — when it is the only one left,
        since a sequence with nothing in it has no frame to show.
        """
        if len(self._flicks) <= 1:
            return None
        del self._flicks[self._index]
        self._index %= len(self._flicks)
        return self.current_path

    def nearby_candidates(self) -> list[Path]:
        if len(self._flicks) <= 1:
            return []
        return [self._flicks[(self._index + delta) % len(self._flicks)] for delta in (1, -1)]
