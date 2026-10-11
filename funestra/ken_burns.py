from __future__ import annotations

import math
import random
from dataclasses import dataclass

__all__: list[str] = []

ZOOMED_IN = 1.10


@dataclass(frozen=True)
class View:
    zoom: float = 1.0
    align_x: float = 0.0
    align_y: float = 0.0

    def placement(self) -> tuple[float, float, float]:
        return math.log2(self.zoom), self.align_x, self.align_y


@dataclass(frozen=True)
class Move:
    start: View
    end: View

    def at(self, progress: float) -> View:
        return View(self.start.zoom * (self.end.zoom / self.start.zoom) ** progress,
                    _between(self.start.align_x, self.end.align_x, progress),
                    _between(self.start.align_y, self.end.align_y, progress))


STANDSTILL = Move(View(), View())


def _between(start: float, end: float, progress: float) -> float:
    return start + (end - start) * progress


def zoom_in(align_x: float, align_y: float) -> Move:
    return Move(View(1.0, align_x, align_y), View(ZOOMED_IN, align_x, align_y))


def zoom_out(align_x: float, align_y: float) -> Move:
    return Move(View(ZOOMED_IN, align_x, align_y), View(1.0, align_x, align_y))


def pan(align_x: float, align_y: float) -> Move:
    return Move(View(ZOOMED_IN, align_x, align_y), View(ZOOMED_IN, -align_x, -align_y))


class Moves:
    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.Random()
        self._last = None

    def deal(self) -> Move:
        kind = self._rng.choice([kind for kind in (zoom_in, zoom_out, pan) if kind is not self._last])
        self._last = kind
        return pan(*self._corner()) if kind is pan else kind(*self._spot())

    def from_rest(self) -> Move:
        self._last = zoom_in
        return zoom_in(*self._spot())

    def _spot(self) -> tuple[float, float]:
        return self._rng.uniform(-1.0, 1.0), self._rng.uniform(-1.0, 1.0)

    def _corner(self) -> tuple[float, float]:
        return self._rng.choice((-1.0, 1.0)), self._rng.choice((-1.0, 1.0))


class RoomClock:
    def __init__(self) -> None:
        self._lost_s = 0.0
        self._frozen_at_s: float | None = None

    def read(self, now_s: float) -> float:
        return (now_s if self._frozen_at_s is None else self._frozen_at_s) - self._lost_s

    def freeze(self, now_s: float) -> None:
        if self._frozen_at_s is None:
            self._frozen_at_s = now_s

    def thaw(self, now_s: float) -> None:
        if self._frozen_at_s is not None:
            self._lost_s += now_s - self._frozen_at_s
            self._frozen_at_s = None


class KenBurns:
    def __init__(self, moves: Moves | None = None, *, looping: bool = False) -> None:
        self._moves = moves or Moves()
        self._clock = RoomClock()
        self._move = STANDSTILL
        self._pace_s = 0.0
        self._started_s = 0.0
        self._held_progress = 0.0
        self._looping = looping

    @property
    def pace_s(self) -> float:
        return self._pace_s

    def set_looping(self, looping: bool, now_s: float) -> None:
        self._reach(now_s)
        self._looping = looping

    def set_pace(self, seconds: float, now_s: float) -> None:
        reached = self._reach(now_s)
        if seconds and self._move is STANDSTILL:
            self._move = self._moves.from_rest()
        self._pace_s = seconds
        if seconds:
            self._started_s = self._clock.read(now_s) - reached * seconds
        else:
            self._held_progress = reached

    def new_picture(self, now_s: float) -> None:
        self._move = self._moves.deal() if self._pace_s else STANDSTILL
        self._started_s = self._clock.read(now_s)
        self._held_progress = 0.0

    def set_paused(self, paused: bool, now_s: float) -> None:
        if paused:
            self._clock.freeze(now_s)
        else:
            self._clock.thaw(now_s)

    def view(self, now_s: float) -> View:
        reached = self._reach(now_s)
        return self._move.at(reached)

    def ran_out(self, now_s: float) -> bool:
        return bool(self._pace_s) and self._reach(now_s) >= 1.0

    def _reach(self, now_s: float) -> float:
        if not self._pace_s:
            return self._held_progress
        progress = (self._clock.read(now_s) - self._started_s) / self._pace_s
        if self._looping and progress >= 1.0:
            progress = self._come_round(progress)
        return min(progress, 1.0)

    def _come_round(self, progress: float) -> float:
        rounds = math.floor(progress)
        self._started_s += rounds * self._pace_s
        self._move = self._moves.deal()
        return progress - rounds
