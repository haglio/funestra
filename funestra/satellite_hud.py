from __future__ import annotations

import contextlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, NamedTuple, Protocol

from PIL import Image
from shared_ui.lettering import fit_text
from shared_ui.spacing import (
    BUTTON_GAP,
    BUTTON_GROUP_GAP,
    BUTTON_PAD_H_TIGHT,
    BUTTON_SIZE_HUD,
    GAP_DIALOG,
    GAP_MEDIUM,
    GAP_SMALL,
    MARGIN_DIALOG,
    MARGIN_STANDARD,
)
from shared_ui.type_scale import SIZES

from .geometry import Rect, contains
from .hud import ACTIVE_DOT
from .hud_button import (
    Button,
    buttons_from_raw,
    buttons_raw,
    reading_its_host_value,
    rows_from_raw,
    rows_raw,
)
from .hud_controls import PLAYBACK_SPEED, playback_speed_buttons
from .hud_osr2 import HEIGHT as OSR2_H
from .hud_placement import HudCorner, HudEdge
from .hud_sections import blocks_height, stack
from .hud_title import SEPARATOR
from .main_hud import max_intensity_from_raw
from .modes import read_mode
from .osr2_visualizer import DriveHud, DriveTrack
from .playback_rate import format_rate
from .video_families import filter_keeps, labels_text, normalized_text

if TYPE_CHECKING:
    from .hud_row import RowLayout


MARGIN = MARGIN_DIALOG

PAD = MARGIN_STANDARD
BLOCK_GAP = GAP_MEDIUM
MAP_THUMB_H = 54
NAV_MAP_GAP = GAP_SMALL
ROW_GAP = GAP_DIALOG
ACT_GAP = GAP_MEDIUM
COL_LABEL_H = 13
COL_LABEL_GAP = GAP_SMALL
ROW_LABEL_GUTTER = 100
LOOP_BTN = 18
FILTER_BTN = 18

NAV_MAP_RIGHT_RESERVE = 2 * (LOOP_BTN + NAV_MAP_GAP)
NAV_MAP_LOWER_RESERVE = LOOP_BTN + NAV_MAP_GAP

NAV_MAP_CELLS = 3
WIDEST_FULL_HEIGHT_SHAPE = {"portrait": (4, 5), "landscape": (16, 9)}

TITLE_ROW_H = 24
TITLE_X = PAD + ACTIVE_DOT + 8
SUBTITLE_GAP = GAP_SMALL

Cell = tuple[str, int]


@dataclass(frozen=True)
class HudCell:
    path: str
    thumb: str = ""
    label: str = ""


class HudSection(Protocol):
    def size(self) -> tuple[int, int]: ...

    def paint(self, image: Image.Image, x: int, y: int, width: int,
              pointer: tuple[int, int] | None) -> list[tuple[Rect, Button]]: ...


@dataclass(frozen=True)
class PaintedFoot:
    file: str
    width: int
    height: int
    stamp: str = ""
    targets: tuple[tuple[Rect, Button], ...] = ()

    def size(self) -> tuple[int, int]:
        return self.width, self.height

    def paint(self, image: Image.Image, x: int, y: int, width: int,
              pointer: tuple[int, int] | None) -> list[tuple[Rect, Button]]:
        with contextlib.suppress(OSError):
            image.alpha_composite(_painted_at(self.file, self.stamp), (x, y))
        return [((x + left, y + top, w, h), button)
                for (left, top, w, h), button in self.targets]

    def raw(self) -> dict:
        return {"file": self.file, "width": self.width, "height": self.height,
                "stamp": self.stamp, "rects": [list(rect) for rect, _button in self.targets],
                "buttons": buttons_raw(tuple(button for _rect, button in self.targets))}

    @classmethod
    def from_raw(cls, raw: object) -> PaintedFoot | None:
        if not isinstance(raw, dict):
            return None
        rects = [tuple(int(side) for side in rect) for rect in raw.get("rects") or ()]
        return cls(file=str(raw.get("file", "") or ""), width=int(raw.get("width", 0) or 0),
                   height=int(raw.get("height", 0) or 0), stamp=str(raw.get("stamp", "") or ""),
                   targets=tuple(zip(rects, buttons_from_raw(raw.get("buttons")), strict=False)))


@lru_cache(maxsize=4)
def _painted_at(path: str, _stamp: str) -> Image.Image:
    with Image.open(path) as opened:
        return opened.convert("RGBA")


@dataclass(frozen=True)
class HudModel:
    funestra: str
    hud_corner: HudCorner = HudCorner.UPPER_LEFT
    hud_edge: HudEdge = HudEdge.LOWER
    hud_minimized: bool = False
    locked: bool = False
    title: str = ""
    active: bool = False

    is_favorite: bool = False
    item_note: str = ""
    corner: HudCell | None = None
    seeds: tuple[HudCell, ...] = ()
    actions: tuple[HudCell, ...] = ()
    current_action: str = ""
    filter_query: str = ""
    active_loop: str = ""
    seed_count: int = 0
    action_count: int = 0
    playing: Cell = ("corner", 0)
    playback_speed: float | None = None
    rows: tuple[tuple[Button, ...], ...] = ()

    osr2: str = ""
    osr2_rows: tuple[tuple[Button, ...], ...] = ()
    osr2_control: str = ""
    osr2_controls: tuple[Button, ...] = ()
    max_intensity: int | None = None
    paused: bool = False
    drive: DriveHud | None = None
    drive_composed: bool = False

    foot: HudSection | None = None


ELLIPSIS = 12
ELLIPSIS_ROOM = ELLIPSIS + 2 * NAV_MAP_GAP
NAV_MAP_COLUMN_H = NAV_MAP_CELLS * MAP_THUMB_H + (NAV_MAP_CELLS - 1) * ROW_GAP
NAV_MAP_H = (COL_LABEL_H + COL_LABEL_GAP + ELLIPSIS_ROOM + NAV_MAP_COLUMN_H
         + ELLIPSIS_ROOM + NAV_MAP_LOWER_RESERVE)


def place_width(funestra: str) -> int:
    across, down = WIDEST_FULL_HEIGHT_SHAPE.get(funestra, WIDEST_FULL_HEIGHT_SHAPE["portrait"])
    return round(MAP_THUMB_H * across / down)


def nav_map_row_width(funestra: str) -> int:
    return NAV_MAP_CELLS * place_width(funestra) + (NAV_MAP_CELLS - 1) * NAV_MAP_GAP


def map_block_width(funestra: str) -> int:
    return (ROW_LABEL_GUTTER + ELLIPSIS_ROOM + nav_map_row_width(funestra) + ELLIPSIS_ROOM
            + NAV_MAP_RIGHT_RESERVE)


def hud_width(funestra: str, name_width: int = 0, *, content_width: int = 0) -> int:
    return max(2 * PAD + map_block_width(funestra),
               TITLE_X + name_width + PAD, content_width)


def device_height(osr2: str, drive: DriveHud | None, drive_h: int,
                  osr2_rows: int = 0) -> int:
    return blocks_height([CTRL_BTN] * osr2_rows + [OSR2_H if osr2 else 0,
                                                    drive_h if drive is not None else 0],
                         BLOCK_GAP)


@dataclass(frozen=True)
class HudLayout:
    bars: int
    row: int
    device: int
    foot: int
    nav_map: int
    height: int
    dividers: tuple[int, ...]


class SectionHeights(NamedTuple):
    title: int
    row: int = 0
    device: int = 0
    foot: int = 0


def hud_layout(*, heights: SectionHeights, bars: int = 0) -> HudLayout:
    stacked = stack(PAD, [heights.title, blocks_height([CTRL_BTN] * bars, BLOCK_GAP),
                          heights.row, heights.device, heights.foot, NAV_MAP_H])
    _title, bars_top, row_top, device_top, foot_top, nav_map_top = stacked.tops
    return HudLayout(bars_top, row_top, device_top,
                     foot_top, nav_map_top, stacked.end + PAD, stacked.dividers)


@dataclass(frozen=True)
class NavMapWindow:
    start: int
    count: int
    more_before: bool
    more_after: bool


def nav_map_window(total: int, playing: int, limit: int = NAV_MAP_CELLS) -> NavMapWindow:
    if total <= 0 or limit <= 0:
        return NavMapWindow(0, 0, False, False)
    playing = max(0, min(playing, total - 1))
    start, end = playing, playing + 1
    while end - start < min(limit, total):
        if end < total and (start == 0 or end - playing - 1 <= playing - start):
            end += 1
        else:
            start -= 1
    return NavMapWindow(start, end - start, start > 0, end < total)


def column_anchor_rect(playing: Cell, corner_rect: Rect, seed_rects: list[Rect]) -> Rect:
    bucket, index = playing
    if bucket == "seed" and 0 <= index < len(seed_rects):
        return seed_rects[index]
    return corner_rect


class NavMapRects(NamedTuple):
    corner: Rect | None
    seeds: list[Rect]
    actions: list[Rect]
    column: Rect | None = None

    @property
    def column_or_corner(self) -> Rect | None:
        return self.corner if self.column is None else self.column


def place_rects(
    *,
    origin: tuple[int, int],
    place_w: int,
    seeds: int,
    actions: int,
    playing: Cell = ("corner", 0),
) -> NavMapRects:
    nav_map_x, nav_map_y = origin
    corner = (nav_map_x, nav_map_y, place_w, MAP_THUMB_H)
    seed_rects = [(nav_map_x + step * (place_w + NAV_MAP_GAP), nav_map_y, place_w, MAP_THUMB_H)
                  for step in range(1, min(seeds + 1, NAV_MAP_CELLS))]
    column = column_anchor_rect(playing, corner, seed_rects)
    column_x = column[0]
    action_rects = [(column_x, nav_map_y + step * (MAP_THUMB_H + ROW_GAP), place_w, MAP_THUMB_H)
                    for step in range(1, min(actions + 1, NAV_MAP_CELLS))]
    return NavMapRects(corner, seed_rects, action_rects, column)


def thumbnail_rect(place: Rect, size: tuple[int, int]) -> Rect:
    x, y, w, h = place
    width, height = size
    return (x + (w - width) // 2, y + (h - height) // 2, width, height)


def playing_rect(
    playing: Cell, corner_rect: Rect, seed_rects: list[Rect], action_rects: list[Rect]
) -> Rect | None:
    bucket, index = playing
    if bucket == "corner":
        return corner_rect
    rects = seed_rects if bucket == "seed" else action_rects if bucket == "action" else []
    return rects[index] if 0 <= index < len(rects) else None


def _row_right(corner_rect: Rect, seed_rects: list[Rect]) -> int:
    cx, _cy, cw, _ch = corner_rect
    return max([cx + cw] + [sx + sw for sx, _sy, sw, _sh in seed_rects])


def _col_lower(corner_rect: Rect, action_rects: list[Rect]) -> int:
    _cx, cy, _cw, ch = corner_rect
    return max([cy + ch] + [ay + ah for _ax, ay, _aw, ah in action_rects])


def loop_button_rects(
    corner_rect: Rect | None,
    *,
    row_end: int,
    column_end: int,
    reserve: int = 0,
    column_rect: Rect | None = None,
) -> tuple[Rect | None, Rect | None]:
    if corner_rect is None:
        return None, None
    _cx, cy, _cw, ch = corner_rect
    col_x, _col_y, col_w, _col_h = corner_rect if column_rect is None else column_rect
    loop_action = (col_x, column_end + reserve + NAV_MAP_GAP, col_w, LOOP_BTN)
    loop_seed = (row_end + reserve + NAV_MAP_GAP, cy, LOOP_BTN, ch)
    return loop_action, loop_seed


def looped_group_rect(rects: NavMapRects, axis: str, *, reserve: int = 0) -> Rect:
    cx, cy, _cw, ch = rects.corner
    if axis == "seed":
        row_right = _row_right(rects.corner, rects.seeds)
        return (cx - reserve, cy, (row_right + reserve) - (cx - reserve), ch)
    col_x, _col_y, col_w, _col_h = rects.column_or_corner
    col_lower = _col_lower(rects.corner, rects.actions)
    return (col_x, cy - reserve, col_w, (col_lower + reserve) - (cy - reserve))


def ellipsis_rects(rects: NavMapRects, axis: str) -> tuple[Rect, Rect]:
    cx, cy, _cw, ch = rects.corner
    if axis == "seed":
        return ((cx - NAV_MAP_GAP - ELLIPSIS, cy, ELLIPSIS, ch),
                (_row_right(rects.corner, rects.seeds) + NAV_MAP_GAP, cy, ELLIPSIS, ch))
    col_x, _col_y, col_w, _col_h = rects.column_or_corner
    return ((col_x, cy - NAV_MAP_GAP - ELLIPSIS, col_w, ELLIPSIS),
            (col_x, _col_lower(rects.corner, rects.actions) + NAV_MAP_GAP, col_w, ELLIPSIS))


CTRL_BTN = BUTTON_SIZE_HUD
MINUS_INSET = (PAD, PAD + (TITLE_ROW_H - CTRL_BTN) // 2)
CONTROL_ROW_H = CTRL_BTN + BLOCK_GAP
MODE_LABEL_PAD = BUTTON_PAD_H_TIGHT


def button_row_width(buttons: Sequence[Button], widths: Sequence[int]) -> int:
    rects = button_row_rects(0, 0, buttons, widths)
    if not rects:
        return 0
    (x, _y, w, _h), _button = rects[-1]
    return x + w


def button_row_rects(x: int, y: int, buttons: Sequence[Button],
                     widths: Sequence[int]) -> list[tuple[Rect, Button]]:
    rects: list[tuple[Rect, Button]] = []
    for button, width in zip(buttons, widths, strict=True):
        if rects:
            x += BUTTON_GROUP_GAP if button.group_break else BUTTON_GAP
        rects.append(((x, y, width, CTRL_BTN), button))
        x += width
    return rects


def rows_with_the_speed(model: HudModel) -> list[list[Button]]:
    rows = [list(row) for row in model.rows]
    if model.playback_speed is None:
        return rows
    if not any(button.host_value == PLAYBACK_SPEED for row in rows for button in row):
        rows.append(list(playback_speed_buttons(model.funestra, in_a_column_of_labels=False)))
    rate = {PLAYBACK_SPEED: format_rate(model.playback_speed)}
    return [[reading_its_host_value(button, rate) for button in row] for row in rows]


TITLE_INDENT = TITLE_X - PAD


def favorite_icon_rect(x: int, y: int, line_h: int) -> Rect:
    return (x + (ACTIVE_DOT + 1 - line_h) // 2, y, line_h, line_h)


def name_line(name: str, note: str, room: int, font) -> str:
    whole = SEPARATOR.join(part for part in (name, note) if part)
    if not (name and note) or font.getlength(whole) <= room:
        return whole
    after = f"{SEPARATOR}{note}"
    shortened = fit_text(font, name, room - font.getlength(after))
    return f"{shortened}{after}" if shortened else note


def largest_size_that_fits(largest: int, room: int, width_at: Callable[[int], int]) -> int:
    sizes = [size for size in SIZES if size <= largest]
    return next((size for size in sizes if width_at(size) <= room), sizes[-1])


WRONG_BTN = 14
WRONG_GAP = GAP_SMALL


def label_stack_top(row_y: int, row_h: int, label_h: int, extra: int = 0) -> int:
    return row_y + (row_h - label_h - extra) // 2


def wrong_action_rect(gutter_right: int, label_bottom: int) -> Rect:
    return (gutter_right - WRONG_BTN, label_bottom + WRONG_GAP, WRONG_BTN, WRONG_BTN)


def seed_column_label(index: int) -> str:
    return f"Seed {index + 1}"


def expand_button_rect(loop_seed_rect: Rect | None) -> Rect | None:
    if loop_seed_rect is None:
        return None
    sx, sy, sw, sh = loop_seed_rect
    return (sx + sw + NAV_MAP_GAP, sy, LOOP_BTN, sh)


@dataclass
class HudTargets:
    click: list[tuple[Rect, str]]
    loop: list[tuple[Rect, str]]
    filter: list[tuple[Rect, str]]
    expand: Rect | None
    buttons: list[tuple[Rect, Button]] = field(default_factory=list)
    favorite: Rect | None = None
    wrong_action: Rect | None = None
    words: list[tuple[Rect, str]] = field(default_factory=list)
    tracks: list[DriveTrack] = field(default_factory=list)
    row: RowLayout | None = None
    foot: Rect | None = None


def build_click_targets(rects: NavMapRects, model: HudModel) -> list[tuple[Rect, str]]:
    targets: list[tuple[Rect, str]] = []
    if rects.corner is not None and model.corner is not None and model.corner.path:
        targets.append((rects.corner, model.corner.path))
    targets.extend((rect, cell.path) for rect, cell in zip(rects.seeds, model.seeds, strict=False))
    targets.extend((rect, cell.path)
                   for rect, cell in zip(rects.actions, model.actions, strict=False))
    return targets


def hit_test_targets(targets: list[tuple[Rect, str]], px: int, py: int) -> str:
    for (x, y, w, h), value in targets:
        if x <= px < x + w and y <= py < y + h:
            return value
    return ""


def button_under(targets: HudTargets, px: int, py: int) -> Button | None:
    for rect, button in targets.buttons:
        if contains(rect, px, py):
            return button
    return None


def filter_button_rects(
    corner_rect: Rect | None,
    action_rects: list[Rect],
    gutter_x: int,
    current_action: str,
    action_labels: list[str] | tuple[str, ...],
) -> list[tuple[Rect, str]]:
    rects: list[tuple[Rect, str]] = []
    if corner_rect is not None and current_action:
        _cx, cy, _cw, ch = corner_rect
        rects.append(((gutter_x, cy, FILTER_BTN, ch), current_action))
    for (_ax, ay, _aw, ah), name in zip(action_rects, action_labels, strict=False):
        if name:
            rects.append(((gutter_x, ay, FILTER_BTN, ah), name))
    return rects


def _acts(text: str) -> list[str]:
    return [act for act in (normalized_text(part) for part in split_acts(text)) if act]


def act_is_filtered(act: str, filter_query: str) -> bool:
    return any(filter_keeps(act, query) for query in _acts(filter_query))


def label_is_filtered(label: str, filter_query: str) -> bool:
    acts, query = _acts(label), _acts(filter_query)
    return bool(acts) and bool(query) and all(
        any(filter_keeps(act, part) for act in acts) for part in query)


def with_act_toggled(filter_query: str, act: str) -> str:
    query, toggled = _acts(filter_query), normalized_text(act)
    kept = [part for part in query if part != toggled]
    return labels_text(kept if kept != query else [*query, toggled])


LOOP_ICON = "loop"
EXPAND_ICON = "expand_horizontal"
FAVORITE_ICON = "star"
WRONG_ACTION_ICON = "cross"


def _titlecase_word(word: str) -> str:
    return word if word.isupper() else word[:1].upper() + word[1:].lower()


def split_acts(name: str) -> list[str]:
    return [" ".join(words) for words in (part.split() for part in str(name or "").split(",")) if words]


def act_named(act: str) -> str:
    words = act.split()
    while len(words) > 1 and words[-1].isdigit():
        words.pop()
    return " ".join(words)


def action_label_blocks(name: str) -> list[list[str]]:
    blocks = [[_titlecase_word(word) for word in act.split()] for act in split_acts(name)]
    return blocks or [["(unknown)"]]


def _cell(raw: object) -> HudCell | None:
    if not isinstance(raw, dict):
        return None
    return HudCell(
        path=str(raw.get("path", "")),
        thumb=str(raw.get("thumb", "") or ""),
        label=str(raw.get("label", "") or ""),
    )


def _cell_raw(cell: HudCell) -> dict[str, str]:
    raw = {"path": cell.path, "thumb": cell.thumb}
    if cell.label:
        raw["label"] = cell.label
    return raw


def hud_text(model: HudModel) -> str:
    return json.dumps({
        "funestra": model.funestra,
        "hud_corner": model.hud_corner,
        "hud_edge": model.hud_edge,
        "hud_minimized": model.hud_minimized,
        "locked": model.locked,
        "title": model.title,
        "active": model.active,
        "is_favorite": model.is_favorite,
        "item_note": model.item_note,
        "filter_query": model.filter_query,
        "seed_count": model.seed_count,
        "action_count": model.action_count,
        "active_loop": model.active_loop,
        "current_action": model.current_action,
        "playing": list(model.playing),
        "corner": None if model.corner is None else _cell_raw(model.corner),
        "seeds": [_cell_raw(cell) for cell in model.seeds],
        "actions": [_cell_raw(cell) for cell in model.actions],
        "rows": rows_raw(model.rows),
        "osr2": model.osr2,
        "osr2_control": model.osr2_control,
        "paused": model.paused,
        "osr2_rows": rows_raw(model.osr2_rows),
        "osr2_controls": buttons_raw(model.osr2_controls),
        "max_intensity": model.max_intensity,
        "foot": model.foot.raw() if isinstance(model.foot, PaintedFoot) else None,
    })


def parse_hud(text: str) -> HudModel | None:
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict) or "funestra" not in raw:
        return None
    playing = raw.get("playing") or ["corner", 0]
    seeds = [_cell(item) for item in raw.get("seeds", []) or []]
    actions = [_cell(item) for item in raw.get("actions", []) or []]
    return HudModel(
        funestra=str(raw["funestra"]),
        hud_corner=read_mode(HudCorner, raw.get("hud_corner"), HudCorner.UPPER_LEFT),
        hud_edge=read_mode(HudEdge, raw.get("hud_edge"), HudEdge.LOWER),
        hud_minimized=bool(raw.get("hud_minimized", False)),
        locked=bool(raw.get("locked", False)),
        title=str(raw.get("title", "") or ""),
        active=bool(raw.get("active", False)),
        is_favorite=bool(raw.get("is_favorite", False)),
        item_note=str(raw.get("item_note", "") or ""),
        corner=_cell(raw.get("corner")),
        seeds=tuple(cell for cell in seeds if cell is not None),
        actions=tuple(cell for cell in actions if cell is not None),
        current_action=str(raw.get("current_action", "") or ""),
        filter_query=str(raw.get("filter_query", "") or ""),
        active_loop=str(raw.get("active_loop", "") or ""),
        seed_count=int(raw.get("seed_count", 0) or 0),
        action_count=int(raw.get("action_count", 0) or 0),
        playing=(str(playing[0]), int(playing[1])),
        rows=rows_from_raw(raw.get("rows")),
        osr2=str(raw.get("osr2", "") or ""),
        osr2_control=str(raw.get("osr2_control", "") or ""),
        paused=bool(raw.get("paused", False)),
        osr2_rows=rows_from_raw(raw.get("osr2_rows")),
        osr2_controls=buttons_from_raw(raw.get("osr2_controls")),
        max_intensity=max_intensity_from_raw(raw.get("max_intensity")),
        foot=PaintedFoot.from_raw(raw.get("foot")),
    )
