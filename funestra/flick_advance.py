from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_INTERVAL_S = 10
MIN_INTERVAL_S = 1
MAX_INTERVAL_S = 60

TRACK_STEPS_PER_S = 20

@dataclass
class FlickAdvanceState:
    locked: bool = True
    interval: int = DEFAULT_INTERVAL_S
    _elapsed: float = 0.0
    _last_tick: float = 0.0
    _flick: Path | None = None
    _awaiting_switch: bool = False

    @property
    def elapsed(self) -> float:
        return round(self._elapsed * TRACK_STEPS_PER_S) / TRACK_STEPS_PER_S


def set_interval(state: FlickAdvanceState, seconds: int) -> None:
    state.interval = max(MIN_INTERVAL_S, min(MAX_INTERVAL_S, int(seconds)))


def adjust_interval(state: FlickAdvanceState, delta: int) -> None:
    set_interval(state, state.interval + delta)


def set_elapsed(state: FlickAdvanceState, seconds: float) -> None:
    if state._awaiting_switch:
        return
    state._elapsed = max(0.0, min(float(state.interval), seconds))


def tick_flick_advance(
    state: FlickAdvanceState,
    now: float,
    *,
    playing: bool,
    on_screen_flick: Path | None,
    step_flick: Callable[[int], None],
) -> None:
    dt = now - state._last_tick
    state._last_tick = now

    if not playing:
        return

    if on_screen_flick is None:
        return

    if on_screen_flick != state._flick:
        state._flick = on_screen_flick
        state._elapsed = 0.0
        state._awaiting_switch = False
        return

    if state._awaiting_switch:
        return

    if dt <= 0 or dt > 1.0:
        return

    state._elapsed += dt
    if state._elapsed < state.interval:
        return
    if state.locked:
        state._elapsed %= state.interval
    else:
        state._awaiting_switch = True
        step_flick(1)
