"""A seek mpv can refuse, and one a Funestra owes the file it is opening."""
from __future__ import annotations

import logging
from collections.abc import Callable

__all__: list[str] = []

logger = logging.getLogger(__name__)

GIVE_UP_AFTER = 120


def seek_if_taken(engine, position_ms: float) -> bool:
    try:
        engine.seek_ms(position_ms)
    except SystemError:
        return False
    return True


class OwedSeek:
    def __init__(self) -> None:
        self._position_ms: float | None = None
        self._asked = 0

    def owe(self, position_ms: float | None) -> None:
        self._position_ms = position_ms
        self._asked = 0

    def pay(self, engine, seek: Callable[[float], bool]) -> None:
        if self._position_ms is None or engine.duration_ms <= 0:
            return
        self._asked += 1
        if seek(self._position_ms):
            self._position_ms = None
        elif self._asked >= GIVE_UP_AFTER:
            logger.warning("mpv never took the seek to %.0f ms; playing on from where it is",
                           self._position_ms)
            self._position_ms = None
