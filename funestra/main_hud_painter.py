from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import NamedTuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shared_ui.spacing import BUTTON_GAP, GAP_SMALL, MARGIN_STANDARD
from shared_ui.type_scale import SIZE_BODY, SIZE_TINY

from .geometry import Rect, contains
from .hud import (
    SYMBOL_FONT,
    ButtonLook,
    Hud,
    draw_button,
    draw_tooltip,
    load_font,
    text_width,
    to_bgra,
)
from .hud_button import reading_its_host_value
from .hud_controls import PLAYBACK_SPEED
from .hud_corners import HudPlace
from .hud_osr2 import HEIGHT as _OSR2_H
from .hud_osr2 import Osr2Line, Osr2Section, VisualizerResolver, line_shown_for
from .hud_placement import HudCorner, PointerReading, block_x
from .hud_sections import blocks_height
from .main_hud import (
    Button,
    MainHudModel,
    _row_width,
    hit_test,
    kino_shows,
    place_rows,
    rows_height,
    tooltip_at,
)
from .osr2_visualizer import (
    DriveHud,
    DriveSection,
    DriveTrack,
    TrackGrip,
    section_size,
    visualizer_targets,
)
from .playback_rate import format_rate

_PAD = MARGIN_STANDARD
_MINUS_INSET = (_PAD, _PAD)
MARGIN = MARGIN_STANDARD
_BLOCK_GAP = GAP_SMALL


@dataclass(frozen=True)
class MainHud:
    main_hud_model: MainHudModel = field(default_factory=MainHudModel)
    drive: DriveHud | None = None
    ground: tuple[int, int, int] | None = None
    flash: str = ""

    @property
    def advance_interval(self) -> int:
        if self.drive is not None:
            return self.drive.advance_interval
        return self.main_hud_model.advance_interval


def hud_xy() -> tuple[int, int]:
    return MARGIN, MARGIN


def osr2_line_on(main_hud: MainHud) -> Osr2Line:
    model = main_hud.main_hud_model
    return line_shown_for(model, main_hud.drive, composed=kino_shows(model.main_mode))


class HudFonts(NamedTuple):
    body: ImageFont.FreeTypeFont
    tiny: ImageFont.FreeTypeFont
    icon: ImageFont.FreeTypeFont


def hud_fonts() -> HudFonts:
    return HudFonts(load_font(SIZE_BODY), load_font(SIZE_TINY), load_font(SIZE_BODY, SYMBOL_FONT))


class Slot(NamedTuple):
    corner: HudCorner
    reserve: int


def x_in(slot: Slot, hud_width: int, extent: int) -> int:
    return block_x(slot.corner, hud_width=hud_width, extent=extent, pad=_PAD, reserve=slot.reserve)


def filled(button: Button, main_hud: MainHud, word_font: ImageFont.FreeTypeFont) -> Button:
    if button.command:
        return button
    read = reading_its_host_value(button, {
        PLAYBACK_SPEED: format_rate(main_hud.main_hud_model.playback_speed),
        "advance_interval": f"{main_hud.advance_interval}s"})
    width = read.width
    if read.is_a_name:
        width = max(width, text_width(word_font, read.icon) + BUTTON_GAP)
    return replace(read, width=width)


def draw_rows(hud: Hud, rows: list[list[Button]], y: int, slot: Slot,
              hover: tuple[int, int] | None, fonts: HudFonts) -> list[tuple[Rect, Button]]:
    corner, reserve = slot
    width = hud.image.width
    placed = place_rows(rows, x=_PAD + (0 if corner.right else reserve), y=y,
                        ends_at=width - _PAD - reserve if corner.right else None)
    row_top = None
    for rect, button in placed:
        draw_button(hud.image, hud.draw, rect, button,
            ButtonLook(
                hovered=hover is not None and contains(rect, *hover),
                icon_font=fonts.icon,
                word_font=fonts.tiny,
                row_label=rect[1] != row_top))
        row_top = rect[1]
    return placed


@dataclass(frozen=True)
class Osr2Block:
    aim_rows: list[list[Button]]
    osr2_line: Osr2Line | None
    drive: DriveHud | None
    drive_w: int
    width: int
    height: int
    shown: bool


class Osr2PartDrawing:
    def __init__(self, fonts: HudFonts) -> None:
        self._fonts = fonts
        self._osr2 = Osr2Section()
        self._drive = DriveSection()

    def block(self, main_hud: MainHud) -> Osr2Block:
        model, drive = main_hud.main_hud_model, main_hud.drive
        aim_rows = [[filled(button, main_hud, self._fonts.tiny) for button in row]
                    for row in model.osr2_rows]
        osr2_line = osr2_line_on(main_hud) if model.has_osr2 else None
        drive_w, drive_h = section_size() if drive is not None else (0, 0)
        return Osr2Block(
            aim_rows, osr2_line, drive, drive_w,
            width=max(_row_width(aim_rows), drive_w,
                      self._osr2.width(osr2_line) if osr2_line is not None else 0),
            height=blocks_height([rows_height(aim_rows), _OSR2_H if osr2_line is not None else 0,
                                  drive_h], _BLOCK_GAP),
            shown=bool(aim_rows) or model.has_osr2 or drive is not None)

    def draw(self, hud: Hud, block: Osr2Block, y: int, slot: Slot,
             hover: tuple[int, int] | None) -> tuple[list[tuple[Rect, Button]], list[DriveTrack]]:
        buttons: list[tuple[Rect, Button]] = []
        tracks: list[DriveTrack] = []
        width = hud.image.width
        if block.aim_rows:
            buttons.extend(draw_rows(hud, block.aim_rows, y, slot, hover, self._fonts))
            y += rows_height(block.aim_rows) + _BLOCK_GAP

        if block.osr2_line is not None:
            osr2_x = x_in(slot, width, self._osr2.width(block.osr2_line))
            buttons.extend(self._osr2.draw(hud.image, hud.draw, (osr2_x, y), block.osr2_line,
                                           hover=hover))
            tracks.extend(self._osr2.bars(osr2_x, y, block.osr2_line))
            y += _OSR2_H + _BLOCK_GAP

        if block.drive is not None:
            drive_x = x_in(slot, width, block.drive_w)
            self._drive.draw(hud.image, drive_x, y, block.drive)
            targets, bars = visualizer_targets(drive_x, y, block.drive)
            buttons.extend(targets)
            tracks.extend(bars)
        return buttons, tracks


class PressableHud:
    def __init__(self, *, clock: Callable[[], float]) -> None:
        self._visualizer = VisualizerResolver(clock=clock)
        self._painted: tuple = (None,)
        self._heatmap = None
        self._fonts = hud_fonts()
        self._base: Image.Image | None = None
        self._tip: tuple[str, tuple[int, int]] | None = None
        self._image: Image.Image | None = None
        self._bgra: np.ndarray | None = None
        self.buttons: list[tuple[Rect, Button]] = []
        self.tracks: list[DriveTrack] = []
        self._grip = TrackGrip()
        self._origin = hud_xy()
        self._pointer: PointerReading[tuple[int, int] | None] = PointerReading(None)

    def _bgra_of(self, hud: MainHud, hover: tuple[int, int] | None, *contents,
                 heatmap=None) -> np.ndarray:
        if self._ensure(hud, hover, contents, heatmap) or self._bgra is None:
            self._bgra = to_bgra(self._image)
        return self._bgra

    def _rgba_of(self, hud: MainHud, hover: tuple[int, int] | None, *contents,
                 heatmap=None) -> tuple[bytes, tuple[int, int]]:
        self._ensure(hud, hover, contents, heatmap)
        return self._image.tobytes(), self._image.size

    # Pillow is nowhere near cheap enough to repaint this sixty times a second, so the bitmap is
    # kept until the HUD's contents or the button under the pointer change.
    def _ensure(self, hud: MainHud, hover: tuple[int, int] | None, contents: tuple,
                heatmap) -> bool:
        hud = self._resolve(hud)
        hover = hover if hover is not None else self._pointer.on(hud.main_hud_model)
        repainted = (hud, self._button_under(hover), *contents) != self._painted             or heatmap is not self._heatmap or self._base is None
        if repainted:
            self._base = self._paint(hud, hover, *contents)
            self._painted, self._heatmap = (hud, self._button_under(hover), *contents), heatmap
        tip = self._tip_at(hover)
        if not repainted and tip == self._tip:
            return False
        self._tip = tip
        self._image = self._base if tip is None else self._with_the_tooltip(*tip)
        return True

    def what_the_pointer_shows(self) -> object:
        at = self._pointer.reading
        return self._button_under(at), self._tip_at(at)

    def _button_under(self, at: tuple[int, int] | None) -> Rect | None:
        if at is None:
            return None
        return next((rect for rect, _button in self.buttons if contains(rect, *at)), None)

    def _tip_at(self, at: tuple[int, int] | None) -> tuple[str, tuple[int, int]] | None:
        tip = tooltip_at(self.buttons, *at) if at is not None else ""
        return (tip, at) if tip else None

    def _with_the_tooltip(self, tip: str, at: tuple[int, int]) -> Image.Image:
        tipped = self._base.copy()
        draw_tooltip(ImageDraw.Draw(tipped), self._fonts.tiny, tip, at, tipped.size)
        return tipped

    def _resolve(self, hud: MainHud) -> MainHud:
        model = hud.main_hud_model
        return replace(hud, drive=self._visualizer.resolve(
            hud.drive if model.has_osr2 else None,
            osr2=model.osr2, control=model.osr2_control, paused=model.paused,
            composed=kino_shows(model.main_mode)))

    def press_at(self, mx: int, my: int) -> str:
        self.release()
        px, py = self._local(mx, my)
        return hit_test(self.buttons, px, py) or self._grip.grab(self.tracks, px, py)

    def covers(self, mx: int, my: int) -> bool:
        return self._image is not None and contains(
            (0, 0, *self._image.size), *self._local(mx, my))

    @property
    def holding(self) -> bool:
        return self._grip.holding

    def drag_to(self, mx: int, my: int) -> str:
        return self._grip.drag_to(*self._local(mx, my))

    def release(self) -> None:
        self._grip.release()

    def hover_at(self, mx: int, my: int) -> tuple[int, int] | None:
        local = self._local(mx, my)
        return local if tooltip_at(self.buttons, *local) or hit_test(self.buttons, *local) else None

    def motion(self, mx: int, my: int) -> None:
        self._pointer.take(self.hover_at(mx, my))

    def leave(self) -> None:
        self._pointer.take(None)

    @property
    def hud_place(self) -> HudPlace | None:
        painted = self._painted[0]
        if painted is None:
            return None
        model = painted.main_hud_model
        return HudPlace(model.funestra, model.hud_corner, MARGIN,
                        minimized=model.hud_minimized, inset=_MINUS_INSET)

    def place(self, *, viewport: tuple[int, int], lower_edge: int = 0) -> tuple[int, int]:
        place = self.hud_place or HudPlace("", HudCorner.UPPER_LEFT, MARGIN)
        size = self._image.size if self._image is not None else (0, 0)
        self._origin = place.origin(hud=size, viewport=viewport, lower_edge=lower_edge)
        return self._origin

    def _local(self, mx: int, my: int) -> tuple[int, int]:
        left, top = self._origin
        return mx - left, my - top

