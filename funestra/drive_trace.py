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
from .robot_hand import FULL_INTENSITY
from .trace_grid import on_the_grid

_PARK_EPSILON = 0.02

_TOUCH_LAG_MS = 350

_SEAM_FEATHER_MS = 300

_TOUCH_FREEZE_AHEAD_MS = 3000


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
        self.motion = None
        if len(base.waveform) == TRACE_SAMPLES:
            self.motion = base.waveform + ((base.edge,) if base.edge is not None else ())
        self.resume_base = 0.0
        if self.motion is not None and base.let_go is None:
            self.resume_base = float(
                min(range(TRACE_SAMPLES), key=self.motion.__getitem__))
        self.climb_ms = 0
        if self.motion is not None and self.motion_at(self.resume_base) > _PARK_EPSILON:
            self.climb_ms = self.ramp_ms

    def planned_window(self) -> tuple[list[float], float]:
        return self.script.planned_trace_window(
            self.position_ms, self.span_ms, TRACE_SAMPLES, self.speed,
            max_intensity=self.max_intensity)

    def planned_position(self) -> float:
        return self.script.planned_position_at(
            self.position_ms, self.speed, max_intensity=self.max_intensity) / 100

    def motion_at(self, index: float) -> float:
        motion = self.motion
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

    def genau_height(self, sample_ms: int, began: int | None) -> float:
        if self.motion is None:
            return 0.0
        if began is None or began + self.climb_ms <= self.position_ms:
            return self.motion_at((sample_ms - self.position_ms) / self.step + self.base.slide)
        return self.motion_at(self.resume_base + (sample_ms - began - self.climb_ms) / self.step)

    def park_touch_after(self, turn_start: int, began: int | None) -> int | None:
        if self.motion is None or min(self.motion) > _PARK_EPSILON:
            return None
        scan_from = turn_start + round(_TOUCH_LAG_MS * self.speed)
        scan_to = scan_from + round(PARK_TOUCH_WAIT_CAP_MS * self.speed)
        if scan_to > self.position_ms + self.span_ms:
            return turn_start
        at_ms = float(scan_from)
        while at_ms <= scan_to:
            if self.genau_height(round(at_ms), began) <= _PARK_EPSILON:
                return round(at_ms)
            at_ms += self.step / 4
        return None

    def descent_entry(self, turn_start: int) -> tuple[float, int | None]:
        base = self.base
        latched = self.latch.choice_for(turn_start) if self.latch is not None else None
        key = DriveKey.cut_from(base)
        if latched is not None and latched.key == key:
            return latched.top, latched.touch
        prev_began, _ = self.script.turn_bounds_at(max(turn_start - 1, 0))
        if base.let_go is not None and self.position_ms >= turn_start:
            top = base.let_go
        else:
            top = self.genau_height(turn_start, prev_began)
        if (latched is not None and latched.key.let_go is None
                and base.let_go is not None):
            touch = latched.touch
        else:
            touch = self.park_touch_after(turn_start, prev_began)
        frozen = (self.position_ms >= turn_start - round(_TOUCH_FREEZE_AHEAD_MS * self.speed)
                  and (base.let_go is None or self.position_ms >= turn_start))
        if self.latch is not None and (frozen or latched is not None):
            horizon = round((PARK_TOUCH_WAIT_CAP_MS + _TOUCH_LAG_MS) * self.speed)
            self.latch.remember(turn_start, DescentChoice(key, top, touch),
                                stale_before=self.position_ms - horizon)
        return top, touch

    def at(self, sample_ms: int, planned: float) -> tuple[float, str]:
        if self.script.is_resting_at(sample_ms):
            return self._resting_at(sample_ms)
        turn_start, _turn_end = self.script.turn_bounds_at(sample_ms)
        if turn_start is not None and self.motion is not None:
            coming_down = self._coming_down_at(sample_ms, turn_start)
            if coming_down is not None:
                return coming_down
        who = (DRIVEN_BY_NEUTRAL if self.script.is_parked_at(sample_ms)
               else DRIVEN_BY_FUNSCRIPT)
        return planned, who

    def _resting_at(self, sample_ms: int) -> tuple[float, str]:
        if self.motion is None:
            return 0.0, DRIVEN_BY_NOTHING
        began, ends_at = self.script.turn_bounds_at(sample_ms)
        if began is not None and self.climb_ms:
            since = sample_ms - began
            if since < self.climb_ms:
                top = self.motion_at(self.resume_base)
                return top * max(0, since) / self.climb_ms, DRIVEN_BY_NEUTRAL
        value = self.genau_height(sample_ms, began)
        feather_ms = round(_SEAM_FEATHER_MS * self.speed)
        if ends_at is not None and ends_at - sample_ms < feather_ms:
            seam_top, seam_touch = self.descent_entry(ends_at)
            if seam_touch is None:
                weight = 1 - (ends_at - sample_ms) / feather_ms
                value = value * (1 - weight) + seam_top * weight
        return value, DRIVEN_BY_ROBOT_HAND

    def _coming_down_at(self, sample_ms: int, turn_start: int) -> tuple[float, str] | None:
        top, touch = self.descent_entry(turn_start)
        if touch is None:
            since = sample_ms - turn_start
            if since < self.ramp_ms:
                return top * (1 - max(0, since) / self.ramp_ms), DRIVEN_BY_NEUTRAL
            return None
        if sample_ms <= touch and self.base.let_go is None:
            prev_began, _ = self.script.turn_bounds_at(max(turn_start - 1, 0))
            value = self.genau_height(sample_ms, prev_began)
            feather_ms = round(_SEAM_FEATHER_MS * self.speed)
            if touch - sample_ms < feather_ms:
                weight = 1 - (touch - sample_ms) / feather_ms
                value = value * (1 - weight)
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
    scripted, slide = reading.planned_window()
    if len(scripted) != TRACE_SAMPLES + 1:
        return base
    anchor_ms = reading.position_ms - slide * reading.step
    values: list[float] = []
    whos: list[str] = []
    for index in range(TRACE_SAMPLES):
        value, who = reading.at(round(anchor_ms + index * reading.step), scripted[index])
        values.append(value)
        whos.append(who)

    edge, _who = reading.at(
        round(anchor_ms + TRACE_SAMPLES * reading.step), scripted[TRACE_SAMPLES])
    height, who_now = reading.at(reading.position_ms, reading.planned_position())
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
