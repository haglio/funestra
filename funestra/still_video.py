from __future__ import annotations

from collections.abc import Callable
from typing import NamedTuple

STOOD_STILL_S = 3.0


class StoodStill(NamedTuple):
    seconds: float


class MovesAgain(NamedTuple):
    seconds: float


class StillVideo:
    def __init__(self, *, seconds: float = STOOD_STILL_S) -> None:
        self._seconds = seconds
        self._position: float | None = None
        self._since = 0.0
        self._said = False

    def note(self, *, position_ms: float, now: float,
             should_play: Callable[[], bool]) -> StoodStill | MovesAgain | None:
        moved = position_ms != self._position
        if moved or not should_play():
            heard = MovesAgain(now - self._since) if moved and self._said else None
            self._position, self._since, self._said = position_ms, now, False
            return heard
        stood = now - self._since
        if self._said or stood < self._seconds:
            return None
        self._said = True
        return StoodStill(stood)
