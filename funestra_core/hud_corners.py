from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw
from shared_ui.spacing import BUTTON_GAP

from .hud_button import Button
from .hud_minimize import BUTTON, RESTORE_GLYPH, mark_font, restore_at_command
from .hud_panel import TOOLTIP_PAD, draw_button, draw_tooltip, text_width, to_bgra
from .hud_placement import HudCorner, corner_at, hud_origin

__all__ = ["CORNER_PLUS_OVERLAY_ID"]

CORNER_PLUS_OVERLAY_ID = 11
REACH = 64
MOVE_TOOLTIP = "Move this HUD here"
SHOW_TOOLTIP = "Show this HUD here"

_TOOLTIP_EDGE = 2
_FAR = 1 << 16


@dataclass(frozen=True)
class HudPlace:
    funestra: str
    corner: HudCorner
    margin: int
    minimized: bool = False
    inset: tuple[int, int] = (0, 0)

    def origin(self, *, panel: tuple[int, int], window: tuple[int, int],
               lower_edge: int = 0) -> tuple[int, int]:
        return hud_origin(self.corner, panel=panel, window=window, margin=self.margin,
                          lower_edge=lower_edge, inset=self.inset if self.minimized else (0, 0))


def _corner_beside(place: HudPlace, x: int, y: int, *,
                   window: tuple[int, int]) -> HudCorner | None:
    width, height = window
    if not (0 <= x < width and 0 <= y < height):
        return None
    right, lower = x >= width - REACH, y >= height - REACH
    if not ((right or x < REACH) and (lower or y < REACH)):
        return None
    corner = corner_at(right=right, lower=lower)
    return None if corner is place.corner else corner


def plus_button(funestra: str, place: str, *, minimized: bool) -> Button:
    return Button(restore_at_command(funestra, place), RESTORE_GLYPH,
                  SHOW_TOOLTIP if minimized else MOVE_TOOLTIP)


def tooltip_size(text: str) -> tuple[int, int]:
    font = mark_font()
    return (text_width(font, text) + 2 * (TOOLTIP_PAD + _TOOLTIP_EDGE),
            sum(font.getmetrics()) + 2 * (TOOLTIP_PAD + _TOOLTIP_EDGE))


@lru_cache(maxsize=16)
def plus_bgra(button: Button, corner: HudCorner) -> np.ndarray:
    font = mark_font()
    tooltip_w, tooltip_h = tooltip_size(button.tooltip)
    width, height = BUTTON + BUTTON_GAP + tooltip_w, max(BUTTON, tooltip_h)
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    rect = (width - BUTTON if corner.right else 0, height - BUTTON if corner.lower else 0,
            BUTTON, BUTTON)
    draw_button(image, draw, rect, button, hovered=True, glyph_font=font, word_font=font)
    inward = (-_FAR if corner.right else _FAR, _FAR if corner.lower else -_FAR)
    draw_tooltip(draw, font, button.tooltip, inward, (width, height))
    return to_bgra(image)


@dataclass(frozen=True)
class _Plus:
    button: Button
    corner: HudCorner
    origin: tuple[int, int]


class HudCorners:
    def __init__(self, panel, engine, *, post: Callable[[str], None],
                 overlay_id: int = CORNER_PLUS_OVERLAY_ID) -> None:
        self._panel = panel
        self._engine = engine
        self._post = post
        self._overlay_id = overlay_id
        self._window: tuple[int, int] | None = None
        self._pointer: tuple[int, int] | None = None
        self._shown: _Plus | None = None

    def motion(self, x: int, y: int) -> None:
        self._pointer = None if self._panel.covers(x, y) else (x, y)

    def leave(self) -> None:
        self._pointer = None

    def press(self, x: int, y: int) -> bool:
        target = None if self._window is None or self._panel.covers(x, y) else self._target(
            x, y, self._window)
        if target is None:
            return False
        self._post(self._button(*target).command)
        return True

    def paint(self, *, window: tuple[int, int]) -> None:
        self._window = window
        plus = self._plus(window)
        if plus == self._shown:
            return
        self._shown = plus
        if plus is None:
            self._engine.remove_overlay(self._overlay_id)
        else:
            self._engine.overlay(self._overlay_id, *plus.origin,
                                 plus_bgra(plus.button, plus.corner))

    @staticmethod
    def _button(place: HudPlace, corner: HudCorner) -> Button:
        return plus_button(place.funestra, corner, minimized=place.minimized)

    def _target(self, x: int, y: int,
                window: tuple[int, int]) -> tuple[HudPlace, HudCorner] | None:
        place = self._panel.hud_place
        corner = None if place is None else _corner_beside(place, x, y, window=window)
        return None if corner is None else (place, corner)

    def _plus(self, window: tuple[int, int]) -> _Plus | None:
        target = None if self._pointer is None else self._target(*self._pointer, window)
        if target is None:
            return None
        place, corner = target
        button = self._button(place, corner)
        height, width = plus_bgra(button, corner).shape[:2]
        return _Plus(button, corner, replace(place, corner=corner, minimized=True).origin(
            panel=(width, height), window=window))
