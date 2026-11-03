from __future__ import annotations

from dataclasses import dataclass


@dataclass
class FlickScrub:
    back_half: bool = False
    extreme: float = 0.0
    height: float = 0.0
    started: bool = False


def scrub_flick(state: FlickScrub, height: float, frame_count: int) -> float:
    height = min(1.0, max(0.0, height))
    epsilon = 2.0 / frame_count if frame_count > 0 else 0.0
    if not state.started:
        state.extreme, state.started = height, True
    elif not state.back_half:
        if height >= state.extreme:
            state.extreme = height
        elif height <= state.extreme - epsilon:
            state.back_half, state.extreme = True, height
    elif height <= state.extreme:
        state.extreme = height
    elif height >= state.extreme + epsilon:
        state.back_half, state.extreme = False, height
    state.height = height
    half = state.extreme / 2
    return 1.0 - half if state.back_half else half
