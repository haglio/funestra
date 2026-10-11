from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from .hud_button import Button
from .hud_corners import plus_bgra, plus_button, tooltip_size
from .hud_minimize import BUTTON, mark_font, minimize_button, restore_button
from .hud_panel import draw_button, draw_tooltip, to_bgra
from .hud_placement import HudCorner, HudEdge

__all__ = ["OutsideButtons"]

_PLUS_NEAREST_THE_PICTURE = {
    HudEdge.LEFT: HudCorner.UPPER_RIGHT,
    HudEdge.RIGHT: HudCorner.UPPER_LEFT,
    HudEdge.UPPER: HudCorner.LOWER_LEFT,
    HudEdge.LOWER: HudCorner.UPPER_LEFT,
}


@dataclass(frozen=True, eq=False)
class PaintedButton:
    command: str
    bgra: np.ndarray


@dataclass(frozen=True)
class OutsideButtons:
    funestra: str
    minimized: bool = False

    def toggle(self, *, pointed: bool) -> PaintedButton:
        button = self._toggle_button()
        return PaintedButton(button.command, _button_bgra(button, pointed))

    def toggle_tip(self) -> np.ndarray:
        return _tip_bgra(self._toggle_button().tooltip)

    def plus_beside(self, edge: HudEdge) -> PaintedButton:
        button = plus_button(self.funestra, edge, minimized=self.minimized)
        return PaintedButton(button.command, plus_bgra(button, _PLUS_NEAREST_THE_PICTURE[edge]))

    def _toggle_button(self) -> Button:
        opens = restore_button if self.minimized else minimize_button
        return opens(self.funestra)


@lru_cache(maxsize=16)
def _button_bgra(button: Button, pointed: bool) -> np.ndarray:
    image = Image.new("RGBA", (BUTTON, BUTTON), (0, 0, 0, 0))
    draw_button(image, ImageDraw.Draw(image), (0, 0, BUTTON, BUTTON), button,
                hovered=pointed, glyph_font=mark_font(), word_font=mark_font())
    return to_bgra(image)


@lru_cache(maxsize=8)
def _tip_bgra(name: str) -> np.ndarray:
    size = tooltip_size(name)
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    draw_tooltip(ImageDraw.Draw(image), mark_font(), name, (0, 0), size)
    return to_bgra(image)
