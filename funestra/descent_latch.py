from __future__ import annotations

from dataclasses import dataclass

from .osr2_visualizer import DriveHud
from .robot_hand import FULL_INTENSITY

_CROWDED = 16


@dataclass(frozen=True)
class DriveKey:
    center: float
    amplitude: float
    speed: float
    let_go: float | None
    max_intensity: int = FULL_INTENSITY

    @classmethod
    def cut_from(cls, published: DriveHud) -> DriveKey:
        return cls(published.center, published.amplitude,
                   published.speed, published.let_go, published.max_intensity)


@dataclass(frozen=True)
class DescentChoice:
    key: DriveKey
    top: float
    touch: int | None


class DescentLatch:
    def __init__(self) -> None:
        self._choices: dict[int, DescentChoice] = {}

    def choice_for(self, turn_start: int) -> DescentChoice | None:
        return self._choices.get(turn_start)

    def remember(self, turn_start: int, choice: DescentChoice, *,
                 stale_before: int) -> None:
        self._choices[turn_start] = choice
        if len(self._choices) > _CROWDED:
            for stale in [turn for turn in self._choices if turn < stale_before]:
                del self._choices[stale]

    def void_all(self) -> None:
        self._choices.clear()
