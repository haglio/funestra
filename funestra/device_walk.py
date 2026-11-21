from __future__ import annotations

from dataclasses import dataclass

from app_support.osr2_hold import HOLD_MOVE_MS

from .tcode import HANDOFF_MS


@dataclass
class RoomHold:
    held: str | None = None


@dataclass(frozen=True)
class Walk:
    start: float
    began: float
    over_s: float

    @property
    def ends(self) -> float:
        return self.began + self.over_s

    def height_at(self, now: float, toward: float) -> float:
        walked = min(1.0, max(0.0, now - self.began) / self.over_s)
        return self.start + (toward - self.start) * walked


def the_broker_holding(start: float, asked_at: float, hold: str) -> Walk:
    return Walk(start, asked_at, HOLD_MOVE_MS[hold] / 1000)


def the_hand_taking_back(start: float, taken_at: float) -> Walk:
    return Walk(start, taken_at, HANDOFF_MS / 1000)
