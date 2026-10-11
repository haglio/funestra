from __future__ import annotations

import math

from .robot_hand import travel_cap

__all__: list[str] = []


def share(demand: float, max_intensity: int) -> float:
    return math.sqrt(depth(demand, max_intensity))


def depth(demand: float, max_intensity: int) -> float:
    cap = travel_cap(max_intensity)
    if cap is None or demand <= cap:
        return 1.0
    return cap / demand
