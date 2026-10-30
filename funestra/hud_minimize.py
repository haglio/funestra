from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw
from shared_ui.palette import TEXT_MUTED
from shared_ui.spacing import BUTTON_GAP, BUTTON_SIZE_HUD, MARGIN_STANDARD
from shared_ui.type_scale import SIZE_SMALL, SIZE_TINY

from .geometry import Rect
from .hud import (
    Hud,
    draw_button,
    draw_tooltip,
    load_font,
    text_width,
    to_bgra,
)
from .hud_button import Button
from .hud_marks import shared_mark
from .hud_placement import HudCorner

BUTTON = BUTTON_SIZE_HUD
ROOM = BUTTON + BUTTON_GAP

MINIMIZE_GLYPH = shared_mark("minus")
RESTORE_GLYPH = shared_mark("plus")
MINIMIZE_TOOLTIP = "Minimize this HUD"
RESTORE_TOOLTIP = "Show this HUD again"

FLASH_S = 3.0

# Room beside the plus for its tooltip, which a HUD this small cannot hold:
# wide enough for RESTORE_TOOLTIP on one line at the family's small size, and one
# line tall.
_TOOLTIP_ROOM_W = 118
_TOOLTIP_ROOM_H = 26


@lru_cache(maxsize=1)
def mark_font():
    return load_font(SIZE_SMALL)


@lru_cache(maxsize=1)
def name_font():
    return load_font(SIZE_TINY)


class NameFlash:
    def __init__(self, clock: Callable[[], float]) -> None:
        self._clock = clock
        self._name = ""
        self._since = 0.0

    def showing(self, on_screen: str) -> str:
        now = self._clock()
        if on_screen != self._name:
            self._name, self._since = on_screen, now
        return self._name if now - self._since < FLASH_S else ""


def minimize_command(funestra: str) -> str:
    return f"{funestra}_hud_minimize"


def restore_command(funestra: str) -> str:
    return f"{funestra}_hud_restore"


def restore_at_command(funestra: str, place: str) -> str:
    return f"{restore_command(funestra)}_at|{place}"


def minimize_button(funestra: str) -> Button:
    return Button(minimize_command(funestra), MINIMIZE_GLYPH, MINIMIZE_TOOLTIP)


def restore_button(funestra: str) -> Button:
    return Button(restore_command(funestra), RESTORE_GLYPH, RESTORE_TOOLTIP)


def corner_button_rect(corner: HudCorner, *, hud: tuple[int, int],
                       inset: tuple[int, int]) -> Rect:
    width, height = hud
    across, down = inset
    x = width - across - BUTTON if corner.right else across
    y = height - down - BUTTON if corner.lower else down
    return (x, y, BUTTON, BUTTON)


def name_slab(name: str) -> Image.Image:
    slab = Hud(text_width(name_font(), name) + 2 * MARGIN_STANDARD, BUTTON)
    slab.draw.text((MARGIN_STANDARD, BUTTON / 2), name, font=name_font(), anchor="lm",
                   fill=(*TEXT_MUTED, 255))
    return slab.image


def _collapsed_size(*, room_for_the_tooltip: bool,
                    beside: Image.Image | None) -> tuple[int, int]:
    if beside is not None:
        return ROOM + beside.width, BUTTON
    if not room_for_the_tooltip:
        return BUTTON, BUTTON
    return BUTTON + _TOOLTIP_ROOM_W, BUTTON + _TOOLTIP_ROOM_H


def collapsed_button(funestra: str, corner: HudCorner = HudCorner.UPPER_LEFT, *,
                     hover: tuple[int, int] | None = None, room_for_the_tooltip: bool = False,
                     flash: str = "") -> tuple[Image.Image, list[tuple[Rect, Button]]]:
    named = name_slab(flash) if flash and hover is None else None
    size = _collapsed_size(room_for_the_tooltip=room_for_the_tooltip or hover is not None,
                           beside=named)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    rect = corner_button_rect(corner, hud=size, inset=(0, 0))
    draw_button(image, ImageDraw.Draw(image), rect, restore_button(funestra),
                hovered=hover is not None, glyph_font=mark_font(), word_font=mark_font())
    if named is not None:
        image.alpha_composite(named, (0 if corner.right else ROOM, 0))
    if hover is not None:
        draw_tooltip(ImageDraw.Draw(image), mark_font(), RESTORE_TOOLTIP, hover, size)
    return image, [(rect, restore_button(funestra))]


def collapsed_hud(funestra: str, corner: HudCorner = HudCorner.UPPER_LEFT, *,
                  hover: tuple[int, int] | None = None, room_for_the_tooltip: bool = False,
                  flash: str = "") -> tuple[np.ndarray, list[tuple[Rect, Button]]]:
    image, buttons = collapsed_button(funestra, corner, hover=hover,
                                      room_for_the_tooltip=room_for_the_tooltip, flash=flash)
    return to_bgra(image), buttons

