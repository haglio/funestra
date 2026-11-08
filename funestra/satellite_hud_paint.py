from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import NamedTuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shared_ui.lettering import fit_text
from shared_ui.palette import (
    BG_BUTTON,
    BG_TERTIARY,
    BLUE,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WHITE,
)
from shared_ui.type_scale import SIZE_BODY, SIZE_TINY

from funestra.hud import (
    SYMBOL_FONT,
    TITLE_BASELINE,
    ButtonGroundState,
    ButtonLook,
    Hud,
    active_dot_top,
    button_ground,
    draw_active_dot,
    draw_button,
    draw_character,
    draw_icon,
    draw_tooltip,
    load_font,
    text_width,
    to_bgra,
)
from funestra.hud_button import Button
from funestra.hud_icons import SHARED_ICON, shared_icon, shared_icon_name

from .geometry import Rect, contains
from .hud_minimize import ROOM as MINIMIZE_ROOM
from .hud_minimize import collapsed_hud, corner_button_rect, minimize_button
from .hud_osr2 import HEIGHT as OSR2_H
from .hud_osr2 import (
    Osr2Line,
    Osr2Section,
    VisualizerResolver,
    line_shown_for,
)
from .hud_placement import block_x
from .hud_row import ROW_H, RowHud, RowSection, row_layout
from .osr2_visualizer import DriveSection, DriveTrack, section_size, visualizer_targets
from .satellite_hud import (
    ACT_GAP,
    BLOCK_GAP,
    COL_LABEL_GAP,
    COL_LABEL_H,
    CONTROL_ROW_H,
    ELLIPSIS_ROOM,
    EXPAND_ICON,
    FAVORITE_ICON,
    LOOP_ICON,
    MAP_THUMB_H,
    MINUS_INSET,
    MODE_LABEL_PAD,
    NAV_MAP_COLUMN_H,
    NAV_MAP_GAP,
    PAD,
    ROW_LABEL_GUTTER,
    SUBTITLE_GAP,
    TITLE_INDENT,
    TITLE_X,
    WRONG_ACTION_ICON,
    WRONG_BTN,
    WRONG_GAP,
    HudCell,
    HudLayout,
    HudModel,
    HudTargets,
    NavMapRects,
    NavMapWindow,
    SectionHeights,
    act_is_filtered,
    act_named,
    action_label_blocks,
    build_click_targets,
    button_row_rects,
    button_row_width,
    device_height,
    expand_button_rect,
    favorite_icon_rect,
    filter_button_rects,
    hud_layout,
    hud_width,
    label_is_filtered,
    label_stack_top,
    largest_size_that_fits,
    loop_button_rects,
    looped_group_rect,
    map_block_width,
    name_line,
    nav_map_row_width,
    place_rects,
    place_width,
    playing_rect,
    rows_with_the_speed,
    seed_column_label,
    split_acts,
    thumbnail_rect,
    wrong_action_rect,
)
from .satellite_hud_nav_map import (
    count_lines,
    dashed_rect,
    draw_ellipses,
    narrowed_to_window,
)

_PLACEHOLDER = BG_TERTIARY

_DIM = 0.5
_BORDER_W = 2
_COUNT_LINE_H = 11

_LOOP_ICON = shared_icon(LOOP_ICON)
_EXPAND_ICON = shared_icon(EXPAND_ICON)


@dataclass(frozen=True)
class RenderedHud:
    bgra: np.ndarray
    targets: HudTargets


@dataclass(frozen=True)
class DrawnWith:
    video: str = ""
    hover_loop: str = ""
    hover_tip: str = ""
    hover_pos: tuple[int, int] | None = None
    may_grow_on_hover: bool = True
    minus_on_the_hud: bool = True
    flash: str = ""


PLAIN = DrawnWith()


class NavMapThumbs(NamedTuple):
    corner: Image.Image | None
    seeds: list[Image.Image]
    actions: list[Image.Image]


class _NavMap(NamedTuple):
    counts: tuple[str, ...]
    thumbs: NavMapThumbs
    windows: tuple[NavMapWindow | None, NavMapWindow | None]


class _Title(NamedTuple):
    font: ImageFont.FreeTypeFont
    subtitle: str
    reserve: int


@dataclass(frozen=True)
class _Sizes:
    rows: list[list[Button]]
    widths: list[list[int]]
    device_rows: list[list[Button]]
    device_row_widths: list[list[int]]
    osr2_line: Osr2Line
    foot_h: int
    width: int
    row_h: int
    layout: HudLayout


@dataclass(frozen=True)
class _DrawnButTheRow:
    drawn_for: tuple
    image: Image.Image
    bgra: np.ndarray
    row_rect: tuple[int, int, int, int]
    targets: HudTargets


class HudRenderer:
    def __init__(self, funestra: str) -> None:
        self._funestra = funestra
        self._body = load_font(SIZE_BODY)
        self._titles: dict[int, ImageFont.FreeTypeFont] = {SIZE_BODY: self._body}
        self._tiny = load_font(SIZE_TINY)
        self._pointer: tuple[int, int] | None = None
        self._icon = load_font(SIZE_BODY, SYMBOL_FONT)
        self._thumbs_by_path: dict[str, Image.Image] = {}
        self._osr2 = Osr2Section()
        self._drive = DriveSection()
        self._visualizer = VisualizerResolver()
        self._item_row = RowSection()
        self._drawn: _DrawnButTheRow | None = None

    def _thumbnail(self, cell: HudCell) -> Image.Image:
        place_w = place_width(self._funestra)
        if cell.thumb:
            cached = self._thumbs_by_path.get(cell.thumb)
            if cached is None:
                try:
                    image = Image.open(cell.thumb).convert("RGBA")
                except OSError:
                    image = None
                if image is not None:
                    scale = min(place_w / max(1, image.width), MAP_THUMB_H / max(1, image.height))
                    cached = image.resize((max(1, round(image.width * scale)),
                                           max(1, round(image.height * scale))))
                    self._thumbs_by_path[cell.thumb] = cached
            if cached is not None:
                return cached
        return Image.new("RGBA", (place_w, MAP_THUMB_H), (*_PLACEHOLDER, 255))

    def _nav_map_thumbnails(
        self, model: HudModel
    ) -> tuple[Image.Image | None, list[Image.Image], list[Image.Image]]:
        if model.corner is None:
            return None, [], []
        return (self._thumbnail(model.corner),
                [self._thumbnail(cell) for cell in model.seeds],
                [self._thumbnail(cell) for cell in model.actions])

    @staticmethod
    def _block_x(model: HudModel, hud_width: int, extent: int, reserve: int = 0) -> int:
        return block_x(model.hud_corner, hud_width=hud_width, extent=extent, pad=PAD,
                       reserve=reserve)

    def render(
        self,
        model: HudModel,
        *,
        item_row: RowHud | None = None,
        heatmap: np.ndarray | None = None,
        drawn_with: DrawnWith = PLAIN,
    ) -> RenderedHud:
        self._pointer = drawn_with.hover_pos
        if model.hud_minimized:
            bgra, buttons = collapsed_hud(
                model.funestra, model.hud_corner, hover=self._pointer,
                room_for_the_tooltip=not drawn_with.may_grow_on_hover, flash=drawn_with.flash)
            return RenderedHud(bgra, HudTargets(click=[], loop=[], filter=[], expand=None,
                                                buttons=buttons))
        model = replace(model, drive=self._visualizer.resolve(
            model.drive, osr2=model.osr2, control=model.osr2_control, paused=model.paused,
            composed=model.drive_composed))
        drawn_for = self._all_but_the_row(model, item_row, drawn_with)
        if drawn_for is not None and self._drawn is not None and self._drawn.drawn_for == drawn_for:
            return self._with_the_row(self._drawn, item_row, heatmap)
        return self._drawn_whole(model, drawn_for, item_row, heatmap, drawn_with)

    def _measure(self, model: HudModel, item_row: RowHud | None,
                 drawn_with: DrawnWith) -> _Sizes:
        rows = rows_with_the_speed(model)
        widths = [self._row_widths(row) for row in rows]
        device_rows = [list(row) for row in model.osr2_rows]
        device_row_widths = [self._row_widths(row) for row in device_rows]
        bar_width = max((
            2 * PAD + button_row_width(row, row_widths)
            for row, row_widths in zip(rows + device_rows, widths + device_row_widths, strict=True)
            if row
        ), default=0)
        osr2_line = line_shown_for(model, model.drive, composed=model.drive_composed)
        drive_w, drive_h = section_size() if model.drive is not None else (0, 0)
        device_w = max(self._osr2.width(osr2_line) if model.osr2 else 0, drive_w)
        foot_w, foot_h = model.foot.size() if model.foot is not None else (0, 0)
        width = hud_width(model.funestra, text_width(self._tiny, drawn_with.video),
                          content_width=max(
                                bar_width,
                                2 * PAD + device_w if device_w else 0,
                                2 * PAD + foot_w if foot_w else 0,
                                2 * PAD + self._item_row.least_width(item_row)
                                if item_row is not None else 0))
        row_h = ROW_H if item_row is not None else 0
        layout = hud_layout(
            heights=SectionHeights(
                self._title_height(), row_h,
                device_height(model.osr2, model.drive, drive_h, len(device_rows)), foot_h),
            bars=len(rows))
        return _Sizes(rows, widths, device_rows, device_row_widths, osr2_line, foot_h, width,
                      row_h, layout)

    def _drawn_whole(self, model: HudModel, drawn_for: tuple | None, item_row: RowHud | None,
                     heatmap: np.ndarray | None, drawn_with: DrawnWith) -> RenderedHud:
        counts = count_lines(model)
        model, seed_win, action_win = narrowed_to_window(model)
        thumbs = NavMapThumbs(*self._nav_map_thumbnails(model))
        sizes = self._measure(model, item_row, drawn_with)
        layout, width, foot_h = sizes.layout, sizes.width, sizes.foot_h
        hud = Hud(width, layout.height)
        for divider in layout.dividers:
            hud.divide(divider)
        image, draw = hud.image, hud.draw

        x = PAD
        minus_room = MINIMIZE_ROOM if drawn_with.minus_on_the_hud else 0
        room = width - TITLE_X - PAD - minus_room
        title_font = self._title_font(largest_size_that_fits(
            SIZE_BODY, room,
            lambda size: text_width(self._title_font(size), model.title)))
        model = replace(model, title=fit_text(title_font, model.title, room))
        favorite = self._draw_title_row(
            hud, PAD, model,
            _Title(title_font, name_line(drawn_with.video, model.item_note, room, self._tiny),
                   0 if model.hud_corner.lower else minus_room))
        buttons: list[tuple[Rect, Button]] = []
        if drawn_with.minus_on_the_hud:
            buttons.append(self._draw_minus(hud, model))
        buttons.extend(self._draw_button_rows(hud, model, sizes.rows, sizes.widths, layout.bars))

        row = None
        if item_row is not None:
            row = row_layout(item_row, rect=(x, layout.row, width - 2 * PAD, sizes.row_h))
        device_buttons, bars = self._draw_device(hud, model, layout.device, sizes)
        buttons.extend(device_buttons)
        foot_rect = None
        if model.foot is not None:
            foot_rect = (x, layout.foot, width - 2 * PAD, foot_h)
            buttons.extend(model.foot.paint(image, x, layout.foot, width - 2 * PAD,
                                            self._pointer))

        nav_map_targets = (self._draw_nav_map(
                               hud, model, layout.nav_map,
                               _NavMap(counts, thumbs, (seed_win, action_win)),
                               drawn_with.hover_loop)
                           if thumbs.corner is not None
                           else HudTargets(click=[], loop=[], filter=[], expand=None))
        targets = replace(nav_map_targets, tracks=bars, row=row, foot=foot_rect, buttons=buttons,
                          favorite=favorite)
        if drawn_for is not None:
            self._drawn = _DrawnButTheRow(drawn_for, image, to_bgra(image), row.rect, targets)
            return self._with_the_row(self._drawn, item_row, heatmap)
        if row is not None:
            self._item_row.draw(image, row, item_row, heatmap=heatmap)
        if drawn_with.hover_tip:
            draw_tooltip(draw, self._tiny, drawn_with.hover_tip, drawn_with.hover_pos,
                         image.size)
        return RenderedHud(hud.to_bgra(), targets)

    def _draw_minus(self, hud: Hud, model: HudModel) -> tuple[Rect, Button]:
        minus = (corner_button_rect(model.hud_corner, hud=hud.image.size, inset=MINUS_INSET),
                 minimize_button(model.funestra))
        draw_button(hud.image, hud.draw, *minus,
            ButtonLook(
                hovered=self._pointer_is_on(minus[0]),
                icon_font=self._icon,
                word_font=self._tiny))
        return minus

    def _draw_button_rows(self, hud: Hud, model: HudModel, rows, widths,
                          y: int) -> list[tuple[Rect, Button]]:
        buttons: list[tuple[Rect, Button]] = []
        for row, row_widths in zip(rows, widths, strict=True):
            placed = button_row_rects(
                self._block_x(model, hud.image.width, button_row_width(row, row_widths)),
                y, row, row_widths)
            for index, (rect, button) in enumerate(placed):
                draw_button(hud.image, hud.draw, rect, button,
                    ButtonLook(
                        hovered=self._pointer_is_on(rect),
                        icon_font=self._icon,
                        word_font=self._tiny,
                        row_label=index == 0))
            buttons.extend(placed)
            y += CONTROL_ROW_H
        return buttons

    def _all_but_the_row(self, model: HudModel, item_row: RowHud | None,
                         drawn_with: DrawnWith) -> tuple | None:
        if item_row is None or drawn_with.hover_tip:
            return None
        return model, self._item_row.least_width(item_row), drawn_with

    def _with_the_row(self, drawn: _DrawnButTheRow, item_row: RowHud, heatmap) -> RenderedHud:
        x, y, width, height = drawn.row_rect
        region = drawn.image.crop((x, y, x + width, y + height))
        self._item_row.draw(region, row_layout(item_row, rect=(0, 0, width, height)), item_row,
                            heatmap=heatmap)
        bgra = drawn.bgra.copy()
        bgra[y:y + height, x:x + width] = to_bgra(region)
        return RenderedHud(bgra, replace(drawn.targets,
                                         row=row_layout(item_row, rect=drawn.row_rect)))

    def _draw_nav_map(self, hud: Hud, model: HudModel, top: int, nav: _NavMap,
                      hover_loop: str) -> HudTargets:
        image, draw = hud.image, hud.draw
        gutter_x = self._block_x(model, image.width, map_block_width(model.funestra))
        self._draw_counts(draw, gutter_x, top, nav.counts)
        nav_map_x = gutter_x + ROW_LABEL_GUTTER + ELLIPSIS_ROOM
        nav_map_y = top + COL_LABEL_H + COL_LABEL_GAP + ELLIPSIS_ROOM
        rects = place_rects(
            origin=(nav_map_x, nav_map_y), place_w=place_width(model.funestra),
            seeds=len(nav.thumbs.seeds), actions=len(nav.thumbs.actions), playing=model.playing)
        seed_win, action_win = nav.windows

        thumbnails = self._draw_thumbnails(image, model, rects, nav.thumbs)
        held = playing_rect(model.playing, rects.corner, rects.seeds, rects.actions)
        if model.locked and held is not None:
            hx, hy, hw, hh = thumbnails[held]
            draw.rectangle([hx, hy, hx + hw - 1, hy + hh - 1],
                           outline=(*WHITE, 255), width=_BORDER_W)
        wrong_rect, word_rects = self._draw_labels(hud, model, (gutter_x, top), rects,
                                                   seed_offset=seed_win.start if seed_win else 0)
        filter_rects = filter_button_rects(rects.corner, rects.actions, gutter_x,
                                           model.current_action,
                                           [cell.label for cell in model.actions])
        self._draw_filter_buttons(hud, filter_rects, model)

        loop_action_rect, loop_seed_rect = loop_button_rects(
            rects.corner, row_end=nav_map_x + nav_map_row_width(model.funestra),
            column_end=nav_map_y + NAV_MAP_COLUMN_H, reserve=ELLIPSIS_ROOM,
            column_rect=rects.column)
        expand_rect = expand_button_rect(loop_seed_rect)
        self._draw_loop_controls(hud, rects, (loop_action_rect, loop_seed_rect),
                                 model.active_loop, hover_loop)
        for axis, window in (("seed", seed_win), ("action", action_win)):
            if window is not None:
                draw_ellipses(image, rects, axis, window)
        if expand_rect is not None:
            self._icon_button(hud, expand_rect, _EXPAND_ICON)
        return HudTargets(
            click=build_click_targets(rects, model),
            loop=[(button, kind)
                  for kind, button in (("action", loop_action_rect), ("seed", loop_seed_rect))
                  if button is not None],
            filter=filter_rects,
            expand=expand_rect,
            wrong_action=wrong_rect,
            words=word_rects,
        )

    def _draw_device(self, hud: Hud, model: HudModel, y: int,
                     sizes: _Sizes) -> tuple[list[tuple[Rect, Button]], list[DriveTrack]]:
        width = hud.image.width
        buttons = self._draw_button_rows(hud, model, sizes.device_rows,
                                         sizes.device_row_widths, y)
        y += CONTROL_ROW_H * len(sizes.device_rows)
        bars: list[DriveTrack] = []
        max_intensity_bars: list[DriveTrack] = []
        if model.osr2:
            osr2_x = self._block_x(model, width, self._osr2.width(sizes.osr2_line))
            buttons.extend(self._osr2.draw(hud.image, hud.draw, (osr2_x, y), sizes.osr2_line,
                                           hover=self._pointer))
            max_intensity_bars = self._osr2.bars(osr2_x, y, sizes.osr2_line)
            y += OSR2_H + BLOCK_GAP
        if model.drive is not None:
            drive_x = self._block_x(model, width, section_size()[0])
            self._drive.draw(hud.image, drive_x, y, model.drive)
            drive_targets, bars = visualizer_targets(drive_x, y, model.drive)
            buttons.extend(drive_targets)
        return buttons, bars + max_intensity_bars

    def _row_widths(self, row: list[Button]) -> list[int]:
        return [self._button_width(button, flush_left=index == 0 and not button.command)
                for index, button in enumerate(row)]

    def _button_width(self, button: Button, *, flush_left: bool) -> int:
        pads = 1 if flush_left else 2
        return button.width or text_width(self._tiny, button.icon) + pads * MODE_LABEL_PAD

    def _title_font(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._titles:
            self._titles[size] = load_font(size)
        return self._titles[size]

    def _draw_title_row(self, hud: Hud, y: int, model: HudModel, title: _Title) -> Rect | None:
        image, draw, width = hud.image, hud.draw, hud.image.width
        title_x = self._block_x(model, width,
                                TITLE_INDENT + text_width(title.font, model.title),
                                reserve=title.reserve)
        draw_active_dot(image, title_x,
                        active_dot_top(self._title_font(SIZE_BODY), y + TITLE_BASELINE),
                        model.active)
        draw.text((title_x + TITLE_INDENT, y + TITLE_BASELINE), model.title,
                  font=title.font, anchor="ls", fill=(*TEXT_PRIMARY, 255))
        if not title.subtitle:
            return None
        line_y = y + self._name_line_top()
        name_x = self._block_x(model, width,
                              TITLE_INDENT + text_width(self._tiny, title.subtitle),
                              reserve=title.reserve)
        draw.text((name_x + TITLE_INDENT, line_y), title.subtitle,
                  font=self._tiny, anchor="la", fill=(*TEXT_MUTED, 255))
        favorite = favorite_icon_rect(name_x, line_y, sum(self._tiny.getmetrics()))
        draw_icon(image, FAVORITE_ICON, favorite,
                  (*(GREEN if model.is_favorite else TEXT_MUTED), 255))
        return favorite

    def _name_line_top(self) -> int:
        _ascent, descent = self._body.getmetrics()
        return TITLE_BASELINE + descent + SUBTITLE_GAP

    def _title_height(self) -> int:
        return self._name_line_top() + sum(self._tiny.getmetrics())

    def _draw_counts(self, draw, x: int, y: int, lines: tuple[str, ...]) -> None:
        for line_no, text in enumerate(lines, start=1):
            draw.text((x, y + _COUNT_LINE_H * line_no), text, font=self._tiny,
                      anchor="ls", fill=(*TEXT_MUTED, 255))

    def _draw_thumbnails(self, image, model: HudModel, rects: NavMapRects,
                         thumbs: NavMapThumbs) -> dict[Rect, Rect]:
        bucket, index = model.playing
        drawn = [(rects.corner, thumbs.corner, bucket == "corner")]
        drawn += [(place, thumb, bucket == "seed" and index == i)
                  for i, (place, thumb) in enumerate(zip(rects.seeds, thumbs.seeds, strict=False))]
        drawn += [(place, thumb, bucket == "action" and index == i)
                  for i, (place, thumb) in enumerate(zip(rects.actions, thumbs.actions, strict=False))]
        thumbnails: dict[Rect, Rect] = {}
        for place, thumb, bright in drawn:
            thumbnails[place] = thumbnail_rect(place, thumb.size)
            shown = thumb
            if not bright:
                shown = thumb.copy()
                shown.putalpha(shown.getchannel("A").point(lambda a: int(a * _DIM)))
            image.alpha_composite(shown, thumbnails[place][:2])
        return thumbnails

    def _draw_labels(self, hud: Hud, model: HudModel, at: tuple[int, int], rects: NavMapRects,
                     *, seed_offset: int = 0) -> tuple[Rect | None, list[tuple[Rect, str]]]:
        image, draw = hud.image, hud.draw
        x, y = at
        words: list[tuple[Rect, str]] = []

        def column(cx: int, cw: int, text: str) -> None:
            strip = Image.new("RGBA", (cw, COL_LABEL_H), (0, 0, 0, 0))
            ImageDraw.Draw(strip).text((cw / 2, COL_LABEL_H / 2), text, font=self._tiny,
                                       anchor="mm", fill=(*TEXT_MUTED, 255))
            image.alpha_composite(strip, (cx, y))

        def row(row_y: int, row_h: int, text: str, *, extra: int = 0) -> int:
            ascent, descent = self._tiny.getmetrics()
            line_h = ascent + descent - 4
            blocks = action_label_blocks(text)
            total = sum(len(block) for block in blocks) * line_h + (len(blocks) - 1) * ACT_GAP
            ty = label_stack_top(row_y, row_h, total, extra)
            words_end = ty + total
            right = x + ROW_LABEL_GUTTER - NAV_MAP_GAP
            acts = split_acts(text)
            for block, act in zip(blocks, acts + [""] * (len(blocks) - len(acts)), strict=True):
                lit = act_is_filtered(" ".join(block), model.filter_query)
                color = TEXT_PRIMARY if lit else TEXT_MUTED
                if act:
                    wide = math.ceil(max(self._tiny.getlength(line) for line in block))
                    words.append(((right - wide, ty, wide, len(block) * line_h), act_named(act)))
                for line in block:
                    draw.text((right, ty + line_h / 2), line,
                              font=self._tiny, anchor="rm", fill=(*color, 255))
                    ty += line_h
                ty += ACT_GAP
            return words_end

        cx, cy, cw, ch = rects.corner
        column(cx, cw, seed_column_label(seed_offset))
        strike = WRONG_BTN + WRONG_GAP if model.current_action else 0
        words_end = row(cy, ch, model.current_action, extra=strike)
        wrong = (wrong_action_rect(x + ROW_LABEL_GUTTER - NAV_MAP_GAP, words_end)
                 if model.current_action else None)
        if wrong is not None:
            self._strike_button(hud, wrong)
        for i, (sx, _sy, sw, _sh) in enumerate(rects.seeds):
            column(sx, sw, seed_column_label(seed_offset + i + 1))
        for i, (_ax, ay, _aw, ah) in enumerate(rects.actions):
            row(ay, ah, model.actions[i].label if i < len(model.actions) else "")
        return wrong, words

    def _pointer_is_on(self, rect: Rect) -> bool:
        return self._pointer is not None and contains(rect, *self._pointer)

    def _button_square(self, draw, rect: Rect, *, on: bool,
                       on_color=BLUE, ink=None) -> tuple[int, int, int, int]:
        return button_ground(draw, rect, on_color if on else BG_BUTTON,
            ButtonGroundState(
                hovered=self._pointer_is_on(rect),
                rest_ink=ink))

    def _icon_button(self, hud: Hud, rect: Rect, icon: str, *, on: bool = False) -> None:
        ink = self._button_square(hud.draw, rect, on=on, on_color=WHITE)
        if icon.startswith(SHARED_ICON):
            draw_icon(hud.image, shared_icon_name(icon), rect, ink)
            return
        bx, by, bw, bh = rect
        draw_character(hud.draw, (bx + bw / 2, by + bh / 2), icon, self._icon, ink)

    def _filter_button(self, hud: Hud, rect: Rect, *, on: bool = False) -> None:
        draw_icon(hud.image, "filter", rect, self._button_square(hud.draw, rect, on=on))

    def _strike_button(self, hud: Hud, rect: Rect) -> None:
        self._button_square(hud.draw, rect, on=False, ink=RED)
        draw_icon(hud.image, WRONG_ACTION_ICON, rect, (*RED, 255))

    def _draw_filter_buttons(self, hud: Hud, rects: list[tuple[Rect, str]],
                             model: HudModel) -> None:
        for rect, name in rects:
            self._filter_button(hud, rect, on=label_is_filtered(name, model.filter_query))

    def _draw_loop_controls(self, hud: Hud, rects: NavMapRects,
                            loop_buttons: tuple[Rect | None, Rect | None], active_loop: str,
                            hover_loop: str) -> None:
        loop_action_rect, loop_seed_rect = loop_buttons
        groups = {
            kind: (button, looped_group_rect(rects, kind, reserve=ELLIPSIS_ROOM))
            for kind, button in (("action", loop_action_rect), ("seed", loop_seed_rect))
        }
        for kind, (button, group_rect) in groups.items():
            if button is None:
                continue
            on = active_loop == kind
            self._icon_button(hud, button, _LOOP_ICON, on=on)
            if on:
                gx, gy, gw, gh = group_rect
                hud.draw.rectangle([gx, gy, gx + gw - 1, gy + gh - 1],
                                   outline=(*WHITE, 255), width=2)
            elif hover_loop == kind:
                dashed_rect(hud.draw, group_rect, (*WHITE, 255))
