"""The main console — the HUD the Main Funestra draws.

The same console is drawn whether Kino or Genau runs on the Main Funestra: over
Kino's video in kino mode, over Genau's flicks in genau mode.  So the mode switch
and the drive controls keep their places as you flip between modes — only the
transport changes, because it steps Kino's video in one and Genau's flicks in the other.

Its top block is Kino's own answer to "what am I playing?" — the title (the
length mode, or the compilation and your place in it) beside the active-Funestra
dot, with the file on screen as a muted line under it, the same shape each
satellite's HUD leads with.  Both are empty in genau mode, where there is no Kino
playlist backing the screen.  Everything else is the console the orchestrator
publishes (:mod:`funestra.console`) plus the Robot Hand's drive readout
(:mod:`funestra.drive_readout`) with its own controls.

The wording and shape are pure functions; the drawing goes onto the slab
:mod:`funestra.hud_panel` owns, the same slab the satellites' HUD is drawn on,
so every Funestra says things the same way and from the same corner.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

import numpy as np
from PIL import Image
from shared_ui.palette import (
    BG_PRIMARY,
    TEXT_MUTED,
    TEXT_PRIMARY,
)
from shared_ui.spacing import BUTTON_GAP

from .console import (
    Button,
    ConsoleModel,
    ModeHud,
    _row_width,
    hit_test,
    kino_shows,
    place_rows,
    rows_height,
    tooltip_at,
)
from .drive_readout import (
    DriveHud,
    DriveSection,
    DriveTrack,
    TrackGrip,
    readout_targets,
    section_size,
)
from .geometry import Rect, contains
from .host_controls import HostControlsHud, HostControlsLayout, HostControlsSection
from .hud_corners import HudPlace
from .hud_minimize import ROOM as MINUS_ROOM
from .hud_minimize import collapsed_button, corner_button_rect, minimize_button
from .hud_osr2 import HEIGHT as _OSR2_H
from .hud_osr2 import (
    Osr2Line,
    Osr2Section,
    ReadoutResolver,
    driving_at_the_playhead,
    state_for,
)
from .hud_panel import (
    ACTIVE_DOT,
    BODY_PT,
    SYMBOL_FONT,
    TINY_PT,
    HudPanel,
    draw_active_dot,
    draw_button,
    draw_tooltip,
    fit_text,
    load_font,
    text_width,
    to_bgra,
)
from .hud_placement import HudCorner, PointerReading, block_x
from .hud_row import ROW_H, RowHud, RowLayout, RowSection, row_layout
from .hud_sections import blocks_height, stack
from .hud_title import (
    LATEST_LABEL,
    SEPARATOR,
    SHUFFLE_LABEL,
    hud_title,
)
from .modes import LengthMode

# What the two length modes are called on the line.  MIXED is absent: it
# applies no length filter at all, so it narrows nothing and prints nothing --
# the same silence a satellite keeps where its act filter would go when it has
# none.
_LENGTH_LABELS = {LengthMode.FULL: "Full", LengthMode.CLIPS: "Clips"}

# A compilation is titled for a shelf: "various - Ultimate Example Studio Alpha
# Collection - Volume 6 (v1)".  Everything up to the last dash is the series and
# the trailing "(v1)" the archivist's revision, leaving the volume as the part
# that says which one you are inside.
_REVISION = re.compile(r"\s*\(v\d+\)$")

def _format_rate(rate: float) -> str:
    """A playback rate as a compact label: 1.0 -> '1×', 1.5 -> '1.5×'."""
    return f"{rate:g}×"


def compilation_label(title: str) -> str:
    """*title* cut down to what tells one compilation from another."""
    volume = title.rsplit(" - ", 1)[-1]
    return _REVISION.sub("", volume).strip()


# --- the panel ---------------------------------------------------------------

_PAD = 10
_MINUS_INSET = (_PAD, _PAD)
DOT_GAP = 8  # the room between the active-Funestra dot and the words beside it
MARGIN = 8    # inset from the window's top-left corner
_BLOCK_GAP = 4
_SUBTITLE_GAP = 2  # between the title and the file name under it


def hud_xy() -> tuple[int, int]:
    """Where the panel goes: the window's top-left corner, the same place the
    satellites put theirs."""
    return MARGIN, MARGIN


@dataclass(frozen=True)
class ConsoleHud:
    """Everything on the main console: the top line, the room's controls, and
    the Robot Hand's drive readout.

    *modes* is drawn only where it applies (kino mode); *console* is what Fun
    Time published; *drive* is the live readout, present once the Robot Hand has
    published one.
    """

    modes: ModeHud = field(default_factory=ModeHud)
    console: ConsoleModel = field(default_factory=ConsoleModel)
    drive: DriveHud | None = None
    # The gray the slab is made of, or None for the canvas color every Funestra
    # floating this over a video wants (see hud_panel.HudPanel).  Part of the
    # value compared for the repaint cache, like the rest.
    ground: tuple[int, int, int] | None = None
    flash: str = ""

    @property
    def advance_interval(self) -> int:
        """How long an unlocked Genau leaves each flick up.

        Genau owns the pace, so it rides its own drive readout rather than the
        console panel Fun Time publishes — and is read back off the readout
        wherever the console needs it, which is both the auto-advance button and
        the title.
        """
        if self.drive is not None:
            return self.drive.advance_interval
        return self.console.advance_interval

    @property
    def title(self) -> str:
        """Everything selecting what is on the main slot, in the order each
        satellite's HUD title says the same things.

        The Main Funestra's words in the slots
        :func:`funestra.hud_title.hud_title` lays out, which is where the
        grammar and the shared states' wording live — the satellites say the same
        sentence, and a reader glancing between two screens is reading one sentence
        in two places.

        The compilation is Kino's playing set — a fixed run it plays through
        rather than the browse it came from.  The order slot carries the browse
        order under either of the two, and Genau's advance pace beside it.  The
        filters are the room's narrowings of the browse; a room publishing none
        leaves Kino's own length word there instead.
        """
        compilation = (
            f"{compilation_label(self.modes.compilation)}"
            f"{SEPARATOR}{self.modes.position}/{self.modes.total}"
        ) if self.modes.compilation else ""
        # The browse order, said the same way whether Kino or Genau is on this slot:
        # both of them browse in these two orders, so a reader who has just asked
        # for Latest reads the same word back wherever they asked it.  Nothing at
        # all for a host with no browse order (see :attr:`ConsoleModel.latest`) —
        # an empty slot takes no room, the way every other optional slot here does.
        order = "" if self.console.latest is None else (
            LATEST_LABEL if self.console.latest else SHUFFLE_LABEL)
        # The pace an unheld Genau flick moves on at, after the order rather than in
        # place of it: the order says which flick is next, the pace says when.  Only
        # while Genau is the one showing — kino mode draws the drive readout too, but
        # an unlocked Kino plays through a playlist rather than on a timer —
        # and only unheld, since nothing is going to move a held flick.
        if not kino_shows(self.console.main_mode) and not self.console.locked and self.advance_interval:
            pace = f"{self.advance_interval}s"
            order = f"{order}{SEPARATOR}{pace}" if order else pace
        return hud_title(
            playing_set=compilation,
            locked=self.console.locked,
            order=order,
            f_mode=self.modes.scripted_filter,
            filters=self.console.filters or (_LENGTH_LABELS.get(self.modes.length_mode, ""),),
        )


def _section_rect(corner: HudCorner, width: int, reserve: int, top: int,
                  height: int) -> Rect:
    return (_PAD + (0 if corner.right else reserve), top, width - 2 * _PAD - reserve, height)


class ConsolePainter:
    """Paints the main console, and only when something on it has moved.

    A Funestra redraws its overlays every frame at 60 fps and Pillow is nowhere
    near cheap enough for that, so the bitmap is kept until the panel's contents
    change.  The button rects from the last painting are kept beside it — the
    console's own and the drive readout's arrows — so what is clickable is exactly
    what was drawn, and the readout's own bands with them, so what is draggable is
    too.
    """

    def __init__(self, *, width: int | None = None, device_only: bool = False,
                 minus_on_the_panel: bool = True,
                 clock: Callable[[], float] = time.monotonic) -> None:
        """*width* holds every panel to one width, whatever is on it.  A console
        hanging in a scene as a screen of its own (FunTimeVR's) otherwise changes
        size with its contents — the genau-mode rows are narrower than the
        kino-mode ones, and a long title widens the panel — and a screen that
        grows and shrinks is a screen that moves.  The rows, the readout and
        the OSR2 line must fit, so a width narrower than them is widened, never
        clipped; the two text lines give way instead, elided to fit.  None
        sizes the panel to its contents, as one drawn over the Funestra's own
        window is."""
        self._width = width
        self._device_only = device_only
        self._minus_on_the_panel = minus_on_the_panel
        self._body = load_font(BODY_PT)
        self._tiny = load_font(TINY_PT)
        self._glyph = load_font(BODY_PT, SYMBOL_FONT)
        self._drive = DriveSection()
        self._osr2 = Osr2Section()
        self._item_row = RowSection()
        self._host_controls = HostControlsSection()
        # What the panel on hand was painted from.  The heatmap is held by
        # identity rather than value: comparing a track's worth of colors every
        # frame costs more than the paint it saves, and a host rebuilds the
        # array rather than writing into it.
        self._painted: tuple = (None, None, None, None, None)
        self._composed_drive: DriveHud | None = None
        self._image: Image.Image | None = None
        self._bgra: np.ndarray | None = None
        self.buttons: list[tuple[Rect, Button]] = []
        self.tracks: list[DriveTrack] = []
        # Where the item's row landed, for a press to be placed in its own
        # coordinates (:func:`funestra.hud_row.row_part`).
        self.row: RowLayout | None = None
        self.host_controls_layout: HostControlsLayout | None = None
        self._grip = TrackGrip()
        self._readout = ReadoutResolver(clock=clock)
        self._origin = hud_xy()
        self._pointer: PointerReading[tuple[int, int] | None] = PointerReading(None)

    def bgra(self, hud: ConsoleHud, *, hover: tuple[int, int] | None = None,
             item_row: RowHud | None = None, heatmap=None,
             host_controls: HostControlsHud | None = None) -> np.ndarray:
        """*hud* as an mpv overlay bitmap — what the Main Funestra composites into its video."""
        if (self._ensure(self._resolve(hud), hover, item_row, heatmap, host_controls)
                or self._bgra is None):
            self._bgra = to_bgra(self._image)
        return self._bgra

    def rgba(self, hud: ConsoleHud, *, hover: tuple[int, int] | None = None,
             item_row: RowHud | None = None, heatmap=None,
             host_controls: HostControlsHud | None = None) -> tuple[bytes, tuple[int, int]]:
        """*hud* as ``(rgba_bytes, size)`` — what pygame takes, for Genau to blit
        into its own window in genau mode.  The size varies with the contents, so
        the caller sizes its blit from what comes back."""
        self._ensure(self._resolve(hud), hover, item_row, heatmap, host_controls)
        return self._image.tobytes(), self._image.size

    def _resolve(self, hud: ConsoleHud) -> ConsoleHud:
        """*hud* with everything the drawing Funestra knows folded into it, before
        anything asks whether the panel has moved.

        Folded here rather than at paint time because a readout that is *not*
        moving has to compare equal: the trace held still while nothing is being
        sent arrives as a fresh scroll of Genau's phase every publish, and folded
        after the comparison it would repaint the whole panel forty times a
        second to draw the same still picture.
        """
        console = hud.console
        return replace(hud, drive=self._readout.resolve(
            hud.drive if console.has_osr2 else None,
            osr2=console.osr2, control=console.osr2_control, paused=console.paused,
            composed=kino_shows(console.main_mode)))

    def _ensure(self, hud: ConsoleHud, hover: tuple[int, int] | None,
                item_row: RowHud | None = None, heatmap=None,
                host_controls: HostControlsHud | None = None) -> bool:
        """Repaint if *hud*/*hover*/the item's row/the host's controls moved; report whether it did
        (so a cached bitmap can be reused).  The panel is redrawn a few times a
        minute at most — Pillow is too slow to run every frame — so the image is
        kept until it changes.  The row is the one part that moves with playback,
        which is why a Funestra redrawing on its beat gets a fresh panel."""
        hover = hover if hover is not None else self._pointer.on(hud.console)
        if ((hud, hover, item_row, host_controls) == self._painted[:4]
                and heatmap is self._painted[4] and self._image is not None):
            return False
        self._painted = (hud, hover, item_row, host_controls, heatmap)
        self._image = self._paint(hud, hover, item_row, heatmap, host_controls)
        return True

    def press_at(self, mx: int, my: int) -> str:
        """The command a press at *window* point ``(mx, my)`` posts, "" over none.

        A press inside one of the drive readout's bands takes hold of it as well
        as posting: :meth:`drag_to` then goes on setting that level as the pointer
        moves, so a bar can be dragged and not only clicked.  Anything already
        held is let go first, so a press on an ordinary button never leaves a band
        still latched.
        """
        self.release()
        px, py = self._local(mx, my)
        return hit_test(self.buttons, px, py) or self._grip.grab(self.tracks, px, py)

    def covers(self, mx: int, my: int) -> bool:
        return self._image is not None and contains(
            (0, 0, *self._image.size), *self._local(mx, my))

    @property
    def holding(self) -> bool:
        """Whether a press took hold of one of the readout's bands and has not let
        go — so the Funestra knows a drag belongs here rather than to whatever else
        it would have offered the pointer."""
        return self._grip.holding

    def drag_to(self, mx: int, my: int) -> str:
        """The command the pointer posts while a band is held."""
        return self._grip.drag_to(*self._local(mx, my))

    def release(self) -> None:
        """Let go of whichever band a press took hold of."""
        self._grip.release()

    def hover_at(self, mx: int, my: int) -> tuple[int, int] | None:
        """Where to name the button under *window* point ``(mx, my)``, else None."""
        local = self._local(mx, my)
        return local if tooltip_at(self.buttons, *local) else None

    def motion(self, mx: int, my: int) -> None:
        """Follow the pointer to *window* point ``(mx, my)``: the next painting
        lights the button under it and names it, until the pointer moves off or
        the panel moves to another corner."""
        self._pointer.take(self.hover_at(mx, my))

    def leave(self) -> None:
        """The pointer has left the window: no button is under it."""
        self._pointer.take(None)

    # Only Genau's old console panel, in checkouts from before its window went,
    # reads row_rect; it answers until none of them is open.
    @property
    def row_rect(self) -> tuple[int, int, int, int] | None:
        return None if self.row is None else self.row.rect

    @property
    def hud_place(self) -> HudPlace | None:
        painted = self._painted[0]
        if painted is None:
            return None
        console = painted.console
        return HudPlace(console.funestra, console.hud_corner, MARGIN,
                        minimized=console.hud_minimized, inset=_MINUS_INSET)

    def place(self, *, window: tuple[int, int], lower_edge: int = 0) -> tuple[int, int]:
        place = self.hud_place or HudPlace("", HudCorner.UPPER_LEFT, MARGIN)
        size = self._image.size if self._image is not None else (0, 0)
        self._origin = place.origin(panel=size, window=window, lower_edge=lower_edge)
        return self._origin

    def _local(self, mx: int, my: int) -> tuple[int, int]:
        left, top = self._origin
        return mx - left, my - top

    def _block_x(self, corner: HudCorner, panel_width: int, extent: int,
                 reserve: int = 0) -> int:
        return block_x(corner, panel_width=panel_width, extent=extent, pad=_PAD,
                       reserve=reserve)

    def _draw_top_block(self, panel: HudPanel, y: int, title: str, filename: str,
                        active: bool, width: int, corner: HudCorner, *,
                        reserve: int) -> None:
        """The active-Funestra dot and the title — what is selecting this
        playlist — with the file on screen muted under it.

        The same shape each satellite's HUD leads with, so a glance between two
        screens finds the same answer in the same corner.  Both are empty in genau
        mode, and the block is then only the dot.
        """
        draw = panel.draw
        ascent, descent = self._body.getmetrics()
        indent = ACTIVE_DOT + DOT_GAP
        title_x = self._block_x(corner, width,
                                 indent + text_width(self._body, title), reserve)
        draw_active_dot(panel.image, title_x, y + (ascent + descent) // 2 - ACTIVE_DOT // 2,
                        active)
        if title:
            draw.text((title_x + indent, y + ascent), title, font=self._body,
                      anchor="ls", fill=(*TEXT_PRIMARY, 255))
        if filename:
            name_x = self._block_x(corner, width,
                                   indent + text_width(self._tiny, filename), reserve)
            draw.text((name_x + indent, y + ascent + descent + _SUBTITLE_GAP), filename,
                      font=self._tiny, anchor="la", fill=(*TEXT_MUTED, 255))

    def _draw_rows(self, panel: HudPanel, rows: list[list[Button]], y: int,
                   corner: HudCorner, hover: tuple[int, int] | None, reserve: int = 0,
                   ) -> list[tuple[Rect, Button]]:
        width = panel.image.width
        placed = place_rows(rows, x=_PAD + (0 if corner.right else reserve), y=y,
                            ends_at=width - _PAD - reserve if corner.right else None)
        row_top = None
        for rect, button in placed:
            draw_button(panel.image, panel.draw, rect, button,
                        hovered=hover is not None and contains(rect, *hover),
                        glyph_font=self._glyph, word_font=self._tiny,
                        row_label=rect[1] != row_top)
            row_top = rect[1]
        return placed

    def _paint(self, hud: ConsoleHud, hover: tuple[int, int] | None = None,
               item_row: RowHud | None = None, heatmap=None,
               host_controls: HostControlsHud | None = None) -> Image.Image:
        console, drive = hud.console, hud.drive
        if console.hud_minimized:
            return self._paint_minimized(console.funestra, console.hud_corner, hover, hud.flash)
        # Held for the OSR2 pill: with a composed trace on the panel the pill
        # reads the trace's own answer to who has the device (see _osr2_state),
        # and the width helpers need it before the pill is drawn.
        self._composed_drive = (
            drive if (drive is not None and drive.segments
                      and kino_shows(console.main_mode)) else None)
        whole = not self._device_only
        rows = [[self._filled(button, hud) for button in row]
                for row in (console.rows if whole else ())]
        aim_rows = [[self._filled(button, hud) for button in row] for row in console.osr2_rows]
        title = hud.title if whole else ""
        filename = hud.modes.video if whole else ""
        item_row = item_row if whole else None
        drive_w, drive_h = section_size() if drive is not None else (0, 0)
        body_ascent, body_descent = self._body.getmetrics()
        top_h = body_ascent + body_descent if whole else 0
        tiny_h = sum(self._tiny.getmetrics())
        filename_h = (_SUBTITLE_GAP + tiny_h) if filename else 0

        corner = console.hud_corner
        text_x = ACTIVE_DOT + DOT_GAP
        widths = [0, _row_width(rows),
                  max(_row_width(aim_rows), drive_w,
                      self._osr2_width(console) if console.has_osr2 else 0),
                  self._item_row.least_width(item_row) if item_row is not None else 0,
                  self._host_controls.least_width(host_controls) if host_controls is not None else 0]
        minus_room = MINUS_ROOM if whole and self._minus_on_the_panel else 0
        last = max(index for index, used in enumerate(
            (True, bool(rows), bool(aim_rows) or console.has_osr2 or drive is not None,
             item_row is not None, host_controls is not None)) if used)
        reserves = [0] * len(widths)
        reserves[last if corner.lower else 0] = minus_room
        parts_w = max(width_ + reserve for width_, reserve in zip(widths, reserves))
        if self._width is None:
            width = 2 * _PAD + max(
                parts_w,
                reserves[0] + text_x + text_width(self._body, title),
                reserves[0] + text_x + text_width(self._tiny, filename),
            )
        else:
            any_row = (self._item_row.least_width_for_any_row()
                       + (minus_room if corner.lower else 0)) if whole else 0
            width = max(self._width, 2 * _PAD + parts_w, 2 * _PAD + any_row)
            room = width - 2 * _PAD - text_x - reserves[0]
            title = fit_text(self._body, title, room)
            filename = fit_text(self._tiny, filename, room)
        # The item's own row, under everything the console says about the room:
        # where the video is and how loud it is, drawn here rather than along
        # the lower edge of the picture (:mod:`funestra.hud_row`).
        row_h = ROW_H if item_row is not None else 0
        sections = stack(_PAD, [
            top_h + filename_h,
            rows_height(rows),
            blocks_height([rows_height(aim_rows), _OSR2_H if console.has_osr2 else 0,
                           drive_h], _BLOCK_GAP),
            row_h,
            HostControlsSection.height if host_controls is not None else 0,
        ])
        title_top, rows_top, device_top, row_top, host_top = sections.tops
        height = sections.end + _PAD

        panel = HudPanel(width, height, ground=hud.ground or BG_PRIMARY)
        for divider in sections.dividers:
            panel.divide(divider)
        draw = panel.draw

        if whole:
            self._draw_top_block(panel, title_top, title, filename, console.active,
                                 width, corner, reserve=reserves[0])
        self.buttons = self._draw_rows(panel, rows, rows_top, corner, hover, reserves[1])
        self.tracks = []

        y = device_top
        if aim_rows:
            self.buttons.extend(self._draw_rows(panel, aim_rows, y, corner, hover, reserves[2]))
            y += rows_height(aim_rows) + _BLOCK_GAP

        if console.has_osr2:
            osr2_line = self._osr2_line(console)
            osr2_x = self._block_x(corner, width, self._osr2.width(osr2_line), reserves[2])
            self.buttons.extend(self._osr2.draw(panel.image, draw, osr2_x, y, osr2_line,
                                                hover=hover))
            self.tracks.extend(self._osr2.bands(osr2_x, y, osr2_line))
            y += _OSR2_H + _BLOCK_GAP

        if drive is not None:
            drive_x = self._block_x(corner, width, drive_w, reserves[2])
            # The panel's image rather than its pen: the readout supersamples
            # its trace and composites it back, which a pen cannot carry.
            self._drive.draw(panel.image, drive_x, y, drive)
            # The readout draws its own arrows and bands; the console only needs
            # them as hit targets, so they answer a press and name themselves on
            # hover.
            targets, bands = readout_targets(drive_x, y, drive)
            self.buttons.extend(targets)
            self.tracks.extend(bands)

        if whole and self._minus_on_the_panel:
            minus = (corner_button_rect(corner, panel=(width, height), inset=_MINUS_INSET),
                     minimize_button(console.funestra))
            draw_button(panel.image, draw, *minus,
                        hovered=hover is not None and contains(minus[0], *hover),
                        glyph_font=self._glyph, word_font=self._tiny)
            self.buttons.append(minus)
        self._draw_the_foot(panel.image, corner, reserves, item_row, row_top, row_h, heatmap,
                            host_controls, host_top)

        if hover is not None:
            tip = tooltip_at(self.buttons, *hover)
            if tip:
                draw_tooltip(draw, self._tiny, tip, hover, (width, height))
        return panel.image

    def _draw_the_foot(self, image: Image.Image, corner: HudCorner, reserves: list[int],
                       item_row: RowHud | None, row_top: int, row_h: int, heatmap,
                       host_controls: HostControlsHud | None, host_top: int) -> None:
        self.row = None
        if item_row is not None:
            self.row = row_layout(item_row, rect=_section_rect(
                corner, image.width, reserves[3], row_top, row_h))
            self._item_row.draw(image, self.row, item_row, heatmap=heatmap)
        self.host_controls_layout = None
        if host_controls is not None:
            self.host_controls_layout = self._host_controls.draw(image, _section_rect(
                corner, image.width, reserves[4], host_top, HostControlsSection.height),
                host_controls)

    def _paint_minimized(self, funestra: str, corner: HudCorner,
                         hover: tuple[int, int] | None, flash: str) -> Image.Image:
        image, buttons = collapsed_button(funestra, corner, hover=hover,
                                          room_for_the_tooltip=self._width is not None,
                                          flash=flash)
        self.buttons, self.tracks, self.row, self.host_controls_layout = buttons, [], None, None
        return image

    def _osr2_state(self, model: ConsoleModel) -> str:
        """What the pill says has the device — the drawn line's own answer
        when a composed trace is on the panel, so the pill flips exactly when
        the line under the dot changes hands, and says Buffer through the gray
        where the device belongs to neither driver.  The round-tripped osr2
        stands in everywhere else, and for its own device-level states.

        The precedence around it -- auto, then a hold, then whoever
        is driving -- is the shared line's (:func:`funestra.hud_osr2.state_for`),
        since every panel that draws this line answers it the same way."""
        return state_for(model.osr2, model.osr2_control,
                         driving=driving_at_the_playhead(self._composed_drive, model.osr2))

    def _osr2_line(self, model: ConsoleModel) -> Osr2Line:
        """The device's line as the shared section takes it — the controls the
        source put on it, and this console's own answer to who has the OSR2."""
        return Osr2Line(state=self._osr2_state(model), controls=model.osr2_controls,
                        max_intensity=model.max_intensity)

    def _osr2_width(self, model: ConsoleModel) -> int:
        return self._osr2.width(self._osr2_line(model))

    def _filled(self, button: Button, hud: ConsoleHud) -> Button:
        """A read-out as it is drawn: the host's own number written in where the
        source named one, and a word's cell widened to hold it.  A button comes
        back as it was.

        The two numbers are the drawing host's -- the video's rate, the seconds
        an unheld clip stays up -- which no source can know, so the source
        names them and whoever draws fills them in.  A name that outgrows the
        cell the source gave it widens the cell: "Playback speed" ran under the
        button beside it once, its last letter under the minus.
        """
        if button.command:
            return button
        glyph = button.glyph
        if button.host_value == "playback_speed":
            glyph = _format_rate(hud.console.playback_speed)
        elif button.host_value == "advance_interval":
            glyph = f"{hud.advance_interval}s"
        width = button.width
        if button.is_a_name:
            width = max(width, text_width(self._tiny, glyph) + BUTTON_GAP)
        return replace(button, glyph=glyph, width=width)


def with_playback_speed(console: ConsoleModel, speed: float) -> ConsoleModel:
    """*console* with the drawing Funestra's own video rate folded in — Kino knows
    its rate, Fun Time does not publish it, so it is added at draw time."""
    return replace(console, playback_speed=speed)
