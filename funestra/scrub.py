from __future__ import annotations

from collections.abc import Callable


class Scrub:
    def __init__(self, *, seek: Callable[[float], None], hold: Callable[[bool], None]) -> None:
        self._seek = seek
        self._hold = hold
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def press(self, ms: float) -> None:
        if not self._held:
            self._held = True
            self._hold(True)
        self._seek(ms)

    def drag(self, ms: float) -> None:
        if self._held:
            self._seek(ms)

    def release(self) -> None:
        if self._held:
            self._held = False
            self._hold(False)
