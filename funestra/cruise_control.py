"""What a checkout from before cruise control was taken out still imports.

Human-inspired motion outclassed it, and on 2026-10-13 the family took it out.
A branch from before then still builds a CruiseControlState, ticks it and asks
it whether it is on, so these stay, doing nothing, until no checkout uses them.
Nothing new may.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class _NoWaves:
    waves: tuple = ()

    def __bool__(self) -> bool:
        return False


@dataclass
class CruiseControlState:
    active: bool = False
    stack: _NoWaves = field(default_factory=_NoWaves)
    clock: float = 0.0


def enable_cruise_control(_state: CruiseControlState) -> None:
    pass


def disable_cruise_control(_state: CruiseControlState) -> None:
    return None


def tick_cruise_control(*_args, **_kwargs) -> None:
    pass
