"""The volume chip every Funestra in this family draws in its timeline row.

A speaker and a slider, sized for the corner of a video: the Main Funestra and Genau each draw
it live and report presses to Fun Time (which holds the authoritative level for
the whole primary display); a silent satellite draws the same chip as a muted
*indicator*.  Because those Funestras are separate processes in separate repos,
the chip lives here in the shared engine rather than in any of them — and it is
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

from PIL import Image, ImageDraw
from shared_ui.palette import TEXT_MUTED, TEXT_PRIMARY

from funestra.hud_panel import KeptBitmap, pill

__all__: list[str] = []  # package-internal: the row hosts the chip

# The chip: a speaker at the left end, a slider filling the rest.  As narrow as
# the two need -- the row's track is what the room is for -- while the slider
# still sets the level by a few per pixel.
CHIP_W = 64
CHIP_H = 22
TRACK_GAP = 6        # between the row's track and the chip
SPEAKER_W = 26       # the left end that toggles the mute
PAD = 6
TRACK_H = 4

MIN_VOLUME = 0
MAX_VOLUME = 100

# The room the control reserves at the right end of the timeline row, so the
# scrubber's track stops clear of it: the chip, flush with the row's end, and
# the gap back to the track.  ``funestra.timeline.bar_track_x`` subtracts
# it, so the two agree on where the track ends and the chip begins.
SLOT_W = TRACK_GAP + CHIP_W

# The row the chip is centered in when the Funestra under it draws no scrubber: the
# height the scrubber would have had, ``funestra.timeline.TIMELINE_HEIGHT``.
# Restated rather than imported, because ``timeline`` reads ``SLOT_W`` from here
# and the import cannot go both ways; ``test_volume`` pins the two together.
ROW_H = 24


def chip_xy(*, win_w: int, win_h: int, timeline_h: int) -> tuple[int, int]:
    """The chip's top-left: flush with the right end of the timeline row,
    centered in its height.

    Beside the scrubber, the way VLC laid the seek bar and the volume out
    together, rather than floating in a row of its own above it.  The track leaves
    ``SLOT_W`` clear on the right for it.  Clamped at the left and the top so a
    window smaller than the chip keeps it on screen.

    A Funestra with no scrubber passes ``timeline_h=0`` and is centered in
    :data:`ROW_H` regardless, so its chip lands exactly where a Funestra with the
    row puts one.
    """
    row_h = timeline_h if timeline_h > 0 else ROW_H
    return (
        max(0, win_w - CHIP_W),
        max(0, win_h - row_h + max(0, (row_h - CHIP_H) // 2)),
    )


# --- hit-testing -------------------------------------------------------------

_TRACK_X0 = SPEAKER_W
_TRACK_X1 = CHIP_W - PAD


def chip_local(mx: int, my: int, *, win_w: int, win_h: int,
               timeline_h: int) -> tuple[int, int]:
    """A window point in the chip's own coordinates — what the hit tests below take.

    The chip is placed from the window's lower-right corner, so its origin moves
    with the window and with the timeline under it.  Undoing ``chip_xy`` lives here
    beside ``chip_xy`` rather than at each call site, where it would be one more
    copy of the chip's position, free to drift from the real one.
    """
    vx, vy = chip_xy(win_w=win_w, win_h=win_h, timeline_h=timeline_h)
    return mx - vx, my - vy


def hit_part(x: int, y: int) -> str:
    """Which control a press at chip-local ``(x, y)`` is on: "mute", "track", or
    "" for neither.  The speaker takes the left end and the slider the rest, so
    every pixel of the chip does something and none of it is decoration."""
    if not (0 <= x < CHIP_W and 0 <= y < CHIP_H):
        return ""
    return "mute" if x < SPEAKER_W else "track"


def volume_at(x: int) -> int:
    """The level a press at chip-local *x* asks for, clamped to the track's ends.

    Past either end saturates rather than doing nothing: dragging off the chip
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


_MUTED_BAR = (200, 70, 70)   # the slash across a muted speaker


def _draw_speaker(draw: ImageDraw.ImageDraw, muted: bool) -> None:
    """A speaker cone at the left end, struck through while muted.

    Drawn rather than typed: the glyph fonts differ on the trailing waves, and a
    missing one draws a tofu where the clearest control on the chip should be.
    """
    color = TEXT_MUTED if muted else TEXT_PRIMARY
    mid = CHIP_H // 2
    x = PAD
    draw.rectangle([x, mid - 3, x + 4, mid + 3], fill=(*color, 255))
    draw.polygon([(x + 4, mid - 3), (x + 10, mid - 7), (x + 10, mid + 7), (x + 4, mid + 3)],
                 fill=(*color, 255))
    if muted:
        draw.line([(x, mid + 7), (x + 13, mid - 7)], fill=(*_MUTED_BAR, 255), width=2)


class VolumeHudPainter(KeptBitmap):
    def _paint(self, hud: VolumeHud) -> Image.Image:
        image, draw = pill(CHIP_W, CHIP_H)
        _draw_speaker(draw, hud.muted)
        mid = CHIP_H // 2
        draw.rounded_rectangle(
            [_TRACK_X0, mid - TRACK_H // 2, _TRACK_X1, mid + TRACK_H // 2],
            radius=TRACK_H // 2, fill=(*TEXT_MUTED, 255),
        )
        # The fill stays put under a mute: the level is what unmuting returns to,
        # so hiding it would lose the only record of where the speaker was set.
        level = min(MAX_VOLUME, max(MIN_VOLUME, hud.volume))
        filled = _TRACK_X0 + round((_TRACK_X1 - _TRACK_X0) * level / MAX_VOLUME)
        if filled > _TRACK_X0:
            draw.rounded_rectangle(
                [_TRACK_X0, mid - TRACK_H // 2, filled, mid + TRACK_H // 2],
                radius=TRACK_H // 2, fill=(*TEXT_PRIMARY, 255),
            )
        return image
