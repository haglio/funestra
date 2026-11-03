from __future__ import annotations

from dataclasses import dataclass, replace

from shared_ui.spacing import GAP_MEDIUM, GAP_SMALL

from .geometry import Rect

AMPLITUDE, CENTER, SPEED = "amp", "center", "speed"
MAX_INTENSITY = "max_intensity"

LESS, MORE = "minus", "plus"

_LABEL_H = 14
_BAR_H = 12
_CTRL = 14
_MARK_GAP = GAP_SMALL
_GAP = GAP_MEDIUM
_WAVE_H = 96
_CTR_LABEL_W = 34
_AMP_LABEL_W = 25
_WAVE_W = 2 * (_CTRL + _MARK_GAP) + _WAVE_H

SECTION_W = _CTR_LABEL_W + _GAP + _CTRL + _GAP + _WAVE_W + _MARK_GAP + _CTRL + _GAP + _AMP_LABEL_W
SECTION_H = _CTRL + _MARK_GAP + _WAVE_H + _MARK_GAP + _CTRL + 2 + _LABEL_H

TRACE_SAMPLES = 80

LABEL_H = _LABEL_H
BAR_H = _BAR_H
CONTROL_SIZE = _CTRL
GAP = _GAP


def section_size() -> tuple[int, int]:
    return SECTION_W, SECTION_H


@dataclass(frozen=True)
class DriveControl:
    rect: Rect
    command: str
    mark: str
    dim: bool


@dataclass(frozen=True)
class DriveTrack:
    rect: Rect
    axis: str
    tooltip: str
    center: float = 0.5
    dim: bool = False
    ceiling: int = 100
    handle_of: Rect | None = None


@dataclass(frozen=True)
class Geometry:
    wave: Rect
    speed_bar: Rect
    speed_down: Rect
    speed_up: Rect
    amp_bar: Rect
    amp_up: Rect
    amp_down: Rect
    center_up: Rect
    center_down: Rect
    center_label: Rect
    center_handle: Rect
    amp_label: Rect
    speed_label_y: int
    speed_label_x: int


def geometry(x: int, y: int, center_frac: float) -> Geometry:
    ctr_ctrl_x = x + _CTR_LABEL_W + _GAP
    wave_x = ctr_ctrl_x + _CTRL + _GAP
    amp_x = wave_x + _WAVE_W + _MARK_GAP
    wave_y = y + _CTRL + _MARK_GAP
    wave = (wave_x, wave_y, _WAVE_W, _WAVE_H)
    wave_lower = wave_y + _WAVE_H

    amp_bar_h = _WAVE_H
    amp_up = (amp_x, y, _CTRL, _CTRL)
    amp_bar = (amp_x + (_CTRL - _BAR_H) // 2, wave_y, _BAR_H, amp_bar_h)
    amp_down = (amp_x, wave_lower + _MARK_GAP, _CTRL, _CTRL)

    center_y = wave_y + round((1 - center_frac) * (_WAVE_H - 1))
    up_y = min(max(wave_y, center_y - _CTRL - _MARK_GAP // 2), wave_lower - 2 * _CTRL - _MARK_GAP)
    center_up = (ctr_ctrl_x, up_y, _CTRL, _CTRL)
    center_down = (ctr_ctrl_x, up_y + _CTRL + _MARK_GAP, _CTRL, _CTRL)
    label_h = 2 * _CTRL + _MARK_GAP
    center_label = (x, up_y, _CTR_LABEL_W, label_h)
    center_handle = (x, up_y, _CTR_LABEL_W + _GAP, label_h)
    amp_label = (amp_x + _CTRL + _GAP, wave_y + (_WAVE_H - label_h) // 2, _AMP_LABEL_W, label_h)

    speed_y = wave_lower + _MARK_GAP
    bar_x = wave_x + _CTRL + _MARK_GAP
    speed_down = (wave_x, speed_y, _CTRL, _CTRL)
    speed_up = (bar_x + amp_bar_h + _MARK_GAP, speed_y, _CTRL, _CTRL)
    speed_bar = (bar_x, speed_y + (_CTRL - _BAR_H) // 2, amp_bar_h, _BAR_H)

    return Geometry(
        wave=wave, speed_bar=speed_bar, speed_down=speed_down, speed_up=speed_up,
        amp_bar=amp_bar, amp_up=amp_up, amp_down=amp_down,
        center_up=center_up, center_down=center_down,
        center_label=center_label, center_handle=center_handle, amp_label=amp_label,
        speed_label_y=speed_y + _CTRL + 2,
        speed_label_x=bar_x + amp_bar_h // 2,
    )


@dataclass(frozen=True)
class Limits:
    spd_at_min: bool = False
    spd_at_max: bool = False
    amp_at_min: bool = False
    amp_at_max: bool = False
    ctr_at_min: bool = False
    ctr_at_max: bool = False


def controls(x: int, y: int, center: int, limits: Limits, *,
             dim: bool = False) -> list[DriveControl]:
    g = geometry(x, y, fraction(center))
    return [
        DriveControl(g.speed_down, "robot_hand_speed_down", LESS, dim or limits.spd_at_min),
        DriveControl(g.speed_up, "robot_hand_speed_up", MORE, dim or limits.spd_at_max),
        DriveControl(g.amp_up, "robot_hand_amplitude_up", MORE, dim or limits.amp_at_max),
        DriveControl(g.amp_down, "robot_hand_amplitude_down", LESS, dim or limits.amp_at_min),
        DriveControl(g.center_up, "robot_hand_center_up", MORE, dim or limits.ctr_at_max),
        DriveControl(g.center_down, "robot_hand_center_down", LESS, dim or limits.ctr_at_min),
    ]


def tracks(x: int, y: int, center: int, *, dim: bool = False,
           amplitude_ceiling: int = 100, speed_ceiling: int = 100) -> list[DriveTrack]:
    center_frac = fraction(center)
    g = geometry(x, y, center_frac)
    return [
        DriveTrack(g.amp_bar, AMPLITUDE, "Set how far the motion reaches",
                   center_frac, dim, amplitude_ceiling),
        DriveTrack(g.wave, CENTER, "Set where the motion is centered",
                   center_frac, dim),
        DriveTrack(g.speed_bar, SPEED, "Set how fast the motion goes",
                   center_frac, dim, speed_ceiling),
    ]


def center_handle(x: int, y: int, center: int, *, dim: bool = False) -> DriveTrack:
    center_frac = fraction(center)
    g = geometry(x, y, center_frac)
    return DriveTrack(g.center_handle, CENTER, "Drag to move where the motion is centered",
                      center_frac, dim, handle_of=g.wave)


def held_bar(track: DriveTrack, py: float) -> tuple[DriveTrack, float]:
    if track.handle_of is None:
        return track, 0.0
    bar = replace(track, rect=track.handle_of, handle_of=None)
    _x, y, _w, h = bar.rect
    return bar, py - (y + (1 - bar.center) * (h - 1))


def track_value(track: DriveTrack, px: int, py: float) -> int:
    return min(track.ceiling, _level_under(track, px, py))


def _level_under(track: DriveTrack, px: int, py: float) -> int:
    x, y, w, h = track.rect
    if track.axis in (SPEED, MAX_INTENSITY):
        return percent((px - x) / max(1, w - 1))
    height = clamp01(1 - (py - y) / max(1, h - 1))
    if track.axis == CENTER:
        return percent(height)
    return percent(2 * abs(height - track.center))


def fraction(percent_value: int) -> float:
    return clamp01(percent_value / 100)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def percent(fraction_value: float) -> int:
    return round(100 * clamp01(fraction_value))
