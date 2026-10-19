"""Motion learned from real scripts -- the Robot Hand's learned mode, shared.

It takes the motion over from the bars, in place of the waveform: the device
follows phrases of real scripting, drawn one after another from a
:mod:`funestra.learned_model`, each phrase joined to the last where it ended,
so the motion is an endless script that no video was written for.

The bars are the envelope rather than the motion.  Amplitude and center say
the range the phrases play inside, and the Speed bar says how many cycles a
minute the motion makes, exactly as it does for the wave: the scripts' own
pace (:attr:`~funestra.learned_model.LearnedModel.native_cycle_ms`) is
scaled to the bar's rate, so a bar at 50 cycles about as often as the wave
does at 50.

The motion has a clock of its own, in script seconds: it advances only while
the motion is running, and faster or slower than the wall as the Speed bar
says, so a pause freezes it where it stood and a move of the bar changes the
pace from here on without a step.
"""
from __future__ import annotations

import bisect
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

from . import learned_model
from .learned_model import LearnedModel
from .robot_hand import MAX_TICK_SECONDS, RobotHandState, bpm_for_speed

# The trained model that ships with the package.
DEFAULT_MODEL = Path(__file__).with_name("learned_motion.json.gz")
# How far past the clock the phrases are laid out, in script seconds, so the
# readout's trace and a command aimed ahead always have motion to read.
_AHEAD_S = 30.0


@dataclass
class LearnedMotionState:
    """The phrases laid out ahead of the clock, and where the clock is.

    ``active`` is the only part of this a caller reads.  ``times`` and
    ``positions`` are the turning points laid out so far, in script seconds and
    the raw 0-100 of the scripts; ``clock`` is the motion's own seconds along
    them.
    """

    model: LearnedModel | None = None
    active: bool = False
    rng: random.Random = field(default_factory=random.Random)
    clock: float = 0.0
    times: list[float] = field(default_factory=list)
    positions: list[float] = field(default_factory=list)
    phrase_class: tuple[int, int, int] | None = None
    # None until the first tick: the first tick has no interval before it.
    _last_tick: float | None = None


def load_default_model() -> LearnedModel:
    return learned_model.load(DEFAULT_MODEL)


def enable_learned_motion(state: LearnedMotionState) -> None:
    """Arm it.  The phrases are laid out on the first tick, from wherever the
    motion is then, so arming cannot move the device."""
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
    """Carry the clock forward and keep phrases laid out ahead of it.

    *start_fraction* is where the device is within the envelope, 0 at its floor
    and 1 at its ceiling, used only on the tick that lays out the first phrase:
    it begins there, so taking over cannot be felt.

    Nothing moves while the motion is not running: the wall clock keeps up so
    resuming picks up where it left off, but the motion's own clock does not.
    """
    if not state.active or not state.model:
        return
    dt = 0.0 if state._last_tick is None else now - state._last_tick
    state._last_tick = now
    if not robot_hand.playing:
        return
    if not state.times:
        _begin(state, start_fraction)
    # A clock that stalled comes back owing a step no motion should take at
    # once, so it is capped like every other clock in the hand.
    step = max(0.0, min(dt, MAX_TICK_SECONDS))
    state.clock += step * _pace(state, robot_hand)
    _lay_out(state, state.clock + _AHEAD_S)
    _forget_the_past(state)


def position(state: LearnedMotionState, robot_hand: RobotHandState | None,
             lead_s: float = 0.0) -> float:
    """Where the motion is now, 0-100 on the device's axis -- or where it will
    be *lead_s* wall seconds on, which is what a command should aim at."""
    at = state.clock + lead_s * _pace(state, robot_hand)
    return _into_the_envelope(_raw(state, at), robot_hand)


def trace_window(state: LearnedMotionState, robot_hand: RobotHandState | None,
                 samples: int, span_s: float) -> tuple[list[float], float]:
    """The coming motion as the readout draws it: *samples* + 1 heights (0-1)
    on knots a fixed stretch of script apart, the last one just past the far
    edge, and how far past the first knot the clock sits as a fraction of one.

    Read on knots rather than from the clock itself so the picture holds
    still: the values only change when the clock crosses a knot, when the
    window moves on by one sample, and between knots the painter slides the
    whole line left by the fraction.  Sampled from the clock instead, the
    heights at fixed columns changed every frame as the swings passed under
    them, and the line writhed rather than glided.
    """
    grid = span_s / max(1, samples - 1) * _pace(state, robot_hand)
    if grid <= 0:
        return [position(state, robot_hand) / 100.0] * (samples + 1), 0.0
    first = math.floor(state.clock / grid) * grid
    heights = [
        _into_the_envelope(_raw(state, first + i * grid), robot_hand) / 100.0
        for i in range(samples + 1)
    ]
    return heights, (state.clock - first) / grid


def rest_at_floor(state: LearnedMotionState) -> None:
    """Put the motion at the floor of its envelope and lay the phrases out
    again from there -- what it resumes with after something else has had
    the device, and what the readout shows while it waits."""
    _clear(state)
    if state.active and state.model:
        _begin(state, 0.0)
        _lay_out(state, state.clock + _AHEAD_S)


def _pace(state: LearnedMotionState, robot_hand: RobotHandState | None) -> float:
    """Script seconds per wall second: the bar's cycles a minute over the
    cycles a minute the scripts were written at."""
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
    """The scripts' own 0-100 at script second *at*, straight between the
    turning points either side of it, and held at the ends."""
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
    """Draw phrases until the turning points reach past *until*, each joined to
    the last where it ended: the phrase's first swing rises from there."""
    while state.times[-1] < until:
        cls = learned_model.next_class(state.model, state.rng, state.phrase_class)
        phrase = learned_model.draw_phrase(state.model, state.rng, cls)
        for duration_ms, end in phrase.swings:
            state.times.append(state.times[-1] + duration_ms / 1000.0)
            state.positions.append(float(end))
        state.phrase_class = cls


def _forget_the_past(state: LearnedMotionState) -> None:
    """Drop turning points the clock has passed, but the one just before it."""
    behind_by = bisect.bisect_right(state.times, state.clock) - 1
    if behind_by > 0:
        del state.times[:behind_by]
        del state.positions[:behind_by]
