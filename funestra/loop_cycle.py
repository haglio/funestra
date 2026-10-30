"""What every Funestra's loop key steps through."""
from __future__ import annotations

from collections.abc import Callable

OFF = ""
LOCK = "lock"
SEED = "seed"
ACTION = "action"
_STOPS = (OFF, LOCK, SEED, ACTION)
_GROUPS = (SEED, ACTION)


def standing_at(*, loop: str, locked: bool) -> str:
    if loop in _GROUPS:
        return loop
    return LOCK if locked else OFF


def next_stop(standing: str, can_loop: Callable[[str], bool]) -> str:
    after = _STOPS.index(standing) + 1
    ahead = _STOPS[after:] + _STOPS[:after]
    return next(stop for stop in ahead if stop not in _GROUPS or can_loop(stop))
