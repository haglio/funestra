"""The Robot Hand: the motion this family generates itself, a waveform shaped
by speed, amplitude and center.

It is what drives the OSR2 whenever no funscript has it — the family's own auto
mode, made so the motion could be steered from the room instead of left to the
device's built-in one.  Genau drives it from a flick's beats and visualizes it;
Origenerator free-runs it over slideshows of stills.  Both take it from this one
arithmetic, so :func:`phase_advanced` is offered here rather than owned here:
what advances the phase is the caller's own clock.

Pure arithmetic: no toolkit, no device, no clock.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from .tcode import POSITION_MAX

__all__ = [
    "FULL_INTENSITY",
    "MAX_SPEED",
    "MAX_TICK_SECONDS",
    "MIN_SPEED",
    "PARK_CENTER",
    "RETRACT_CENTER",
    "RobotHandState",
    "WaveformShape",
    "adjust_amplitude",
    "adjust_center",
    "adjust_speed",
    "bpm_for_speed",
    "cycle_shape",
    "phase_advanced",
    "position_fraction",
    "set_amplitude",
    "set_center",
    "set_max_intensity",
    "set_speed",
    "trace_window",
]

class WaveformShape(Enum):
    SINE = "sine"
    TRIANGLE = "triangle"
    ROUNDED_SQUARE = "rounded_square"
    SAWTOOTH = "sawtooth"

MIN_BPM = 5.0
MAX_BPM = 200.0
MIN_SPEED = 5
MAX_SPEED = 100
FULL_INTENSITY = 100

# The two ends a still motion is held at, on the same 0-100 axis the center runs
# on: home, and as far from the user as the travel goes.  Named here because
# every app that holds this motion has to agree which end is which.
PARK_CENTER = 0
RETRACT_CENTER = 100

# The most wall time one tick of a caller's clock may move the phase — see
# :func:`phase_advanced`.
MAX_TICK_SECONDS = 0.1

# How far a float may fall short of a whole bar step and still be that step:
# a ceiling worked out exactly on a step comes back a hair under it.
_ROUNDING = 1e-9
_HALVINGS = 40
_BEND = 80


def bpm_for_speed(speed: int) -> float:
    """Map speed MIN_SPEED-MAX_SPEED to BPM using exponential curve."""
    t = (speed - MIN_SPEED) / (MAX_SPEED - MIN_SPEED)
    return MIN_BPM * (MAX_BPM / MIN_BPM) ** t


def wave_travel(amplitude: float, bpm: float) -> float:
    return 2 * amplitude * bpm / 60


def travel_cap(max_intensity: int) -> float | None:
    if max_intensity >= FULL_INTENSITY:
        return None
    level = bar_level_for(max_intensity)
    return wave_travel(level, bpm_for_speed(level))


def bar_level_for(max_intensity: int) -> float:
    return FULL_INTENSITY * math.log1p(_BEND * max_intensity / FULL_INTENSITY) / math.log1p(_BEND)


def amplitude_ceiling(max_intensity: int, speed: int) -> int:
    cap = travel_cap(max_intensity)
    if cap is None:
        return 100
    return min(100, math.floor(cap / wave_travel(1, bpm_for_speed(speed)) + _ROUNDING))


def speed_ceiling(max_intensity: int, amplitude: int) -> int:
    cap = travel_cap(max_intensity)
    if cap is None:
        return MAX_SPEED
    return _fastest_speed_within(cap / wave_travel(max(1, amplitude), 1))


def _fastest_speed_within(bpm: float) -> int:
    if bpm <= MIN_BPM:
        return MIN_SPEED
    speed = MIN_SPEED + (MAX_SPEED - MIN_SPEED) * math.log(bpm / MIN_BPM) / math.log(MAX_BPM / MIN_BPM)
    return min(MAX_SPEED, math.floor(speed + _ROUNDING))


def _share_of_the_bars_within(cap: float, amplitude: int, speed: int) -> float:
    fits, too_much = 0.0, 1.0
    for _ in range(_HALVINGS):
        share = (fits + too_much) / 2
        if wave_travel(amplitude * share, bpm_for_speed(speed * share)) <= cap:
            fits = share
        else:
            too_much = share
    return fits


def toward_the_park(height: float, kept: float) -> float:
    return PARK_CENTER + (height - PARK_CENTER) * kept


@dataclass
class RobotHandState:
    playing: bool = False
    speed: int = 50
    bpm: float = 0.0
    amplitude: int = 100
    center: int = 50
    intended_center: int = 50
    shape: WaveformShape = WaveformShape.SINE
    max_intensity: int = FULL_INTENSITY
    exact_bars: tuple[float, float, float] | None = field(default=None, compare=False,
                                                           repr=False)

    def __post_init__(self) -> None:
        if self.bpm == 0.0:
            self.bpm = bpm_for_speed(self.speed)
        _recompute_center(self)


def set_speed(state: RobotHandState, speed: int) -> None:
    speed = max(MIN_SPEED, min(speed_ceiling(state.max_intensity, state.amplitude), speed))
    state.speed = speed
    state.bpm = bpm_for_speed(speed)


def adjust_speed(state: RobotHandState, delta: int) -> None:
    set_speed(state, state.speed + delta)


def _recompute_center(state: RobotHandState) -> None:
    """Set effective center from intended_center, clamped to amplitude range."""
    half = state.amplitude // 2
    state.center = max(half, min(100 - half, state.intended_center))


def set_max_intensity(state: RobotHandState, value: int) -> None:
    state.max_intensity = max(0, min(FULL_INTENSITY, value))
    _push_within_the_max_intensity(state)


def set_dials(state: RobotHandState, *, speed: int, amplitude: int, center: int) -> None:
    state.speed = max(MIN_SPEED, min(MAX_SPEED, speed))
    state.bpm = bpm_for_speed(state.speed)
    state.amplitude = max(0, min(100, amplitude))
    state.intended_center = max(0, min(100, center))
    _recompute_center(state)
    _push_within_the_max_intensity(state)


def _push_within_the_max_intensity(state: RobotHandState) -> None:
    cap = travel_cap(state.max_intensity)
    if cap is None or wave_travel(state.amplitude, state.bpm) <= cap:
        return
    amplitude, speed, center = _the_bars_before_rounding(state)
    kept = _share_of_the_bars_within(cap, amplitude, speed)
    state.exact_bars = (amplitude * kept, speed * kept, toward_the_park(center, kept))
    state.amplitude, state.speed, state.intended_center = _rounded(state.exact_bars)
    state.bpm = bpm_for_speed(state.speed)
    state.amplitude = min(state.amplitude, amplitude_ceiling(state.max_intensity, state.speed))
    _recompute_center(state)


def _the_bars_before_rounding(state: RobotHandState) -> tuple[float, float, float]:
    shown = (state.amplitude, state.speed, state.intended_center)
    if state.exact_bars is not None and _rounded(state.exact_bars) == shown:
        return state.exact_bars
    return float(state.amplitude), float(state.speed), float(state.center)


def _rounded(bars: tuple[float, float, float]) -> tuple[int, int, int]:
    amplitude, speed, center = bars
    return (math.floor(amplitude + _ROUNDING),
            max(MIN_SPEED, math.floor(speed + _ROUNDING)),
            round(center))


def set_amplitude(state: RobotHandState, value: int) -> None:
    state.amplitude = max(0, min(amplitude_ceiling(state.max_intensity, state.speed), value))
    _recompute_center(state)


def adjust_amplitude(state: RobotHandState, delta: int) -> None:
    set_amplitude(state, state.amplitude + delta)


def set_center(state: RobotHandState, value: int) -> None:
    state.intended_center = max(0, min(100, value))
    _recompute_center(state)


def adjust_center(state: RobotHandState, delta: int) -> None:
    half = state.amplitude // 2
    lo, hi = half, 100 - half
    new = state.intended_center + delta
    if new < lo:
        if state.intended_center <= lo:
            return
        new = lo
    elif new > hi:
        if state.intended_center >= hi:
            return
        new = hi
    new = max(0, min(100, new))
    state.intended_center = new
    _recompute_center(state)


def cycle_shape(state: RobotHandState, step: int = 1) -> None:
    """Advance the waveform shape by *step* (default +1; pass -1 to go back)."""
    shapes = list(WaveformShape)
    idx = shapes.index(state.shape)
    state.shape = shapes[(idx + step) % len(shapes)]


def _waveform_raw(phase: float, shape: WaveformShape) -> float:
    """Return 0-1 normalized waveform value for one round trip per cycle."""
    frac = phase % 1.0
    if shape is WaveformShape.TRIANGLE:
        return 1 - abs(2 * frac - 1)
    if shape is WaveformShape.ROUNDED_SQUARE:
        k = 3.0
        return (1 - math.tanh(k * math.cos(2 * math.pi * frac)) / math.tanh(k)) / 2
    if shape is WaveformShape.SAWTOOTH:
        rise = 0.3
        if frac < rise:
            return frac / rise
        return 1 - (frac - rise) / (1 - rise)
    # SINE, and the fall-through with it: an unhandled shape still moves.
    return (1 - math.cos(2 * math.pi * phase)) / 2


def trace_window(
    shape: WaveformShape,
    amplitude: int,
    center: int,
    *,
    phase: float,
    bpm: float,
    samples: int,
    span_s: float,
) -> tuple[list[float], float]:
    """The wave as the readout draws it: *samples* + 1 heights (0-1) on knots
    a fixed stretch of phase apart, the first at or before *phase* and the
    last just past the far edge, and how far past the first knot *phase* sits
    as a fraction of one.

    *phase* has to be the wave's phase counted up without wrapping (the
    sender's), so the knots stay put from one cycle to the next; the heights
    change only when the phase crosses a knot, and between knots the painter
    slides the whole line by the fraction.  Sampled from the phase itself
    instead, the heights at fixed columns changed every frame as the wave
    passed under them.
    """
    grid = span_s / max(1, samples - 1) * bpm / 60.0
    if grid <= 0:
        held = position_fraction(phase, shape=shape, amplitude=amplitude, center=center)
        return [held] * (samples + 1), 0.0
    first = math.floor(phase / grid) * grid
    heights = [
        position_fraction(first + i * grid, shape=shape, amplitude=amplitude, center=center)
        for i in range(samples + 1)
    ]
    return heights, (phase - first) / grid


def position_fraction(
    phase: float,
    *,
    shape: WaveformShape = WaveformShape.SINE,
    amplitude: int = 100,
    center: int = 50,
) -> float:
    """Where the motion sits at *phase*, 0 (the floor of the axis) to 1 (the ceiling).

    The scale-free form of :func:`phase_to_position`. Callers speaking T-Code
    want that one's 0-9999; a readout drawing a trace, or an app whose device
    layer takes percent, wants this.
    """
    raw = _waveform_raw(phase, shape)
    half = amplitude / 100 / 2
    low = max(0.0, center / 100 - half)
    high = min(1.0, center / 100 + half)
    return min(1.0, max(0.0, low + raw * (high - low)))


def phase_to_position(
    phase: float,
    *,
    shape: WaveformShape = WaveformShape.SINE,
    amplitude: int = 100,
    center: int = 50,
) -> int:
    return round(POSITION_MAX * position_fraction(
        phase, shape=shape, amplitude=amplitude, center=center))


def phase_for_position_fraction(
    fraction: float,
    *,
    shape: WaveformShape = WaveformShape.SINE,
    amplitude: int = 100,
    center: int = 50,
    rising: bool = True,
    samples: int = 720,
) -> float:
    """The phase that puts the motion at *fraction* of the axis, on its way up
    (*rising*) or on its way down.

    :func:`position_fraction` inverted.  Every shape here is one round trip a
    cycle, so it takes each height twice and the caller has to say which visit it
    means.  Found by walking a sampled cycle rather than by four hand-written
    inversions -- a seek asks for this once, and half a degree of phase is finer
    than the frame a flick can show for it.  With the amplitude turned down the
    wave never reaches the ends, and the nearest phase to an unreachable height
    is the peak or the trough, which is where the motion would put the picture.
    """
    fraction = min(1.0, max(0.0, fraction))
    heights = [
        position_fraction(i / samples, shape=shape, amplitude=amplitude, center=center)
        for i in range(samples)
    ]
    best, best_gap = 0.0, None
    for i, height in enumerate(heights):
        if (heights[(i + 1) % samples] >= height) is not rising:
            continue
        gap = abs(height - fraction)
        if best_gap is None or gap < best_gap:
            best, best_gap = i / samples, gap
    return best


def phase_advanced(phase: float, bpm: float, dt_s: float) -> float:
    """*phase* moved on by *dt_s* seconds of motion at *bpm* cycles a minute.

    The step is capped at :data:`MAX_TICK_SECONDS`, because a clock that stalled
    — the app blocked, the machine suspended — comes back owing a step no device
    should be asked to take at once. The motion slows through the gap instead of
    slingshotting across it, which is the same cap Genau's engine puts on its
    own tick.
    """
    return (phase + max(0.0, min(dt_s, MAX_TICK_SECONDS)) * bpm / 60.0) % 1.0


@dataclass(frozen=True)
class ControlLimits:
    """Which of the hand's arrows would do nothing.

    Six booleans, published twice: the status file an orchestrator reads has
    them so its dashboard can dim a button, and the drive readout the console
    draws has them so it can dim an arrow.  They are two publications of one
    fact, worked out once here -- the center clamp included, so a change to it
    cannot leave the console dimming an arrow the status file calls live.
    """

    amp_at_max: bool
    amp_at_min: bool
    ctr_at_max: bool
    ctr_at_min: bool
    spd_at_max: bool
    spd_at_min: bool


def control_limits(hand: RobotHandState) -> ControlLimits:
    # The center's range is what the travel leaves it: it cannot push a motion
    # off the ceiling or floor of the device, so it stops half a travel in from
    # each end.
    half = hand.amplitude // 2
    return ControlLimits(
        amp_at_max=hand.amplitude >= amplitude_ceiling(hand.max_intensity, hand.speed),
        amp_at_min=hand.amplitude <= 0,
        ctr_at_max=hand.center >= 100 - half,
        ctr_at_min=hand.center <= half,
        spd_at_max=hand.speed >= speed_ceiling(hand.max_intensity, hand.amplitude),
        spd_at_min=hand.speed <= MIN_SPEED,
    )
