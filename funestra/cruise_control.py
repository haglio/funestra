"""Hands-free variation of the motion — the Robot Hand's cruise control, shared.

It lives beside :mod:`funestra.robot_hand` because the state it varies is
that one's: an app that has the motion gets this with it, rather than growing
its own idea of what "vary it for me" means.

What it hands the device is :mod:`funestra.wave_stack`'s — waves summed, each
with its own travel, center and speed. This is the part with the dice in it. It
decides how many waves there are and how far below the main one the others run,
and then never stops: every ramp has the next one chained on, decided a minute
ahead of the motion's clock, so no bar in the motion is ever simply a number
-- and the readout's picture of what is coming is written once and only slides
into view, never redrawn as a ramp arrives.

Four things it is careful about.

**Every range is pinned to the bars you set.** The speed, the travel and the
center the motion had when this took it over are kept as anchors, and every draw
here is an excursion around one of them rather than a draw from the axis at
large. Nothing accumulates: the tenth minute is drawn from the same ranges as
the first, so an hour of cruising is still recognizably the motion you asked
for, at a pace within sight of the one you set. Only a hand on a bar moves an
anchor, and it moves it by exactly what the hand turned.

**What rides on what.** The first wave *is* the motion: it keeps most of the
travel and runs at the pace the bar names. Every other one runs far slower — a
fifth of it down to a fortieth, measured against the least the main wave runs
while the swell's own ramp lasts — and gets what travel is left, so what it
adds is a swell carrying the whole motion from base to tip and back. A wave at
half the main pace with as much travel is not a swell; it is a second motion
interfering with the first, and that interference is what makes a stack sound
busy while feeling weak — no two swings the same depth, and none of them the
depth you asked for.

**Room to be dramatic.** A ramp that moves a bar five points over twenty
seconds is a ramp nobody can feel. The times here are long and the bands as wide
as being anchored allows: a speed crossing its whole band over half a minute, a
travel closing to two thirds of yours and opening back to all of it, a center
walking as far either way as the swing leaves room for. The motion should be
plainly somewhere different from where it was a minute ago.

**The sum, not the parts.** Every range here is what the *whole* motion is drawn
from, split among the waves — so two waves average what one used to, rather than
piling two full motions on top of each other and sitting the device high and
wide.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from . import wave_stack
from .robot_hand import (
    MAX_SPEED,
    MAX_TICK_SECONDS,
    MIN_SPEED,
    WaveformShape,
    set_amplitude,
    set_center,
    set_speed,
)
from .wave_stack import Ramp, Wave, WaveStack

__all__ = [
    "CruiseControlState",
    "disable_cruise_control",
    "enable_cruise_control",
    "tick_cruise_control",
]

if TYPE_CHECKING:
    from .robot_hand import RobotHandState

# How many waves a session gets: a pair most of the time, sometimes the plain
# single wave, sometimes three.
_COUNTS = (1, 2, 2, 2, 3)
# What the whole motion's travel wanders over, as a fraction of the travel the
# bar was set to. It reaches what you asked for and never passes it — there is
# no room above — and the shallow end is still most of what you asked for.
_TRAVEL_BAND = (0.62, 1.0)
# How far the whole motion's center may wander either side of the one you set,
# and the ends of the axis it is kept off. How much of that wander survives is
# the swing's to say: :func:`wave_stack.room` pulls the center in far enough
# that the travel still lands, so a motion using the whole axis has nowhere to
# walk and a shallow one has the width of this.
_CENTER_SWING = 25.0
_CENTER_LIMITS = (10.0, 90.0)
# What the wave the Speed bar names keeps of the travel. The rest is split
# among the swells — enough to carry the motion about, not enough to be a second
# motion of its own.
_MAIN_SHARE = (0.68, 0.88)
# How long a ramp on each axis takes. Long, because what is wanted is a motion
# gradually speeding up or opening out, not a bar being dragged.
_SPEED_S = (10.0, 40.0)
_TRAVEL_S = (8.0, 30.0)
_CENTER_S = (15.0, 60.0)
# Where the main wave's speed wanders, in bar units either side of the
# session's base, and where each swell's runs, in bar units under the least
# the main wave runs while the swell's ramp lasts. The Speed bar is exponential —
# about 18 units doubles the cycles a minute — so the first wave is the motion
# you set, and the ones under it run at a fifth to a fortieth of it: swells,
# not partials.
_MAIN_SPAN = (-12.0, 12.0)
_UNDER_SPANS = ((-72.0, -45.0), (-95.0, -70.0))
# The base drifts, so an hour of cruising is not all one pace — but only within
# sight of the speed you set. Unbounded, the same walk arrives an hour later at
# half the pace you asked for and has no way back to it.
_BASE_STEP = (-10.0, -5.0, 5.0, 10.0)
_BASE_SWING = 10.0
_BASE_S = (60.0, 120.0)
# What a swell may be shaped like. The main wave can be any of them; a swell is
# an envelope, and one that snaps between two levels is a lurch, not a carry.
_SWELL_SHAPES = (WaveformShape.SINE, WaveformShape.TRIANGLE)
# How far ahead of the motion's clock every ramp is decided.  The readout shows
# the coming motion, and a motion whose next stretch is drawn only when the
# last one arrives rewrites the picture as it is being watched; decided this
# far ahead -- past any span the readout draws -- the future is written once
# and only slides into view.
_DECIDED_AHEAD_S = 60.0


@dataclass
class CruiseControlState:
    """Hands-free variation of the motion itself — never of which flick plays.

    Moving on to another flick is :mod:`funestra.flick_advance`'s job, and the two are
    independent: a session can vary the motion on one held flick, or hold the
    motion steady while the flicks change, or both.

    ``active`` is the only part of this a caller reads. The stack under it is
    what the device follows while it is set; ``clock`` is the motion's own
    seconds, which move only while it is actually running, so every ramp
    freezes where it stood through a pause.

    The three anchors are the bars as the session set them. Every range the
    dice are drawn from is measured off one of them, and only a hand on a bar
    moves one — which is what keeps an hour of this from wandering off.
    """

    active: bool = False
    rng: random.Random = field(default_factory=random.Random)
    stack: WaveStack = field(default_factory=WaveStack)
    clock: float = 0.0
    anchor_speed: float = 50.0
    anchor_travel: float = 100.0
    anchor_center: float = 50.0
    base_speed: float = 50.0
    # Where the main wave's speed is drawn from: the base, either side.
    band: tuple[float, float] = (50.0, 50.0)
    # How the travel is divided: most of it to the wave the bar names.
    shares: list[float] = field(default_factory=list)
    next_base: float = 0.0
    # The bars as this last wrote them, so a hand that has moved one since can
    # be told from this module's own writing.
    wrote: tuple | None = None
    # None until the first tick: the wall clock a caller hands in is whatever
    # its own clock reads, so the first tick has no interval before it and must
    # not be given one — the motion would jump the whole of it in a step.
    _last_tick: float | None = None


def enable_cruise_control(state: CruiseControlState) -> None:
    """Arm it. The waves themselves are drawn on the first tick, from whatever
    the bars say then, so arming cannot move the motion."""
    state.active = True


def disable_cruise_control(state: CruiseControlState) -> float | None:
    """Give the motion back, and say where the single wave should pick it up."""
    phase = (wave_stack.biggest(state.stack, state.clock).phase
             if state.stack else None)
    state.active = False
    state.stack = WaveStack()
    state.shares = []
    state.wrote = None
    return phase


def tick_cruise_control(
    robot_hand: RobotHandState,
    cc: CruiseControlState,
    now: float,
    *,
    phase: float = 0.0,
) -> None:
    """One tick of the dice: carry the waves forward, pick up any hand on the
    bars, give every arrived ramp somewhere new to go, and write what the
    motion now is back to the bars for the console to read.

    *phase* is where the motion is, used only when this is the tick that draws
    the waves — they all start there, so taking over cannot be felt.

    Nothing moves while the motion is not running: the wall clock keeps up so
    resuming picks up where it left off, but the motion's own clock — the one
    every ramp is timed against — does not.
    """
    if not cc.active:
        return

    dt = 0.0 if cc._last_tick is None else now - cc._last_tick
    cc._last_tick = now

    if not robot_hand.playing:
        return

    if not cc.stack:
        _draw_the_waves(cc, robot_hand, phase)

    # A clock that stalled — the app blocked, the machine suspended — comes back
    # owing a step no motion should take at once, and the same cap the phase
    # puts on that is what the ramps under it get.
    step = max(0.0, min(dt, MAX_TICK_SECONDS))
    cc.clock += step
    wave_stack.advance(cc.stack, cc.clock, step, max_intensity=robot_hand.max_intensity)
    _hand_turns(cc, robot_hand)
    _onward_all(cc)
    _write_bars(cc, robot_hand)


def _clamped(speed: float) -> float:
    return min(float(MAX_SPEED), max(float(MIN_SPEED), speed))


def _within(low: float, high: float, value: float) -> float:
    return min(high, max(low, value))


def _band(base: float) -> tuple[float, float]:
    """Where the main wave's speed may wander."""
    return (_clamped(base + _MAIN_SPAN[0]), _clamped(base + _MAIN_SPAN[1]))


def _shares(rng: random.Random, count: int) -> list[float]:
    """How the travel is divided among the waves: most of it to the first, the
    rest split evenly among the swells under it.

    Drawn once, when the waves are, so which wave is the big one is settled for
    the session rather than swapping about — the pace the bar names is the pace
    with most of the travel under it, every minute this is on.
    """
    if count == 1:
        return [1.0]
    main = rng.uniform(*_MAIN_SHARE)
    return [main] + [(1.0 - main) / (count - 1)] * (count - 1)


def _travel_span(cc: CruiseControlState, index: int) -> tuple[float, float]:
    """What one wave's travel is drawn from: its share of the whole motion's
    band, which is itself a fraction of the travel the bar was set to."""
    share = cc.anchor_travel * cc.shares[index]
    return (share * _TRAVEL_BAND[0], share * _TRAVEL_BAND[1])


def _center_span(cc: CruiseControlState, count: int) -> tuple[float, float]:
    """What one wave's center is drawn from: the whole motion's wander either
    side of the center the bar was set to, divided among the waves."""
    low, high = _CENTER_LIMITS
    return (_within(low, high, cc.anchor_center - _CENTER_SWING) / count,
            _within(low, high, cc.anchor_center + _CENTER_SWING) / count)


def _settled(value: float, now: float) -> Ramp:
    """A ramp already arrived and holding *value* — what every parameter looks
    like the moment cruise control takes the motion over, before the first tick
    gives it somewhere to go."""
    return Ramp(value, value, now, 0.0)


def _onward(cc: CruiseControlState, ramp: Ramp, span: tuple[float, float],
            seconds: tuple[float, float]) -> Ramp:
    """Somewhere new for the chain ending in *ramp* to be next — from where
    that ramp arrives, to a fresh draw out of *span*, over a fresh stretch of
    seconds, beginning the moment it arrives."""
    return Ramp(ramp.end, cc.rng.uniform(*span), ramp.ends_at, cc.rng.uniform(*seconds))


def _decided_ahead(cc: CruiseControlState, ramp: Ramp, span: tuple[float, float],
                   seconds: tuple[float, float], *, until: float,
                   shapes: tuple[WaveformShape, ...] | None = None) -> None:
    """Chain ramps onto *ramp* until they reach past *until*.

    A speed chain (*shapes* given) schedules a shape swap with each ramp that
    follows a drawn one -- never with the one that follows the ramp born
    finished at the takeover, whose whole point is that it cannot be felt.
    """
    last = ramp.last()
    while last.ends_at < until:
        following = _onward(cc, last, span, seconds)
        if shapes is not None and last.seconds > 0:
            following.shape = cc.rng.choice(list(shapes))
        last.then = following
        last = following


def _decided_under(cc: CruiseControlState, ramp: Ramp, main: Ramp,
                   span: tuple[float, float], *, until: float) -> None:
    """A swell's speed chained on until *until*, each ramp drawn under the
    main wave: *span* below the least the main runs while the ramp lasts, so a
    swell is never within earshot of the pace you feel, whatever the main
    does meanwhile -- and never below the bar's floor, where the slowest
    swells pile up."""
    last = ramp.last()
    while last.ends_at < until:
        seconds = cc.rng.uniform(*_SPEED_S)
        lowest = _lowest(main, last.ends_at, last.ends_at + seconds)
        following = Ramp(last.end, _clamped(lowest + cc.rng.uniform(*span)),
                         last.ends_at, seconds)
        if last.seconds > 0:
            following.shape = cc.rng.choice(list(_SWELL_SHAPES))
        last.then = following
        last = following


def _lowest(ramp: Ramp, since: float, until: float) -> float:
    """The least a chain reads between *since* and *until*: at one end of the
    stretch, or where a ramp inside it arrives, each being straight between."""
    values = [ramp.at(since), ramp.at(until)]
    link: Ramp | None = ramp
    while link is not None:
        if since < link.ends_at < until:
            values.append(link.at(link.ends_at))
        link = link.then
    return min(values)


def _promoted(ramp: Ramp, now: float) -> Ramp:
    """The ramp active at *now*: every finished one before it is dropped."""
    while ramp.then is not None and ramp.finished(now):
        ramp = ramp.then
    return ramp


def _draw_the_waves(cc: CruiseControlState, robot_hand: RobotHandState,
                    phase: float) -> None:
    """Take the motion over, from exactly where the bars have it.

    The bars become the anchors every later draw is measured off, and the
    travel is divided among the waves in the shares they will keep. Every ramp
    is born already arrived, so the sum is the bars to the point — and with
    every wave at the phase the motion is already at and running the same speed,
    the sum *is* the single wave. The rest of this tick draws them all somewhere
    to go, and the motion opens out from where it stood.
    """
    count = cc.rng.choice(_COUNTS)
    now = cc.clock
    cc.anchor_speed = cc.base_speed = float(robot_hand.speed)
    cc.anchor_travel = float(robot_hand.amplitude)
    cc.anchor_center = float(robot_hand.intended_center)
    cc.shares = _shares(cc.rng, count)
    cc.band = _band(cc.base_speed)
    cc.next_base = now + cc.rng.uniform(*_BASE_S)
    cc.wrote = None
    cc.stack = WaveStack(waves=[
        Wave(
            shape=robot_hand.shape,
            speed=_settled(float(robot_hand.speed), now),
            amplitude=_settled(robot_hand.amplitude * share, now),
            center=_settled(robot_hand.center / count, now),
            phase=phase,
        )
        for share in cc.shares
    ])


def _onward_all(cc: CruiseControlState) -> None:
    now = cc.clock
    waves = cc.stack.waves
    count = len(waves)
    if now >= cc.next_base:
        cc.base_speed = _clamped(_within(
            cc.anchor_speed - _BASE_SWING, cc.anchor_speed + _BASE_SWING,
            cc.base_speed + cc.rng.choice(_BASE_STEP)))
        cc.band = _band(cc.base_speed)
        cc.next_base = now + cc.rng.uniform(*_BASE_S)
    until = now + _DECIDED_AHEAD_S
    for wave in waves:
        # A ramp that has arrived hands over to the one decided after it.  A
        # shape swapping under the phase steps the position a little, so it is
        # not free: a wave takes one only as a speed ramp begins, and the swap
        # was scheduled with that ramp when it was decided -- taken up here,
        # and cleared so a shape set by hand afterwards is not overridden by it.
        wave.speed = _promoted(wave.speed, now)
        if wave.speed.shape is not None and now >= wave.speed.begun:
            wave.shape, wave.speed.shape = wave.speed.shape, None
        wave.amplitude = _promoted(wave.amplitude, now)
        wave.center = _promoted(wave.center, now)
    # The main wave's pace first, decided far enough past *until* that every
    # swell's ramp drawn up to *until* runs under a main wave already decided.
    main = waves[0]
    _decided_ahead(cc, main.speed, cc.band, _SPEED_S, until=until + _SPEED_S[1],
                   shapes=tuple(WaveformShape))
    for index, wave in enumerate(waves):
        if index > 0:
            _decided_under(cc, wave.speed, main.speed, _UNDER_SPANS[index - 1], until=until)
        _decided_ahead(cc, wave.amplitude, _travel_span(cc, index), _TRAVEL_S, until=until)
        _decided_ahead(cc, wave.center, _center_span(cc, count), _CENTER_S, until=until)


def _write_bars(cc: CruiseControlState, robot_hand: RobotHandState) -> None:
    """The stack as the bars, so every console and status file draws what is
    actually being sent."""
    bars = wave_stack.bars(cc.stack, cc.clock)
    set_amplitude(robot_hand, round(bars.travel))
    set_center(robot_hand, round(bars.center))
    set_speed(robot_hand, round(bars.speed))
    robot_hand.shape = bars.shape
    cc.wrote = (robot_hand.amplitude, robot_hand.intended_center, robot_hand.speed,
                robot_hand.shape)


def _hand_turns(cc: CruiseControlState, robot_hand: RobotHandState) -> None:
    """A bar that has moved since this last wrote it moved by hand — so cruise
    carries on from there rather than yanking it back.

    Every bar is the whole motion's, and the motion is several waves, so each
    turn has to be spread over them: travel in proportion, so the shares survive
    the turn; center and pace by the same amount each, so their spacing does.
    The anchor moves by what the hand turned as well — a hand asking for more
    travel is asking for it from here on, not for one ramp's worth of it.
    """
    if cc.wrote is None:
        return
    now = cc.clock
    amplitude, center, speed, shape = cc.wrote
    waves = cc.stack.waves
    count = len(waves)
    if robot_hand.amplitude != amplitude:
        was = cc.anchor_travel
        cc.anchor_travel = _within(
            0.0, 100.0, cc.anchor_travel + robot_hand.amplitude - amplitude)
        # Every ramp already decided ahead was drawn off the old anchor, so
        # where each is going, and every one after it, is scaled to the new.
        factor = cc.anchor_travel / was if was > 0 else 1.0
        travel = sum(wave.amplitude.at(now) for wave in waves)
        for wave in waves:
            part = (wave.amplitude.at(now) * robot_hand.amplitude / travel
                    if travel > 0 else robot_hand.amplitude / count)
            wave.amplitude = wave.amplitude.resumed(part, now).rescaled_ahead(factor)
    if robot_hand.intended_center != center:
        cc.anchor_center = _within(
            *_CENTER_LIMITS,
            cc.anchor_center + robot_hand.intended_center - center)
        moved = (robot_hand.intended_center
                 - sum(wave.center.at(now) for wave in waves)) / count
        for wave in waves:
            wave.center = wave.center.resumed(wave.center.at(now) + moved, now).moved_ahead(moved)
    if robot_hand.speed != speed:
        delta = robot_hand.speed - speed
        cc.anchor_speed = _clamped(cc.anchor_speed + delta)
        cc.base_speed = _clamped(cc.base_speed + delta)
        cc.band = _band(cc.base_speed)
        for wave in waves:
            wave.speed = wave.speed.shifted(delta).clamped(float(MIN_SPEED), float(MAX_SPEED))
    if robot_hand.shape is not shape:
        waves[0].shape = robot_hand.shape  # the console named the main wave's
        # ...and holds until the next swap already scheduled, not one this
        # ramp still carried from before.
        waves[0].speed.shape = None
