from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shared_ui import lettering
from shared_ui.app_icon import draw_letter
from shared_ui.button_pil import slab
from shared_ui.icons_pil import paste_icon
from shared_ui.lettering import BOLD_FACE, wrap_text
from shared_ui.palette import (
    BG_BUTTON,
    BG_BUTTON_ACTIVE,
    BG_PRIMARY,
    BLUE,
    BORDER_PANEL,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WHITE,
    YELLOW,
    hovered,
)
from shared_ui.spacing import BUTTON_ICON_INSET, BUTTON_RADIUS, GAP_SMALL
from shared_ui.toggle_geometry import TRACK_HUD
from shared_ui.toggle_switch_pil import paste_toggle_switch
from shared_ui.type_scale import in_pixels

from .hud_icons import (
    APP_ICON,
    SHARED_ICON,
    TOGGLE_SWITCH,
    app_mark_letter,
    shared_icon_name,
)

# Segoe UI Bold lacks these marks, and Pillow draws a .notdef box for a missing glyph.
SYMBOL_FONT = "seguisym.ttf"

HUD_ALPHA = 224
CORNER_RADIUS = BUTTON_RADIUS

hovered_fill = hovered


def load_font(points: int, family: str = BOLD_FACE) -> ImageFont.FreeTypeFont:
    return lettering.load_font(in_pixels(points), family)


def text_width(font: ImageFont.FreeTypeFont, text: str) -> int:
    return int(font.getlength(text))


_INK_OFFSETS: dict[tuple[str, int, str], tuple[float, float] | None] = {}


def ink_center_offset(font: ImageFont.FreeTypeFont, icon: str) -> tuple[float, float] | None:
    key = (str(getattr(font, "path", "")), int(getattr(font, "size", 0)), icon)
    if key not in _INK_OFFSETS:
        pad = 8
        bounds = font.getbbox(icon)
        probe = Image.new("L", (int(bounds[2]) + 2 * pad, int(bounds[3]) + 2 * pad), 0)
        ImageDraw.Draw(probe).text((pad, pad), icon, font=font, fill=255)
        ink = probe.getbbox()
        _INK_OFFSETS[key] = None if ink is None else (
            (ink[0] + ink[2] - 1) / 2 - pad, (ink[1] + ink[3] - 1) / 2 - pad,
        )
    return _INK_OFFSETS[key]


def draw_character(draw: ImageDraw.ImageDraw, center: tuple[float, float], icon: str,
                   font: ImageFont.FreeTypeFont, fill) -> None:
    offset = ink_center_offset(font, icon)
    if offset is None:
        return
    cx, cy = center
    draw.text((cx - offset[0], cy - offset[1]), icon, font=font, fill=fill)


def draw_icon(image: Image.Image, name: str, rect: tuple[int, int, int, int],
              fill) -> None:
    x, y, w, h = rect
    paste_icon(image, name,
               (x + BUTTON_ICON_INSET, y + BUTTON_ICON_INSET, w - 2 * BUTTON_ICON_INSET,
                h - 2 * BUTTON_ICON_INSET),
               fill)


ACTIVE_DOT = 10
_DISC_FRAME = ACTIVE_DOT + 2


def draw_active_dot(image: Image.Image, x: int, y: int, active: bool) -> None:
    paste_icon(image, "disc", (x, y, _DISC_FRAME, _DISC_FRAME), WHITE if active else TEXT_MUTED)


TOOLTIP_PAD = GAP_SMALL
TOOLTIP_RADIUS = BUTTON_RADIUS
TOOLTIP_ALPHA = 240
_TOOLTIP_EDGE = 2
_TOOLTIP_OFFSET = (14, 16)


def draw_tooltip(draw: ImageDraw.ImageDraw, font: ImageFont.FreeTypeFont, text: str,
                 pos: tuple[int, int], bounds: tuple[int, int]) -> tuple[int, int, int, int]:
    room = max(1, bounds[0] - 2 * (_TOOLTIP_EDGE + TOOLTIP_PAD))
    lines = wrap_text(font, text, room)
    if not lines:
        return (0, 0, 0, 0)
    ascent, descent = font.getmetrics()
    line_h = ascent + descent
    w = max(text_width(font, line) for line in lines) + 2 * TOOLTIP_PAD
    h = line_h * len(lines) + 2 * TOOLTIP_PAD
    x = max(_TOOLTIP_EDGE, min(pos[0] + _TOOLTIP_OFFSET[0], bounds[0] - w - _TOOLTIP_EDGE))
    y = max(_TOOLTIP_EDGE, min(pos[1] + _TOOLTIP_OFFSET[1], bounds[1] - h - _TOOLTIP_EDGE))
    draw.rounded_rectangle([x, y, x + w - 1, y + h - 1], radius=TOOLTIP_RADIUS,
                           fill=(*BG_PRIMARY, TOOLTIP_ALPHA),
                           outline=(*BORDER_PANEL, 255), width=1)
    for index, line in enumerate(lines):
        draw.text((x + w / 2, y + TOOLTIP_PAD + index * line_h + ascent), line,
                  font=font, anchor="ms", fill=(*TEXT_PRIMARY, 255))
    return (x, y, w, h)


def to_bgra(image: Image.Image) -> np.ndarray:
    rgba = np.asarray(image, dtype=np.uint8)
    return np.ascontiguousarray(rgba[:, :, [2, 1, 0, 3]], dtype=np.uint8)


class Hud:
    def __init__(self, width: int, height: int, *,
                 ground: tuple[int, int, int] = BG_PRIMARY) -> None:
        self.image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        self.draw = ImageDraw.Draw(self.image)
        self.draw.rounded_rectangle(
            [0, 0, width - 1, height - 1], radius=CORNER_RADIUS,
            fill=(*ground, HUD_ALPHA), outline=(*BORDER_PANEL, 255), width=1,
        )

    def divide(self, y: int) -> None:
        self.draw.line([(0, y), (self.image.width - 1, y)], fill=(*BORDER_PANEL, 255))

    def to_bgra(self) -> np.ndarray:
        return to_bgra(self.image)


PILL_ALPHA = 200


def pill(width: int, height: int) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle([0, 0, width - 1, height - 1], radius=height // 2,
                           fill=(*BG_PRIMARY, PILL_ALPHA), outline=(*BORDER_PANEL, 255), width=1)
    return image, draw


TRACK_H = 4


def draw_track(draw: ImageDraw.ImageDraw, left: int, right: int, middle: int, *,
               filled_to: int | None) -> None:
    upper, lower = middle - TRACK_H // 2, middle + TRACK_H // 2
    draw.rounded_rectangle([left, upper, right, lower], radius=TRACK_H // 2,
                           fill=(*TEXT_MUTED, 255))
    if filled_to is not None:
        draw.rounded_rectangle([left, upper, filled_to, lower], radius=TRACK_H // 2,
                               fill=(*TEXT_PRIMARY, 255))


class KeptBitmap:
    def __init__(self) -> None:
        self._painted = None
        self._image: Image.Image | None = None
        self._bgra: np.ndarray | None = None

    def bgra(self, hud) -> np.ndarray:
        if self._ensure(hud) or self._bgra is None:
            self._bgra = to_bgra(self._image)
        return self._bgra

    def rgba(self, hud) -> tuple[bytes, tuple[int, int]]:
        self._ensure(hud)
        return self._image.tobytes(), self._image.size

    def _ensure(self, hud) -> bool:
        if hud == self._painted and self._image is not None:
            return False
        self._painted, self._image = hud, self._paint(hud)
        return True

    def _paint(self, hud) -> Image.Image:
        raise NotImplementedError


@dataclass(frozen=True)
class ButtonGroundState:
    hovered: bool = False
    dim: bool = False
    rest_ink: tuple[int, int, int] | None = None


@dataclass(frozen=True)
class ButtonLook:
    hovered: bool
    icon_font: ImageFont.FreeTypeFont
    word_font: ImageFont.FreeTypeFont
    row_label: bool = False


def button_ground(draw: ImageDraw.ImageDraw, rect: tuple[int, int, int, int], fill,
                  state: ButtonGroundState) -> tuple[int, int, int, int]:
    edge = TEXT_MUTED if (state.dim or fill in (BG_BUTTON, BG_BUTTON_ACTIVE)) else fill
    if state.hovered and not state.dim:
        fill = hovered_fill(fill)
    slab(draw, rect, fill, edge)
    if fill in (WHITE, YELLOW):
        return (*BG_PRIMARY, 255)
    if fill in (BG_BUTTON, BG_BUTTON_ACTIVE):
        return (*(TEXT_MUTED if state.dim else state.rest_ink or TEXT_PRIMARY), 255)
    return (*WHITE, 255)


def draw_button(image: Image.Image, draw: ImageDraw.ImageDraw,
                rect: tuple[int, int, int, int], button, look: ButtonLook) -> None:
    hovered, icon_font, word_font, row_label = (
        look.hovered, look.icon_font, look.word_font, look.row_label)
    x, y, w, h = rect
    if not button.command:
        named = button.is_a_name and not button.lit
        ink = TEXT_MUTED if named else TEXT_PRIMARY
        if row_label:
            draw.text((x, y + h / 2), button.icon, font=word_font, anchor="lm",
                      fill=(*ink, 255))
        else:
            draw.text((x + w / 2, y + h / 2), button.icon, font=word_font,
                      anchor="mm", fill=(*ink, 255))
        return
    if button.icon == TOGGLE_SWITCH:
        paste_toggle_switch(image, (x + (w - TRACK_HUD[0]) // 2, y + (h - TRACK_HUD[1]) // 2),
                            on=button.lit, hovered=hovered)
        return

    lit = GREEN if button.favorite else YELLOW if button.enhanced else BLUE
    fill = (lit if button.lit else RED if button.warn else BLUE if button.hold
            else BG_BUTTON_ACTIVE if button.remembered else BG_BUTTON)
    ink = button_ground(draw, rect, fill, ButtonGroundState(
        hovered=hovered, dim=button.dim,
        rest_ink=RED if button.danger else YELLOW if button.enhanced else None))
    icon = button.icon
    if icon.startswith(APP_ICON):
        draw_letter(draw, rect, app_mark_letter(icon))
    elif icon.startswith(SHARED_ICON):
        draw_icon(image, shared_icon_name(icon), rect, ink)
    elif len(icon) == 1 and not icon.isalnum():
        draw_character(draw, (x + w / 2, y + h / 2), icon, icon_font, ink)
    else:
        draw.text((x + w / 2, y + h / 2), icon, font=word_font, anchor="mm", fill=ink)
