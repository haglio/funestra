"""How long a flick holds the screen, and the lock that keeps it there.

Genau's flicks are fractions of a second long, so playing them the way a playlist
plays videos would be a strobe: every flick has to repeat for a while before the
next one arrives.  That "while" is the interval here.  The lock is the same lock
every Funestra in this family has — repeat-one on what is on screen — and it is on
by default, because a held flick is what Genau has always opened on.  The count
runs either way; the lock only decides what happens when it reaches the end.

There is no separate "auto advance" switch: advancing is simply what an unlocked
Genau does, and the interval is how fast.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

__all__ = [
    "FlickAdvanceState",
]

if TYPE_CHECKING:
    from pathlib import Path

# Seconds a flick holds the screen, and the range the controls move it through.
# One second is already a strobe; a minute is longer than anyone waits for a
# switch they asked to be automatic.
DEFAULT_INTERVAL_S = 10
MIN_INTERVAL_S = 1
MAX_INTERVAL_S = 60

# How many times a second the track at the console's foot moves.  The console
# is repainted whenever its row moves, and the count moves every tick.
TRACK_STEPS_PER_S = 20

@dataclass
class FlickAdvanceState:
    # Locked, the flick on screen comes round again at the end of its interval
    # instead of giving way to the next.
    locked: bool = True
    # Seconds each flick holds the screen while unlocked.
    interval: int = DEFAULT_INTERVAL_S
    _elapsed: float = 0.0
    _last_tick: float = 0.0
    # The flick the current interval is being measured against, and whether we
    # have already asked to move on from it.  Together these make the timer
    # count the flick that is *on screen*, not the one we requested — see
    # tick_flick_advance.
    _flick: Path | None = None
    _awaiting_switch: bool = False

    @property
    def elapsed(self) -> float:
        """Seconds the flick on screen has had of its interval, kept to the step
        the track draws it at."""
        return round(self._elapsed * TRACK_STEPS_PER_S) / TRACK_STEPS_PER_S


def set_interval(state: FlickAdvanceState, seconds: int) -> None:
    """Set the seconds a flick holds the screen, clamped to the usable range."""
    state.interval = max(MIN_INTERVAL_S, min(MAX_INTERVAL_S, int(seconds)))


def adjust_interval(state: FlickAdvanceState, delta: int) -> None:
    set_interval(state, state.interval + delta)


def set_elapsed(state: FlickAdvanceState, seconds: float) -> None:
    """A press along the track: put the flick *seconds* into its interval, unless
    the next flick is already on its way."""
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

    # A paused room is a still one: OmniPause, and the plain space-bar pause,
    # both land here as playing=False, and neither should leave the flick the
    # user walked away from.  The elapsed count simply stops rather than
    # resetting, so resuming finishes the interval it was part-way through.
    if not playing:
        return

    # Measure the interval from the flick that is actually on screen, not from
    # the moment we asked to advance.  Genau can take seconds to decode a flick,
    # so a short interval timed from the request would elapse again and again
    # while the first switch was still loading — each elapse stacking another
    # decode that never got its turn on screen.  Two guards below hold the
    # count until a flick has genuinely arrived.
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
