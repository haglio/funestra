"""The Main Funestra's HUD — the HUD the Main Funestra draws.

The same HUD is drawn whether Kino or Genau runs on the Main Funestra: over
Kino's video in kino mode, over Genau's flicks in genau mode.  So the mode switch
and the drive controls keep their places as you flip between modes — only the
transport changes, because it steps Kino's video in one and Genau's flicks in the other.

Its top block is Kino's own answer to "what am I playing?" — the title (the
length mode, or the compilation and your place in it) beside the active-Funestra
dot, with the file on screen as a muted line under it, the same shape each
satellite's HUD leads with.  Both are empty in genau mode, where there is no Kino
playlist backing the screen.  Everything else is the Main Funestra's HUD the orchestrator
publishes (:mod:`funestra.main_hud`) plus the Robot Hand's OSR2 visualizer
(:mod:`funestra.drive_readout`) with its own controls.

The wording and shape are pure functions; the drawing goes onto the slab
:mod:`funestra.hud` owns, the same slab the satellites' HUD is drawn on,
so every Funestra says things the same way and from the same corner.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace

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
    Hud,
    draw_active_dot,
    draw_button,
    draw_tooltip,
    load_font,
    text_width,
    to_bgra,
)
from .hud_corners import HudPlace
from .hud_minimize import ROOM as MINUS_ROOM
from .hud_minimize import collapsed_button, corner_button_rect, minimize_button
from .hud_osr2 import HEIGHT as _OSR2_H
from .hud_osr2 import (
    Osr2Line,
    Osr2Section,
    VisualizerResolver,
    driving_at_the_playhead,
    state_for,
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
from .osr2_visualizer import (
    DriveHud,
    DriveSection,
    DriveTrack,
    TrackGrip,
    section_size,
    visualizer_targets,
)

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


# --- the HUD ---------------------------------------------------------------

_PAD = MARGIN_STANDARD
_MINUS_INSET = (_PAD, _PAD)
DOT_GAP = GAP_MEDIUM  # the app between the active-Funestra dot and the words beside it
MARGIN = MARGIN_STANDARD    # inset from the window's top-left corner
_BLOCK_GAP = GAP_SMALL
_SUBTITLE_GAP = GAP_SMALL  # between the title and the file name under it


def hud_xy() -> tuple[int, int]:
    """Where the HUD goes: the window's top-left corner, the same place the
    satellites put theirs."""
    return MARGIN, MARGIN


@dataclass(frozen=True)
class MainHud:
    """Everything on the Main Funestra's HUD: the top line, the app's controls, and
    the Robot Hand's OSR2 visualizer.

    *modes* is drawn only where it applies (kino mode); *console* is what Fun
    Time published; *drive* is the live visualizer, present once the Robot Hand has
    published one.
    """

    modes: ModeHud = field(default_factory=ModeHud)
    main_hud_model: MainHudModel = field(default_factory=MainHudModel)
    drive: DriveHud | None = None
    # The gray the slab is made of, or None for the canvas color every Funestra
    # floating this over a video wants (see hud.Hud).  Part of the
    # value compared for the repaint cache, like the rest.
    ground: tuple[int, int, int] | None = None
    flash: str = ""

    @property
    def advance_interval(self) -> int:
        """How long an unlocked Genau leaves each flick up.

        Genau owns the pace, so it rides its own OSR2 visualizer rather than the
        Main Funestra's HUD Fun Time publishes — and is read back off the visualizer
        wherever the Main Funestra's HUD needs it, which is both the auto-advance button and
        the title.
        """
        if self.drive is not None:
            return self.drive.advance_interval
        return self.main_hud_model.advance_interval

    @property
    def title(self) -> str:
        """Everything selecting what is on the main place, in the order each
        satellite's HUD title says the same things.

        The Main Funestra's words in the places
        :func:`funestra.hud_title.hud_title` lays out, which is where the
        grammar and the shared states' wording live — the satellites say the same
        sentence, and a reader glancing between two screens is reading one sentence
        in two places.

        The compilation is Kino's playing set — a fixed run it plays through
        rather than the browse it came from.  The order place carries the browse
        order under either of the two, and Genau's advance pace beside it.  The
        filters are the app's narrowings of the browse; a room publishing none
        leaves Kino's own length word there instead.
        """
        compilation = (
            f"{compilation_label(self.modes.compilation)}"
            f"{SEPARATOR}{self.modes.position}/{self.modes.total}"
        ) if self.modes.compilation else ""
        # The browse order, said the same way whether Kino or Genau is on this place:
        # both of them browse in these two orders, so a reader who has just asked
        # for Latest reads the same word back wherever they asked it.  Nothing at
        # all for a host with no browse order (see :attr:`MainHudModel.latest`) —
        # an empty place takes no room, the way every other optional place here does.
        order = "" if self.main_hud_model.latest is None else (
            LATEST_LABEL if self.main_hud_model.latest else SHUFFLE_LABEL)
        # The pace an unheld Genau flick moves on at, after the order rather than in
        # place of it: the order says which flick is next, the pace says when.  Only
        # while Genau is the one showing — kino mode draws the OSR2 visualizer too, but
        # an unlocked Kino plays through a playlist rather than on a timer —
        # and only unheld, since nothing is going to move a held flick.
        if not kino_shows(self.main_hud_model.main_mode) and not self.main_hud_model.locked and self.advance_interval:
            pace = f"{self.advance_interval}s"
            order = f"{order}{SEPARATOR}{pace}" if order else pace
        return hud_title(
            playing_set=compilation,
            locked=self.main_hud_model.locked,
            order=order,
            f_mode=self.modes.scripted_filter,
            filters=self.main_hud_model.filters or (_LENGTH_LABELS.get(self.modes.length_mode, ""),),
        )


def _section_rect(corner: HudCorner, width: int, reserve: int, top: int,
                  height: int) -> Rect:
    return (_PAD + (0 if corner.right else reserve), top, width - 2 * _PAD - reserve, height)


class MainHudPainter:
    """Paints the Main Funestra's HUD, and only when something on it has moved.

    A Funestra redraws its overlays every frame at 60 fps and Pillow is nowhere
    near cheap enough for that, so the bitmap is kept until the HUD's contents
    change.  The button rects from the last painting are kept beside it — the
    HUD's own and the OSR2 visualizer's arrows — so what is clickable is exactly
    what was drawn, and the visualizer's own bars with them, so what is draggable is
    too.
    """

    def __init__(self, *, width: int | None = None, device_only: bool = False,
                 minus_on_the_hud: bool = True,
                 clock: Callable[[], float] = time.monotonic) -> None:
        """*width* holds every HUD to one width, whatever is on it.  A console
        hanging in a scene as a screen of its own (FunTimeVR's) otherwise changes
        size with its contents — the genau-mode rows are narrower than the
        kino-mode ones, and a long title widens the HUD — and a screen that
        grows and shrinks is a screen that moves.  The rows, the visualizer and
        the OSR2 line must fit, so a width narrower than them is widened, never
        clipped; the two text lines give way instead, elided to fit.  None
        sizes the HUD to its contents, as one drawn over the Funestra's own
        window is."""
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
        # What the HUD on hand was painted from.  The heatmap is held by
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
        self._visualizer = VisualizerResolver(clock=clock)
        self._origin = hud_xy()
        self._pointer: PointerReading[tuple[int, int] | None] = PointerReading(None)

    def bgra(self, hud: MainHud, *, hover: tuple[int, int] | None = None,
             item_row: RowHud | None = None, heatmap=None,
             host_controls: HostControlsHud | None = None) -> np.ndarray:
        """*hud* as an mpv overlay bitmap — what the Main Funestra composites into its video."""
        if (self._ensure(self._resolve(hud), hover, item_row, heatmap, host_controls)
                or self._bgra is None):
            self._bgra = to_bgra(self._image)
        return self._bgra

    def rgba(self, hud: MainHud, *, hover: tuple[int, int] | None = None,
             item_row: RowHud | None = None, heatmap=None,
             host_controls: HostControlsHud | None = None) -> tuple[bytes, tuple[int, int]]:
        """*hud* as ``(rgba_bytes, size)`` — what pygame takes, for Genau to blit
        into its own window in genau mode.  The size varies with the contents, so
        the caller sizes its blit from what comes back."""
        self._ensure(self._resolve(hud), hover, item_row, heatmap, host_controls)
        return self._image.tobytes(), self._image.size

    def _resolve(self, hud: MainHud) -> MainHud:
        """*hud* with everything the drawing Funestra knows folded into it, before
        anything asks whether the HUD has moved.

        Folded here rather than at paint time because a visualizer that is *not*
        moving has to compare equal: the trace held still while nothing is being
        sent arrives as a fresh scroll of Genau's phase every publish, and folded
        after the comparison it would repaint the whole HUD forty times a
        second to draw the same image.
        """
        main_hud_model = hud.main_hud_model
        return replace(hud, drive=self._visualizer.resolve(
            hud.drive if main_hud_model.has_osr2 else None,
            osr2=main_hud_model.osr2, control=main_hud_model.osr2_control, paused=main_hud_model.paused,
            composed=kino_shows(main_hud_model.main_mode)))

    def _ensure(self, hud: MainHud, hover: tuple[int, int] | None,
                item_row: RowHud | None = None, heatmap=None,
                host_controls: HostControlsHud | None = None) -> bool:
        """Repaint if *hud*/*hover*/the item's row/the host's controls moved; report whether it did
        (so a cached bitmap can be reused).  The HUD is redrawn a few times a
        minute at most — Pillow is too slow to run every frame — so the image is
        kept until it changes.  The row is the one part that moves with playback,
        which is why a Funestra redrawing on its beat gets a fresh HUD."""
        hover = hover if hover is not None else self._pointer.on(hud.main_hud_model)
        if ((hud, hover, item_row, host_controls) == self._painted[:4]
                and heatmap is self._painted[4] and self._image is not None):
            return False
        self._painted = (hud, hover, item_row, host_controls, heatmap)
        self._image = self._paint(hud, hover, item_row, heatmap, host_controls)
        return True

    def press_at(self, mx: int, my: int) -> str:
        """The command a press at *window* point ``(mx, my)`` posts, "" over none.

        A press inside one of the OSR2 visualizer's bars takes hold of it as well
        as posting: :meth:`drag_to` then goes on setting that level as the pointer
        moves, so a bar can be dragged and not only clicked.  Anything already
        held is let go first, so a press on an ordinary button never leaves a bar
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
        """Whether a press took hold of one of the visualizer's bars and has not let
        go — so the Funestra knows a drag belongs here rather than to whatever else
        it would have offered the pointer."""
        return self._grip.holding

    def drag_to(self, mx: int, my: int) -> str:
        """The command the pointer posts while a bar is held."""
        return self._grip.drag_to(*self._local(mx, my))

    def release(self) -> None:
        """Let go of whichever bar a press took hold of."""
        self._grip.release()

    def hover_at(self, mx: int, my: int) -> tuple[int, int] | None:
        """Where to name the button under *window* point ``(mx, my)``, else None."""
        local = self._local(mx, my)
        return local if tooltip_at(self.buttons, *local) or hit_test(self.buttons, *local) else None

    def motion(self, mx: int, my: int) -> None:
        """Follow the pointer to *window* point ``(mx, my)``: the next painting
        lights the button under it and names it, until the pointer moves off or
        the HUD moves to another corner."""
        self._pointer.take(self.hover_at(mx, my))

    def leave(self) -> None:
        """The pointer has left the window: no button is under it."""
        self._pointer.take(None)

    @property
    def hud_place(self) -> HudPlace | None:
        painted = self._painted[0]
        if painted is None:
            return None
        main_hud_model = painted.main_hud_model
        return HudPlace(main_hud_model.funestra, main_hud_model.hud_corner, MARGIN,
                        minimized=main_hud_model.hud_minimized, inset=_MINUS_INSET)

    def place(self, *, window: tuple[int, int], lower_edge: int = 0) -> tuple[int, int]:
        place = self.hud_place or HudPlace("", HudCorner.UPPER_LEFT, MARGIN)
        size = self._image.size if self._image is not None else (0, 0)
        self._origin = place.origin(hud=size, window=window, lower_edge=lower_edge)
        return self._origin

    def _local(self, mx: int, my: int) -> tuple[int, int]:
        left, top = self._origin
        return mx - left, my - top

    def _block_x(self, corner: HudCorner, hud_width: int, extent: int,
                 reserve: int = 0) -> int:
        return block_x(corner, hud_width=hud_width, extent=extent, pad=_PAD,
                       reserve=reserve)

    def _draw_top_block(self, hud: Hud, y: int, title: str, filename: str,
                        active: bool, width: int, corner: HudCorner, *,
                        reserve: int) -> None:
        """The active-Funestra dot and the title — what is selecting this
        playlist — with the file on screen muted under it.

        The same shape each satellite's HUD leads with, so a glance between two
        screens finds the same answer in the same corner.  Both are empty in genau
        mode, and the block is then only the dot.
        """
        draw = hud.draw
        ascent, descent = self._body.getmetrics()
        indent = ACTIVE_DOT + DOT_GAP
        title_x = self._block_x(corner, width,
                                 indent + text_width(self._body, title), reserve)
        draw_active_dot(hud.image, title_x, y + (ascent + descent) // 2 - ACTIVE_DOT // 2,
                        active)
        if title:
            draw.text((title_x + indent, y + ascent), title, font=self._body,
                      anchor="ls", fill=(*TEXT_PRIMARY, 255))
        if filename:
            name_x = self._block_x(corner, width,
                                   indent + text_width(self._tiny, filename), reserve)
            draw.text((name_x + indent, y + ascent + descent + _SUBTITLE_GAP), filename,
                      font=self._tiny, anchor="la", fill=(*TEXT_MUTED, 255))

    def _draw_rows(self, hud: Hud, rows: list[list[Button]], y: int,
                   corner: HudCorner, hover: tuple[int, int] | None, reserve: int = 0,
                   ) -> list[tuple[Rect, Button]]:
        width = hud.image.width
        placed = place_rows(rows, x=_PAD + (0 if corner.right else reserve), y=y,
                            ends_at=width - _PAD - reserve if corner.right else None)
        row_top = None
        for rect, button in placed:
            draw_button(hud.image, hud.draw, rect, button,
                        hovered=hover is not None and contains(rect, *hover),
                        icon_font=self._icon, word_font=self._tiny,
                        row_label=rect[1] != row_top)
            row_top = rect[1]
        return placed

    def _paint(self, main_hud: MainHud, hover: tuple[int, int] | None = None,
               item_row: RowHud | None = None, heatmap=None,
               host_controls: HostControlsHud | None = None) -> Image.Image:
        main_hud_model, drive = main_hud.main_hud_model, main_hud.drive
        if main_hud_model.hud_minimized:
            return self._paint_minimized(main_hud_model.funestra, main_hud_model.hud_corner, hover, main_hud.flash)
        # Held for the OSR2 pill: with a composed trace on the HUD the pill
        # reads the trace's own answer to who has the device (see _osr2_state),
        # and the width helpers need it before the pill is drawn.
        self._composed_drive = (
            drive if (drive is not None and drive.segments
                      and kino_shows(main_hud_model.main_mode)) else None)
        whole = not self._device_only
        rows = [[self._filled(button, main_hud) for button in row]
                for row in (main_hud_model.rows if whole else ())]
        aim_rows = [[self._filled(button, main_hud) for button in row] for row in main_hud_model.osr2_rows]
        title = main_hud.title if whole else ""
        filename = main_hud.modes.video if whole else ""
        item_row = item_row if whole else None
        drive_w, drive_h = section_size() if drive is not None else (0, 0)
        body_ascent, body_descent = self._body.getmetrics()
        top_h = body_ascent + body_descent if whole else 0
        tiny_h = sum(self._tiny.getmetrics())
        filename_h = (_SUBTITLE_GAP + tiny_h) if filename else 0

        corner = main_hud_model.hud_corner
        text_x = ACTIVE_DOT + DOT_GAP
        widths = [0, _row_width(rows),
                  max(_row_width(aim_rows), drive_w,
                      self._osr2_width(main_hud_model) if main_hud_model.has_osr2 else 0),
                  self._item_row.least_width(item_row) if item_row is not None else 0,
                  self._host_controls.least_width(host_controls) if host_controls is not None else 0]
        minus_room = MINUS_ROOM if whole and self._minus_on_the_hud else 0
        last = max(index for index, used in enumerate(
            (True, bool(rows), bool(aim_rows) or main_hud_model.has_osr2 or drive is not None,
             item_row is not None, host_controls is not None)) if used)
        reserves = [0] * len(widths)
        reserves[last if corner.lower else 0] = minus_room
        parts_w = max(width_ + reserve for width_, reserve in zip(widths, reserves, strict=True))
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
        # The item's own row, under everything the Main Funestra's HUD says about the app:
        # where the video is and how loud it is, drawn here rather than along
        # the lower edge of the item (:mod:`funestra.hud_row`).
        row_h = ROW_H if item_row is not None else 0
        sections = stack(_PAD, [
            top_h + filename_h,
            rows_height(rows),
            blocks_height([rows_height(aim_rows), _OSR2_H if main_hud_model.has_osr2 else 0,
                           drive_h], _BLOCK_GAP),
            row_h,
            HostControlsSection.height if host_controls is not None else 0,
        ])
        title_top, rows_top, device_top, row_top, host_top = sections.tops
        height = sections.end + _PAD

        hud = Hud(width, height, ground=main_hud.ground or BG_PRIMARY)
        for divider in sections.dividers:
            hud.divide(divider)
        draw = hud.draw

        if whole:
            self._draw_top_block(hud, title_top, title, filename, main_hud_model.active,
                                 width, corner, reserve=reserves[0])
        self.buttons = self._draw_rows(hud, rows, rows_top, corner, hover, reserves[1])
        self.tracks = []

        y = device_top
        if aim_rows:
            self.buttons.extend(self._draw_rows(hud, aim_rows, y, corner, hover, reserves[2]))
            y += rows_height(aim_rows) + _BLOCK_GAP

        if main_hud_model.has_osr2:
            osr2_line = self._osr2_line(main_hud_model)
            osr2_x = self._block_x(corner, width, self._osr2.width(osr2_line), reserves[2])
            self.buttons.extend(self._osr2.draw(hud.image, draw, osr2_x, y, osr2_line,
                                                hover=hover))
            self.tracks.extend(self._osr2.bars(osr2_x, y, osr2_line))
            y += _OSR2_H + _BLOCK_GAP

        if drive is not None:
            drive_x = self._block_x(corner, width, drive_w, reserves[2])
            # The HUD's image rather than its pen: the visualizer supersamples
            # its trace and composites it back, which a pen cannot carry.
            self._drive.draw(hud.image, drive_x, y, drive)
            # The visualizer draws its own arrows and bars; the Main Funestra's HUD only needs
            # them as hit targets, so they answer a press and name themselves on
            # hover.
            targets, bars = visualizer_targets(drive_x, y, drive)
            self.buttons.extend(targets)
            self.tracks.extend(bars)

        if whole and self._minus_on_the_hud:
            minus = (corner_button_rect(corner, hud=(width, height), inset=_MINUS_INSET),
                     minimize_button(main_hud_model.funestra))
            draw_button(hud.image, draw, *minus,
                        hovered=hover is not None and contains(minus[0], *hover),
                        icon_font=self._icon, word_font=self._tiny)
            self.buttons.append(minus)
        self._draw_the_foot(hud.image, corner, reserves, item_row, row_top, row_h, heatmap,
                            host_controls, host_top)

        if hover is not None:
            tip = tooltip_at(self.buttons, *hover)
            if tip:
                draw_tooltip(draw, self._tiny, tip, hover, (width, height))
        return hud.image

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

    def _osr2_state(self, model: MainHudModel) -> str:
        """What the pill says has the device — the drawn line's own answer
        when a composed trace is on the HUD, so the pill flips exactly when
        the line under the dot changes hands, and says Buffer through the gray
        where the device belongs to neither driver.  The round-tripped osr2
        stands in everywhere else, and for its own device-level states.

        The precedence around it -- auto, then a hold, then whoever
        is driving -- is the shared line's (:func:`funestra.hud_osr2.state_for`),
        since every HUD that draws this line answers it the same way."""
        return state_for(model.osr2, model.osr2_control,
                         driving=driving_at_the_playhead(self._composed_drive, model.osr2),
                         paused=model.paused)

    def _osr2_line(self, model: MainHudModel) -> Osr2Line:
        """The device's line as the shared section takes it — the controls the
        source put on it, and this Main Funestra's HUD's own answer to who has the OSR2."""
        return Osr2Line(state=self._osr2_state(model), controls=model.osr2_controls,
                        max_intensity=model.max_intensity)

    def _osr2_width(self, model: MainHudModel) -> int:
        return self._osr2.width(self._osr2_line(model))

    def _filled(self, button: Button, hud: MainHud) -> Button:
        """A read-out as it is drawn: the host's own number written in where the
        source named one, and a word's cell widened to hold it.  A button comes
        back as it was.

        The two numbers are the drawing host's -- the video's rate, the seconds
        an unheld video stays up -- which no source can know, so the source
        names them and whoever draws fills them in.  A name that outgrows the
        cell the source gave it widens the cell: "Playback speed" ran under the
        button beside it once, its last letter under the minus.
        """
        if button.command:
            return button
        icon = button.icon
        if button.host_value == "playback_speed":
            icon = _format_rate(hud.main_hud_model.playback_speed)
        elif button.host_value == "advance_interval":
            icon = f"{hud.advance_interval}s"
        width = button.width
        if button.is_a_name:
            width = max(width, text_width(self._tiny, icon) + BUTTON_GAP)
        return replace(button, icon=icon, width=width)


def with_playback_speed(main_hud_model: MainHudModel, speed: float) -> MainHudModel:
    """*console* with the drawing Funestra's own video rate folded in — Kino knows
    its rate, Fun Time does not publish it, so it is added at draw time."""
    return replace(main_hud_model, playback_speed=speed)
