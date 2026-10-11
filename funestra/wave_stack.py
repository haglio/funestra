"""The motion as a sum of waves, each of them always on its way somewhere.

One wave is one shape at one speed, and a minute of it is the same sentence over
and over. Several make a motion: the main wave at the pace the bar is set to,
and under it a much slower swell of its own size, so the place the motion is
working drifts from base to tip and back while the motion goes on. Nothing
inside a wave holds still either — its speed, its travel and its center are all
:class:`Ramp`s rather than numbers, each on its way from what it was to
somewhere else over its own stretch of seconds, drawing a new somewhere when it
arrives.

Every wave owns its own travel and its own center outright. The motion's travel
and center — the numbers on the console, the dashed line on the readout — are
read back off the sum rather than handed down to the waves, so a wave can drift
where it likes without asking the others. What keeps that from walking off the
end of the axis is :func:`fit`, at the last moment before a position is taken:
the summed swing is scaled down if the waves have between them asked for more
than the axis has, and the summed center is moved in far enough that the swing
still lands. Both are rare, because the draws that feed the ramps are already
divided by how many waves there are (see :mod:`funestra.cruise_control`) — the
fit is the guarantee, not the mechanism.

Pure arithmetic, as :mod:`funestra.robot_hand` is. No clock of its own —
the caller says what time it is — and no randomness: drawing the ramps is
:mod:`funestra.cruise_control`'s job. The waveform itself is
:mod:`funestra.robot_hand`'s; this only sums copies of it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .max_intensity import share
from .robot_hand import (
    FULL_INTENSITY,
    WaveformShape,
    bpm_for_speed,
    phase_advanced,
    position_fraction,
    toward_the_park,
    wave_travel,
)

__all__ = [
    "bars",
    "position",
    "position_ahead",
    "trace_window",
]

@dataclass
class Ramp:
    """A value on its way from *start* to *end*, taking *seconds* over it,
    and the ramp that follows.

    This is the dynamic half of the motion: a travel that is 40 going on 20
    rather than a travel that is 30. Before it begins it reads *start* and after
    it ends it reads what follows -- ``then``, the next ramp, decided already
    so the motion a window ahead is written once and the readout can show it
    sliding; only a ramp with nothing chained on yet holds its *end*.  A
    speed ramp may carry the *shape* the wave takes as it begins, so a swap
    is scheduled with the ramp rather than rolled when it arrives.
    """

    start: float
    end: float
    begun: float = 0.0
    seconds: float = 0.0
    then: Ramp | None = None
    shape: WaveformShape | None = None

    @property
    def ends_at(self) -> float:
        return self.begun + self.seconds

    def at(self, now: float) -> float:
        if self.then is not None and now >= self.ends_at:
            return self.then.at(now)
        if self.seconds <= 0:
            return self.end
        through = (now - self.begun) / self.seconds
        if through <= 0.0:
            return self.start
        if through >= 1.0:
            return self.end
        return self.start + (self.end - self.start) * through

    def finished(self, now: float) -> bool:
        return now >= self.ends_at

    def last(self) -> Ramp:
        """The end of the chain: where the next ramp is chained on."""
        ramp = self
        while ramp.then is not None:
            ramp = ramp.then
        return ramp

    def resumed(self, value: float, now: float) -> Ramp:
        """This ramp carried on from *value* — a hand on the bar mid-glide.

        Same destination, and the time that was left to reach it, but starting
        from where the hand put it rather than snapping back to where the glide
        had got to on its own.  What follows still follows.
        """
        return Ramp(value, self.end, now, max(0.0, self.ends_at - now),
                    then=self.then, shape=self.shape)

    def shifted(self, delta: float) -> Ramp:
        """This ramp and every one chained on with both ends moved by *delta*,
        keeping their schedule — a bar nudged by hand while cruise control is
        steering it."""
        return Ramp(self.start + delta, self.end + delta, self.begun, self.seconds,
                    then=None if self.then is None else self.then.shifted(delta),
                    shape=self.shape)

    def rescaled_ahead(self, factor: float) -> Ramp:
        """Where this ramp is going, and every ramp chained on, scaled by
        *factor* -- the travel the hand asked for from here on -- with where
        it is now left alone."""
        return Ramp(self.start, self.end * factor, self.begun, self.seconds,
                    then=None if self.then is None else self.then.scaled(factor),
                    shape=self.shape)

    def scaled(self, factor: float) -> Ramp:
        return Ramp(self.start * factor, self.end * factor, self.begun, self.seconds,
                    then=None if self.then is None else self.then.scaled(factor),
                    shape=self.shape)

    def moved_ahead(self, delta: float) -> Ramp:
        """Where this ramp is going, and every ramp chained on, moved by
        *delta*, with where it is now left alone."""
        return Ramp(self.start, self.end + delta, self.begun, self.seconds,
                    then=None if self.then is None else self.then.shifted(delta),
                    shape=self.shape)

    def clamped(self, low: float, high: float) -> Ramp:
        """This ramp and every one chained on kept within *low* and *high*."""
        return Ramp(min(high, max(low, self.start)), min(high, max(low, self.end)),
                    self.begun, self.seconds,
                    then=None if self.then is None else self.then.clamped(low, high),
                    shape=self.shape)


@dataclass
class Wave:
    """One of the summed waves: a shape, and a speed, a travel and a center of
    its own, each of the three on its way somewhere.

    The center is the wave's alone. Only the sum of them is a place on the axis,
    which is what the console shows — but a wave whose center is ramping while
    another's holds is a different motion from one where they move together, and
    that difference is the whole reason each carries its own.

    ``shape`` is the shape the wave has now; a speed ramp chained on ahead may
    carry the one it swaps to as it begins (:func:`shape_at`).
    """

    shape: WaveformShape = WaveformShape.SINE
    speed: Ramp = field(default_factory=lambda: Ramp(50.0, 50.0))
    amplitude: Ramp = field(default_factory=lambda: Ramp(100.0, 100.0))
    center: Ramp = field(default_factory=lambda: Ramp(50.0, 50.0))
    phase: float = 0.0


@dataclass
class WaveStack:
    """The waves that are summed to make the motion.

    The first is the motion's own pace — the one the Speed bar is set to and
    the one a hand on that bar is turning. The ones after it run slower, and
    are the swells that carry it about (:mod:`funestra.cruise_control` is what
    makes that so, and the console's speed and shape name that first wave
    because of it).
    """

    waves: list[Wave] = field(default_factory=list)

    def __bool__(self) -> bool:
        """False while there are no waves — while the motion is the single
        hand-driven one and this is not what the device is following."""
        return bool(self.waves)


@dataclass
class Fit:
    """The sum squeezed into the axis: how much every wave's travel had to give
    (``scale``, 1.0 nearly always), and what the motion's travel and center come
    to once it has."""

    scale: float
    travel: float
    center: float


@dataclass
class Bars:
    """The stack as the three numbers and the shape a console can show."""

    travel: float
    center: float
    speed: float
    shape: WaveformShape


def shape_at(wave: Wave, at: float) -> WaveformShape:
    """The shape *wave* has at *at*: its own, swapped by every speed ramp that
    has begun by then and carries one -- so a swap scheduled ahead shows in the
    readout's picture before it happens, as the rest of the motion does."""
    shape = wave.shape
    ramp: Ramp | None = wave.speed
    while ramp is not None and at >= ramp.begun:
        if ramp.shape is not None:
            shape = ramp.shape
        ramp = ramp.then
    return shape


def room(travel: float, center: float) -> float:
    """*center*, moved in far enough that a swing of *travel* still fits.

    A motion 90 wide cannot sit at 25 — a quarter of it would be under the floor
    — so the center gives way, the same way it gives way on the bars when the
    amplitude opens past it. Here it gives way continuously, because every ramp
    under it moves on its own schedule and none waits for the others.
    """
    half = travel / 2
    return min(100.0 - half, max(half, center))


def fit(stack: WaveStack, now: float) -> Fit:
    """The waves added up and made to land on the axis.

    Their travels sum to the motion's travel and their centers to its center —
    that way round, so no wave has to be told where to sit. Only when the sum
    asks for more swing than the axis has does anything give: every travel is
    scaled by the same fraction, which shrinks the motion without changing which
    wave is the big one.
    """
    travel = sum(wave.amplitude.at(now) for wave in stack.waves)
    center = sum(wave.center.at(now) for wave in stack.waves)
    scale = 1.0 if travel <= 100.0 else 100.0 / travel
    travel *= scale
    return Fit(scale=scale, travel=travel, center=room(travel, center))


def position(stack: WaveStack, now: float,
             phases: list[float] | None = None, *, max_intensity: int = FULL_INTENSITY) -> float:
    """Where the summed motion sits at *now*, 0-100.

    *phases* is where each wave is, defaulting to where they actually are — the
    projections below pass their own rather than moving the waves to ask.
    """
    if phases is None:
        phases = [wave.phase for wave in stack.waves]
    landed = fit(stack, now)
    total = landed.center
    for wave, phase in zip(stack.waves, phases):
        # position_fraction on its default bars is the bare waveform, 0-1.
        raw = position_fraction(phase, shape=shape_at(wave, now))
        total += landed.scale * wave.amplitude.at(now) * (raw - 0.5)
    return toward_the_park(min(100.0, max(0.0, total)), _kept(stack, now, max_intensity))


def _kept(stack: WaveStack, now: float, max_intensity: int) -> float:
    scale = fit(stack, now).scale
    return share(sum(wave_travel(scale * wave.amplitude.at(now),
                                 bpm_for_speed(wave.speed.at(now)))
                     for wave in stack.waves), max_intensity)


def advance(stack: WaveStack, now: float, dt_s: float, *,
            max_intensity: int = FULL_INTENSITY) -> None:
    """Carry every wave's phase forward by *dt_s* seconds of motion, ending at
    *now* -- at the speed each was running halfway through, which is what a
    ramping speed comes to over a tick, and what the readout's projection of
    the same stretch assumes."""
    halfway = now - dt_s / 2
    pace = _kept(stack, halfway, max_intensity)
    for wave in stack.waves:
        wave.phase = phase_advanced(
            wave.phase, pace * bpm_for_speed(wave.speed.at(halfway)), dt_s)


def position_ahead(stack: WaveStack, now: float, lead_s: float, *,
                   max_intensity: int = FULL_INTENSITY) -> float:
    """Where the sum will be *lead_s* from *now* — what a command aims at.

    Each wave's phase is projected rather than advanced (nothing here moves the
    stack), at the speed it will be running halfway through the lead, which is
    what a ramping speed comes to over so short a hop.
    """
    phases = _carried(stack, [wave.phase for wave in stack.waves], now + lead_s / 2,
                      lead_s, max_intensity)
    return position(stack, now + lead_s, phases, max_intensity=max_intensity)


def trace_window(stack: WaveStack, now: float, samples: int, span_s: float, *,
                 max_intensity: int = FULL_INTENSITY) -> tuple[list[float], float]:
    """The sum as the readout draws it: *samples* + 1 heights on knots a fixed
    stretch of the motion's clock apart, the first at or before *now* and the
    last just past the far edge, and how far past the first knot *now* sits as
    a fraction of one.

    Read on knots rather than from *now* so the picture holds still between
    knots and slides by the fraction, instead of being redrawn at fixed
    columns every frame (:func:`trace` is that redraw).  The phases at the
    first knot are the waves' own carried back by the fraction of a knot they
    have moved since, at the speed each was running halfway back -- exact for
    a steady speed, and as near as makes no difference for a ramping one.
    """
    step = span_s / max(1, samples - 1)
    first = math.floor(now / step) * step
    back = now - first
    phases = _carried(stack, [wave.phase for wave in stack.waves], now - back / 2,
                      -back, max_intensity)
    heights = []
    for i in range(samples + 1):
        at = first + i * step
        heights.append(position(stack, at, phases, max_intensity=max_intensity) / 100.0)
        phases = _carried(stack, phases, at + step / 2, step, max_intensity)
    return heights, back / step


def _carried(stack: WaveStack, phases: list[float], halfway: float, seconds: float,
             max_intensity: int) -> list[float]:
    pace = _kept(stack, halfway, max_intensity)
    return [phase + seconds * pace * bpm_for_speed(wave.speed.at(halfway)) / 60.0
            for wave, phase in zip(stack.waves, phases)]


def biggest(stack: WaveStack, now: float) -> Wave:
    """The wave with the most travel — the one the device is mostly following,
    whichever of them it happens to be at the moment."""
    return max(stack.waves, key=lambda wave: wave.amplitude.at(now))


def bars(stack: WaveStack, now: float) -> Bars:
    """What the console reads while the stack has the motion.

    The travel and the center are read off the sum, so the readout's bar and its
    dashed line are the envelope the device is really working in rather than
    anything the waves were told. Speed and shape are the main wave's: there is
    no single number for two speeds at once, and the pace of the motion you set
    is the one a reader is asking after — the swells under it are slow by
    construction, and naming whichever wave is momentarily the biggest would
    have the number stepping between them while the motion did nothing.
    """
    landed = fit(stack, now)
    lead = stack.waves[0]
    return Bars(travel=landed.travel, center=landed.center,
                speed=lead.speed.at(now), shape=shape_at(lead, now))


dials = bars


def rest_at_floor(stack: WaveStack) -> None:
    """Put every wave at phase 0 — the foot of the motion's swing.

    Phase 0 is where every waveform shape's raw value is 0, so all of them at
    once is the lowest point the stack's travel and center reach: the nearest
    the motion comes to the device's park, and where it should resume from after
    something else has had the device.
    """
    for wave in stack.waves:
        wave.phase = 0.0
