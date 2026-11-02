"""The volume control every Funestra in this family draws in its timeline row.

A speaker and a slider, sized for the corner of a video: the Main Funestra and Genau each draw
it live and report presses to Fun Time (which holds the authoritative level for
the whole primary display); a silent satellite draws the same chip as a muted
*indicator*.  Because those Funestras are separate processes in separate repos,
the volume control lives here in the shared engine rather than in any of them — and it is
painted into both an mpv overlay bitmap and a pygame surface, since the Funestras
that draw it live do not share a renderer.

It shows the level *and* the mute as separate facts.  Fun Time silences a sink by
publishing a level of zero, which is all a sink needs and useless to draw: muted
and turned-all-the-way-down look the same, and unmuting has to return to the
level the speaker chose.  So the mute rides alongside the level, and the fill
stays put under it.

Geometry and hit-testing are pure functions with no Pillow, the way
:mod:`funestra.satellite_hud` keeps its layout testable without a font.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image
from shared_ui.icons_pil import paste_icon
from shared_ui.palette import TEXT_MUTED, TEXT_PRIMARY
from shared_ui.spacing import GAP_MEDIUM, GAP_SMALL

from funestra.hud import KeptBitmap, draw_track, pill

# The volume control: a speaker at the left end, a slider filling the rest.  As narrow as
# the two need -- the row's track is what the app is for -- while the slider
# still sets the level by a few per pixel.
VOLUME_CONTROL_W = 64
VOLUME_CONTROL_H = 22
TRACK_GAP = GAP_MEDIUM        # between the row's track and the volume control
SPEAKER_W = 26       # the left end that toggles the mute
PAD = GAP_SMALL

MIN_VOLUME = 0
MAX_VOLUME = 100

# The app the control reserves at the right end of the scrubber row, so the
# scrubber's track stops clear of it: the volume control, flush with the row's end, and
# the gap back to the track.  ``funestra.scrubber_bar.bar_track_x`` subtracts
# it, so the two agree on where the track ends and the volume control begins.
PLACE_W = TRACK_GAP + VOLUME_CONTROL_W

# The row the volume control is centered in when the Funestra under it draws no scrubber: the
# height the scrubber would have had, ``funestra.scrubber_bar.SCRUBBER_HEIGHT``.
# Restated rather than imported, because ``timeline`` reads ``SLOT_W`` from here
# and the import cannot go both ways; ``test_volume`` pins the two together.
ROW_H = 24


def volume_control_xy(*, viewport_w: int | None = None, viewport_h: int | None = None, timeline_h: int,
                      win_w: int | None = None, win_h: int | None = None) -> tuple[int, int]:
    """The volume control's top-left: flush with the right end of the scrubber row,
    centered in its height.

    Beside the scrubber, the way VLC laid the seek bar and the volume out
    together, rather than floating in a row of its own above it.  The track leaves
    ``SLOT_W`` clear on the right for it.  Clamped at the left and the top so a
    window smaller than the volume control keeps it on screen.

    A Funestra with no scrubber passes ``timeline_h=0`` and is centered in
    :data:`ROW_H` regardless, so its volume control lands exactly where a Funestra with the
    row puts one.
    """
    row_h = timeline_h if timeline_h > 0 else ROW_H
    viewport_w, viewport_h = viewport_w or win_w, viewport_h or win_h
    return (
        max(0, viewport_w - VOLUME_CONTROL_W),
        max(0, viewport_h - row_h + max(0, (row_h - VOLUME_CONTROL_H) // 2)),
    )


# --- hit-testing -------------------------------------------------------------

_TRACK_X0 = SPEAKER_W
_TRACK_X1 = VOLUME_CONTROL_W - PAD


def volume_control_local(mx: int, my: int, *, viewport_w: int, viewport_h: int,
               timeline_h: int) -> tuple[int, int]:
    """A viewport point in the volume control's own coordinates — what the hit tests below take.

    The volume control is placed from the viewport's lower-right corner, so its origin moves
    with the window and with the scrubber under it.  Undoing ``chip_xy`` lives here
    beside ``chip_xy`` rather than at each call site, where it would be one more
    copy of the volume control's position, free to drift from the real one.
    """
    vx, vy = volume_control_xy(viewport_w=viewport_w, viewport_h=viewport_h, timeline_h=timeline_h)
    return mx - vx, my - vy


def hit_part(x: int, y: int) -> str:
    """Which control a press at chip-local ``(x, y)`` is on: "mute", "track", or
    "" for neither.  The speaker takes the left end and the slider the rest, so
    every pixel of the volume control does something and none of it is decoration."""
    if not (0 <= x < VOLUME_CONTROL_W and 0 <= y < VOLUME_CONTROL_H):
        return ""
    return "mute" if x < SPEAKER_W else "track"


def volume_at(x: int) -> int:
    """The level a press at chip-local *x* asks for, clamped to the track's ends.

    Past either end saturates rather than doing nothing: dragging off the volume control
    should pin the level at silent or full, which is what the pointer is asking
    for, not abandon the drag mid-way.
    """
    span = max(1, _TRACK_X1 - _TRACK_X0)
    fraction = (x - _TRACK_X0) / span
    return int(round(min(1.0, max(0.0, fraction)) * MAX_VOLUME))


# --- what it shows -----------------------------------------------------------


@dataclass(frozen=True)
class VolumeHud:
    """The level being published, and whether it is muted there."""

    volume: int = MAX_VOLUME
    muted: bool = False


# The family's speaker as tall as the volume control, set in so its cone starts a pad in.
_SPEAKER_MARK = (PAD // 2, 1, VOLUME_CONTROL_H - 2, VOLUME_CONTROL_H - 2)


def _draw_speaker(image: Image.Image, muted: bool) -> None:
    """The family's speaker at the left end, crossed out while muted."""
    paste_icon(image, "speaker_off" if muted else "speaker", _SPEAKER_MARK,
               TEXT_MUTED if muted else TEXT_PRIMARY)


class VolumeHudPainter(KeptBitmap):
    def _paint(self, hud: VolumeHud) -> Image.Image:
        image, draw = pill(VOLUME_CONTROL_W, VOLUME_CONTROL_H)
        _draw_speaker(image, hud.muted)
        # The fill stays put under a mute: the level is what unmuting returns to,
        # so hiding it would lose the only record of where the speaker was set.
        level = min(MAX_VOLUME, max(MIN_VOLUME, hud.volume))
        filled = _TRACK_X0 + round((_TRACK_X1 - _TRACK_X0) * level / MAX_VOLUME)
        draw_track(draw, _TRACK_X0, _TRACK_X1, VOLUME_CONTROL_H // 2,
                   filled_to=filled if filled > _TRACK_X0 else None)
        return image
