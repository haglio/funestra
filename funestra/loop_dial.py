"""The dial beside a flick's track: a clock hand that goes round once per loop.

A flick has two senses of time.  How long it stays up before the next one
arrives is the track's: a scrubber, filled left to right like a video's.  The
loop of the flick itself has no start or end to scrub between, so it is a dial,
the hand at twelve o'clock at the loop's A end and at six at its B end, going
round once per turn of the loop.  A mark at twelve and a dot at six say where
those ends are.
"""
from __future__ import annotations

import math

from PIL import Image, ImageDraw
from shared_ui.palette import BG_PRIMARY, BORDER_PANEL, TEXT_MUTED, TEXT_PRIMARY

from .hud_panel import PILL_ALPHA, KeptBitmap
from .volume import CHIP_H

__all__: list[str] = []  # package-internal: the row hosts it and hud_row says where

# As tall as the chip and the readout it shares the row with.
DIAL_SIZE = CHIP_H
# The positions the hand can show -- four degrees apart, which is as fine as a
# dial this size draws -- so a turn is repainted only when it moves a step.
HAND_STEPS = 90

_SUPERSAMPLE = 4
_TICK = 3        # the mark at twelve o'clock, reaching in from the rim
_DOT = 1.5       # the dot at six, centered where the mark's middle is
_HAND_W = 2
_HAND_REACH = DIAL_SIZE / 2 - 3
_PIVOT = 1.5


def on_dial(px: int, py: int, *, at: tuple[int, int]) -> bool:
    """Whether ``(px, py)`` is on a dial whose top-left corner is *at*."""
    x, y = at
    return x <= px < x + DIAL_SIZE and y <= py < y + DIAL_SIZE


def turn_at(px: int, py: int, *, at: tuple[int, int]) -> float:
    """The turn a press at ``(px, py)`` asks of a dial whose top-left corner is
    *at*: how far round it the press is, clockwise from twelve o'clock, 0 to 1."""
    x, y = at
    cx, cy = x + DIAL_SIZE / 2, y + DIAL_SIZE / 2
    return math.atan2(px + 0.5 - cx, cy - (py + 0.5)) / math.tau % 1.0


class LoopDialPainter(KeptBitmap):
    """The dial, kept until the hand moves a step.

    Drawn larger and scaled back down, the way the drive readout draws its
    trace: Pillow's lines have no antialiasing of their own, and a hand two
    pixels wide turning on a dial this small would otherwise jump between
    staircases.
    """

    @staticmethod
    def hand(turn: float) -> int:
        """The step the hand falls on for *turn* -- what the bitmap is keyed by."""
        return round(turn * HAND_STEPS) % HAND_STEPS

    def _paint(self, step: int) -> Image.Image:
        s = _SUPERSAMPLE
        size = DIAL_SIZE * s
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse([0, 0, size - 1, size - 1], fill=(*BG_PRIMARY, PILL_ALPHA),
                     outline=(*BORDER_PANEL, 255), width=s)
        c = size / 2
        draw.line([(c, s), (c, s * (1 + _TICK))], fill=(*TEXT_MUTED, 255), width=s)
        dot, dot_y = _DOT * s, size - s * (1 + _TICK / 2)
        draw.ellipse([c - dot, dot_y - dot, c + dot, dot_y + dot], fill=(*TEXT_MUTED, 255))
        angle = math.tau * step / HAND_STEPS
        reach = _HAND_REACH * s
        draw.line([(c, c), (c + math.sin(angle) * reach, c - math.cos(angle) * reach)],
                  fill=(*TEXT_PRIMARY, 255), width=_HAND_W * s)
        pivot = _PIVOT * s
        draw.ellipse([c - pivot, c - pivot, c + pivot, c + pivot], fill=(*TEXT_PRIMARY, 255))
        return image.resize((DIAL_SIZE, DIAL_SIZE), Image.LANCZOS)
