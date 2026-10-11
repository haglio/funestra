from __future__ import annotations

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw
from shared_ui.spacing import BUTTON_GAP, BUTTON_SIZE_HUD

from .geometry import Rect
from .hud_button import Button
from .hud_marks import shared_mark
from .hud_panel import draw_button, draw_tooltip, load_font, to_bgra
from .hud_placement import HudCorner

__all__: list[str] = []

BUTTON = BUTTON_SIZE_HUD
ROOM = BUTTON + BUTTON_GAP

MINIMIZE_GLYPH = shared_mark("minus")
RESTORE_GLYPH = shared_mark("plus")
MINIMIZE_TOOLTIP = "Minimize this HUD"
RESTORE_TOOLTIP = "Show this HUD again"

_MARK_FONT_PT = 9

# Room beside the plus for its tooltip, which a panel this small cannot hold:
# wide enough for RESTORE_TOOLTIP on one line at _MARK_FONT_PT, and one line tall.
_TOOLTIP_ROOM_W = 118
_TOOLTIP_ROOM_H = 26


@lru_cache(maxsize=1)
def mark_font():
    return load_font(_MARK_FONT_PT)


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


def corner_button_rect(corner: HudCorner, *, panel: tuple[int, int],
                       inset: tuple[int, int]) -> Rect:
    width, height = panel
    across, down = inset
    x = width - across - BUTTON if corner.right else across
    y = height - down - BUTTON if corner.lower else down
    return (x, y, BUTTON, BUTTON)


def _collapsed_size(*, room_for_the_tooltip: bool) -> tuple[int, int]:
    if not room_for_the_tooltip:
        return BUTTON, BUTTON
    return BUTTON + _TOOLTIP_ROOM_W, BUTTON + _TOOLTIP_ROOM_H


def collapsed_button(funestra: str, corner: HudCorner = HudCorner.UPPER_LEFT, *,
                     hover: tuple[int, int] | None = None, room_for_the_tooltip: bool = False
                     ) -> tuple[Image.Image, list[tuple[Rect, Button]]]:
    size = _collapsed_size(room_for_the_tooltip=room_for_the_tooltip or hover is not None)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    rect = corner_button_rect(corner, panel=size, inset=(0, 0))
    draw_button(image, ImageDraw.Draw(image), rect, restore_button(funestra),
                hovered=hover is not None, glyph_font=mark_font(), word_font=mark_font())
    if hover is not None:
        draw_tooltip(ImageDraw.Draw(image), mark_font(), RESTORE_TOOLTIP, hover, size)
    return image, [(rect, restore_button(funestra))]


def collapsed_panel(funestra: str, corner: HudCorner = HudCorner.UPPER_LEFT, *,
                    hover: tuple[int, int] | None = None, room_for_the_tooltip: bool = False
                    ) -> tuple[np.ndarray, list[tuple[Rect, Button]]]:
    image, buttons = collapsed_button(funestra, corner, hover=hover,
                                      room_for_the_tooltip=room_for_the_tooltip)
    return to_bgra(image), buttons

