from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shared_ui.icons_pil import paste_icon
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
from shared_ui.spacing import BUTTON_GROUP_GAP
from shared_ui.type_scale import SIZE_BODY, SIZE_TINY

from funestra.hud import (
    SYMBOL_FONT,
    Hud,
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
    driving_at_the_playhead,
    state_for,
)
from .hud_placement import block_x
from .hud_row import ROW_H, RowHud, RowSection, row_layout
from .hud_title import PLAYBACK_SPEED_LABEL
from .osr2_visualizer import DriveSection, DriveTrack, section_size, visualizer_targets
from .playback_rate import format_rate
from .satellite_hud import (
    ACT_GAP,
    BLOCK_GAP,
    COL_LABEL_GAP,
    COL_LABEL_H,
    CONTROL_ROW_H,
    CTRL_BTN,
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
    TITLE_BASELINE,
    TITLE_INDENT,
    TITLE_X,
    WRONG_ACTION_ICON,
    WRONG_BTN,
    WRONG_GAP,
    HudCell,
    HudModel,
    HudTargets,
    NavMapWindow,
    act_is_filtered,
    action_label_blocks,
    build_click_targets,
    button_row_rects,
    button_row_width,
    column_anchor_rect,
    device_height,
    ellipsis_rects,
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
    nav_map_window,
    place_rects,
    place_width,
    playing_rect,
    seed_column_label,
    speed_row,
    speed_row_width,
    thumbnail_rect,
    wrong_action_rect,
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
class _DrawnWith:
    video: str
    hover_loop: str
    hover_tip: str
    hover_pos: tuple[int, int] | None
    may_grow_on_hover: bool
    minus_on_the_hud: bool
    flash: str


@dataclass(frozen=True)
class _DrawnButTheRow:
    drawn_for: tuple
    image: Image.Image
    bgra: np.ndarray
    row_rect: tuple[int, int, int, int]
    targets: HudTargets


def _dashed_rect(draw: ImageDraw.ImageDraw, rect: Rect, color, dash: int = 4) -> None:
    # Pillow draws only solid lines.
    x, y, w, h = rect
    for start in range(x, x + w, dash * 2):
        end = min(start + dash, x + w)
        draw.line([(start, y), (end, y)], fill=color)
        draw.line([(start, y + h - 1), (end, y + h - 1)], fill=color)
    for start in range(y, y + h, dash * 2):
        end = min(start + dash, y + h)
        draw.line([(x, start), (x, end)], fill=color)
        draw.line([(x + w - 1, start), (x + w - 1, end)], fill=color)


class HudRenderer:
    def __init__(self, funestra: str) -> None:
        self._funestra = funestra
        self._body = load_font(SIZE_BODY)
        self._titles: dict[int, ImageFont.FreeTypeFont] = {SIZE_BODY: self._body}
        self._tiny = load_font(SIZE_TINY)
        self._pointer: tuple[int, int] | None = None
        self._icon = load_font(SIZE_BODY, SYMBOL_FONT)
        self._thumbs: dict[str, Image.Image] = {}
        self._osr2 = Osr2Section()
        self._drive = DriveSection()
        self._visualizer = VisualizerResolver()
        self._item_row = RowSection()
        self._drawn: _DrawnButTheRow | None = None

    def _thumbnail(self, cell: HudCell) -> Image.Image:
        place_w = place_width(self._funestra)
        if cell.thumb:
            cached = self._thumbs.get(cell.thumb)
            if cached is None:
                try:
                    image = Image.open(cell.thumb).convert("RGBA")
                except OSError:
                    image = None
                if image is not None:
                    scale = min(place_w / max(1, image.width), MAP_THUMB_H / max(1, image.height))
                    cached = image.resize((max(1, round(image.width * scale)),
                                           max(1, round(image.height * scale))))
                    self._thumbs[cell.thumb] = cached
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
        video: str = "",
        item_row: RowHud | None = None,
        heatmap: np.ndarray | None = None,
        hover_loop: str = "",
        hover_tip: str = "",
        hover_pos: tuple[int, int] | None = None,
        may_grow_on_hover: bool = True,
        minus_on_the_hud: bool = True,
        flash: str = "",
    ) -> RenderedHud:
        self._pointer = hover_pos
        if model.hud_minimized:
            bgra, buttons = collapsed_hud(
                model.funestra, model.hud_corner, hover=self._pointer,
                room_for_the_tooltip=not may_grow_on_hover, flash=flash)
            return RenderedHud(bgra, HudTargets(click=[], loop=[], filter=[], expand=None,
                                                buttons=buttons))
        model = replace(model, drive=self._visualizer.resolve(
            model.drive, osr2=model.osr2, control=model.osr2_control, paused=model.paused,
            composed=model.drive_composed))
        drawn_with = _DrawnWith(video, hover_loop, hover_tip, hover_pos, may_grow_on_hover,
                                minus_on_the_hud, flash)
        drawn_for = self._all_but_the_row(model, item_row, drawn_with)
        if drawn_for is not None and self._drawn is not None and self._drawn.drawn_for == drawn_for:
            return self._with_the_row(self._drawn, item_row, heatmap)
        return self._drawn_whole(model, drawn_for, item_row, heatmap, drawn_with)

    def _drawn_whole(self, model: HudModel, drawn_for: tuple | None, item_row: RowHud | None,
                     heatmap: np.ndarray | None, drawn_with: _DrawnWith) -> RenderedHud:
        counts = self._count_lines(model)
        model, seed_win, action_win = self._window(model)
        corner_thumb, seed_thumbs, action_thumbs = self._nav_map_thumbnails(model)
        rows = [list(row) for row in model.rows]
        widths = [[self._button_width(button) for button in row] for row in rows]
        device_rows = [list(row) for row in model.osr2_rows]
        device_row_widths = [[self._button_width(b) for b in row] for row in device_rows]
        bar_width = max((
            2 * PAD + button_row_width(row, row_widths)
            for row, row_widths in zip(rows + device_rows, widths + device_row_widths, strict=True)
            if row
        ), default=0)
        composed = (model.drive if model.drive_composed and model.drive is not None
                    and model.drive.segments else None)
        osr2_line = Osr2Line(
            state=state_for(model.osr2, model.osr2_control,
                            driving=driving_at_the_playhead(composed, model.osr2),
                            paused=model.paused),
            controls=model.osr2_controls, max_intensity=model.max_intensity)
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
            title_h=self._title_height(),
            bars=len(rows), speed=model.playback_speed is not None, row_h=row_h,
            device_h=device_height(model.osr2, model.drive, drive_h, len(device_rows)),
            foot_h=foot_h)
        height = layout.height
        hud = Hud(width, height)
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
            image, draw, PAD, model, width, title_font,
            name_line(drawn_with.video, model.item_note, room, self._tiny),
            reserve=0 if model.hud_corner.lower else minus_room)
        y = layout.bars
        buttons: list[tuple[Rect, Button]] = []
        if drawn_with.minus_on_the_hud:
            minus = (corner_button_rect(model.hud_corner, hud=(width, height),
                                        inset=MINUS_INSET),
                     minimize_button(model.funestra))
            draw_button(image, draw, *minus, hovered=self._pointer_is_on(minus[0]),
                        icon_font=self._icon, word_font=self._tiny)
            buttons.append(minus)

        for row, row_widths in zip(rows, widths, strict=True):
            placed = button_row_rects(
                self._block_x(model, width, button_row_width(row, row_widths)),
                y, row, row_widths)
            for index, (rect, button) in enumerate(placed):
                draw_button(image, draw, rect, button, hovered=self._pointer_is_on(rect),
                            icon_font=self._icon, word_font=self._tiny,
                            row_label=index == 0)
            buttons.extend(placed)
            y += CONTROL_ROW_H

        if model.playback_speed is not None:
            label_width = text_width(self._tiny, PLAYBACK_SPEED_LABEL) + BUTTON_GROUP_GAP
            speed_x = self._block_x(model, width, speed_row_width(label_width))
            speed_buttons, rate_rect = speed_row(model.funestra, speed_x, layout.speed,
                                                 label_width=label_width)
            draw.text((speed_x, layout.speed + CTRL_BTN / 2), PLAYBACK_SPEED_LABEL,
                      font=self._tiny, anchor="lm", fill=(*TEXT_MUTED, 255))
            for rect, button in speed_buttons:
                draw_button(image, draw, rect, button, hovered=self._pointer_is_on(rect),
                            icon_font=self._icon, word_font=self._tiny)
            rx, ry, rw, rh = rate_rect
            draw.text((rx + rw / 2, ry + rh / 2), format_rate(model.playback_speed),
                      font=self._tiny, anchor="mm", fill=(*TEXT_PRIMARY, 255))
            buttons.extend(speed_buttons)

        row = None
        if item_row is not None:
            row = row_layout(item_row, rect=(x, layout.row, width - 2 * PAD, row_h))
        device_buttons, bars = self._draw_device(
            image, draw, width, layout.device, model, osr2_line, drive_h,
            rows=device_rows, widths=device_row_widths)
        buttons.extend(device_buttons)
        foot_rect = None
        if model.foot is not None:
            foot_rect = (x, layout.foot, width - 2 * PAD, foot_h)
            buttons.extend(model.foot.paint(image, x, layout.foot, width - 2 * PAD,
                                            self._pointer))

        nav_map_targets = (self._draw_nav_map(image, draw, model, layout.nav_map, width, counts,
                                      (corner_thumb, seed_thumbs, action_thumbs),
                                      (seed_win, action_win), drawn_with.hover_loop)
                       if corner_thumb is not None
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
                         (width, height))
        return RenderedHud(hud.to_bgra(), targets)

    def _all_but_the_row(self, model: HudModel, item_row: RowHud | None,
                         drawn_with: _DrawnWith) -> tuple | None:
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

    def _draw_nav_map(self, image, draw, model: HudModel, top: int, width: int,
                  counts: tuple[str, ...], thumbs, windows, hover_loop: str) -> HudTargets:
        corner_thumb, seed_thumbs, action_thumbs = thumbs
        seed_win, action_win = windows
        gutter_x = self._block_x(model, width, map_block_width(model.funestra))
        self._draw_counts(draw, gutter_x, top, counts)
        nav_map_x = gutter_x + ROW_LABEL_GUTTER + ELLIPSIS_ROOM
        nav_map_y = top + COL_LABEL_H + COL_LABEL_GAP + ELLIPSIS_ROOM
        corner_rect, seed_rects, action_rects = place_rects(
            nav_map_x=nav_map_x, nav_map_y=nav_map_y, place_w=place_width(model.funestra),
            seeds=len(seed_thumbs), actions=len(action_thumbs), playing=model.playing)
        column_rect = column_anchor_rect(model.playing, corner_rect, seed_rects)

        thumbnails = self._draw_thumbnails(image, model, corner_rect, seed_rects, action_rects,
                                           corner_thumb, seed_thumbs, action_thumbs)
        held = playing_rect(model.playing, corner_rect, seed_rects, action_rects)
        if model.locked and held is not None:
            hx, hy, hw, hh = thumbnails[held]
            draw.rectangle([hx, hy, hx + hw - 1, hy + hh - 1],
                           outline=(*WHITE, 255), width=_BORDER_W)
        wrong_rect = self._draw_labels(image, draw, model, gutter_x, top,
                                       corner_rect, seed_rects, action_rects,
                                       seed_offset=seed_win.start if seed_win else 0)
        filter_rects = filter_button_rects(corner_rect, action_rects, gutter_x,
                                           model.current_action,
                                           [cell.label for cell in model.actions])
        self._draw_filter_buttons(image, draw, filter_rects, model)

        loop_action_rect, loop_seed_rect = loop_button_rects(
            corner_rect, row_end=nav_map_x + nav_map_row_width(model.funestra),
            column_end=nav_map_y + NAV_MAP_COLUMN_H, reserve=ELLIPSIS_ROOM, column_rect=column_rect)
        expand_rect = expand_button_rect(loop_seed_rect)
        self._draw_loop_controls(image, draw, corner_rect, column_rect, loop_action_rect,
                                 loop_seed_rect, seed_rects, action_rects,
                                 model.active_loop, hover_loop)
        for axis, window in (("seed", seed_win), ("action", action_win)):
            if window is not None:
                self._draw_ellipses(image, corner_rect, column_rect, seed_rects,
                                    action_rects, axis, window)
        if expand_rect is not None:
            self._icon_button(image, draw, expand_rect, _EXPAND_ICON)
        return HudTargets(
            click=build_click_targets(corner_rect, seed_rects, action_rects,
                                      model.corner, model.seeds, model.actions),
            loop=[(button, kind)
                  for kind, button in (("action", loop_action_rect), ("seed", loop_seed_rect))
                  if button is not None],
            filter=filter_rects,
            expand=expand_rect,
            wrong_action=wrong_rect,
        )

    def _draw_device(self, image, draw, width: int, y: int, model: HudModel,
                     osr2_line: Osr2Line, drive_h: int, *, rows, widths,
                     ) -> tuple[list[tuple[Rect, Button]], list[DriveTrack]]:
        buttons: list[tuple[Rect, Button]] = []
        bars: list[DriveTrack] = []
        for row, row_widths in zip(rows, widths, strict=True):
            placed = button_row_rects(
                self._block_x(model, width, button_row_width(row, row_widths)),
                y, row, row_widths)
            for index, (rect, button) in enumerate(placed):
                draw_button(image, draw, rect, button, hovered=self._pointer_is_on(rect),
                            icon_font=self._icon, word_font=self._tiny,
                            row_label=index == 0)
            buttons.extend(placed)
            y += CONTROL_ROW_H
        max_intensity_bars: list[DriveTrack] = []
        if model.osr2:
            osr2_x = self._block_x(model, width, self._osr2.width(osr2_line))
            buttons.extend(self._osr2.draw(image, draw, (osr2_x, y), osr2_line,
                                           hover=self._pointer))
            max_intensity_bars = self._osr2.bars(osr2_x, y, osr2_line)
            y += OSR2_H + BLOCK_GAP
        if model.drive is not None:
            drive_x = self._block_x(model, width, section_size()[0])
            self._drive.draw(image, drive_x, y, model.drive)
            drive_targets, bars = visualizer_targets(drive_x, y, model.drive)
            buttons.extend(drive_targets)
        return buttons, bars + max_intensity_bars

    def _button_width(self, button: Button) -> int:
        return button.width or text_width(self._tiny, button.icon) + 2 * MODE_LABEL_PAD

    def _title_font(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._titles:
            self._titles[size] = load_font(size)
        return self._titles[size]

    def _draw_title_row(self, image, draw, y: int, model: HudModel, width: int,
                         title_font: ImageFont.FreeTypeFont, subtitle: str, *,
                         reserve: int) -> Rect | None:
        title_x = self._block_x(model, width,
                                TITLE_INDENT + text_width(title_font, model.title),
                                reserve=reserve)
        draw_active_dot(image, title_x, y + 2, model.active)
        draw.text((title_x + TITLE_INDENT, y + TITLE_BASELINE), model.title,
                  font=title_font, anchor="ls", fill=(*TEXT_PRIMARY, 255))
        if not subtitle:
            return None
        line_y = y + self._name_line_top()
        name_x = self._block_x(model, width,
                              TITLE_INDENT + text_width(self._tiny, subtitle),
                              reserve=reserve)
        draw.text((name_x + TITLE_INDENT, line_y), subtitle,
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

    def _window(
        self, model: HudModel
    ) -> tuple[HudModel, NavMapWindow | None, NavMapWindow | None]:
        if model.corner is None:
            return model, None, None
        bucket, index = model.playing
        seed_strip = [model.corner, *model.seeds]
        action_strip = [model.corner, *model.actions]
        seed_at = index + 1 if bucket == "seed" else 0
        action_at = index + 1 if bucket == "action" else 0
        seed_win = nav_map_window(len(seed_strip), seed_at)
        action_win = nav_map_window(len(action_strip), action_at)
        window = action_win if bucket == "action" else seed_win
        strip = action_strip if bucket == "action" else seed_strip
        corner = strip[window.start]
        lit = (action_at if bucket == "action" else seed_at) - window.start
        narrowed = replace(
            model,
            corner=corner,
            seeds=tuple(seed_strip[seed_win.start + 1:seed_win.start + seed_win.count]),
            actions=tuple(action_strip[action_win.start + 1:action_win.start + action_win.count]),
            playing=("corner", 0) if lit <= 0 else (bucket, lit - 1),
        )
        if bucket == "action":
            narrowed = replace(narrowed, current_action=corner.label or model.current_action)
        return narrowed, seed_win, action_win

    @staticmethod
    def _count_lines(model: HudModel) -> tuple[str, ...]:
        if not (model.seed_count or model.action_count):
            return ()
        return (f"Seeds: {model.seed_count}", f"Actions: {model.action_count}")

    def _draw_counts(self, draw, x: int, y: int, lines: tuple[str, ...]) -> None:
        for line_no, text in enumerate(lines, start=1):
            draw.text((x, y + _COUNT_LINE_H * line_no), text, font=self._tiny,
                      anchor="ls", fill=(*TEXT_MUTED, 255))

    def _draw_ellipses(self, image, corner_rect, column_rect, seed_rects, action_rects,
                       axis, window) -> None:
        before, after = ellipsis_rects(corner_rect, seed_rects, action_rects, axis,
                                       column_rect=column_rect)
        for rect, show in ((before, window.more_before), (after, window.more_after)):
            if not show:
                continue
            paste_icon(image, "more" if axis == "seed" else "more_vertical", rect,
                       TEXT_PRIMARY)

    def _draw_thumbnails(self, image, model, corner_rect, seed_rects, action_rects,
                         corner_thumb, seed_thumbs, action_thumbs) -> dict[Rect, Rect]:
        bucket, index = model.playing
        drawn = [(corner_rect, corner_thumb, bucket == "corner")]
        drawn += [(place, thumb, bucket == "seed" and index == i)
                  for i, (place, thumb) in enumerate(zip(seed_rects, seed_thumbs, strict=False))]
        drawn += [(place, thumb, bucket == "action" and index == i)
                  for i, (place, thumb) in enumerate(zip(action_rects, action_thumbs, strict=False))]
        thumbnails: dict[Rect, Rect] = {}
        for place, thumb, bright in drawn:
            thumbnails[place] = thumbnail_rect(place, thumb.size)
            shown = thumb
            if not bright:
                shown = thumb.copy()
                shown.putalpha(shown.getchannel("A").point(lambda a: int(a * _DIM)))
            image.alpha_composite(shown, thumbnails[place][:2])
        return thumbnails

    def _draw_labels(self, image, draw, model, x, y, corner_rect, seed_rects,
                     action_rects, *, seed_offset: int = 0) -> Rect | None:
        def column(cx: int, cw: int, text: str) -> None:
            strip = Image.new("RGBA", (cw, COL_LABEL_H), (0, 0, 0, 0))
            ImageDraw.Draw(strip).text((cw / 2, COL_LABEL_H / 2), text, font=self._tiny,
                                       anchor="mm", fill=(*TEXT_MUTED, 255))
            image.alpha_composite(strip, (cx, y))

        def row(row_y: int, row_h: int, text: str, *, extra: int = 0) -> int:
            row_lit = label_is_filtered(text, model.filter_query, model.camera_words)
            ascent, descent = self._tiny.getmetrics()
            line_h = ascent + descent - 4
            blocks = action_label_blocks(text, model.camera_words)
            total = sum(len(block) for block in blocks) * line_h + (len(blocks) - 1) * ACT_GAP
            ty = label_stack_top(row_y, row_h, total, extra)
            words_end = ty + total
            for block in blocks:
                lit = row_lit and act_is_filtered(
                    " ".join(block), model.filter_query, model.camera_words)
                color = TEXT_PRIMARY if lit else TEXT_MUTED
                for line in block:
                    draw.text((x + ROW_LABEL_GUTTER - NAV_MAP_GAP, ty + line_h / 2), line,
                              font=self._tiny, anchor="rm", fill=(*color, 255))
                    ty += line_h
                ty += ACT_GAP
            return words_end

        cx, cy, cw, ch = corner_rect
        column(cx, cw, seed_column_label(seed_offset))
        strike = WRONG_BTN + WRONG_GAP if model.current_action else 0
        words_end = row(cy, ch, model.current_action, extra=strike)
        wrong = (wrong_action_rect(x + ROW_LABEL_GUTTER - NAV_MAP_GAP, words_end)
                 if model.current_action else None)
        if wrong is not None:
            self._strike_button(image, draw, wrong)
        for i, (sx, _sy, sw, _sh) in enumerate(seed_rects):
            column(sx, sw, seed_column_label(seed_offset + i + 1))
        for i, (_ax, ay, _aw, ah) in enumerate(action_rects):
            row(ay, ah, model.actions[i].label if i < len(model.actions) else "")
        return wrong

    def _pointer_is_on(self, rect: Rect) -> bool:
        return self._pointer is not None and contains(rect, *self._pointer)

    def _button_square(self, draw, rect: Rect, *, on: bool,
                       on_color=BLUE, ink=None) -> tuple[int, int, int, int]:
        return button_ground(draw, rect, on_color if on else BG_BUTTON,
                             hovered=self._pointer_is_on(rect), rest_ink=ink)

    def _icon_button(self, image, draw, rect: Rect, icon: str, *, on: bool = False,
                      on_color=WHITE, ink=None) -> None:
        ink = self._button_square(draw, rect, on=on, on_color=on_color, ink=ink)
        if icon.startswith(SHARED_ICON):
            draw_icon(image, shared_icon_name(icon), rect, ink)
            return
        bx, by, bw, bh = rect
        draw_character(draw, (bx + bw / 2, by + bh / 2), icon, self._icon, ink)

    def _filter_button(self, image, draw, rect: Rect, *, on: bool = False) -> None:
        draw_icon(image, "filter", rect, self._button_square(draw, rect, on=on))

    def _strike_button(self, image, draw, rect: Rect) -> None:
        self._button_square(draw, rect, on=False, ink=RED)
        draw_icon(image, WRONG_ACTION_ICON, rect, (*RED, 255))

    def _draw_filter_buttons(self, image, draw, rects: list[tuple[Rect, str]],
                             model: HudModel) -> None:
        for rect, name in rects:
            self._filter_button(image, draw, rect, on=label_is_filtered(
                name, model.filter_query, model.camera_words))

    def _draw_loop_controls(self, image, draw, corner_rect, column_rect, loop_action_rect,
                            loop_seed_rect, seed_rects, action_rects, active_loop,
                            hover_loop) -> None:
        rects = {
            kind: (
                button,
                looped_group_rect(corner_rect, seed_rects, action_rects, kind,
                                  reserve=ELLIPSIS_ROOM, column_rect=column_rect),
            )
            for kind, button in (("action", loop_action_rect), ("seed", loop_seed_rect))
        }
        for kind, (button, group_rect) in rects.items():
            if button is None:
                continue
            on = active_loop == kind
            self._icon_button(image, draw, button, _LOOP_ICON, on=on)
            if on:
                gx, gy, gw, gh = group_rect
                draw.rectangle([gx, gy, gx + gw - 1, gy + gh - 1],
                               outline=(*WHITE, 255), width=2)
            elif hover_loop == kind:
                _dashed_rect(draw, group_rect, (*WHITE, 255))

