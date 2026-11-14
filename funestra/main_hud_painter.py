from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import NamedTuple

import numpy as np
from PIL import Image, ImageFont
from shared_ui.lettering import fit_text
from shared_ui.palette import (
    BG_PRIMARY,
    TEXT_MUTED,
    TEXT_PRIMARY,
)
from shared_ui.spacing import BUTTON_GAP, GAP_MEDIUM, GAP_SMALL, MARGIN_STANDARD
from shared_ui.type_scale import SIZE_BODY, SIZE_TINY

from .geometry import Rect, contains
from .host_controls import HostControlsHud, HostControlsLayout, HostControlsSection
from .hud import (
    ACTIVE_DOT,
    SYMBOL_FONT,
    TITLE_BASELINE,
    ButtonLook,
    Hud,
    active_dot_top,
    draw_active_dot,
    draw_button,
    draw_icon,
    draw_tooltip,
    load_font,
    text_width,
    to_bgra,
)
from .hud_button import reading_its_host_value
from .hud_controls import PLAYBACK_SPEED
from .hud_corners import HudPlace
from .hud_minimize import ROOM as MINUS_ROOM
from .hud_minimize import collapsed_button, corner_button_rect, minimize_button
from .hud_osr2 import HEIGHT as _OSR2_H
from .hud_osr2 import Osr2Line, Osr2Section, VisualizerResolver, line_shown_for
from .hud_placement import HudCorner, PointerReading, block_x
from .hud_row import ROW_H, RowHud, RowLayout, RowSection, row_layout
from .hud_sections import Stacked, blocks_height, stack
from .hud_title import (
    LATEST_LABEL,
    SEPARATOR,
    SHUFFLE_LABEL,
    HudTitleFacts,
    compilation_label,
    hud_title,
)
from .main_hud import (
    Button,
    MainHudModel,
    ModeHud,
    _row_width,
    hit_test,
    kino_shows,
    place_rows,
    rows_height,
    tooltip_at,
)
from .modes import LengthMode
from .name_copy import COPY_GAP, COPY_ICON, copy_button, copy_icon_ink, copy_icon_rect
from .osr2_visualizer import (
    DriveHud,
    DriveSection,
    DriveTrack,
    TrackGrip,
    section_size,
    visualizer_targets,
)
from .playback_rate import format_rate

_LENGTH_LABELS = {LengthMode.FULL: "Full", LengthMode.CLIPS: "Clips"}

_PAD = MARGIN_STANDARD
_MINUS_INSET = (_PAD, _PAD)
DOT_GAP = GAP_MEDIUM
MARGIN = MARGIN_STANDARD
_BLOCK_GAP = GAP_SMALL
_SUBTITLE_GAP = GAP_SMALL


@dataclass(frozen=True)
class MainHud:
    modes: ModeHud = field(default_factory=ModeHud)
    main_hud_model: MainHudModel = field(default_factory=MainHudModel)
    drive: DriveHud | None = None
    ground: tuple[int, int, int] | None = None
    flash: str = ""

    @property
    def advance_interval(self) -> int:
        if self.drive is not None:
            return self.drive.advance_interval
        return self.main_hud_model.advance_interval

    @property
    def title(self) -> str:
        compilation = (
            f"{compilation_label(self.modes.compilation)}"
            f"{SEPARATOR}{self.modes.position}/{self.modes.total}"
        ) if self.modes.compilation else ""
        order = "" if self.main_hud_model.latest is None else (
            LATEST_LABEL if self.main_hud_model.latest else SHUFFLE_LABEL)
        if not kino_shows(self.main_hud_model.main_mode) and not self.main_hud_model.locked and self.advance_interval:
            pace = f"{self.advance_interval}s"
            order = f"{order}{SEPARATOR}{pace}" if order else pace
        return hud_title(HudTitleFacts(
            playing_set=compilation,
            locked=self.main_hud_model.locked,
            order=order,
            f_mode=self.modes.scripted_filter,
            filters=self.main_hud_model.filters or (_LENGTH_LABELS.get(self.modes.length_mode, ""),),
        ))


def _section_rect(corner: HudCorner, width: int, reserve: int, top: int,
                  height: int) -> Rect:
    return (_PAD + (0 if corner.right else reserve), top, width - 2 * _PAD - reserve, height)


class _TopBlock(NamedTuple):
    title: str
    filename: str
    active: bool


@dataclass(frozen=True)
class _Plan:
    rows: list[list[Button]]
    device: Osr2Block
    top: _TopBlock
    item_row: RowHud | None
    host_controls: HostControlsHud | None
    row_h: int
    width: int
    reserves: list[int]
    sections: Stacked


def _reserved(widths: list[int], used: tuple[bool, ...], corner: HudCorner,
              minus_room: int) -> tuple[list[int], int]:
    last = max(index for index, present in enumerate(used) if present)
    reserves = [0] * len(widths)
    reserves[last if corner.lower else 0] = minus_room
    return reserves, max(width + reserve for width, reserve in zip(widths, reserves, strict=True))


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
    # kept until the HUD's contents change.
    def _ensure(self, hud: MainHud, hover: tuple[int, int] | None, contents: tuple,
                heatmap) -> bool:
        hud = self._resolve(hud)
        hover = hover if hover is not None else self._pointer.on(hud.main_hud_model)
        painted = (hud, hover, *contents)
        if painted == self._painted and heatmap is self._heatmap and self._image is not None:
            return False
        self._painted, self._heatmap = painted, heatmap
        self._image = self._paint(hud, hover, *contents)
        return True

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

    def _tooltip(self, hud: Hud, hover: tuple[int, int] | None, tiny: ImageFont.FreeTypeFont) -> None:
        if hover is not None:
            tip = tooltip_at(self.buttons, *hover)
            if tip:
                draw_tooltip(hud.draw, tiny, tip, hover, hud.image.size)


class MainHudPainter(PressableHud):
    def __new__(cls, *, device_only: bool = False, clock: Callable[[], float] = time.monotonic,
                **_whole):
        if device_only:
            from .osr2_part_painter import Osr2PartPainter  # noqa: PLC0415

            return Osr2PartPainter(clock=clock)
        return super().__new__(cls)

    def __init__(self, *, width: int | None = None, device_only: bool = False,
                 minus_on_the_hud: bool = True,
                 clock: Callable[[], float] = time.monotonic) -> None:
        assert not device_only
        super().__init__(clock=clock)
        self._width = width
        self._minus_on_the_hud = minus_on_the_hud
        self._fonts = hud_fonts()
        self._body, self._tiny, self._icon = self._fonts
        self._part = Osr2PartDrawing(self._fonts)
        self._item_row = RowSection()
        self._host_controls = HostControlsSection()
        self.row: RowLayout | None = None
        self.host_controls_layout: HostControlsLayout | None = None

    def bgra(self, hud: MainHud, *, hover: tuple[int, int] | None = None,
             item_row: RowHud | None = None, heatmap=None,
             host_controls: HostControlsHud | None = None) -> np.ndarray:
        return self._bgra_of(hud, hover, item_row, host_controls, heatmap=heatmap)

    def rgba(self, hud: MainHud, *, hover: tuple[int, int] | None = None,
             item_row: RowHud | None = None, heatmap=None,
             host_controls: HostControlsHud | None = None) -> tuple[bytes, tuple[int, int]]:
        return self._rgba_of(hud, hover, item_row, host_controls, heatmap=heatmap)

    def _copy_room(self, filename: str) -> int:
        return COPY_GAP + sum(self._tiny.getmetrics()) if filename else 0

    def _draw_top_block(self, hud: Hud, y: int, block: _TopBlock, slot: Slot,
                        hover: tuple[int, int] | None) -> Rect | None:
        draw = hud.draw
        width = hud.image.width
        _ascent, descent = self._body.getmetrics()
        baseline = y + TITLE_BASELINE
        indent = ACTIVE_DOT + DOT_GAP
        title_x = x_in(slot, width, indent + text_width(self._body, block.title))
        draw_active_dot(hud.image, title_x, active_dot_top(self._body, baseline), block.active)
        if block.title:
            draw.text((title_x + indent, baseline), block.title, font=self._body,
                      anchor="ls", fill=(*TEXT_PRIMARY, 255))
        if not block.filename:
            return None
        name_w = text_width(self._tiny, block.filename)
        name_x = x_in(slot, width, indent + name_w + self._copy_room(block.filename))
        line_top = baseline + descent + _SUBTITLE_GAP
        draw.text((name_x + indent, line_top), block.filename,
                  font=self._tiny, anchor="la", fill=(*TEXT_MUTED, 255))
        copy = copy_icon_rect(name_x + indent + name_w, line_top, sum(self._tiny.getmetrics()))
        draw_icon(hud.image, COPY_ICON, copy, copy_icon_ink(copy, hover))
        return copy

    def _paint(self, main_hud: MainHud, hover: tuple[int, int] | None,
               item_row: RowHud | None, host_controls: HostControlsHud | None) -> Image.Image:
        main_hud_model = main_hud.main_hud_model
        if main_hud_model.hud_minimized:
            return self._paint_minimized(main_hud_model.funestra, main_hud_model.hud_corner, hover, main_hud.flash)
        plan = self._plan(main_hud, item_row, host_controls)
        return self._draw_plan(main_hud, hover, plan)

    def _plan(self, main_hud: MainHud, item_row: RowHud | None,
              host_controls: HostControlsHud | None) -> _Plan:
        main_hud_model = main_hud.main_hud_model
        rows = [[filled(button, main_hud, self._tiny) for button in row]
                for row in main_hud_model.rows]
        device = self._part.block(main_hud)
        title = main_hud.title
        filename = main_hud.modes.video
        _body_ascent, body_descent = self._body.getmetrics()
        top_h = TITLE_BASELINE + body_descent
        tiny_h = sum(self._tiny.getmetrics())
        filename_h = (_SUBTITLE_GAP + tiny_h) if filename else 0

        corner = main_hud_model.hud_corner
        text_x = ACTIVE_DOT + DOT_GAP
        widths = [0, _row_width(rows), device.width,
                  self._item_row.least_width(item_row) if item_row is not None else 0,
                  self._host_controls.least_width(host_controls) if host_controls is not None else 0]
        minus_room = MINUS_ROOM if self._minus_on_the_hud else 0
        used = (True, bool(rows), device.shown, item_row is not None, host_controls is not None)
        reserves, parts_w = _reserved(widths, used, corner, minus_room)
        if self._width is None:
            width = 2 * _PAD + max(
                parts_w,
                reserves[0] + text_x + text_width(self._body, title),
                reserves[0] + text_x + text_width(self._tiny, filename)
                + self._copy_room(filename),
            )
        else:
            any_row = self._item_row.least_width_for_any_row() + (minus_room if corner.lower else 0)
            width = max(self._width, 2 * _PAD + parts_w, 2 * _PAD + any_row)
            room = width - 2 * _PAD - text_x - reserves[0]
            title = fit_text(self._body, title, room)
            filename = fit_text(self._tiny, filename, room - self._copy_room(filename))
        row_h = ROW_H if item_row is not None else 0
        sections = stack(_PAD, [
            top_h + filename_h,
            rows_height(rows),
            device.height,
            row_h,
            HostControlsSection.height if host_controls is not None else 0,
        ])
        return _Plan(rows, device, _TopBlock(title, filename, main_hud_model.active),
                     item_row, host_controls, row_h, width, reserves, sections)

    def _draw_plan(self, main_hud: MainHud, hover: tuple[int, int] | None,
                   plan: _Plan) -> Image.Image:
        main_hud_model = main_hud.main_hud_model
        corner = main_hud_model.hud_corner
        width, height = plan.width, plan.sections.end + _PAD
        hud = Hud(width, height, ground=main_hud.ground or BG_PRIMARY)
        for divider in plan.sections.dividers:
            hud.divide(divider)
        title_top, rows_top, device_top, _row_top, _host_top = plan.sections.tops

        copy = self._draw_top_block(hud, title_top, plan.top, Slot(corner, plan.reserves[0]), hover)
        self.buttons = draw_rows(hud, plan.rows, rows_top, Slot(corner, plan.reserves[1]),
                                 hover, self._fonts)
        if copy is not None:
            self.buttons.append((copy, copy_button()))
        device_buttons, self.tracks = self._part.draw(
            hud, plan.device, device_top, Slot(corner, plan.reserves[2]), hover)
        self.buttons.extend(device_buttons)

        if self._minus_on_the_hud:
            minus = (corner_button_rect(corner, hud=(width, height), inset=_MINUS_INSET),
                     minimize_button(main_hud_model.funestra))
            draw_button(hud.image, hud.draw, *minus,
                ButtonLook(
                    hovered=hover is not None and contains(minus[0], *hover),
                    icon_font=self._icon,
                    word_font=self._tiny))
            self.buttons.append(minus)
        self._draw_the_foot(hud.image, plan, corner)
        self._tooltip(hud, hover, self._tiny)
        return hud.image

    def _draw_the_foot(self, image: Image.Image, plan: _Plan, corner: HudCorner) -> None:
        *_above, row_top, host_top = plan.sections.tops
        self.row = None
        if plan.item_row is not None:
            self.row = row_layout(plan.item_row, rect=_section_rect(
                corner, image.width, plan.reserves[3], row_top, plan.row_h))
            self._item_row.draw(image, self.row, plan.item_row, heatmap=self._heatmap)
        self.host_controls_layout = None
        if plan.host_controls is not None:
            self.host_controls_layout = self._host_controls.draw(image, _section_rect(
                corner, image.width, plan.reserves[4], host_top, HostControlsSection.height),
                plan.host_controls)

    def _paint_minimized(self, funestra: str, corner: HudCorner,
                         hover: tuple[int, int] | None, flash: str) -> Image.Image:
        image, buttons = collapsed_button(funestra, corner, hover=hover,
                                          room_for_the_tooltip=self._width is not None,
                                          flash=flash)
        self.buttons, self.tracks, self.row, self.host_controls_layout = buttons, [], None, None
        return image


def with_playback_speed(main_hud_model: MainHudModel, speed: float) -> MainHudModel:
    return replace(main_hud_model, playback_speed=speed)
