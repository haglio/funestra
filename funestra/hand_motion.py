from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from . import learned_motion
from .learned_motion import LearnedMotionState
from .robot_hand import RobotHandState, TraceSpan, Waveform, trace_window


class Way(Protocol):
    @property
    def in_play(self) -> bool: ...

    def tick(self, hand: RobotHandState, now: float, *, start_fraction: float) -> None: ...

    def height(self, hand: RobotHandState, phase: float, lead_s: float) -> float: ...

    def trace(self, hand: RobotHandState, span: TraceSpan) -> tuple[list[float], float]: ...

    def rest_at_floor(self) -> None: ...


class TheBars:
    in_play = True

    def tick(self, hand: RobotHandState, now: float, *, start_fraction: float) -> None:
        pass

    def height(self, hand: RobotHandState, phase: float, lead_s: float) -> float:
        return 100.0 * Waveform.of(hand).height_at(phase + lead_s * hand.bpm / 60.0)

    def trace(self, hand: RobotHandState, span: TraceSpan) -> tuple[list[float], float]:
        return trace_window(Waveform.of(hand), span)

    def rest_at_floor(self) -> None:
        pass


class Learned:
    def __init__(self, state: LearnedMotionState | None) -> None:
        self._state = state

    @property
    def in_play(self) -> bool:
        return self._state is not None and self._state.active

    def tick(self, hand: RobotHandState, now: float, *, start_fraction: float) -> None:
        if self._state is not None:
            learned_motion.tick_learned_motion(
                hand, self._state, now, start_fraction=start_fraction)

    def height(self, hand: RobotHandState, phase: float, lead_s: float) -> float:
        return learned_motion.position(self._state, hand, lead_s)

    def trace(self, hand: RobotHandState, span: TraceSpan) -> tuple[list[float], float]:
        return learned_motion.trace_window(self._state, hand, span.samples, span.span_s)

    def rest_at_floor(self) -> None:
        if self._state is not None:
            learned_motion.rest_at_floor(self._state)


def ways_the_hand_moves(learned: LearnedMotionState | None) -> tuple[Way, ...]:
    return (
        Learned(learned),
        TheBars(),
    )


class HandMotion:
    def __init__(self, hand: RobotHandState | None, ways: Sequence[Way]) -> None:
        self._hand = RobotHandState() if hand is None else hand
        self._ways = tuple(ways)

    @property
    def _way(self) -> Way:
        return next(way for way in self._ways if way.in_play)

    def tick(self, now: float, *, start_fraction: float = 0.0) -> None:
        for way in self._ways:
            way.tick(self._hand, now, start_fraction=start_fraction)

    def height(self, phase: float, *, lead_s: float = 0.0) -> float:
        return self._way.height(self._hand, phase, lead_s)

    def trace(self, span: TraceSpan) -> tuple[list[float], float]:
        return self._way.trace(self._hand, span)

    def rest_at_floor(self) -> None:
        for way in self._ways:
            way.rest_at_floor()
