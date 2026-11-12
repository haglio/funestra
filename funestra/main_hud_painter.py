from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import NamedTuple

import numpy as np
from PIL import Image
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
from .hud_osr2 import (
    Osr2Line,
    Osr2Section,
    VisualizerResolver,
    line_shown_for,
)
from .hud_placement import HudCorner, PointerReading, block_x
from .hud_row import ROW_H, RowHud, RowLayout, RowSection, row_layout
from .hud_sections import Stacked, blocks_height, stack
from .hud_title import (
    LATEST_LABEL,
    SEPARATOR,
    SHUFFLE_LABEL,
    HudTitleFacts,
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

_REVISION = re.compile(r"\s*\(v\d+\)$")


def compilation_label(title: str) -> str:
    volume = title.rsplit(" - ", 1)[-1]
    return _REVISION.sub("", volume).strip()


_PAD = MARGIN_STANDARD
_MINUS_INSET = (_PAD, _PAD)
DOT_GAP = GAP_MEDIUM
MARGIN = MARGIN_STANDARD
_BLOCK_GAP = GAP_SMALL
_SUBTITLE_GAP = GAP_SMALL


def hud_xy() -> tuple[int, int]:
    return MARGIN, MARGIN


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


class _Slot(NamedTuple):
    corner: HudCorner
    reserve: int


class _TopBlock(NamedTuple):
    title: str
    filename: str
    active: bool


@dataclass(frozen=True)
class _Plan:
    whole: bool
    rows: list[list[Button]]
    aim_rows: list[list[Button]]
    top: _TopBlock
    osr2_line: Osr2Line | None
    item_row: RowHud | None
    host_controls: HostControlsHud | None
    drive_w: int
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


def osr2_line_on(main_hud: MainHud) -> Osr2Line:
    model = main_hud.main_hud_model
    return line_shown_for(model, main_hud.drive, composed=kino_shows(model.main_mode))


class MainHudPainter:
    def __init__(self, *, width: int | None = None, device_only: bool = False,
                 minus_on_the_hud: bool = True,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self._width = width
        self._device_only = device_only
        self._minus_on_the_hud = minus_on_the_hud
        self._body = load_font(SIZE_BODY)
        self._tiny = load_font(SIZE_TINY)
        self._icon = load_font(SIZE_BODY, SYMBOL_FONT)
        self._drive = DriveSection()
        self._osr2 = Osr2Section()
        self._item_row = RowSection()
        self._host_controls = HostControlsSection()
        self._painted: tuple = (None, None, None, None, None)
        self._image: Image.Image | None = None
        self._bgra: np.ndarray | None = None
        self.buttons: list[tuple[Rect, Button]] = []
        self.tracks: list[DriveTrack] = []
        self.row: RowLayout | None = None
        self.host_controls_layout: HostControlsLayout | None = None
        self._grip = TrackGrip()
        self._visualizer = VisualizerResolver(clock=clock)
        self._origin = hud_xy()
        self._pointer: PointerReading[tuple[int, int] | None] = PointerReading(None)

    def bgra(self, hud: MainHud, *, hover: tuple[int, int] | None = None,
             item_row: RowHud | None = None, heatmap=None,
             host_controls: HostControlsHud | None = None) -> np.ndarray:
        if (self._ensure(self._resolve(hud), hover, item_row, heatmap, host_controls)
                or self._bgra is None):
            self._bgra = to_bgra(self._image)
        return self._bgra

    def rgba(self, hud: MainHud, *, hover: tuple[int, int] | None = None,
             item_row: RowHud | None = None, heatmap=None,
             host_controls: HostControlsHud | None = None) -> tuple[bytes, tuple[int, int]]:
        self._ensure(self._resolve(hud), hover, item_row, heatmap, host_controls)
        return self._image.tobytes(), self._image.size

    def _resolve(self, hud: MainHud) -> MainHud:
        main_hud_model = hud.main_hud_model
        return replace(hud, drive=self._visualizer.resolve(
            hud.drive if main_hud_model.has_osr2 else None,
            osr2=main_hud_model.osr2, control=main_hud_model.osr2_control, paused=main_hud_model.paused,
            composed=kino_shows(main_hud_model.main_mode)))

    # Pillow is nowhere near cheap enough to repaint this sixty times a second, so the bitmap is
    # kept until the HUD's contents change.
    def _ensure(self, hud: MainHud, hover: tuple[int, int] | None,
                item_row: RowHud | None = None, heatmap=None,
                host_controls: HostControlsHud | None = None) -> bool:
        hover = hover if hover is not None else self._pointer.on(hud.main_hud_model)
        if ((hud, hover, item_row, host_controls) == self._painted[:4]
                and heatmap is self._painted[4] and self._image is not None):
            return False
        self._painted = (hud, hover, item_row, host_controls, heatmap)
        self._image = self._paint(hud, hover, item_row, heatmap, host_controls)
        return True

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
        main_hud_model = painted.main_hud_model
        return HudPlace(main_hud_model.funestra, main_hud_model.hud_corner, MARGIN,
                        minimized=main_hud_model.hud_minimized, inset=_MINUS_INSET)

    def place(self, *, viewport: tuple[int, int], lower_edge: int = 0) -> tuple[int, int]:
        place = self.hud_place or HudPlace("", HudCorner.UPPER_LEFT, MARGIN)
        size = self._image.size if self._image is not None else (0, 0)
        self._origin = place.origin(hud=size, viewport=viewport, lower_edge=lower_edge)
        return self._origin

    def _local(self, mx: int, my: int) -> tuple[int, int]:
        left, top = self._origin
        return mx - left, my - top

    def _block_x(self, corner: HudCorner, hud_width: int, extent: int,
                 reserve: int = 0) -> int:
        return block_x(corner, hud_width=hud_width, extent=extent, pad=_PAD,
                       reserve=reserve)

    def _copy_room(self, filename: str) -> int:
        return COPY_GAP + sum(self._tiny.getmetrics()) if filename else 0

    def _draw_top_block(self, hud: Hud, y: int, block: _TopBlock, slot: _Slot,
                        hover: tuple[int, int] | None) -> Rect | None:
        draw = hud.draw
        width = hud.image.width
        _ascent, descent = self._body.getmetrics()
        baseline = y + TITLE_BASELINE
        indent = ACTIVE_DOT + DOT_GAP
        title_x = self._block_x(slot.corner, width,
                                 indent + text_width(self._body, block.title), slot.reserve)
        draw_active_dot(hud.image, title_x, active_dot_top(self._body, baseline), block.active)
        if block.title:
            draw.text((title_x + indent, baseline), block.title, font=self._body,
                      anchor="ls", fill=(*TEXT_PRIMARY, 255))
        if not block.filename:
            return None
        name_w = text_width(self._tiny, block.filename)
        name_x = self._block_x(slot.corner, width,
                               indent + name_w + self._copy_room(block.filename), slot.reserve)
        line_top = baseline + descent + _SUBTITLE_GAP
        draw.text((name_x + indent, line_top), block.filename,
                  font=self._tiny, anchor="la", fill=(*TEXT_MUTED, 255))
        copy = copy_icon_rect(name_x + indent + name_w, line_top, sum(self._tiny.getmetrics()))
        draw_icon(hud.image, COPY_ICON, copy, copy_icon_ink(copy, hover))
        return copy

    def _draw_rows(self, hud: Hud, rows: list[list[Button]], y: int, slot: _Slot,
                   hover: tuple[int, int] | None) -> list[tuple[Rect, Button]]:
        corner, reserve = slot
        width = hud.image.width
        placed = place_rows(rows, x=_PAD + (0 if corner.right else reserve), y=y,
                            ends_at=width - _PAD - reserve if corner.right else None)
        row_top = None
        for rect, button in placed:
            draw_button(hud.image, hud.draw, rect, button,
                ButtonLook(
                    hovered=hover is not None and contains(rect, *hover),
                    icon_font=self._icon,
                    word_font=self._tiny,
                    row_label=rect[1] != row_top))
            row_top = rect[1]
        return placed

    def _paint(self, main_hud: MainHud, hover: tuple[int, int] | None = None,
               item_row: RowHud | None = None, heatmap=None,
               host_controls: HostControlsHud | None = None) -> Image.Image:
        main_hud_model = main_hud.main_hud_model
        if main_hud_model.hud_minimized:
            return self._paint_minimized(main_hud_model.funestra, main_hud_model.hud_corner, hover, main_hud.flash)
        plan = self._plan(main_hud, item_row, host_controls)
        return self._draw_plan(main_hud, hover, plan, heatmap)

    def _plan(self, main_hud: MainHud, item_row: RowHud | None,
              host_controls: HostControlsHud | None) -> _Plan:
        main_hud_model, drive = main_hud.main_hud_model, main_hud.drive
        whole = not self._device_only
        rows = [[self._filled(button, main_hud) for button in row]
                for row in (main_hud_model.rows if whole else ())]
        aim_rows = [[self._filled(button, main_hud) for button in row] for row in main_hud_model.osr2_rows]
        title = main_hud.title if whole else ""
        filename = main_hud.modes.video if whole else ""
        item_row = item_row if whole else None
        drive_w, drive_h = section_size() if drive is not None else (0, 0)
        _body_ascent, body_descent = self._body.getmetrics()
        top_h = TITLE_BASELINE + body_descent if whole else 0
        tiny_h = sum(self._tiny.getmetrics())
        filename_h = (_SUBTITLE_GAP + tiny_h) if filename else 0

        corner = main_hud_model.hud_corner
        text_x = ACTIVE_DOT + DOT_GAP
        osr2_line = osr2_line_on(main_hud) if main_hud_model.has_osr2 else None
        widths = [0, _row_width(rows),
                  max(_row_width(aim_rows), drive_w,
                      self._osr2.width(osr2_line) if osr2_line is not None else 0),
                  self._item_row.least_width(item_row) if item_row is not None else 0,
                  self._host_controls.least_width(host_controls) if host_controls is not None else 0]
        minus_room = MINUS_ROOM if whole and self._minus_on_the_hud else 0
        used = (True, bool(rows), bool(aim_rows) or main_hud_model.has_osr2 or drive is not None,
                item_row is not None, host_controls is not None)
        reserves, parts_w = _reserved(widths, used, corner, minus_room)
        if self._width is None:
            width = 2 * _PAD + max(
                parts_w,
                reserves[0] + text_x + text_width(self._body, title),
                reserves[0] + text_x + text_width(self._tiny, filename)
                + self._copy_room(filename),
            )
        else:
            any_row = (self._item_row.least_width_for_any_row()
                       + (minus_room if corner.lower else 0)) if whole else 0
            width = max(self._width, 2 * _PAD + parts_w, 2 * _PAD + any_row)
            room = width - 2 * _PAD - text_x - reserves[0]
            title = fit_text(self._body, title, room)
            filename = fit_text(self._tiny, filename, room - self._copy_room(filename))
        row_h = ROW_H if item_row is not None else 0
        sections = stack(_PAD, [
            top_h + filename_h,
            rows_height(rows),
            blocks_height([rows_height(aim_rows), _OSR2_H if osr2_line is not None else 0,
                           drive_h], _BLOCK_GAP),
            row_h,
            HostControlsSection.height if host_controls is not None else 0,
        ])
        return _Plan(whole, rows, aim_rows, _TopBlock(title, filename, main_hud_model.active),
                     osr2_line, item_row, host_controls, drive_w, row_h, width, reserves, sections)

    def _draw_plan(self, main_hud: MainHud, hover: tuple[int, int] | None, plan: _Plan,
                   heatmap) -> Image.Image:
        main_hud_model = main_hud.main_hud_model
        corner = main_hud_model.hud_corner
        width, height = plan.width, plan.sections.end + _PAD
        hud = Hud(width, height, ground=main_hud.ground or BG_PRIMARY)
        for divider in plan.sections.dividers:
            hud.divide(divider)
        title_top, rows_top, device_top, _row_top, _host_top = plan.sections.tops

        copy = (self._draw_top_block(hud, title_top, plan.top, _Slot(corner, plan.reserves[0]),
                                     hover)
                if plan.whole else None)
        self.buttons = self._draw_rows(hud, plan.rows, rows_top, _Slot(corner, plan.reserves[1]),
                                       hover)
        if copy is not None:
            self.buttons.append((copy, copy_button()))
        self.tracks = []
        self._draw_device_block(hud, main_hud, plan, device_top, hover)

        if plan.whole and self._minus_on_the_hud:
            minus = (corner_button_rect(corner, hud=(width, height), inset=_MINUS_INSET),
                     minimize_button(main_hud_model.funestra))
            draw_button(hud.image, hud.draw, *minus,
                ButtonLook(
                    hovered=hover is not None and contains(minus[0], *hover),
                    icon_font=self._icon,
                    word_font=self._tiny))
            self.buttons.append(minus)
        self._draw_the_foot(hud.image, plan, corner, heatmap)

        if hover is not None:
            tip = tooltip_at(self.buttons, *hover)
            if tip:
                draw_tooltip(hud.draw, self._tiny, tip, hover, (width, height))
        return hud.image

    def _draw_device_block(self, hud: Hud, main_hud: MainHud, plan: _Plan, y: int,
                           hover: tuple[int, int] | None) -> None:
        main_hud_model, drive = main_hud.main_hud_model, main_hud.drive
        corner, width, reserve = main_hud_model.hud_corner, hud.image.width, plan.reserves[2]
        if plan.aim_rows:
            self.buttons.extend(self._draw_rows(hud, plan.aim_rows, y, _Slot(corner, reserve),
                                                hover))
            y += rows_height(plan.aim_rows) + _BLOCK_GAP

        if plan.osr2_line is not None:
            osr2_x = self._block_x(corner, width, self._osr2.width(plan.osr2_line), reserve)
            self.buttons.extend(self._osr2.draw(hud.image, hud.draw, (osr2_x, y), plan.osr2_line,
                                                hover=hover))
            self.tracks.extend(self._osr2.bars(osr2_x, y, plan.osr2_line))
            y += _OSR2_H + _BLOCK_GAP

        if drive is not None:
            drive_x = self._block_x(corner, width, plan.drive_w, reserve)
            self._drive.draw(hud.image, drive_x, y, drive)
            targets, bars = visualizer_targets(drive_x, y, drive)
            self.buttons.extend(targets)
            self.tracks.extend(bars)

    def _draw_the_foot(self, image: Image.Image, plan: _Plan, corner: HudCorner,
                       heatmap) -> None:
        *_above, row_top, host_top = plan.sections.tops
        self.row = None
        if plan.item_row is not None:
            self.row = row_layout(plan.item_row, rect=_section_rect(
                corner, image.width, plan.reserves[3], row_top, plan.row_h))
            self._item_row.draw(image, self.row, plan.item_row, heatmap=heatmap)
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

    def _filled(self, button: Button, hud: MainHud) -> Button:
        if button.command:
            return button
        read = reading_its_host_value(button, {
            PLAYBACK_SPEED: format_rate(hud.main_hud_model.playback_speed),
            "advance_interval": f"{hud.advance_interval}s"})
        width = read.width
        if read.is_a_name:
            width = max(width, text_width(self._tiny, read.icon) + BUTTON_GAP)
        return replace(read, width=width)


def with_playback_speed(main_hud_model: MainHudModel, speed: float) -> MainHudModel:
    return replace(main_hud_model, playback_speed=speed)
