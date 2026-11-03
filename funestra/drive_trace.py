"""What the device is about to be asked to do, and by whom: the trace's model, free of Pillow."""
from __future__ import annotations

from dataclasses import replace

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


def osr2_visualizer(
    published: DriveHud | None,
    *,
    script,
    position_ms: int,
    speed: float = 1.0,
    latch: DescentLatch | None = None,
    max_intensity: int = FULL_INTENSITY,
) -> DriveHud:
    base = published or DriveHud()
    if script is None:
        return base
    position_ms = on_the_grid(position_ms)
    span_ms = round(base.trace_seconds * 1000 * speed)
    step = span_ms / max(1, TRACE_SAMPLES - 1)
    ramp_ms = round(HANDOFF_RAMP_MS * speed)
    scripted, slide = script.planned_trace_window(
        position_ms, span_ms, TRACE_SAMPLES, speed, max_intensity=max_intensity)
    if len(scripted) != TRACE_SAMPLES + 1:
        return base
    anchor_ms = position_ms - slide * step
    motion = None
    if len(base.waveform) == TRACE_SAMPLES:
        motion = base.waveform + ((base.edge,) if base.edge is not None else ())

    def motion_at(index: float) -> float:
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

    resume_base = 0.0
    if motion is not None and base.let_go is None:
        resume_base = float(min(range(TRACE_SAMPLES), key=motion.__getitem__))
    climb_ms = 0
    if motion is not None and motion_at(resume_base) > _PARK_EPSILON:
        climb_ms = ramp_ms

    def genau_height(sample_ms: int, began: int | None) -> float:
        if motion is None:
            return 0.0
        if began is None or began + climb_ms <= position_ms:
            return motion_at((sample_ms - position_ms) / step + base.slide)
        return motion_at(resume_base + (sample_ms - began - climb_ms) / step)

    def park_touch_after(turn_start: int, began: int | None) -> int | None:
        if motion is None or min(motion) > _PARK_EPSILON:
            return None
        scan_from = turn_start + round(_TOUCH_LAG_MS * speed)
        scan_to = scan_from + round(PARK_TOUCH_WAIT_CAP_MS * speed)
        if scan_to > position_ms + span_ms:
            return turn_start
        at_ms = float(scan_from)
        while at_ms <= scan_to:
            if genau_height(round(at_ms), began) <= _PARK_EPSILON:
                return round(at_ms)
            at_ms += step / 4
        return None

    def descent_entry(turn_start: int) -> tuple[float, int | None]:
        latched = latch.choice_for(turn_start) if latch is not None else None
        key = DriveKey.cut_from(base)
        if latched is not None and latched.key == key:
            return latched.top, latched.touch
        prev_began, _ = script.turn_bounds_at(max(turn_start - 1, 0))
        if base.let_go is not None and position_ms >= turn_start:
            top = base.let_go
        else:
            top = genau_height(turn_start, prev_began)
        if (latched is not None and latched.key.let_go is None
                and base.let_go is not None):
            touch = latched.touch
        else:
            touch = park_touch_after(turn_start, prev_began)
        frozen = (position_ms >= turn_start - round(_TOUCH_FREEZE_AHEAD_MS * speed)
                  and (base.let_go is None or position_ms >= turn_start))
        if latch is not None and (frozen or latched is not None):
            horizon = round((PARK_TOUCH_WAIT_CAP_MS + _TOUCH_LAG_MS) * speed)
            latch.remember(turn_start, DescentChoice(key, top, touch),
                           stale_before=position_ms - horizon)
        return top, touch

    def at(sample_ms: int, planned: float) -> tuple[float, str]:
        if script.is_resting_at(sample_ms):
            if motion is None:
                return 0.0, DRIVEN_BY_NOTHING
            began, ends_at = script.turn_bounds_at(sample_ms)
            if began is not None and climb_ms:
                since = sample_ms - began
                if since < climb_ms:
                    top = motion_at(resume_base)
                    return top * max(0, since) / climb_ms, DRIVEN_BY_NEUTRAL
            value = genau_height(sample_ms, began)
            feather_ms = round(_SEAM_FEATHER_MS * speed)
            if ends_at is not None and ends_at - sample_ms < feather_ms:
                seam_top, seam_touch = descent_entry(ends_at)
                if seam_touch is None:
                    weight = 1 - (ends_at - sample_ms) / feather_ms
                    value = value * (1 - weight) + seam_top * weight
            return value, DRIVEN_BY_ROBOT_HAND
        turn_start, _turn_end = script.turn_bounds_at(sample_ms)
        if turn_start is not None and motion is not None:
            top, touch = descent_entry(turn_start)
            if touch is not None:
                if sample_ms <= touch and base.let_go is None:
                    prev_began, _ = script.turn_bounds_at(max(turn_start - 1, 0))
                    value = genau_height(sample_ms, prev_began)
                    feather_ms = round(_SEAM_FEATHER_MS * speed)
                    if touch - sample_ms < feather_ms:
                        weight = 1 - (touch - sample_ms) / feather_ms
                        value = value * (1 - weight)
                    return value, DRIVEN_BY_ROBOT_HAND
            else:
                since = sample_ms - turn_start
                if since < ramp_ms:
                    return top * (1 - max(0, since) / ramp_ms), DRIVEN_BY_NEUTRAL
        who = (DRIVEN_BY_NEUTRAL if script.is_parked_at(sample_ms)
               else DRIVEN_BY_FUNSCRIPT)
        return planned, who

    values: list[float] = []
    whos: list[str] = []
    for index in range(TRACE_SAMPLES):
        value, who = at(round(anchor_ms + index * step), scripted[index])
        values.append(value)
        whos.append(who)

    marks: list[tuple[int, str]] = []
    for index, who in enumerate(whos):
        if not marks or marks[-1][1] != who:
            marks.append((index, who))
    edge, _who = at(
        round(anchor_ms + TRACE_SAMPLES * step), scripted[TRACE_SAMPLES])
    height, who_now = at(
        position_ms, script.planned_position_at(position_ms, speed, max_intensity=max_intensity) / 100)
    marker = (base.position if who_now == DRIVEN_BY_ROBOT_HAND
              else round(height * POSITION_MAX))
    return replace(
        base,
        driven=who_now,
        waveform=tuple(values),
        slide=slide,
        edge=edge,
        segments=tuple(marks),
        position=marker,
    )
