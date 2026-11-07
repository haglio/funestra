from __future__ import annotations

import bisect
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from . import learned_model
from .learned_model import LearnedModel
from .robot_hand import MAX_TICK_SECONDS, RobotHandState, bpm_for_speed

DEFAULT_MODEL = Path(__file__).with_name("learned_motion.json.gz")
_AHEAD_S = 30.0


@dataclass
class LearnedMotionState:
    model: LearnedModel | None = None
    active: bool = False
    rng: random.Random = field(default_factory=random.Random)
    clock: float = 0.0
    times: list[float] = field(default_factory=list)
    positions: list[float] = field(default_factory=list)
    phrase_class: tuple[int, int, int] | None = None
    _last_tick: float | None = None


def load_default_model() -> LearnedModel:
    return learned_model.load(DEFAULT_MODEL)


def enable_learned_motion(state: LearnedMotionState) -> None:
    state.active = True


def disable_learned_motion(state: LearnedMotionState) -> None:
    state.active = False
    _clear(state)


def toggle_learned_motion(state: LearnedMotionState) -> bool:
    if state.active:
        disable_learned_motion(state)
    else:
        enable_learned_motion(state)
    return state.active


def tick_learned_motion(robot_hand: RobotHandState, state: LearnedMotionState, now: float,
                        *, start_fraction: float = 0.0) -> None:
    if not state.active or not state.model:
        return
    dt = 0.0 if state._last_tick is None else now - state._last_tick
    state._last_tick = now
    if not robot_hand.playing:
        return
    if not state.times:
        _begin(state, start_fraction)
    step = max(0.0, min(dt, MAX_TICK_SECONDS))
    state.clock += step * _pace(state, robot_hand)
    _lay_out(state, state.clock + _AHEAD_S)
    _forget_the_past(state)


def position(state: LearnedMotionState, robot_hand: RobotHandState | None,
             lead_s: float = 0.0) -> float:
    at = state.clock + lead_s * _pace(state, robot_hand)
    _laid_out_to(state, at)
    return _into_the_envelope(_raw(state, at), robot_hand)


def trace_window(state: LearnedMotionState, robot_hand: RobotHandState | None,
                 samples: int, span_s: float) -> tuple[list[float], float]:
    grid = span_s / max(1, samples - 1) * _pace(state, robot_hand)
    if grid <= 0:
        return [position(state, robot_hand) / 100.0] * (samples + 1), 0.0
    first = math.floor(state.clock / grid) * grid
    _laid_out_to(state, first + samples * grid)
    heights = [
        _into_the_envelope(_raw(state, first + i * grid), robot_hand) / 100.0
        for i in range(samples + 1)
    ]
    return heights, (state.clock - first) / grid


def rest_at_floor(state: LearnedMotionState) -> None:
    _clear(state)
    if state.active and state.model:
        _begin(state, 0.0)
        _lay_out(state, state.clock + _AHEAD_S)


def _pace(state: LearnedMotionState, robot_hand: RobotHandState | None) -> float:
    if robot_hand is None or state.model is None:
        return 1.0
    return bpm_for_speed(robot_hand.speed) * state.model.native_cycle_ms / 60_000.0


def _into_the_envelope(raw: float, robot_hand: RobotHandState | None) -> float:
    if robot_hand is None:
        return raw
    half = robot_hand.amplitude / 2
    low = max(0.0, robot_hand.center - half)
    high = min(100.0, robot_hand.center + half)
    return low + raw / 100.0 * (high - low)


def _raw(state: LearnedMotionState, at: float) -> float:
    times, positions = state.times, state.positions
    if not times:
        return 0.0
    index = bisect.bisect_right(times, at) - 1
    if index < 0:
        return positions[0]
    if index >= len(times) - 1:
        return positions[-1]
    t0, t1 = times[index], times[index + 1]
    p0, p1 = positions[index], positions[index + 1]
    return p0 + (p1 - p0) * (at - t0) / (t1 - t0)


def _begin(state: LearnedMotionState, start_fraction: float) -> None:
    state.times = [state.clock]
    state.positions = [100.0 * min(1.0, max(0.0, start_fraction))]
    state.phrase_class = None


def _clear(state: LearnedMotionState) -> None:
    state.times = []
    state.positions = []
    state.phrase_class = None


def _lay_out(state: LearnedMotionState, until: float) -> None:
    while state.times[-1] < until:
        cls = learned_model.next_class(state.model, state.rng, state.phrase_class)
        phrase = learned_model.draw_phrase(state.model, state.rng, cls)
        for duration_ms, end in phrase.swings:
            state.times.append(state.times[-1] + duration_ms / 1000.0)
            state.positions.append(float(end))
        state.phrase_class = cls


def _laid_out_to(state: LearnedMotionState, at: float) -> None:
    if state.model and state.times:
        _lay_out(state, at)


def _forget_the_past(state: LearnedMotionState) -> None:
    behind_by = bisect.bisect_right(state.times, state.clock) - 1
    if behind_by > 0:
        del state.times[:behind_by]
        del state.positions[:behind_by]
