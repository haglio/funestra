"""Where the drive readout's parts sit, and what a press on one of them asks for.

The readout — the trace of the motion with Center down its left, Amplitude down
its right and Speed under it — is placed here and painted in
:mod:`funestra.drive_readout`. This module draws nothing: it says how big the
block is, where each mark and band lands, which marks are dead at the end of
their range, and what value a press at a point is asking for.

Kept apart from the painter because the halves fail differently. A painter can
be wrong and look wrong; this can be wrong and look right — a hit target that
has drifted a few pixels from the mark over it is invisible until a press lands
on the wrong thing. So it is plain functions over plain numbers, and every panel
showing the readout is a thin painter over one tested layout.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .geometry import Rect

# The three axes, named as the numeric set commands name them (``robot_hand_amp_57``),
# and the OSR2's max intensity, which is the device's rather than the motion's
# (``max_intensity_57``).
AMPLITUDE, CENTER, SPEED = "amp", "center", "speed"
MAX_INTENSITY = "max_intensity"

# One pair of the family's marks for every axis: speed, amplitude and center are
# the same kind of control, so the same minus and plus step all three.
LESS, MORE = "minus", "plus"

_LABEL_H = 14        # a "key value" line
_BAR_H = 12          # the speed track's thickness
_CTRL = 14           # an integrated control button (square)
_MARK_GAP = 2
_GAP = 6
_WAVE_H = 96         # the trace's own height
# The side labels stack their number under their word, so each column is only as
# wide as the wider of the two rather than as wide as both plus a gap.
_CTR_LABEL_W = 34    # room for "Center" down the left
_AMP_LABEL_W = 25    # room for "Amp" down the right
_WAVE_W = 2 * (_CTRL + _MARK_GAP) + _WAVE_H

SECTION_W = _CTR_LABEL_W + _GAP + _CTRL + _GAP + _WAVE_W + _MARK_GAP + _CTRL + _GAP + _AMP_LABEL_W
SECTION_H = _CTRL + _MARK_GAP + _WAVE_H + _MARK_GAP + _CTRL + 2 + _LABEL_H

# How many points the trace is drawn from. Shared, because a funscript sampled
# to take the trace over has to arrive at the same resolution as the motion it
# replaces — a coarser or finer line would read as a different kind of thing.
TRACE_SAMPLES = 80

# What a painter needs to place its own text and marks beside these rects.
LABEL_H = _LABEL_H
BAR_H = _BAR_H
CONTROL_SIZE = _CTRL
GAP = _GAP


def section_size() -> tuple[int, int]:
    """How much room the readout needs."""
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
    """Every rect the readout draws or hit-tests, placed once from the block's
    top-left corner, so the trace and the mark over it cannot drift apart."""

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

    # The center marks ride its dotted line, kept inside the trace's band so a
    # center at either end cannot push one off the block.
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
    """Which of the three axes have run out of road, in which direction.

    Carried as a bundle so a caller cannot hand six booleans over in the wrong
    order: what they do is dim the mark that would now do nothing, and a
    transposed pair dims the wrong end of the wrong axis — a readout that is
    only quietly wrong.
    """

    spd_at_min: bool = False
    spd_at_max: bool = False
    amp_at_min: bool = False
    amp_at_max: bool = False
    ctr_at_min: bool = False
    ctr_at_max: bool = False


def controls(x: int, y: int, center: int, limits: Limits, *,
             dim: bool = False) -> list[DriveControl]:
    """The readout's marks at ``(x, y)`` — a −/+ pair for each of speed,
    amplitude and center — each carrying the command it posts and whether it is
    dimmed at the end of its range.

    The commands are the ones Fun Time routes to the Robot Hand, written out so
    a verb can be grepped from either end.  *dim* dims all of them at once,
    which is what a readout nobody can adjust looks like — a funscript has the
    device, or the motion is not running.
    """
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
    """The readout's bands at ``(x, y)`` — the three you press to set a level
    outright instead of walking to it with the marks.

    A press anywhere on a bar asks for exactly the value drawn under the
    pointer, and holding the button keeps asking as the pointer moves. None of
    them carries a limit flag: a band sets an absolute value, so there is no end
    of a range to run out of.
    """
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


def held_band(track: DriveTrack, py: float) -> tuple[DriveTrack, float]:
    if track.handle_of is None:
        return track, 0.0
    band = replace(track, rect=track.handle_of, handle_of=None)
    _x, y, _w, h = band.rect
    return band, py - (y + (1 - band.center) * (h - 1))


def track_value(track: DriveTrack, px: int, py: float) -> int:
    return min(track.ceiling, _level_under(track, px, py))


def _level_under(track: DriveTrack, px: int, py: float) -> int:
    """The 0-100 level a press at ``(px, py)`` asks *track* for.

    Read off the drawing rather than merely off the rect, so what you point at
    is what you get: the speed bar fills from its left edge, so a press is how
    far along it sits; the trace puts the center's dotted line at its own
    height, so a press is that height; and the amplitude bar is drawn out from
    the center in both directions, so a press is how far the motion has to reach
    to arrive there — grab either end of the bar and pull.

    A point outside the band reads as its nearer end, so a drag that wanders off
    the bar goes on setting it rather than stopping dead at the edge.
    """
    x, y, w, h = track.rect
    if track.axis in (SPEED, MAX_INTENSITY):
        return percent((px - x) / max(1, w - 1))
    height = clamp01(1 - (py - y) / max(1, h - 1))
    if track.axis == CENTER:
        return percent(height)
    return percent(2 * abs(height - track.center))


def fraction(percent_value: int) -> float:
    """A 0-100 control value as a 0-1 bar fill, clamped."""
    return clamp01(percent_value / 100)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def percent(fraction_value: float) -> int:
    """A 0-1 bar fill back as the 0-100 value that would draw it."""
    return round(100 * clamp01(fraction_value))
