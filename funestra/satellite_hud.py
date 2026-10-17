"""The satellite lock HUD: the published panel's geometry and hit-testing.

Shared through funestra because two apps draw this exact HUD: each of Fun
Time's Satellite Funestras composites it into its video, and a hosted
Origenerator's region shows wear it as a widget — one HUD, one codebase, so
the two surfaces cannot drift apart.

fun_time owns each Funestra's *model* — which clips sit on the map, whether the
satellite is locked, which axis is looping — because only fun_time has the
library metadata.  It serializes that to a small JSON file per Funestra; this module
parses it and lays it out.  (A hosted Origenerator builds its shows' models
directly — the same dataclass, no file in between.)  :mod:`funestra.satellite_hud_paint` turns the layout into a bitmap mpv
composites into the video, so the HUD has no window and therefore no z-order at
all — it *is* the frame.

Kept free of Pillow so the geometry and hit-testing are unit-testable without a
font: the paint module measures text and hands the width back in.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from shared_ui.icon_geometry import tooltip_for
from shared_ui.spacing import (
    BUTTON_GAP,
    BUTTON_GROUP_GAP,
    BUTTON_SIZE_HUD,
)

from .console import VALUE_W, max_intensity_from_raw
from .drive_readout import DriveHud, DriveTrack, TrackGrip
from .geometry import Rect, contains
from .hud_button import Button, buttons_from_raw, buttons_raw, rows_from_raw, rows_raw
from .hud_osr2 import HEIGHT as OSR2_H
from .hud_placement import HudCorner, HudEdge
from .hud_sections import blocks_height, stack
from .hud_status import SEPARATOR
from .modes import read_mode
from .renamed import answers_to_old_names

if TYPE_CHECKING:
    from PIL import Image

    from .hud_row import RowLayout

__all__ = [
    "BLOCK_GAP",
    "CTRL_BTN",
    "MAP_THUMB_H",
    "MARGIN",
    "MODE_LABEL_PAD",
    "HudCell",
    "HudModel",
    "button_row_rects",
    "hud_text",
    "label_is_filtered",
    "parse_hud",
]

# --- layout constants (px) ---------------------------------------------------
# Inset of the HUD from the Funestra's top-left corner.
MARGIN = 12

PAD = 10
BLOCK_GAP = 6
MAP_THUMB_H = 54
MAP_GAP = 5
ROW_GAP = 12        # vertical gap between action rows — roomier than the seed gap
ACT_GAP = 6         # gap between two acts stacked in one row label
COL_LABEL_H = 13    # header strip above the map for the "Seed N" column labels
COL_LABEL_GAP = 4   # breathing room between a column label and its thumbnail
ROW_LABEL_GUTTER = 100
LOOP_BTN = 18       # loop-button thickness: below the action column, right of the row
FILTER_BTN = 18     # act-filter button: at the head of each row, in the gutter

MAP_RIGHT_RESERVE = 2 * (LOOP_BTN + MAP_GAP)
MAP_LOWER_RESERVE = LOOP_BTN + MAP_GAP

MAP_CELLS = 3
WIDEST_FULL_HEIGHT_SHAPE = {"portrait": (4, 5), "landscape": (16, 9)}

STATUS_BAND_H = 24        # the band the line sits in — one line deep, always
STATUS_DOT = 10           # the active-Funestra dot at the head of the band
STATUS_TEXT_X = PAD + STATUS_DOT + 8  # where the status text starts, clear of it
STATUS_BASELINE = 11      # the status line's baseline, down from the band's top
# The file on screen, muted under the status line — the same second line the Main
# Funestra's console carries, so the two panels answer "what am I playing?" in the
# same corner and the same shape.  Its own height comes from the paint module,
# which has the face; this is only the gap between the two lines.
SUBTITLE_GAP = 2

Cell = tuple[str, int]            # ("corner", 0) | ("seed", i) | ("action", i)


@dataclass(frozen=True)
class HudCell:
    """One clip drawn on the map: its path, its cached thumbnail, its row label.

    ``thumb`` is "" while fun_time's background prewarm has not produced the
    frame yet — the map draws a placeholder there rather than waiting.
    """

    path: str
    thumb: str = ""
    label: str = ""


class HudSection(Protocol):
    """A block the source paints into the panel itself, at its very foot."""

    def size(self) -> tuple[int, int]: ...

    def paint(self, image: Image.Image, x: int, y: int, width: int,
              pointer: tuple[int, int] | None) -> list[tuple[Rect, Button]]: ...


@answers_to_old_names({"player": "funestra"})
@dataclass(frozen=True)
class HudModel:
    """One satellite's HUD contents, exactly as fun_time published them."""

    # Which Funestra this is: "portrait" or "landscape".
    funestra: str
    hud_corner: HudCorner = HudCorner.UPPER_LEFT
    hud_edge: HudEdge = HudEdge.LOWER
    hud_minimized: bool = False
    locked: bool = False
    lock_label: str = ""
    # Whether a bare command naming no Funestra lands here — the Funestra addressed
    # most recently.  Drawn as the dot beside the status line, and the only thing on
    # any HUD that says where those words are going.
    active: bool = False

    # Whether the clip on screen is one of the favorites — marked in the control
    # band, beside the buttons that act on that clip.
    is_favorite: bool = False
    item_note: str = ""
    corner: HudCell | None = None
    seeds: tuple[HudCell, ...] = ()
    actions: tuple[HudCell, ...] = ()
    current_action: str = ""
    # The act(s) this Funestra is filtered to, if any: the map lights every row the
    # filter keeps and, within a row, the acts the filter actually names.  Pressing
    # a row's button moves the filter onto that row, or lifts it when the filter is
    # already exactly that row.
    filter_query: str = ""
    # The words the library writes in front of an act to say how the clip was
    # shot, as it writes them.  The source names them because they are library
    # vocabulary; a row sets a leading one apart as an act of its own.
    camera_words: tuple[str, ...] = ()
    active_loop: str = ""
    # How many clips each axis stands for, the clip on screen included.  The map
    # draws only MAP_CELLS of them, so it prints these in its top-left corner —
    # the only place the real size of each axis can be read.
    seed_count: int = 0
    action_count: int = 0
    # The map cell actually on screen — the corner normally, or another cell
    # while a loop plays a non-anchor clip of the group.  Drawn bright; the
    # rest dim.
    playing: Cell = ("corner", 0)
    # The rate this Funestra plays at, folded into its own HUD so the painter draws
    # the speed row under the bands; None for a surface with no rate to show.
    playback_speed: float | None = None
    # The buttons the source declares for this Funestra, in the bands the panel
    # draws them in: what each posts, its face, its tooltip and its state.  The
    # panel draws nothing it was not handed.
    rows: tuple[tuple[Button, ...], ...] = ()

    # --- the device, for a panel whose Funestra has the OSR2 ----------------
    # Which driver has the OSR2, and the controls that aim it: the same line the
    # main console draws (:mod:`funestra.hud_osr2`), grown here because a host
    # can be both the thing browsing a set AND the thing driving the device.
    # Origenerator's shows are: they floated this HUD for the set and the whole
    # console underneath it for the device, which is two status lines that
    # disagree and two copies of every transport button.
    osr2: str = ""
    # The rows that AIM the device -- the hands-free switches, the waveform, the
    # four control states.  They sit in the device's own block rather than among
    # the rows above, because they are the OSR2's and the reader looks for them
    # beside the line naming who has it: on the main console those rows happen to
    # be the last ones before that line, so nothing showed, and on a panel with a
    # map between them they came out as one group of OSR2 controls split in two.
    osr2_rows: tuple[tuple[Button, ...], ...] = ()
    # And what the host is doing to the device, which is a different question:
    # driving, parked or retracted, or empty from a host with no such switch.
    # The panel resolves the two into one word exactly as the console does
    # (:func:`funestra.hud_osr2.state_for`).
    osr2_control: str = ""
    osr2_controls: tuple[Button, ...] = ()
    max_intensity: int | None = None
    paused: bool = False
    # The motion being sent, drawn under that line — the main console's readout
    # (:mod:`funestra.drive_readout`), hosted here rather than on a panel of
    # its own.  None wherever there is nothing to report.
    drive: DriveHud | None = None
    drive_composed: bool = False

    foot: HudSection | None = None


# --- map geometry ------------------------------------------------------------

ELLIPSIS = 12
ELLIPSIS_ROOM = ELLIPSIS + 2 * MAP_GAP
MAP_COLUMN_H = MAP_CELLS * MAP_THUMB_H + (MAP_CELLS - 1) * ROW_GAP
MAP_H = (COL_LABEL_H + COL_LABEL_GAP + ELLIPSIS_ROOM + MAP_COLUMN_H
         + ELLIPSIS_ROOM + MAP_LOWER_RESERVE)


def slot_width(funestra: str) -> int:
    across, down = WIDEST_FULL_HEIGHT_SHAPE.get(funestra, WIDEST_FULL_HEIGHT_SHAPE["portrait"])
    return round(MAP_THUMB_H * across / down)


def map_row_width(funestra: str) -> int:
    return MAP_CELLS * slot_width(funestra) + (MAP_CELLS - 1) * MAP_GAP


def map_block_width(funestra: str) -> int:
    return (ROW_LABEL_GUTTER + ELLIPSIS_ROOM + map_row_width(funestra) + ELLIPSIS_ROOM
            + MAP_RIGHT_RESERVE)


def panel_width(funestra: str, name_width: int = 0, *, content_width: int = 0) -> int:
    return max(2 * PAD + map_block_width(funestra),
               STATUS_TEXT_X + name_width + PAD, content_width)


def device_height(osr2: str, drive: DriveHud | None, drive_h: int,
                  osr2_rows: int = 0) -> int:
    return blocks_height([CTRL_BTN] * osr2_rows + [OSR2_H if osr2 else 0,
                                                    drive_h if drive is not None else 0],
                         BLOCK_GAP)


@dataclass(frozen=True)
class PanelLayout:
    bands: int
    speed: int
    row: int
    device: int
    foot: int
    map: int
    height: int
    dividers: tuple[int, ...]


def panel_layout(*, status_h: int, bands: int = 0, speed: bool = False,
                 row_h: int = 0, device_h: int = 0, foot_h: int = 0) -> PanelLayout:
    stacked = stack(PAD, [status_h, blocks_height([CTRL_BTN] * (bands + speed), BLOCK_GAP),
                          row_h, device_h, foot_h, MAP_H])
    _status, bands_top, row_top, device_top, foot_top, map_top = stacked.tops
    return PanelLayout(bands_top, bands_top + bands * CTRL_BAND_H, row_top, device_top,
                       foot_top, map_top, stacked.end + PAD, stacked.dividers)


@dataclass(frozen=True)
class MapWindow:
    """Which run of an axis is drawn, and whether it runs on past either end."""

    start: int
    count: int
    more_before: bool
    more_after: bool


def map_window(total: int, playing: int, limit: int = MAP_CELLS) -> MapWindow:
    """The run of at most *limit* cells to draw from an axis of *total*, keeping
    *playing* near its middle.

    The run always holds *playing* and grows outward from it, alternating sides and
    taking the right first: an axis whose head is on screen therefore fills away
    from the corner, while one whose playing cell has moved along keeps that cell in
    the middle — which is what stops the lit cell walking off the end of the map and
    leaving nothing highlighted at all.
    """
    if total <= 0 or limit <= 0:
        return MapWindow(0, 0, False, False)
    playing = max(0, min(playing, total - 1))
    start, end = playing, playing + 1
    while end - start < min(limit, total):
        # Take from whichever side has been given fewer cells so far — that is what
        # centers *playing* — with the right winning ties so a fresh loop reads left
        # to right.  A side that has run out defers to the other.
        if end < total and (start == 0 or end - playing - 1 <= playing - start):
            end += 1
        else:
            start -= 1
    return MapWindow(start, end - start, start > 0, end < total)


def column_anchor_rect(playing: Cell, corner_rect: Rect, seed_rects: list[Rect]) -> Rect:
    """The seed-row cell the action column hangs under: the playing cell while it
    is out along the row, the corner otherwise.

    fun_time builds the column as the playing seed's other acts, so it has to
    hang under the cell it belongs to — under the corner it would read as the
    corner seed's acts, which mid-loop it no longer is.
    """
    bucket, index = playing
    if bucket == "seed" and 0 <= index < len(seed_rects):
        return seed_rects[index]
    return corner_rect


def slot_rects(
    *,
    map_x: int,
    map_y: int,
    slot_w: int,
    seeds: int,
    actions: int,
    playing: Cell = ("corner", 0),
) -> tuple[Rect, list[Rect], list[Rect]]:
    corner = (map_x, map_y, slot_w, MAP_THUMB_H)
    seed_rects = [(map_x + step * (slot_w + MAP_GAP), map_y, slot_w, MAP_THUMB_H)
                  for step in range(1, min(seeds + 1, MAP_CELLS))]
    column_x = column_anchor_rect(playing, corner, seed_rects)[0]
    action_rects = [(column_x, map_y + step * (MAP_THUMB_H + ROW_GAP), slot_w, MAP_THUMB_H)
                    for step in range(1, min(actions + 1, MAP_CELLS))]
    return corner, seed_rects, action_rects


def picture_rect(slot: Rect, size: tuple[int, int]) -> Rect:
    x, y, w, h = slot
    width, height = size
    return (x + (w - width) // 2, y + (h - height) // 2, width, height)


def playing_rect(
    playing: Cell, corner_rect: Rect, seed_rects: list[Rect], action_rects: list[Rect]
) -> Rect | None:
    """The rect of the cell holding the clip on screen, or None when that cell was
    not drawn (its axis's window closed before reaching it).

    Usually the corner — but a lock taken inside a running loop holds a clip the
    map is not anchored on, and the ring saying "this is the clip being held" has to
    land on the cell that clip is actually drawn in, not on the loop's anchor.
    """
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
    loop_action = (col_x, column_end + reserve + MAP_GAP, col_w, LOOP_BTN)
    loop_seed = (row_end + reserve + MAP_GAP, cy, LOOP_BTN, ch)
    return loop_action, loop_seed


def looped_group_rect(
    corner_rect: Rect, seed_rects: list[Rect], action_rects: list[Rect], axis: str,
    *, reserve: int = 0, column_rect: Rect | None = None,
) -> Rect:
    """The rectangle drawn around the clips an *axis* loop is cycling — the row for
    "seed", the column for "action" — grown by *reserve* at each end so the loop's
    "…" marks fall inside it, saying those clips are in the loop too.  The column's
    rect stands on *column_rect*, the row cell the column hangs under
    (:func:`column_anchor_rect`); it defaults to the corner."""
    cx, cy, cw, ch = corner_rect
    if axis == "seed":
        row_right = _row_right(corner_rect, seed_rects)
        return (cx - reserve, cy, (row_right + reserve) - (cx - reserve), ch)
    col_x, _col_y, col_w, _col_h = corner_rect if column_rect is None else column_rect
    col_lower = _col_lower(corner_rect, action_rects)
    return (col_x, cy - reserve, col_w, (col_lower + reserve) - (cy - reserve))


def ellipsis_rects(
    corner_rect: Rect, seed_rects: list[Rect], action_rects: list[Rect], axis: str,
    *, column_rect: Rect | None = None,
) -> tuple[Rect, Rect]:
    """The two slots an axis keeps for the "…" marks that say it runs on past what is
    drawn: flanking the seed row left and right, or the action column above and
    below.  Each sits a gap in from the loop rectangle, so a mark never reads as part
    of that border.  The column's slots stand on *column_rect*, the row cell the
    column hangs under (:func:`column_anchor_rect`); it defaults to the corner."""
    cx, cy, cw, ch = corner_rect
    if axis == "seed":
        return ((cx - MAP_GAP - ELLIPSIS, cy, ELLIPSIS, ch),
                (_row_right(corner_rect, seed_rects) + MAP_GAP, cy, ELLIPSIS, ch))
    col_x, _col_y, col_w, _col_h = corner_rect if column_rect is None else column_rect
    return ((col_x, cy - MAP_GAP - ELLIPSIS, col_w, ELLIPSIS),
            (col_x, _col_lower(corner_rect, action_rects) + MAP_GAP, col_w, ELLIPSIS))


# --- the Funestra's own buttons ------------------------------------------------
# What a source declares for this Funestra, drawn in bands between the status line
# and the map: each row of ``HudModel.rows`` is one band, a square per button, a
# word button as wide as its word (the painter measures it), and the wider gap
# before a button that starts a group -- the way the console's rows break.
CTRL_BTN = BUTTON_SIZE_HUD
MINUS_INSET = (PAD, PAD + (STATUS_BAND_H - CTRL_BTN) // 2)
CTRL_BAND_H = CTRL_BTN + BLOCK_GAP
# Inside a word button, the room either side of its word.
MODE_LABEL_PAD = 6


def button_row_width(buttons: Sequence[Button], widths: Sequence[int]) -> int:
    rects = button_row_rects(0, 0, buttons, widths)
    if not rects:
        return 0
    (x, _y, w, _h), _button = rects[-1]
    return x + w


def button_row_rects(x: int, y: int, buttons: Sequence[Button],
                     widths: Sequence[int]) -> list[tuple[Rect, Button]]:
    """Each button's ``(rect, button)`` along a row running right from ``(x, y)``,
    *widths* being each one's width as the painter measured it -- this module
    is font-free."""
    rects: list[tuple[Rect, Button]] = []
    for button, width in zip(buttons, widths):
        if rects:
            x += BUTTON_GROUP_GAP if button.group_break else BUTTON_GAP
        rects.append(((x, y, width, CTRL_BTN), button))
        x += width
    return rects


# The speed row's two buttons, drawn by the Funestra rather than declared by the
# source, since only the drawing Funestra knows the rate that sits between them.
_SPEED_BUTTONS = (
    ("speed_down", "−", "Play the video slower"),
    ("speed_up", "+", "Play the video faster"),
)


def speed_row_width(label_width: int) -> int:
    return label_width + 2 * CTRL_BTN + 2 * MAP_GAP + VALUE_W


def speed_row(funestra: str, x: int, y: int, *,
              label_width: int) -> tuple[list[tuple[Rect, Button]], Rect]:
    """*funestra*'s slower and faster buttons after a name *label_width* wide, and
    the cell between them the rate is written in."""
    down_x = x + label_width
    rate_x = down_x + CTRL_BTN + MAP_GAP
    up_x = rate_x + VALUE_W + MAP_GAP
    buttons = [
        ((button_x, y, CTRL_BTN, CTRL_BTN), Button(f"{funestra}_{name}", face, tooltip))
        for button_x, (name, face, tooltip) in zip((down_x, up_x), _SPEED_BUTTONS)
    ]
    return buttons, (rate_x, y, VALUE_W, CTRL_BTN)


STATUS_INDENT = STATUS_TEXT_X - PAD


def favorite_mark_rect(x: int, y: int, line_h: int) -> Rect:
    """The favorite mark: at the head of the file-name line, under the dot.

    A readout, not a button, so it belongs where the panel keeps readouts and
    not in the control band: the one column already used for "what is true of
    this Funestra" — the active dot is directly above it — and immediately left of
    the name of the very clip it is answering about.

    *y* is the file-name line's top and *line_h* its height, and the mark is as
    tall as that line: a mark beside words wants to be the size of the words,
    and anything smaller reads as a speck rather than as a state.
    """
    return (x + (STATUS_DOT + 1 - line_h) // 2, y, line_h, line_h)


SHORTENED_MARK = "…"


def name_line(name: str, note: str, room: int, width_of: Callable[[str], int]) -> str:
    whole = SEPARATOR.join(part for part in (name, note) if part)
    if not (name and note) or width_of(whole) <= room:
        return whole
    for kept in range(len(name) - 1, -1, -1):
        shortened = f"{name[:kept].rstrip()}{SHORTENED_MARK}{SEPARATOR}{note}"
        if width_of(shortened) <= room:
            return shortened
    return note


def largest_size_that_fits(largest: int, room: int, width_at: Callable[[int], int]) -> int:
    return next((size for size in range(largest, 1, -1) if width_at(size) <= room), 1)


# The strike under the current clip's act: this act is wrong, ask about it again.
# Smaller than a control button and in the gutter rather than on the band,
# because it is about the words above it rather than about the Funestra — the one
# place on the panel where that act is named is the only place the strike can
# say which act it means.
WRONG_BTN = 14
WRONG_GAP = 3   # between the act's last line and the strike under it


def label_stack_top(row_y: int, row_h: int, label_h: int, extra: int = 0) -> int:
    """Where a gutter row's label starts, centered in its row with *extra* room
    kept under it.

    The corner row keeps that room for the strike; every other row asks for none
    and centers the words alone, exactly as before.
    """
    return row_y + (row_h - label_h - extra) // 2


def wrong_action_rect(gutter_right: int, label_bottom: int) -> Rect:
    """The strike, under the act it strikes and right-aligned with it."""
    return (gutter_right - WRONG_BTN, label_bottom + WRONG_GAP, WRONG_BTN, WRONG_BTN)


def seed_column_label(index: int) -> str:
    """The header over a seed column: its place in the family, counting from one.

    A window can open partway along the family, so the headers carry the real
    ordinals — "Seed 7" over the seventh seed — rather than restarting at one and
    hiding how far along the row has got.
    """
    return f"Seed {index + 1}"


def expand_button_rect(loop_seed_rect: Rect | None) -> Rect | None:
    if loop_seed_rect is None:
        return None
    sx, sy, sw, sh = loop_seed_rect
    return (sx + sw + MAP_GAP, sy, LOOP_BTN, sh)


# --- hit-testing -------------------------------------------------------------


@dataclass
class HudTargets:
    """What the last render put where — the rects a press is tested against."""

    click: list[tuple[Rect, str]]
    loop: list[tuple[Rect, str]]
    filter: list[tuple[Rect, str]]
    expand: Rect | None
    # The declared buttons, each with what it posts and what it is called.
    buttons: list[tuple[Rect, Button]] = field(default_factory=list)
    # The favorite mark is a readout, so it is here only to carry its tooltip.
    favorite: Rect | None = None
    # The strike under the current clip's act, or None where no act is named.
    wrong_action: Rect | None = None
    # The drive readout's three bands, on a host that draws one: pressed to set
    # a level outright, and held while the pointer drags along them.
    tracks: list[DriveTrack] = field(default_factory=list)
    # Where the item's own row landed and how it is laid out, for a press to
    # be placed on it (:class:`funestra.hud_row.RowPress`).
    row: RowLayout | None = None
    # Where the block the source paints at the foot landed: its presses and
    # the wheel go back to the source in that block's own pixels.
    foot: Rect | None = None


def build_click_targets(
    corner_rect: Rect | None,
    seed_rects: list[Rect],
    action_rects: list[Rect],
    corner: HudCell | None,
    seeds: list[HudCell] | tuple[HudCell, ...],
    actions: list[HudCell] | tuple[HudCell, ...],
) -> list[tuple[Rect, str]]:
    """(rect, video_path) for every clickable thumbnail: the corner is the current
    clip, then each drawn seed and action zipped to its path."""
    targets: list[tuple[Rect, str]] = []
    if corner_rect is not None and corner is not None and corner.path:
        targets.append((corner_rect, corner.path))
    targets.extend((rect, cell.path) for rect, cell in zip(seed_rects, seeds))
    targets.extend((rect, cell.path) for rect, cell in zip(action_rects, actions))
    return targets


def hit_test_targets(targets: list[tuple[Rect, str]], px: int, py: int) -> str:
    """The value whose rect contains ``(px, py)``, or "" if none does — used for
    the thumbnail (path), loop-button (axis) and action-label (action) targets."""
    for (x, y, w, h), value in targets:
        if x <= px < x + w and y <= py < y + h:
            return value
    return ""


def button_at(buttons: list[tuple[Rect, Button]], px: int, py: int) -> Button | None:
    """The declared button under ``(px, py)``, or None off all of them."""
    for rect, button in buttons:
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
    """(rect, action_name) for the filter button at the head of each map row — the
    corner's row is the current action, the rows below are the sibling actions.
    Pressing one filters the satellite to that action.

    One button per row, at the gutter's left edge and as tall as its row: the same
    shape the seed-loop button has beside the seed row, because it stands to its row
    the same way.  The button is the whole affordance; the name beside it is only a
    label.

    A row with no action name gets no button: there is nothing to filter to.
    """
    rects: list[tuple[Rect, str]] = []
    if corner_rect is not None and current_action:
        _cx, cy, _cw, ch = corner_rect
        rects.append(((gutter_x, cy, FILTER_BTN, ch), current_action))
    for (_ax, ay, _aw, ah), name in zip(action_rects, action_labels):
        if name:
            rects.append(((gutter_x, ay, FILTER_BTN, ah), name))
    return rects


def _norm_act(text: str) -> str:
    """An act label or a filter query flattened for comparison: lower-cased with
    runs of whitespace collapsed, the way fun_time normalizes both sides of its own
    match (``media_metadata._norm_text``)."""
    return " ".join(str(text or "").split()).lower()


def _acts(text: str, camera_words: Sequence[str]) -> list[str]:
    """*text* as its separate acts, normalized — for a row label or for a filter
    query, which is set from one and so is shaped like one."""
    return [act for act in (_norm_act(part) for part in split_acts(text, camera_words)) if act]


def act_is_filtered(act: str, filter_query: str, camera_words: Sequence[str]) -> bool:
    """Whether *act* is one of the acts the filter names — what decides which of a
    row's acts is drawn lit.

    A filter for one act lights that act alone: on a "Side / Gamma" row a "gamma"
    filter whitens "Gamma" and leaves "Side" gray, which is what says *why* the clip
    is here.  A filter set from a clip carrying two acts names both, so both light.
    """
    return any(query in _norm_act(act) for query in _acts(filter_query, camera_words))


def label_is_filtered(label: str, filter_query: str, camera_words: Sequence[str]) -> bool:
    """Whether the filter keeps a row labeled *label* — its button's lit state, and
    what the press reads to decide between narrowing and lifting.

    fun_time keeps a clip when the query appears as a *contiguous substring* of its
    recorded act (``media_metadata.matches_query``), so every act the query names has
    to be one of the row's: filtered to "gamma", both a "Side Gamma" row and a "Gamma,
    Theta" row are clips it keeps, while a plain "Alpha" row is *not* kept by an
    "alpha, beta" filter and must not read as though it were.
    Within a row an act still matches on a substring ("gamma" catching "theta
    gamma") — the same rule fun_time uses, one act down.

    One rule for the whole row, used by the map to light its button and by the press
    to know whether it is already exactly this row, so what looks on and what turns
    off cannot disagree.
    """
    acts, query = _acts(label, camera_words), _acts(filter_query, camera_words)
    return bool(acts) and bool(query) and all(
        any(part in act for act in acts) for part in query)


LOOP_TOOLTIPS = {"action": "Loop this action column", "seed": "Loop this seed row"}
FILTER_TOOLTIP = "Filter to this action"
EXPAND_TOOLTIP = "More seeds — widen the net"
FAVORITE_TOOLTIP = "In the favorites"
WRONG_ACTION_TOOLTIP = "Wrong action — strike it, and it gets asked about again"
LOOP_MARK = "loop"
EXPAND_MARK = "expand_horizontal"
FAVORITE_MARK = "star"
WRONG_ACTION_MARK = "cross"


def _in(rect: Rect | None, px: int, py: int) -> bool:
    return rect is not None and contains(rect, px, py)


def button_tooltip(targets: HudTargets, px: int, py: int) -> str:
    """What the HUD control under ``(px, py)`` is, or "" over none of them.

    Every glyph on this panel is cryptic on purpose — it is read over moving video
    — so each one names itself on hover: a declared button by the tooltip its
    source gave it, the map's own chrome by the words here.
    """
    button = button_at(targets.buttons, px, py)
    if button is not None:
        return button.tooltip_on_hover
    loop = hit_test_targets(targets.loop, px, py)
    if loop:
        return tooltip_for(LOOP_MARK, LOOP_TOOLTIPS.get(loop, ""))
    if _in(targets.wrong_action, px, py):
        return tooltip_for(WRONG_ACTION_MARK, WRONG_ACTION_TOOLTIP)
    if hit_test_targets(targets.filter, px, py):
        return FILTER_TOOLTIP
    if _in(targets.expand, px, py):
        return tooltip_for(EXPAND_MARK, EXPAND_TOOLTIP)
    if _in(targets.favorite, px, py):
        return tooltip_for(FAVORITE_MARK, FAVORITE_TOOLTIP)
    return ""


# --- clicks ------------------------------------------------------------------

# Windows' default double-click time.  A click that turns out to be the first
# half of a double-click must not also post a switch, so a lone click waits this
# long before it is posted.  Erring short is safe: a slow double-click simply
# switches to the clip it then locks.
DOUBLE_CLICK_S = 0.5


class HudClicks:
    """Turns presses on the HUD into the fun_time commands they stand for.

    A press on a thumbnail is ambiguous until the double-click window passes —
    single switches to the clip, double locks it — so :meth:`press` defers it and
    :meth:`due` posts it once no second click has arrived.  Every other press
    (loop buttons, expand, filter buttons) is unambiguous and posts immediately.

    A press inside one of the drive readout's bands, on a host that draws one,
    takes hold of it as well as posting: :meth:`drag_to` then goes on setting
    that level as the pointer moves, so a bar can be dragged and not only
    clicked.
    """

    def __init__(self, funestra: str, *, double_click_s: float = DOUBLE_CLICK_S) -> None:
        self._funestra = funestra
        self._double_click_s = double_click_s
        self._pending_path = ""
        self._pending_at = 0.0
        self._grip = TrackGrip()
        # Which axis is looping, and which act the Funestra is filtered to.  Both are
        # mirrored from the published panel on every refresh, and set optimistically
        # on a click so the control lights up before fun_time's answer comes back.
        self.active_loop = ""
        self.active_filter = ""

    @property
    def holding(self) -> bool:
        """Whether a press took hold of a readout band and has not let go."""
        return self._grip.holding

    def drag_to(self, px: int, py: int) -> str:
        """The command the pointer posts while a band is held; "" while none is."""
        return self._grip.drag_to(px, py)

    def release(self) -> None:
        """Let go of whichever band a press took hold of."""
        self._grip.release()

    def press(self, targets: HudTargets, px: int, py: int, *, now: float) -> str:
        """The command for a press at ``(px, py)``, or "" when it posts nothing
        yet (a first thumbnail click, or empty space).

        Anything already held is let go first, so a press on an ordinary button
        never leaves a band still latched.
        """
        self.release()
        button = button_at(targets.buttons, px, py)
        if button is not None and button.command:
            # Verbatim: the source said what a press posts.  A dimmed one is at
            # the end of its range or has nothing to act on, and posts nothing.
            return "" if button.dim else button.command
        # A target with nothing to post is a readout band, there only to name
        # itself on hover; the press belongs to the band under it.
        grabbed = self._grip.grab(targets.tracks, px, py)
        if grabbed:
            return grabbed
        loop = hit_test_targets(targets.loop, px, py)
        if loop:
            return self._toggle_loop(loop)
        if _in(targets.expand, px, py):
            return f"{self._funestra}_more_seeds"
        # Tested before the row's filter button: the strike sits inside the
        # corner row's own band, and the filter button spans that whole band.
        if _in(targets.wrong_action, px, py):
            return f"{self._funestra}_wrong_action"
        action = hit_test_targets(targets.filter, px, py)
        if action:
            # Narrow before you lift: a press on a row the filter only partly keeps
            # ("Side Gamma" under "gamma") moves the filter onto that whole row, and
            # only a press on the row the filter already *is* turns it off, so a
            # broad filter can be tightened from the map.
            query = _norm_act(action)
            if query == _norm_act(self.active_filter):
                self.active_filter = ""
                return f"{self._funestra}_no_filter"
            self.active_filter = query
            return f"filter_{self._funestra}_{query.replace(' ', '_')}"
        path = hit_test_targets(targets.click, px, py)
        if not path:
            return ""
        if path == self._pending_path and now - self._pending_at <= self._double_click_s:
            self._pending_path = ""
            return f"{self._funestra}_lock_video|{path}"
        self._pending_path = path
        self._pending_at = now
        return ""

    def due(self, *, now: float) -> str:
        """The deferred single-click switch, once its double-click window lapsed."""
        if not self._pending_path or now - self._pending_at <= self._double_click_s:
            return ""
        path, self._pending_path = self._pending_path, ""
        return f"{self._funestra}_play_video|{path}"

    def _toggle_loop(self, kind: str) -> str:
        """Turn *kind*'s loop on, or — if it is already on — off.  Turning one on
        turns the other off: the two loops cannot coexist, matching the command
        the dispatch loop runs."""
        if self.active_loop == kind:
            self.active_loop = ""
            return f"{self._funestra}_no_loop"
        self.active_loop = kind
        return f"{self._funestra}_{kind}_loop"


# --- action labels -----------------------------------------------------------

def _titlecase_word(word: str) -> str:
    return word[:1].upper() + word[1:].lower()


def split_acts(name: str, camera_words: Sequence[str]) -> list[str]:
    """*name* as the separate acts it carries, in order and unnormalized.

    Commas separate acts ("Alpha, Theta Motion"), and a leading camera word is an
    act of its own.  The single split backing both the drawing and the filter comparisons,
    so a row cannot be lit act by act along one seam and drawn along another.
    """
    cameras = {word.lower() for word in camera_words}
    acts: list[str] = []
    for part in str(name or "").split(","):
        words = part.split()
        if len(words) > 1 and words[0].lower() in cameras:
            acts.append(words[0])
            words = words[1:]
        if words:
            acts.append(" ".join(words))
    return acts


def action_label_blocks(name: str, camera_words: Sequence[str]) -> list[list[str]]:
    """A clip's action(s) drawn nicely, as one block of word-lines per action.

    A clip can carry several acts ("Alpha, Theta Motion", "Side Gamma") — each becomes
    its own block, so they can be drawn with a gap between the acts but tight
    wrapping within one, and each can be lit on its own.  A camera word is drawn as
    the source writes it, which plain title case would get wrong for an initialism.
    "(unknown)" when there is no action metadata.
    """
    as_written = {word.lower(): word for word in camera_words}
    blocks = [[as_written.get(word.lower()) or _titlecase_word(word) for word in act.split()]
              for act in split_acts(name, camera_words)]
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
    """*model* as the text a source publishes, and :func:`parse_hud` reads back.

    The two are one module so the keys are spelled once: a source in another
    process (Fun Time, for its satellites) writes this into the Funestra's HUD
    file, and a source in the Funestra's own (a hosted Origenerator) hands the
    model over without it.
    """
    return json.dumps({
        "funestra": model.funestra,
        # The same, under the key a reader from before the rename looks for.
        "player": model.funestra,
        "hud_corner": model.hud_corner,
        "hud_edge": model.hud_edge,
        "hud_minimized": model.hud_minimized,
        "locked": model.locked,
        "lock_label": model.lock_label,
        "active": model.active,
        "is_favorite": model.is_favorite,
        "item_note": model.item_note,
        "filter_query": model.filter_query,
        "camera_words": list(model.camera_words),
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
    })


def parse_hud(text: str) -> HudModel | None:
    """The published panel, or None when *text* is not a complete panel.

    fun_time rewrites the file in place while the Funestra is reading it, so a
    torn or empty read is expected and simply means "keep the HUD you have".
    """
    try:
        raw = json.loads(text)
    except (ValueError, TypeError):
        return None
    if not isinstance(raw, dict) or not ({"funestra", "player"} & raw.keys()):
        return None
    playing = raw.get("playing") or ["corner", 0]
    seeds = [_cell(item) for item in raw.get("seeds", []) or []]
    actions = [_cell(item) for item in raw.get("actions", []) or []]
    return HudModel(
        funestra=str(raw.get("funestra", raw.get("player", ""))),
        hud_corner=read_mode(HudCorner, raw.get("hud_corner"), HudCorner.UPPER_LEFT),
        hud_edge=read_mode(HudEdge, raw.get("hud_edge"), HudEdge.LOWER),
        hud_minimized=bool(raw.get("hud_minimized", False)),
        locked=bool(raw.get("locked", False)),
        lock_label=str(raw.get("lock_label", "") or ""),
        active=bool(raw.get("active", False)),
        is_favorite=bool(raw.get("is_favorite", False)),
        item_note=str(raw.get("item_note", "") or ""),
        corner=_cell(raw.get("corner")),
        seeds=tuple(cell for cell in seeds if cell is not None),
        actions=tuple(cell for cell in actions if cell is not None),
        current_action=str(raw.get("current_action", "") or ""),
        filter_query=str(raw.get("filter_query", "") or ""),
        camera_words=tuple(str(word) for word in raw.get("camera_words") or ()),
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
    )
