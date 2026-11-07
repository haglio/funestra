from __future__ import annotations

from dataclasses import replace
from typing import NamedTuple

from funestra.funscript import HANDOFF_RAMP_MS, PARK_TOUCH_WAIT_CAP_MS
from funestra.osr2_visualizer import (
    DRIVEN_BY_FUNSCRIPT,
    DRIVEN_BY_NEUTRAL,
    DRIVEN_BY_NOTHING,
    DRIVEN_BY_ROBOT_HAND,
    POSITION_MAX,
    TRACE_SAMPLES,
    DriveHud,
)

from .descent_latch import DescentChoice, DescentLatch, DriveKey
from .robot_hand import FULL_INTENSITY, ON_THE_PARK_WITHIN
from .trace_grid import on_the_grid

_ARBITER_LAG_MS = 350

_SEAM_FEATHER_MS = 300

_LATCH_WITHIN_MS = 3000


class Playhead(NamedTuple):
    position_ms: int
    speed: float = 1.0
    max_intensity: int = FULL_INTENSITY


class _Reading:
    def __init__(self, base: DriveHud, script, playhead: Playhead,
                 latch: DescentLatch | None) -> None:
        self.base = base
        self.script = script
        self.latch = latch
        self.position_ms = on_the_grid(playhead.position_ms)
        self.speed = playhead.speed
        self.max_intensity = playhead.max_intensity
        self.span_ms = round(base.trace_seconds * 1000 * self.speed)
        self.step = self.span_ms / max(1, TRACE_SAMPLES - 1)
        self.ramp_ms = round(HANDOFF_RAMP_MS * self.speed)
        motion = None
        if len(base.waveform) == TRACE_SAMPLES:
            motion = base.waveform + ((base.edge,) if base.edge is not None else ())
        self.motion = motion
        self.resume_base = 0.0
        if motion is not None and base.let_go is None:
            self.resume_base = float(min(range(TRACE_SAMPLES), key=motion.__getitem__))
        self.climb_ms = 0
        if motion is not None and _motion_at(self, self.resume_base) > ON_THE_PARK_WITHIN:
            self.climb_ms = self.ramp_ms


def _planned_window(r: _Reading) -> tuple[list[float], float]:
    return r.script.planned_trace_window(
        r.position_ms, r.span_ms, TRACE_SAMPLES, r.speed,
        max_intensity=r.max_intensity)


def _planned_position(r: _Reading) -> float:
    return r.script.planned_position_at(
        r.position_ms, r.speed, max_intensity=r.max_intensity) / 100


def _motion_at(r: _Reading, index: float) -> float:
    motion = r.motion
    last = len(motion) - 1
    if index <= 0:
        return motion[0]
    if index >= last:
        return motion[last]
    whole = int(index)
    frac = index - whole
    if not frac:
        return motion[whole]
    return motion[whole] * (1 - frac) + motion[whole + 1] * frac


def _genau_height(r: _Reading, sample_ms: int, began: int | None) -> float:
    if r.motion is None:
        return 0.0
    if began is None or began + r.climb_ms <= r.position_ms:
        return _motion_at(r, (sample_ms - r.position_ms) / r.step + r.base.slide)
    return _motion_at(r, r.resume_base + (sample_ms - began - r.climb_ms) / r.step)


def _eased_onto_the_seam(
        r: _Reading, value: float, ms_to_seam: int, seam_value: float) -> float:
    weight = 1 - ms_to_seam / _feather_ms(r)
    return value * (1 - weight) + seam_value * weight


def _feather_ms(r: _Reading) -> int:
    return round(_SEAM_FEATHER_MS * r.speed)


def _park_touch_after(r: _Reading, turn_start: int, began: int | None) -> int | None:
    if r.motion is None or min(r.motion) > ON_THE_PARK_WITHIN:
        return None
    scan_from = turn_start + round(_ARBITER_LAG_MS * r.speed)
    scan_to = scan_from + round(PARK_TOUCH_WAIT_CAP_MS * r.speed)
    if scan_to > r.position_ms + r.span_ms:
        return turn_start
    at_ms = float(scan_from)
    while at_ms <= scan_to:
        if _genau_height(r, round(at_ms), began) <= ON_THE_PARK_WITHIN:
            return round(at_ms)
        at_ms += r.step / 4
    return None


def _descent_entry(r: _Reading, turn_start: int) -> tuple[float, int | None]:
    base = r.base
    latched = r.latch.choice_for(turn_start) if r.latch is not None else None
    key = DriveKey.cut_from(base)
    if latched is not None and latched.key == key:
        return latched.top, latched.touch
    prev_began, _ = r.script.turn_bounds_at(max(turn_start - 1, 0))
    if base.let_go is not None and r.position_ms >= turn_start:
        top = base.let_go
    else:
        top = _genau_height(r, turn_start, prev_began)
    if (latched is not None and latched.key.let_go is None
            and base.let_go is not None):
        touch = latched.touch
    else:
        touch = _park_touch_after(r, turn_start, prev_began)
    frozen = (r.position_ms >= turn_start - round(_LATCH_WITHIN_MS * r.speed)
              and (base.let_go is None or r.position_ms >= turn_start))
    if r.latch is not None and (frozen or latched is not None):
        the_scan_for_a_boundary_is_over_after = round(
            (PARK_TOUCH_WAIT_CAP_MS + _ARBITER_LAG_MS) * r.speed)
        r.latch.remember(turn_start, DescentChoice(key, top, touch),
                         stale_before=r.position_ms - the_scan_for_a_boundary_is_over_after)
    return top, touch


def _at(r: _Reading, sample_ms: int, planned: float) -> tuple[float, str]:
    if r.script.is_resting_at(sample_ms):
        return _resting_at(r, sample_ms)
    turn_start, _turn_end = r.script.turn_bounds_at(sample_ms)
    if turn_start is not None and r.motion is not None:
        coming_down = _coming_down_at(r, sample_ms, turn_start)
        if coming_down is not None:
            return coming_down
    who = (DRIVEN_BY_NEUTRAL if r.script.is_parked_at(sample_ms)
           else DRIVEN_BY_FUNSCRIPT)
    return planned, who


def _resting_at(r: _Reading, sample_ms: int) -> tuple[float, str]:
    if r.motion is None:
        return 0.0, DRIVEN_BY_NOTHING
    began, ends_at = r.script.turn_bounds_at(sample_ms)
    if began is not None and r.climb_ms:
        since = sample_ms - began
        if since < r.climb_ms:
            top = _motion_at(r, r.resume_base)
            return top * max(0, since) / r.climb_ms, DRIVEN_BY_NEUTRAL
    value = _genau_height(r, sample_ms, began)
    if ends_at is not None and ends_at - sample_ms < _feather_ms(r):
        seam_top, seam_touch = _descent_entry(r, ends_at)
        if seam_touch is None:
            value = _eased_onto_the_seam(
                r, value, ends_at - sample_ms, seam_top)
    return value, DRIVEN_BY_ROBOT_HAND


def _coming_down_at(r: _Reading, sample_ms: int, turn_start: int) -> tuple[float, str] | None:
    top, touch = _descent_entry(r, turn_start)
    if touch is None:
        since = sample_ms - turn_start
        if since < r.ramp_ms:
            return top * (1 - max(0, since) / r.ramp_ms), DRIVEN_BY_NEUTRAL
        return None
    if sample_ms <= touch and r.base.let_go is None:
        prev_began, _ = r.script.turn_bounds_at(max(turn_start - 1, 0))
        value = _genau_height(r, sample_ms, prev_began)
        if touch - sample_ms < _feather_ms(r):
            value = _eased_onto_the_seam(
                r, value, touch - sample_ms, 0.0)
        return value, DRIVEN_BY_ROBOT_HAND
    return None


def _driver_runs(whos: list[str]) -> tuple[tuple[int, str], ...]:
    marks: list[tuple[int, str]] = []
    for index, who in enumerate(whos):
        if not marks or marks[-1][1] != who:
            marks.append((index, who))
    return tuple(marks)


def osr2_visualizer(
    published: DriveHud | None,
    playhead: Playhead,
    *,
    script,
    latch: DescentLatch | None = None,
) -> DriveHud:
    base = published or DriveHud()
    if script is None:
        return base
    reading = _Reading(base, script, playhead, latch)
    scripted, slide = _planned_window(reading)
    if len(scripted) != TRACE_SAMPLES + 1:
        return base
    anchor_ms = reading.position_ms - slide * reading.step
    values: list[float] = []
    whos: list[str] = []
    for index in range(TRACE_SAMPLES):
        value, who = _at(reading, round(anchor_ms + index * reading.step), scripted[index])
        values.append(value)
        whos.append(who)

    edge, _who = _at(
        reading,
        round(anchor_ms + TRACE_SAMPLES * reading.step), scripted[TRACE_SAMPLES])
    height, who_now = _at(reading, reading.position_ms, _planned_position(reading))
    marker = (base.position if who_now == DRIVEN_BY_ROBOT_HAND
              else round(height * POSITION_MAX))
    return replace(
        base,
        driven=who_now,
        waveform=tuple(values),
        slide=slide,
        edge=edge,
        segments=_driver_runs(whos),
        position=marker,
    )
