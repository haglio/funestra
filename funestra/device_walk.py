from __future__ import annotations

from dataclasses import dataclass

from .funscript import PARK_SETTLE_MS
from .tcode import HANDOFF_MS

__all__: list[str] = []

BROKER_HOLD_DELAY_MS = 1000


@dataclass
class RoomHold:
    height: float | None = None


@dataclass(frozen=True)
class Walk:
    start: float
    began: float
    wait_s: float
    over_s: float

    def height_at(self, now: float, toward: float) -> float:
        walked = min(1.0, max(0.0, now - self.began - self.wait_s) / self.over_s)
        return self.start + (toward - self.start) * walked


def the_broker_holding(start: float, asked_at: float) -> Walk:
    return Walk(start, asked_at, BROKER_HOLD_DELAY_MS / 1000, PARK_SETTLE_MS / 1000)


def the_hand_taking_back(start: float, taken_at: float) -> Walk:
    return Walk(start, taken_at, 0.0, HANDOFF_MS / 1000)
