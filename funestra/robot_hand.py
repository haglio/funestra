from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple

from .tcode import POSITION_MAX


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

PARK_CENTER = 0
RETRACT_CENTER = 100

MAX_TICK_SECONDS = 0.1

_ROUNDING = 1e-9
_HALVINGS = 40
_BEND = 80


def bpm_for_speed(speed: int) -> float:
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
    half = state.amplitude // 2
    state.center = max(half, min(100 - half, state.intended_center))


def set_max_intensity(state: RobotHandState, value: int) -> None:
    state.max_intensity = max(0, min(FULL_INTENSITY, value))
    _push_within_the_max_intensity(state)


def set_bars(state: RobotHandState, *, speed: int, amplitude: int, center: int) -> None:
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
    shapes = list(WaveformShape)
    idx = shapes.index(state.shape)
    state.shape = shapes[(idx + step) % len(shapes)]


def _waveform_raw(phase: float, shape: WaveformShape) -> float:
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
    return (1 - math.cos(2 * math.pi * phase)) / 2


class Waveform(NamedTuple):
    shape: WaveformShape
    amplitude: int
    center: int


class TraceSpan(NamedTuple):
    phase: float
    bpm: float
    samples: int
    span_s: float


def trace_window(waveform: Waveform, span: TraceSpan) -> tuple[list[float], float]:
    phase, bpm, samples, span_s = span
    grid = span_s / max(1, samples - 1) * bpm / 60.0
    if grid <= 0:
        held = position_fraction(phase, **waveform._asdict())
        return [held] * (samples + 1), 0.0
    first = math.floor(phase / grid) * grid
    heights = [
        position_fraction(first + i * grid, **waveform._asdict())
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


_PHASE_SEARCH_SAMPLES = 720


def phase_for_position_fraction(
    fraction: float,
    *,
    shape: WaveformShape = WaveformShape.SINE,
    amplitude: int = 100,
    center: int = 50,
    rising: bool = True,
) -> float:
    samples = _PHASE_SEARCH_SAMPLES
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
    return (phase + max(0.0, min(dt_s, MAX_TICK_SECONDS)) * bpm / 60.0) % 1.0


@dataclass(frozen=True)
class ControlLimits:
    amp_at_max: bool
    amp_at_min: bool
    ctr_at_max: bool
    ctr_at_min: bool
    spd_at_max: bool
    spd_at_min: bool


def control_limits(hand: RobotHandState) -> ControlLimits:
    half = hand.amplitude // 2
    return ControlLimits(
        amp_at_max=hand.amplitude >= amplitude_ceiling(hand.max_intensity, hand.speed),
        amp_at_min=hand.amplitude <= 0,
        ctr_at_max=hand.center >= 100 - half,
        ctr_at_min=hand.center <= half,
        spd_at_max=hand.speed >= speed_ceiling(hand.max_intensity, hand.amplitude),
        spd_at_min=hand.speed <= MIN_SPEED,
    )
