from __future__ import annotations

from collections import deque
from collections.abc import Callable
from functools import partial
from typing import NamedTuple

import numpy as np

Answered = Callable[[BaseException | None], None]


class Handed:
    def __init__(self) -> None:
        self.taken = False


class _Picture(NamedTuple):
    x: int
    y: int
    bgra: np.ndarray
    handed: Handed


class OverlayHandOver:
    def __init__(self, *, add: Callable[[int, int, int, np.ndarray, Answered], None],
                 remove: Callable[[int], None]) -> None:
        self._add = add
        self._remove = remove
        self._to_put_up: dict[int, _Picture] = {}
        self._in_mpv: dict[int, _Picture] = {}
        self._answers: deque[tuple[int, _Picture, bool]] = deque()
        self._refused: set[int] = set()

    def put_up(self, ident: int, x: int, y: int, bgra: np.ndarray) -> Handed:
        picture = self._to_put_up[ident] = _Picture(x, y, bgra, Handed())
        self._hand_over_what_waits()
        return picture.handed

    def take_down(self, ident: int) -> None:
        self._to_put_up.pop(ident, None)
        self._refused.discard(ident)
        self._remove(ident)

    def hand_over(self) -> None:
        self._hand_over_what_waits()
        if self._refused:
            raise MemoryError("mpv had no memory for a copy of the overlay")

    def _hand_over_what_waits(self) -> None:
        while self._answers:
            self._take_the_answer(*self._answers.popleft())
        for ident, picture in self._to_put_up.items():
            if ident not in self._in_mpv:
                self._add(ident, picture.x, picture.y, picture.bgra,
                          partial(self._answered, ident, picture))
                self._in_mpv[ident] = picture

    def _take_the_answer(self, ident: int, picture: _Picture, refused: bool) -> None:
        del self._in_mpv[ident]
        if self._to_put_up.get(ident) is not picture:
            return
        if refused:
            self._refused.add(ident)
            return
        self._refused.discard(ident)
        del self._to_put_up[ident]

    def _answered(self, ident: int, picture: _Picture, error: BaseException | None) -> None:
        picture.handed.taken = error is None
        self._answers.append((ident, picture, error is not None))
