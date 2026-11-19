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
    Tooltip,
    active_dot_top,
    button_ground,
    draw_active_dot,
    draw_button,
    draw_character,
    draw_icon,
    draw_the_tooltip,
    draw_tooltip,
    load_font,
    text_width,
    to_bgra,
    tooltip_for,
)
from funestra.hud_button import Button
from funestra.hud_icons import SHARED_ICON, shared_icon, shared_icon_name

from .geometry import Rect, contains
from .host_controls import HostControlsHud, HostControlsSection
from .hud_kinds import HudKind, title_choices
from .hud_minimize import ROOM as MINIMIZE_ROOM
from .hud_minimize import collapsed_hud, corner_button_rect, minimize_button
from .hud_placement import block_x
from .hud_row import ROW_H, RowHud, RowSection, row_layout
from .name_copy import COPY_GAP, COPY_ICON, copy_button, copy_icon_ink, copy_icon_rect
from .satellite_hud import (
    ACT_GAP,
    COL_LABEL_GAP,
    COL_LABEL_H,
    CONTROL_ROW_H,
    ELLIPSIS_ROOM,
    EXPAND_ICON,
    FAVORITE_ICON,
    LOOP_ICON,
    MAP_THUMB_H,
    MINUS_INSET,
    NAV_MAP_COLUMN_H,
    NAV_MAP_GAP,
    PAD,
    ROW_LABEL_GUTTER,
    SUBTITLE_GAP,
    TITLE_INDENT,
    TITLE_X,
    WORD_PAD,
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
    actions_are_filtered,
    build_click_targets,
    button_row_rects,
    button_row_width,
    expand_button_rect,
    favorite_icon_rect,
    filter_button_rects,
    has_a_nav_map,
    hud_layout,
    hud_width,
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
    width: int | None = None


PLAIN = DrawnWith()


class NavMapThumbs(NamedTuple):
    corner: Image.Image | None
    seeds: list[Image.Image]
    actions: list[Image.Image]


class _NavMap(NamedTuple):
    counts: tuple[str, ...]
    thumbs: NavMapThumbs
    windows: tuple[NavMapWindow | None, NavMapWindow | None]


def _minus_room(drawn_with: DrawnWith) -> int:
    return MINIMIZE_ROOM if drawn_with.minus_on_the_hud else 0


def _name_reserve(model: HudModel, drawn_with: DrawnWith) -> int:
    return 0 if model.hud_corner.lower else _minus_room(drawn_with)


class _Title(NamedTuple):
    font: ImageFont.FreeTypeFont
    subtitle: str
    reserve: int
    copy_room: int = 0


@dataclass(frozen=True)
class _Sizes:
    rows: list[list[Button]]
    widths: list[list[int]]
    foot_h: int
    width: int
    row_h: int
    layout: HudLayout


class _Drawing(NamedTuple):
    drawn_with: DrawnWith
    host_controls: HostControlsHud | None


class _Patch(NamedTuple):
    rect: Rect
    image: Image.Image


class _BitmapsInTurn:
    # mpv copies an overlay as it takes it, so the bitmap from two draws back is free to draw
    # on again, and only the patches differ from one draw of an unchanged HUD to the next.

    def __init__(self, image: Image.Image) -> None:
        self._as_drawn = to_bgra(image)
        self._pair = [self._as_drawn.copy(), self._as_drawn.copy()]
        self._patched: list[tuple[Rect, ...]] = [(), ()]
        self._turn = 0

    def with_the(self, patches: list[_Patch]) -> np.ndarray:
        turn, self._turn = self._turn, 1 - self._turn
        bitmap = self._pair[turn]
        rects = tuple(patch.rect for patch in patches)
        for x, y, width, height in self._patched[turn]:
            if (x, y, width, height) not in rects:
                bitmap[y:y + height, x:x + width] = self._as_drawn[y:y + height, x:x + width]
        for (x, y, width, height), image in patches:
            bitmap[y:y + height, x:x + width] = to_bgra(image)
        self._patched[turn] = rects
        return bitmap


@dataclass(frozen=True)
class _DrawnButTheRow:
    drawn_for: tuple
    image: Image.Image
    bitmaps: _BitmapsInTurn
    row_rect: tuple[int, int, int, int]
    targets: HudTargets


class _TooltipAlone(NamedTuple):
    over: _DrawnButTheRow
    drawn_with: DrawnWith
    patch: _Patch


def _overlap(one: Rect, other: Rect) -> bool:
    return (one[0] < other[0] + other[2] and other[0] < one[0] + one[2]
            and one[1] < other[1] + other[3] and other[1] < one[1] + one[3])


def _around(one: Rect, other: Rect) -> Rect:
    left, top = min(one[0], other[0]), min(one[1], other[1])
    right = max(one[0] + one[2], other[0] + other[2])
    bottom = max(one[1] + one[3], other[1] + other[3])
    return (left, top, right - left, bottom - top)


def _cut(image: Image.Image, rect: Rect) -> Image.Image:
    x, y, width, height = rect
    return image.crop((x, y, x + width, y + height))


def _fitted_thumbnail(thumb: str, place_w: int) -> Image.Image | None:
    try:
        image = Image.open(thumb).convert("RGBA")
    except OSError:
        return None
    scale = min(place_w / max(1, image.width), MAP_THUMB_H / max(1, image.height))
    return image.resize((max(1, round(image.width * scale)), max(1, round(image.height * scale))))


class HudRenderer:
    def __init__(self, funestra: str) -> None:
        self._funestra = funestra
        self._body = load_font(SIZE_BODY)
        self._titles: dict[int, ImageFont.FreeTypeFont] = {SIZE_BODY: self._body}
        self._tiny = load_font(SIZE_TINY)
        self._pointer: tuple[int, int] | None = None
        self._icon = load_font(SIZE_BODY, SYMBOL_FONT)
        self._thumbs_by_path: dict[str, Image.Image | None] = {}
        self._scrubber_row = RowSection()
        self._host_controls = HostControlsSection()
        self._widest_titles: dict[HudKind, int] = {}
        self._drawn: _DrawnButTheRow | None = None
        self._tooltip_alone: _TooltipAlone | None = None

    def _thumbnail(self, cell: HudCell) -> Image.Image:
        place_w = place_width(self._funestra)
        if cell.thumb:
            if cell.thumb not in self._thumbs_by_path:
                self._thumbs_by_path[cell.thumb] = _fitted_thumbnail(cell.thumb, place_w)
            cached = self._thumbs_by_path[cell.thumb]
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
        scrubber_row: RowHud | None = None,
        heatmap: np.ndarray | None = None,
        drawn_with: DrawnWith = PLAIN,
        host_controls: HostControlsHud | None = None,
    ) -> RenderedHud:
        self._pointer = drawn_with.hover_pos
        if model.hud_minimized:
            bgra, buttons = collapsed_hud(
                model.funestra, model.hud_corner, hover=self._pointer,
                room_for_the_tooltip=not drawn_with.may_grow_on_hover, flash=drawn_with.flash)
            return RenderedHud(bgra, HudTargets(click=[], loop=[], filter=[], expand=None,
                                                buttons=buttons))
        model = replace(model, osr2="", osr2_rows=(), osr2_controls=(), max_intensity=None,
                        drive=None)
        drawn_for = self._all_but_the_row(model, scrubber_row, drawn_with, host_controls)
        if drawn_for is not None and self._drawn is not None and self._drawn.drawn_for == drawn_for:
            return self._with_the_row(self._drawn, scrubber_row, heatmap, drawn_with)
        return self._drawn_whole(model, drawn_for, scrubber_row, heatmap,
                                 _Drawing(drawn_with, host_controls))

    def _measure(self, model: HudModel, scrubber_row: RowHud | None,
                 drawing: _Drawing) -> _Sizes:
        host_controls = drawing.host_controls
        rows = rows_with_the_speed(model)
        widths = [self._row_widths(row) for row in rows]
        bar_width = max((
            2 * PAD + button_row_width(row, row_widths)
            for row, row_widths in zip(rows, widths, strict=True)
            if row
        ), default=0)
        foot_w, foot_h = model.foot.size() if model.foot is not None else (0, 0)
        nav_map = has_a_nav_map(model)
        width = hud_width(model.funestra, nav_map=nav_map,
                          content_width=max(
                                bar_width,
                                2 * PAD + foot_w if foot_w else 0,
                                drawing.drawn_with.width or 0,
                                self._room_for_the_widest_title(model.kind, drawing.drawn_with),
                                2 * PAD + self._host_controls.least_width(host_controls)
                                if host_controls is not None else 0,
                                2 * PAD + self._scrubber_row.least_width(scrubber_row)
                                if scrubber_row is not None else 0))
        row_h = ROW_H if scrubber_row is not None else 0
        layout = hud_layout(
            heights=SectionHeights(
                self._title_height(), row_h,
                HostControlsSection.height if host_controls is not None else 0, foot_h),
            bars=len(rows), nav_map=nav_map)
        return _Sizes(rows, widths, foot_h, width, row_h, layout)

    def _drawn_whole(self, model: HudModel, drawn_for: tuple | None, scrubber_row: RowHud | None,
                     heatmap: np.ndarray | None, drawing: _Drawing) -> RenderedHud:
        drawn_with = drawing.drawn_with
        counts = count_lines(model)
        model, seed_win, action_win = narrowed_to_window(model)
        thumbs = NavMapThumbs(*self._nav_map_thumbnails(model))
        sizes = self._measure(model, scrubber_row, drawing)
        layout, width, foot_h = sizes.layout, sizes.width, sizes.foot_h
        hud = Hud(width, layout.height)
        for divider in layout.dividers:
            hud.divide(divider)
        image, draw = hud.image, hud.draw

        x = PAD
        minus_room = _minus_room(drawn_with)
        room = width - TITLE_X - PAD - minus_room
        title_font = self._title_font(largest_size_that_fits(
            SIZE_BODY, room,
            lambda size: text_width(self._title_font(size), model.title)))
        model = replace(model, title=fit_text(title_font, model.title, room))
        copy_room = self._copy_room(drawn_with)
        favorite, copy = self._draw_title_row(
            hud, PAD, model,
            _Title(title_font,
                   name_line(drawn_with.video, model.item_note, room - copy_room, self._tiny),
                   _name_reserve(model, drawn_with), copy_room))
        buttons: list[tuple[Rect, Button]] = [] if copy is None else [(copy, copy_button())]
        if drawn_with.minus_on_the_hud:
            buttons.append(self._draw_minus(hud, model))
        buttons.extend(self._draw_button_rows(hud, model, sizes.rows, sizes.widths, layout.bars))

        row = None
        if scrubber_row is not None:
            row = row_layout(scrubber_row, rect=(x, layout.row, width - 2 * PAD, sizes.row_h))
        host_controls = None
        if drawing.host_controls is not None:
            host_controls = self._host_controls.draw(
                image, (x, layout.host_controls, width - 2 * PAD, HostControlsSection.height),
                drawing.host_controls)
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
        targets = replace(nav_map_targets, tracks=[], row=row, foot=foot_rect, buttons=buttons,
                          favorite=favorite, host_controls=host_controls)
        if drawn_for is not None:
            self._drawn = _DrawnButTheRow(drawn_for, image, _BitmapsInTurn(image), row.rect,
                                          targets)
            return self._with_the_row(self._drawn, scrubber_row, heatmap, drawn_with)
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

    def _all_but_the_row(self, model: HudModel, scrubber_row: RowHud | None,
                         drawn_with: DrawnWith,
                         host_controls: HostControlsHud | None) -> tuple | None:
        if scrubber_row is None:
            return None
        return model, self._scrubber_row.least_width(scrubber_row), drawn_with, host_controls

    def _with_the_row(self, drawn: _DrawnButTheRow, scrubber_row: RowHud, heatmap,
                      drawn_with: DrawnWith) -> RenderedHud:
        _x, _y, width, height = drawn.row_rect
        row = _Patch(drawn.row_rect, _cut(drawn.image, drawn.row_rect))
        self._scrubber_row.draw(row.image, row_layout(scrubber_row, rect=(0, 0, width, height)),
                                scrubber_row, heatmap=heatmap)
        patches = self._under_the_tooltip(drawn, row, drawn_with) if drawn_with.hover_tip else [row]
        return RenderedHud(drawn.bitmaps.with_the(patches),
                           replace(drawn.targets,
                                   row=row_layout(scrubber_row, rect=drawn.row_rect)))

    def _under_the_tooltip(self, drawn: _DrawnButTheRow, row: _Patch,
                           drawn_with: DrawnWith) -> list[_Patch]:
        tooltip = tooltip_for(self._tiny, drawn_with.hover_tip, drawn_with.hover_pos,
                              drawn.image.size)
        if tooltip is None:
            return [row]
        if not _overlap(tooltip.rect, row.rect):
            return [row, self._the_tooltip_alone(drawn, drawn_with, tooltip)]
        both = _around(tooltip.rect, row.rect)
        image = _cut(drawn.image, both)
        image.paste(row.image, (row.rect[0] - both[0], row.rect[1] - both[1]))
        draw_the_tooltip(ImageDraw.Draw(image), self._tiny, tooltip.moved_by(-both[0], -both[1]))
        return [_Patch(both, image)]

    def _the_tooltip_alone(self, drawn: _DrawnButTheRow, drawn_with: DrawnWith,
                           tooltip: Tooltip) -> _Patch:
        kept = self._tooltip_alone
        if kept is None or kept.over is not drawn or kept.drawn_with != drawn_with:
            image = _cut(drawn.image, tooltip.rect)
            draw_the_tooltip(ImageDraw.Draw(image), self._tiny,
                             tooltip.moved_by(-tooltip.rect[0], -tooltip.rect[1]))
            kept = self._tooltip_alone = _TooltipAlone(drawn, drawn_with,
                                                       _Patch(tooltip.rect, image))
        return kept.patch

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

    def _room_for_the_widest_title(self, kind: HudKind | None, drawn_with: DrawnWith) -> int:
        if kind is None:
            return 0
        if kind not in self._widest_titles:
            self._widest_titles[kind] = max(text_width(self._body, title)
                                            for title in title_choices(kind))
        return TITLE_X + self._widest_titles[kind] + PAD + _minus_room(drawn_with)

    def _row_widths(self, row: list[Button]) -> list[int]:
        return [button.width or text_width(self._tiny, button.icon) + 2 * WORD_PAD
                for button in row]

    def _title_font(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._titles:
            self._titles[size] = load_font(size)
        return self._titles[size]

    def _copy_room(self, drawn_with: DrawnWith) -> int:
        return COPY_GAP + self._tiny_line_h() if drawn_with.video else 0

    def _tiny_line_h(self) -> int:
        return sum(self._tiny.getmetrics())

    def _draw_title_row(self, hud: Hud, y: int, model: HudModel,
                        title: _Title) -> tuple[Rect | None, Rect | None]:
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
            return None, None
        line_y = y + self._name_line_top()
        subtitle_w = text_width(self._tiny, title.subtitle)
        name_x = self._block_x(model, width, TITLE_INDENT + subtitle_w + title.copy_room,
                              reserve=title.reserve)
        draw.text((name_x + TITLE_INDENT, line_y), title.subtitle,
                  font=self._tiny, anchor="la", fill=(*TEXT_MUTED, 255))
        favorite = favorite_icon_rect(name_x, line_y, self._tiny_line_h())
        draw_icon(image, FAVORITE_ICON, favorite,
                  (*(GREEN if model.is_favorite else TEXT_MUTED), 255))
        if not title.copy_room:
            return favorite, None
        copy = copy_icon_rect(name_x + TITLE_INDENT + subtitle_w, line_y, self._tiny_line_h())
        draw_icon(image, COPY_ICON, copy, copy_icon_ink(copy, self._pointer))
        return favorite, copy

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
            self._filter_button(hud, rect, on=actions_are_filtered(name, model.filter_query))

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
