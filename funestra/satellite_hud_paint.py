"""Draw the satellite's lock HUD as a bitmap mpv composites into the video.

Drawing it into the frame rather than into a window of its own is the whole
point: an mpv overlay has no z-order, so it can neither fall beneath the video nor
float above the desktop.

The slab it is drawn on — the rounded translucent panel, the palette, the Segoe
face sized the way Qt sized it, the BGRA hand-off — comes from
:mod:`funestra.hud_panel`, which the Main Funestra's own HUD is drawn on too, so the two
Funestras go on looking like one another.  The layout and hit-test rects come from
:mod:`funestra.satellite_hud`, so what is drawn and what is clickable cannot drift apart.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from shared_ui.palette import (
    BG_BUTTON,
    BLUE,
    GREEN,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
    WHITE,
)
from shared_ui.spacing import BUTTON_GROUP_GAP

from funestra.hud_button import Button
from funestra.hud_marks import SHARED_MARK, shared_mark, shared_mark_name
from funestra.hud_panel import (
    SYMBOL_FONT,
    HudPanel,
    button_ground,
    draw_active_dot,
    draw_button,
    draw_glyph,
    draw_mark,
    draw_tooltip,
    load_font,
    text_width,
)

from .drive_readout import DriveSection, DriveTrack, readout_targets, section_size
from .geometry import Rect, contains
from .hud_minimize import ROOM as MINIMIZE_ROOM
from .hud_minimize import collapsed_panel, corner_button_rect, minimize_button
from .hud_osr2 import HEIGHT as OSR2_H
from .hud_osr2 import (
    Osr2Line,
    Osr2Section,
    ReadoutResolver,
    driving_at_the_playhead,
    state_for,
)
from .hud_placement import block_x
from .hud_row import ROW_H, RowHud, RowSection, row_layout
from .hud_status import PLAYBACK_SPEED_LABEL
from .playback_rate import format_rate
from .satellite_hud import (
    ACT_GAP,
    BLOCK_GAP,
    COL_LABEL_GAP,
    COL_LABEL_H,
    CTRL_BAND_H,
    CTRL_BTN,
    ELLIPSIS_ROOM,
    EXPAND_MARK,
    FAVORITE_MARK,
    LOOP_MARK,
    MAP_COLUMN_H,
    MAP_GAP,
    MAP_THUMB_H,
    MINUS_INSET,
    MODE_LABEL_PAD,
    PAD,
    ROW_LABEL_GUTTER,
    STATUS_BASELINE,
    STATUS_INDENT,
    STATUS_TEXT_X,
    SUBTITLE_GAP,
    WRONG_ACTION_MARK,
    WRONG_BTN,
    WRONG_GAP,
    HudCell,
    HudModel,
    HudTargets,
    MapWindow,
    act_is_filtered,
    action_label_blocks,
    build_click_targets,
    button_row_rects,
    button_row_width,
    column_anchor_rect,
    device_height,
    ellipsis_rects,
    expand_button_rect,
    favorite_mark_rect,
    filter_button_rects,
    label_is_filtered,
    label_stack_top,
    largest_size_that_fits,
    loop_button_rects,
    looped_group_rect,
    map_block_width,
    map_row_width,
    map_window,
    name_line,
    panel_layout,
    panel_width,
    picture_rect,
    playing_rect,
    seed_column_label,
    slot_rects,
    slot_width,
    speed_row,
    speed_row_width,
    wrong_action_rect,
)

__all__ = [
    "HudRenderer",
]

_PLACEHOLDER = (48, 48, 60)  # a thumbnail fun_time has not produced yet

_DIM = 0.5      # non-playing thumbnails; the one on screen stays full
_BORDER_W = 2   # the lock ring around the held clip
_DOT = 1        # radius of one dot in a "…" mark — small, so three read as three
_DOT_GAP = 4    # center-to-center spacing of those dots along the axis
_COUNT_LINE_H = 11  # line pitch of the axis counts in the map's top-left corner

_SIZE_BODY = 11
_SIZE_TINY = 8
_ROW_LABEL_PT = 7
_LOOP_GLYPH = shared_mark(LOOP_MARK)
_EXPAND_GLYPH = shared_mark(EXPAND_MARK)
# The filter mark, drawn rather than typed: Segoe UI Symbol — the face the other
# buttons take their icons from — carries no funnel at any codepoint, and this is
# the one button whose shape *is* its meaning, so a ".notdef" tofu would say
# nothing at all.  A mouth _FUNNEL_W wide narrowing to a stem, sized like the
# glyphs beside it.
_FUNNEL_W = 9
_FUNNEL_H = 9
_FUNNEL_NECK = 3  # width of the stem the mouth narrows to


@dataclass(frozen=True)
class RenderedHud:
    """The HUD as mpv wants it, plus what the pixels under the cursor mean."""

    bgra: np.ndarray
    targets: HudTargets


def _dashed_rect(draw: ImageDraw.ImageDraw, rect: Rect, color, dash: int = 4) -> None:
    """A 1px dashed outline — Pillow draws only solid lines, and the hover preview
    has to read as provisional next to the solid border a running loop gets."""
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
    """Paints one satellite's HUD, reusing its fonts and decoded thumbnails.

    A render happens whenever the published panel changes (every few seconds, as
    clips advance) or the cursor moves onto or off a button, so the thumbnails are
    cached by path: fun_time's cache filenames fold in the clip's mtime, so a path
    that is still valid is still the right image.
    """

    def __init__(self, funestra: str) -> None:
        self._funestra = funestra
        self._body = load_font(_SIZE_BODY)
        self._titles: dict[int, ImageFont.FreeTypeFont] = {_SIZE_BODY: self._body}
        self._tiny = load_font(_SIZE_TINY)
        self._row = load_font(_ROW_LABEL_PT)
        self._pointer: tuple[int, int] | None = None
        self._glyph = load_font(_SIZE_BODY, SYMBOL_FONT)
        self._thumbs: dict[str, Image.Image] = {}
        # The main console's own two blocks, hosted here for a panel whose
        # Funestra has the OSR2 -- see HudModel.osr2.
        self._osr2 = Osr2Section()
        self._drive = DriveSection()
        self._readout = ReadoutResolver()
        self._clip_row = RowSection()

    def _thumbnail(self, cell: HudCell) -> Image.Image:
        slot_w = slot_width(self._funestra)
        if cell.thumb:
            cached = self._thumbs.get(cell.thumb)
            if cached is None:
                try:
                    image = Image.open(cell.thumb).convert("RGBA")
                except OSError:
                    image = None
                if image is not None:
                    scale = min(slot_w / max(1, image.width), MAP_THUMB_H / max(1, image.height))
                    cached = image.resize((max(1, round(image.width * scale)),
                                           max(1, round(image.height * scale))))
                    self._thumbs[cell.thumb] = cached
            if cached is not None:
                return cached
        return Image.new("RGBA", (slot_w, MAP_THUMB_H), (*_PLACEHOLDER, 255))

    def _map_thumbnails(
        self, model: HudModel
    ) -> tuple[Image.Image | None, list[Image.Image], list[Image.Image]]:
        if model.corner is None:
            return None, [], []
        return (self._thumbnail(model.corner),
                [self._thumbnail(cell) for cell in model.seeds],
                [self._thumbnail(cell) for cell in model.actions])

    @staticmethod
    def _block_x(model: HudModel, panel_width: int, extent: int, reserve: int = 0) -> int:
        return block_x(model.hud_corner, panel_width=panel_width, extent=extent, pad=PAD,
                       reserve=reserve)

    def render(
        self,
        model: HudModel,
        *,
        video: str = "",
        clip_row: RowHud | None = None,
        heatmap: np.ndarray | None = None,
        hover_loop: str = "",
        hover_tip: str = "",
        hover_pos: tuple[int, int] = (0, 0),
        may_grow_on_hover: bool = True,
        minus_on_the_panel: bool = True,
    ) -> RenderedHud:
        """The panel as a BGRA bitmap plus the rects its controls occupy.

        The current clip anchors the map — its seed family runs right along the row
        and distinct other actions run down the column, so stepping an action
        moves down and the row reloads with that action's seeds.  The column hangs
        under whichever row cell is playing (fun_time builds it from that seed's
        own acts), the corner when the corner is.  A lock rings the cell being
        held in white: the corner normally, or the clip a loop had reached when
        the lock was taken.

        *clip_row* is where the clip on screen has got to and how loud it is, with
        *heatmap* its funscript's colors for a host that has one: the row every
        Funestra used to lay along the lower edge of its own picture, drawn here
        instead (:mod:`funestra.hud_row`).  Like *video* it comes from the
        Funestra rather than from *model*, being what is decoding rather than what
        the source published.

        *video* is the file on screen, named under the status line.  It comes from
        the Funestra rather than from *model*: the published panel is fun_time's answer
        to what this side is browsing, and what is actually decoding is the Funestra's
        own — the same split the Main Funestra draws, which names its file from its own
        session and takes the rest of its console off the wire.
        """
        # Where the pointer is for this frame, or None off the panel.  The
        # position is only current while something under it has a tooltip —
        # every control here has one — so an empty tip means "not on a button".
        self._pointer = hover_pos if hover_tip else None
        if model.hud_minimized:
            bgra, buttons = collapsed_panel(
                model.funestra, model.hud_corner, hover=self._pointer,
                room_for_the_tooltip=not may_grow_on_hover)
            return RenderedHud(bgra, HudTargets(click=[], loop=[], filter=[], expand=None,
                                                buttons=buttons))
        model = replace(model, drive=self._readout.resolve(
            model.drive, osr2=model.osr2, control=model.osr2_control,
            composed=model.drive_composed))
        counts = self._count_lines(model)
        model, seed_win, action_win = self._window(model)
        corner_thumb, seed_thumbs, action_thumbs = self._map_thumbnails(model)
        # The bands' own demand: a row the panel cannot hold clips away in
        # silence — the buttons past the edge are simply not there, with nothing
        # raised — so the panel is measured around the widest row.
        rows = [list(row) for row in model.rows]
        widths = [[self._button_width(button) for button in row] for row in rows]
        # The rows that aim the device are measured with the rest -- they are
        # drawn in the device's own block, but a panel too narrow for them clips
        # them away just as silently.
        device_rows = [list(row) for row in model.osr2_rows]
        device_row_widths = [[self._button_width(b) for b in row] for row in device_rows]
        band_width = max((
            2 * PAD + button_row_width(row, row_widths)
            for row, row_widths in zip(rows + device_rows, widths + device_row_widths)
            if row
        ), default=0)
        # The device's own blocks, on a host that drives it: the OSR2 line and
        # the readout ask for width the way the bands do, and for room under them.
        composed = (model.drive if model.drive_composed and model.drive is not None
                    and model.drive.segments else None)
        osr2_line = Osr2Line(
            state=state_for(model.osr2, model.osr2_control,
                            driving=driving_at_the_playhead(composed, model.osr2)),
            controls=model.osr2_controls, max_intensity=model.max_intensity)
        drive_w, drive_h = section_size() if model.drive is not None else (0, 0)
        device_w = max(self._osr2.width(osr2_line) if model.osr2 else 0, drive_w)
        foot_w, foot_h = model.foot.size() if model.foot is not None else (0, 0)
        width = panel_width(model.funestra, text_width(self._tiny, video),
                            content_width=max(
                                band_width,
                                2 * PAD + device_w if device_w else 0,
                                2 * PAD + foot_w if foot_w else 0,
                                2 * PAD + self._clip_row.least_width(clip_row)
                                if clip_row is not None else 0))
        row_h = ROW_H if clip_row is not None else 0
        layout = panel_layout(
            status_h=self._status_height(),
            bands=len(rows), speed=model.playback_speed is not None, row_h=row_h,
            device_h=device_height(model.osr2, model.drive, drive_h, len(device_rows)),
            foot_h=foot_h)
        height = layout.height
        panel = HudPanel(width, height)
        for divider in layout.dividers:
            panel.divide(divider)
        image, draw = panel.image, panel.draw

        x = PAD
        minus_room = MINIMIZE_ROOM if minus_on_the_panel else 0
        room = width - STATUS_TEXT_X - PAD - minus_room
        title = self._title_font(largest_size_that_fits(
            _SIZE_BODY, room,
            lambda size: text_width(self._title_font(size), model.lock_label)))
        favorite = self._draw_status_band(
            image, draw, PAD, model, width, title,
            name_line(video, model.item_note, room, lambda text: text_width(self._tiny, text)),
            reserve=0 if model.hud_corner.lower else minus_room)
        y = layout.bands
        buttons: list[tuple[Rect, Button]] = []
        if minus_on_the_panel:
            minus = (corner_button_rect(model.hud_corner, panel=(width, height),
                                        inset=MINUS_INSET),
                     minimize_button(model.funestra))
            draw_button(image, draw, *minus, hovered=self._pointer_is_on(minus[0]),
                        glyph_font=self._glyph, word_font=self._tiny)
            buttons.append(minus)

        # Laid out against the panel rather than against the map: they act on the
        # side and the clip on screen, and are there whether or not there is a map.
        for row, row_widths in zip(rows, widths):
            placed = button_row_rects(
                self._block_x(model, width, button_row_width(row, row_widths)),
                y, row, row_widths)
            for index, (rect, button) in enumerate(placed):
                draw_button(image, draw, rect, button, hovered=self._pointer_is_on(rect),
                            glyph_font=self._glyph, word_font=self._tiny,
                            row_label=index == 0)
            buttons.extend(placed)
            y += CTRL_BAND_H

        # The rate this side plays at, its own row under the bands -- drawn here
        # rather than declared, since only the drawing Funestra knows the number.
        # Its two buttons still register as declared buttons, so a press posts
        # the side's speed verb and a hover names it like any other.
        if model.playback_speed is not None:
            label_width = text_width(self._tiny, PLAYBACK_SPEED_LABEL) + BUTTON_GROUP_GAP
            speed_x = self._block_x(model, width, speed_row_width(label_width))
            speed_buttons, rate_rect = speed_row(model.funestra, speed_x, layout.speed,
                                                 label_width=label_width)
            draw.text((speed_x, layout.speed + CTRL_BTN / 2), PLAYBACK_SPEED_LABEL,
                      font=self._tiny, anchor="lm", fill=(*TEXT_MUTED, 255))
            for rect, button in speed_buttons:
                draw_button(image, draw, rect, button, hovered=self._pointer_is_on(rect),
                            glyph_font=self._glyph, word_font=self._tiny)
            rx, ry, rw, rh = rate_rect
            draw.text((rx + rw / 2, ry + rh / 2), format_rate(model.playback_speed),
                      font=self._tiny, anchor="mm", fill=(*TEXT_PRIMARY, 255))
            buttons.extend(speed_buttons)

        row = None
        if clip_row is not None:
            row = row_layout(clip_row, rect=(x, layout.row, width - 2 * PAD, row_h))
            self._clip_row.draw(image, row, clip_row, heatmap=heatmap)
        device_buttons, bands = self._draw_device(
            image, draw, width, layout.device, model, osr2_line, drive_h,
            rows=device_rows, widths=device_row_widths)
        buttons.extend(device_buttons)
        foot_rect = None
        if model.foot is not None:
            foot_rect = (x, layout.foot, width - 2 * PAD, foot_h)
            buttons.extend(model.foot.paint(image, x, layout.foot, width - 2 * PAD,
                                            self._pointer))

        map_targets = (self._draw_map(image, draw, model, layout.map, width, counts,
                                      (corner_thumb, seed_thumbs, action_thumbs),
                                      (seed_win, action_win), hover_loop)
                       if corner_thumb is not None
                       else HudTargets(click=[], loop=[], filter=[], expand=None))
        if hover_tip:
            draw_tooltip(draw, self._tiny, hover_tip, hover_pos, (width, height))
        return RenderedHud(panel.to_bgra(), replace(
            map_targets, tracks=bands, row=row, foot=foot_rect, buttons=buttons,
            favorite=favorite))

    def _draw_map(self, image, draw, model: HudModel, top: int, width: int,
                  counts: tuple[str, ...], thumbs, windows, hover_loop: str) -> HudTargets:
        corner_thumb, seed_thumbs, action_thumbs = thumbs
        seed_win, action_win = windows
        gutter_x = self._block_x(model, width, map_block_width(model.funestra))
        self._draw_counts(draw, gutter_x, top, counts)
        map_x = gutter_x + ROW_LABEL_GUTTER + ELLIPSIS_ROOM
        map_y = top + COL_LABEL_H + COL_LABEL_GAP + ELLIPSIS_ROOM
        corner_rect, seed_rects, action_rects = slot_rects(
            map_x=map_x, map_y=map_y, slot_w=slot_width(model.funestra),
            seeds=len(seed_thumbs), actions=len(action_thumbs), playing=model.playing)
        column_rect = column_anchor_rect(model.playing, corner_rect, seed_rects)

        pictures = self._draw_thumbnails(image, model, corner_rect, seed_rects, action_rects,
                                         corner_thumb, seed_thumbs, action_thumbs)
        held = playing_rect(model.playing, corner_rect, seed_rects, action_rects)
        if model.locked and held is not None:
            hx, hy, hw, hh = pictures[held]
            draw.rectangle([hx, hy, hx + hw - 1, hy + hh - 1],
                           outline=(*WHITE, 255), width=_BORDER_W)
        wrong_rect = self._draw_labels(image, draw, model, gutter_x, top,
                                       corner_rect, seed_rects, action_rects,
                                       seed_offset=seed_win.start if seed_win else 0)
        filter_rects = filter_button_rects(corner_rect, action_rects, gutter_x,
                                           model.current_action,
                                           [cell.label for cell in model.actions])
        self._draw_filter_buttons(draw, filter_rects, model)

        loop_action_rect, loop_seed_rect = loop_button_rects(
            corner_rect, row_end=map_x + map_row_width(model.funestra),
            column_end=map_y + MAP_COLUMN_H, reserve=ELLIPSIS_ROOM, column_rect=column_rect)
        expand_rect = expand_button_rect(loop_seed_rect)
        self._draw_loop_controls(image, draw, corner_rect, column_rect, loop_action_rect,
                                 loop_seed_rect, seed_rects, action_rects,
                                 model.active_loop, hover_loop)
        for axis, window in (("seed", seed_win), ("action", action_win)):
            if window is not None:
                self._draw_ellipses(draw, corner_rect, column_rect, seed_rects,
                                    action_rects, axis, window)
        if expand_rect is not None:
            self._glyph_button(image, draw, expand_rect, _EXPAND_GLYPH)
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
        bands: list[DriveTrack] = []
        for row, row_widths in zip(rows, widths):
            placed = button_row_rects(
                self._block_x(model, width, button_row_width(row, row_widths)),
                y, row, row_widths)
            for index, (rect, button) in enumerate(placed):
                draw_button(image, draw, rect, button, hovered=self._pointer_is_on(rect),
                            glyph_font=self._glyph, word_font=self._tiny,
                            row_label=index == 0)
            buttons.extend(placed)
            y += CTRL_BAND_H
        max_intensity_bands: list[DriveTrack] = []
        if model.osr2:
            osr2_x = self._block_x(model, width, self._osr2.width(osr2_line))
            buttons.extend(self._osr2.draw(image, draw, osr2_x, y, osr2_line,
                                           hover=self._pointer))
            max_intensity_bands = self._osr2.bands(osr2_x, y, osr2_line)
            y += OSR2_H + BLOCK_GAP
        if model.drive is not None:
            drive_x = self._block_x(model, width, section_size()[0])
            # The panel's image rather than its pen: the readout supersamples its
            # trace and composites it back, which a pen cannot carry.
            self._drive.draw(image, drive_x, y, model.drive)
            drive_targets, bands = readout_targets(drive_x, y, model.drive)
            buttons.extend(drive_targets)
        return buttons, bands + max_intensity_bands

    def _button_width(self, button: Button) -> int:
        """A declared button's width: its own, or -- asking to fit its word --
        the word as this face draws it, padded either side."""
        return button.width or text_width(self._tiny, button.glyph) + 2 * MODE_LABEL_PAD

    def _title_font(self, size: int) -> ImageFont.FreeTypeFont:
        if size not in self._titles:
            self._titles[size] = load_font(size)
        return self._titles[size]

    def _draw_status_band(self, image, draw, y: int, model: HudModel, width: int,
                          title: ImageFont.FreeTypeFont, under_status: str, *,
                          reserve: int) -> Rect | None:
        status_x = self._block_x(model, width,
                                 STATUS_INDENT + text_width(title, model.lock_label),
                                 reserve=reserve)
        draw_active_dot(draw, status_x, y + 2, model.active)
        draw.text((status_x + STATUS_INDENT, y + STATUS_BASELINE), model.lock_label,
                  font=title, anchor="ls", fill=(*TEXT_PRIMARY, 255))
        if not under_status:
            return None
        line_y = y + self._name_line_top()
        name_x = self._block_x(model, width,
                              STATUS_INDENT + text_width(self._tiny, under_status),
                              reserve=reserve)
        draw.text((name_x + STATUS_INDENT, line_y), under_status,
                  font=self._tiny, anchor="la", fill=(*TEXT_MUTED, 255))
        favorite = favorite_mark_rect(name_x, line_y, sum(self._tiny.getmetrics()))
        draw_mark(image, FAVORITE_MARK, favorite,
                  (*(GREEN if model.is_favorite else TEXT_MUTED), 255))
        return favorite

    def _name_line_top(self) -> int:
        _ascent, descent = self._body.getmetrics()
        return STATUS_BASELINE + descent + SUBTITLE_GAP

    def _status_height(self) -> int:
        return self._name_line_top() + sum(self._tiny.getmetrics())

    def _window(
        self, model: HudModel
    ) -> tuple[HudModel, MapWindow | None, MapWindow | None]:
        """*model* narrowed to the cells actually drawn, plus each axis's window.

        An axis can hold far more clips than the map draws — a loop's group
        especially — so each axis is drawn through a window of MAP_CELLS that keeps
        the playing cell near the middle, rather than drawing the first few and
        leaving the clip on screen off the map once playback moves past them.
        Narrowing the model here means everything downstream — rects, labels, hit
        targets and the bright cell — works off the drawn cells alone.
        """
        if model.corner is None:
            return model, None, None
        bucket, index = model.playing
        seed_strip = [model.corner, *model.seeds]
        action_strip = [model.corner, *model.actions]
        seed_at = index + 1 if bucket == "seed" else 0
        action_at = index + 1 if bucket == "action" else 0
        seed_win = map_window(len(seed_strip), seed_at)
        action_win = map_window(len(action_strip), action_at)
        # The corner slot belongs to whichever axis the clip on screen sits on: that
        # is the only axis whose window can have moved off the corner.  Both strips
        # hold the corner, so both windows hold at least it.
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
            # A column window can open on a sibling act, so the corner's row label
            # comes from the cell drawn there rather than the anchor's own action.
            narrowed = replace(narrowed, current_action=corner.label or model.current_action)
        return narrowed, seed_win, action_win

    @staticmethod
    def _count_lines(model: HudModel) -> tuple[str, ...]:
        """"Seeds: n" / "Actions: n" — how many clips each axis stands for.

        Empty until fun_time's index has answered, so a satellite still starting up
        prints nothing rather than a confident "Seeds: 0".
        """
        if not (model.seed_count or model.action_count):
            return ()
        return (f"Seeds: {model.seed_count}", f"Actions: {model.action_count}")

    def _draw_counts(self, draw, x: int, y: int, lines: tuple[str, ...]) -> None:
        """The axis counts, in the corner left of the map and above its first row.

        The map draws only MAP_CELLS of each axis — and a window can hide a whole
        loop's worth — so this is the only place its real size can be read.  It sits
        outside the map proper, in the gutter's own column, and is there whether or
        not a loop is running.
        """
        for line_no, text in enumerate(lines, start=1):
            draw.text((x, y + _COUNT_LINE_H * line_no), text, font=self._tiny,
                      anchor="ls", fill=(*TEXT_MUTED, 255))

    def _draw_ellipses(self, draw, corner_rect, column_rect, seed_rects, action_rects,
                       axis, window) -> None:
        """Three dots in the slots kept at each end of *axis*, on whichever side it
        runs on past what is drawn — along the row, down the column.  They fall inside
        a running loop's rectangle, so they read as "more of these are in the loop"
        rather than as something outside it, and a gap in from its border, so they do
        not read as part of that border either.

        Drawn rather than typed: an "…" glyph hangs off the text baseline, which in a
        slot this small puts it against the lower edge instead of in the middle.
        """
        before, after = ellipsis_rects(corner_rect, seed_rects, action_rects, axis,
                                       column_rect=column_rect)
        for rect, show in ((before, window.more_before), (after, window.more_after)):
            if not show:
                continue
            bx, by, bw, bh = rect
            mx, my = bx + bw / 2, by + bh / 2
            for step in (-1, 0, 1):
                dx, dy = (step * _DOT_GAP, 0) if axis == "seed" else (0, step * _DOT_GAP)
                draw.ellipse([mx + dx - _DOT, my + dy - _DOT, mx + dx + _DOT, my + dy + _DOT],
                             fill=(*TEXT_PRIMARY, 255))

    def _draw_thumbnails(self, image, model, corner_rect, seed_rects, action_rects,
                         corner_thumb, seed_thumbs, action_thumbs) -> dict[Rect, Rect]:
        bucket, index = model.playing
        drawn = [(corner_rect, corner_thumb, bucket == "corner")]
        drawn += [(slot, thumb, bucket == "seed" and index == i)
                  for i, (slot, thumb) in enumerate(zip(seed_rects, seed_thumbs))]
        drawn += [(slot, thumb, bucket == "action" and index == i)
                  for i, (slot, thumb) in enumerate(zip(action_rects, action_thumbs))]
        pictures: dict[Rect, Rect] = {}
        for slot, thumb, bright in drawn:
            pictures[slot] = picture_rect(slot, thumb.size)
            if not bright:
                thumb = thumb.copy()
                thumb.putalpha(thumb.getchannel("A").point(lambda a: int(a * _DIM)))
            image.alpha_composite(thumb, pictures[slot][:2])
        return pictures

    def _draw_labels(self, image, draw, model, x, y, corner_rect, seed_rects,
                     action_rects, *, seed_offset: int = 0) -> Rect | None:
        """Column labels ("Seed N") in the header strip and action names down the
        left gutter, drawn over the (possibly dimmed) thumbnails at full opacity.

        Returns the strike's rect — the button under the current clip's act that
        says the act is wrong — or None where no act is named.
        """
        def column(cx: int, cw: int, text: str) -> None:
            # Clipped to its own column: a portrait map's columns are barely wider
            # than the label, and neighbouring "Seed N"s running together is
            # illegible.  Drawn into a column-sized scratch, so the overflow is cut.
            strip = Image.new("RGBA", (cw, COL_LABEL_H), (0, 0, 0, 0))
            ImageDraw.Draw(strip).text((cw / 2, COL_LABEL_H / 2), text, font=self._tiny,
                                       anchor="mm", fill=(*TEXT_MUTED, 255))
            image.alpha_composite(strip, (cx, y))

        def row(row_y: int, row_h: int, text: str, *, extra: int = 0) -> int:
            # One block of tight word-lines per act, with a bigger gap between
            # acts, so a two-word act ("Motion" / "Bounce") wraps close but two acts
            # ("Alpha" then "Theta Motion") are clearly separated.  Each act is lit
            # on its own account, and only inside a row the filter actually keeps:
            # the row says whether the clip is here at all, the act says which of
            # its acts is why.  Lighting a matching act inside a row the filter
            # drops would mark a clip that is not in the playlist.
            row_lit = label_is_filtered(text, model.filter_query, model.camera_words)
            ascent, descent = self._row.getmetrics()
            line_h = ascent + descent - 4
            blocks = action_label_blocks(text, model.camera_words)
            total = sum(len(block) for block in blocks) * line_h + (len(blocks) - 1) * ACT_GAP
            # *extra* is room kept under the words — the corner row's strike.  The
            # words and it are centered in the row together, so a two-act label
            # cannot run down into the button.
            ty = label_stack_top(row_y, row_h, total, extra)
            words_end = ty + total
            for block in blocks:
                lit = row_lit and act_is_filtered(
                    " ".join(block), model.filter_query, model.camera_words)
                color = TEXT_PRIMARY if lit else TEXT_MUTED
                for line in block:
                    draw.text((x + ROW_LABEL_GUTTER - MAP_GAP, ty + line_h / 2), line,
                              font=self._row, anchor="rm", fill=(*color, 255))
                    ty += line_h
                ty += ACT_GAP
            return words_end

        cx, cy, cw, ch = corner_rect
        # Offset by where a windowed loop opens, so the headers carry each seed's
        # real place in the family instead of restarting at one every window.
        column(cx, cw, seed_column_label(seed_offset))
        # Only the corner row keeps room for the strike: it is the clip on screen
        # whose act would be wrong, and the rows under it are other clips'.
        strike = WRONG_BTN + WRONG_GAP if model.current_action else 0
        words_end = row(cy, ch, model.current_action, extra=strike)
        wrong = (wrong_action_rect(x + ROW_LABEL_GUTTER - MAP_GAP, words_end)
                 if model.current_action else None)
        if wrong is not None:
            self._strike_button(image, draw, wrong)
        for i, (sx, _sy, sw, _sh) in enumerate(seed_rects):
            column(sx, sw, seed_column_label(seed_offset + i + 1))
        for i, (_ax, ay, _aw, ah) in enumerate(action_rects):
            row(ay, ah, model.actions[i].label if i < len(model.actions) else "")
        return wrong

    def _pointer_is_on(self, rect: Rect) -> bool:
        """Whether the pointer is inside *rect* in the frame being drawn.

        Read off the hover the render was handed rather than passed down through
        every button: the panel is redrawn on every hover change anyway, and
        threading a flag through six drawing helpers to say one thing is how the
        lock ended up with three ways to be told it was on.
        """
        return self._pointer is not None and contains(rect, *self._pointer)

    def _button_square(self, draw, rect: Rect, *, on: bool,
                       on_color=BLUE, ink=None) -> tuple[int, int, int, int]:
        """The panel's square button, and the color to draw its mark in — the
        single button shape every control on this HUD is drawn with, so a new one
        cannot invent its own look.

        Off, the square sits on the family's own button ground -- an outline over
        the slab and nothing else read as a gap cut in the panel rather than as
        the raised button every window here offers -- with an edge in the muted
        gray the rest of the chrome uses, and the MARK is full-strength -- the same way the Main Funestra's console
        draws its own.  Both were muted here, which left these panels reading as
        dim and half-disabled beside the console's, for controls that were
        neither.  On, the square fills *on_color*: the family's ACTIVE ground, one
        step up from the resting one, which is the step Origenerator's checked
        buttons take and now the step every HUD here takes with them.  It used to
        fill white, the loudest thing on the panel for a control whose whole news
        is that it is on.  The lock is the exception: green across this family
        means favorites and the funscripts, and the lock is the gesture that
        favorites a clip, so it is the one control that earns the color.

        *ink* overrides the off-state mark -- the bin takes red, the color
        Origenerator's Delete wears, since it is the one control here that takes
        something away.
        """
        return button_ground(draw, rect, on_color if on else BG_BUTTON,
                             hovered=self._pointer_is_on(rect), rest_ink=ink)

    def _glyph_button(self, image, draw, rect: Rect, glyph: str, *, on: bool = False,
                      on_color=WHITE, ink=None) -> None:
        """One of the panel's square buttons, with a mark or a glyph on it.

        A mark the family draws is rendered from its geometry, so the bin here is
        the bin on Origenerator's toolbar rather than whatever a symbol face had.
        A typed glyph is centered on its own ink instead: the padlock and the
        transport arrows sit high in bounds that run to the descender, so the
        font's own centering dropped every one of them toward its button's floor.
        """
        ink = self._button_square(draw, rect, on=on, on_color=on_color, ink=ink)
        if glyph.startswith(SHARED_MARK):
            draw_mark(image, shared_mark_name(glyph), rect, ink)
            return
        bx, by, bw, bh = rect
        draw_glyph(draw, bx + bw / 2, by + bh / 2, glyph, self._glyph, ink)

    def _filter_button(self, draw, rect: Rect, *, on: bool = False) -> None:
        """The same square button with a funnel drawn on it, for the act filter."""
        ink = self._button_square(draw, rect, on=on)
        bx, by, bw, bh = rect
        cx, cy = bx + bw / 2, by + bh / 2
        mouth, neck = _FUNNEL_W / 2, _FUNNEL_NECK / 2
        upper, lower = cy - _FUNNEL_H / 2, cy + _FUNNEL_H / 2
        draw.polygon(
            [(cx - mouth, upper), (cx + mouth, upper), (cx + neck, cy), (cx + neck, lower),
             (cx - neck, lower), (cx - neck, cy)],
            fill=ink,
        )

    def _strike_button(self, image, draw, rect: Rect) -> None:
        """The strike under the current clip's act: the family's cross, drawn red.

        Red because it takes something away — the same red the bin on the control
        band wears, and the one color on this panel worth stopping at before
        pressing.  Never lit: striking an act is a thing done, not a state the
        side sits in, and the act is relabeled out from under it.
        """
        self._button_square(draw, rect, on=False, ink=RED)
        draw_mark(image, WRONG_ACTION_MARK, rect, (*RED, 255))

    def _draw_filter_buttons(self, draw, rects: list[tuple[Rect, str]],
                             model: HudModel) -> None:
        """The filter button at the head of each row, lit on every row the filter
        keeps — which is more than the row that names it exactly, since fun_time
        matches a query as a substring (see :func:`label_is_filtered`).

        It lights off the published filter, exactly as the loop buttons light off
        the published loop — so a filter set any other way (spoken, or from the
        other side's map) shows here too, and pressing a lit one lifts it.
        """
        for rect, name in rects:
            self._filter_button(draw, rect, on=label_is_filtered(
                name, model.filter_query, model.camera_words))

    def _draw_loop_controls(self, image, draw, corner_rect, column_rect, loop_action_rect,
                            loop_seed_rect, seed_rects, action_rects, active_loop,
                            hover_loop) -> None:
        """The two loop buttons, and — while one is hovered or its loop is on — a
        border around the videos it loops (dashed for a hover preview, solid once
        on).  The border wraps the room kept for that axis's "…" marks, so the clips
        they stand for read as part of the looped set."""
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
            self._glyph_button(image, draw, button, _LOOP_GLYPH, on=on)
            if on:
                gx, gy, gw, gh = group_rect
                draw.rectangle([gx, gy, gx + gw - 1, gy + gh - 1],
                               outline=(*WHITE, 255), width=2)
            elif hover_loop == kind:
                _dashed_rect(draw, group_rect, (*WHITE, 255))

