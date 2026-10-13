"""The device's own line: who has the OSR2, and the controls that aim it.

Every panel whose host drives the device draws this line, so the word for a
parked OSR2 is the same word wherever it is read — the Main Funestra's console
(:mod:`funestra.console_hud`) and a HUD over a host that drives it itself
(:mod:`funestra.satellite_hud_paint`) share this one rather than each
spelling the states again.

The controls sit together at the head of the line because they act on the
device rather than on any Funestra: placed by hand rather than through the row
layout, which would read them as different families and open a gap between
them.  The label then hugs its pill, well clear of them, so "OSR2 Robot Hand"
reads as one read-out instead of as another button.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from PIL import Image, ImageDraw
from shared_ui.palette import (
    BLUE,
    GREEN,
    MAGENTA,
    RED,
    TEXT_MUTED,
    TEXT_PRIMARY,
)

from .console import GAP, HELD_HEIGHT, OSR2_CONTROL_OFF, OSR2_PARKED, OSR2_RETRACTED
from .drive_layout import BAR_H, MAX_INTENSITY, DriveTrack, fraction
from .drive_readout import (
    DISABLED_INK,
    DRIVEN_BY_AUTO,
    DRIVEN_BY_FUNSCRIPT,
    DRIVEN_BY_NEUTRAL,
    DRIVEN_BY_NOTHING,
    DRIVEN_BY_ROBOT_HAND,
    POSITION_MAX,
    DriveHud,
    draw_level_bar,
)
from .geometry import Rect, contains
from .hud_button import BUTTON, Button
from .hud_panel import SYMBOL_FONT, draw_button, load_font, text_width
from .modes import Osr2State
from .robot_hand import FULL_INTENSITY

# Package-internal: the two panels that draw this line are both in here, and a
# host says what its line shows through the model it already hands over
# (:class:`funestra.console.ConsoleModel`,
# :class:`funestra.satellite_hud.HudModel`) rather than by building one.
__all__: list[str] = []

# The line is as deep as the controls sharing it.
HEIGHT = BUTTON
LABEL = "OSR2"
_LABEL_GAP = 5   # "OSR2" sits right up against the pill it names …
_GROUP_GAP = 16  # … and well clear of the controls beside them
_PILL_PAD = 10   # the room the state word keeps either side of itself

_SIZE_BODY = 11
_SIZE_TINY = 8

MAX_INTENSITY_LABEL = "Max intensity"
MAX_INTENSITY_TIP = ("Max intensity: all the way up puts no limit on the OSR2; lower, "
                     "its motion gets shorter and slower; all the way down, it stops")
_MAX_INTENSITY_W = 72

# The pill's own word for a device that belongs to neither driver at the
# playhead -- drawn, never published, so it is not one of the wire's states.
BUFFER = "buffer"
# The buffer pill wears the trace's own neutral gray, so the word and the line
# under the dot are visibly the same state.
_NEUTRAL_PILL = (168, 168, 174)

LABELS = {
    Osr2State.OFF: "Off", Osr2State.AUTO: "Auto", Osr2State.FUNSCRIPT: "FunScript",
    Osr2State.ROBOT_HAND: "Robot Hand", BUFFER: "Buffer",
    # Said in three words because two of them would be read as the device: the
    # OSR2 is on and well, this app has simply stopped sending it anything.  In
    # the red its own button wears, so the lit control and the pill saying what
    # it did are visibly the one fact.
    OSR2_CONTROL_OFF: "Control off",
    OSR2_PARKED: "Parked", OSR2_RETRACTED: "Retracted",
}
COLORS = {
    Osr2State.FUNSCRIPT: GREEN, Osr2State.ROBOT_HAND: BLUE, Osr2State.AUTO: MAGENTA,
    Osr2State.OFF: TEXT_MUTED, BUFFER: _NEUTRAL_PILL,
    OSR2_CONTROL_OFF: RED,
    # The held device's line is the handoff's gray -- nobody is moving it -- and
    # the word beside it says so in the same ink.
    OSR2_PARKED: _NEUTRAL_PILL, OSR2_RETRACTED: _NEUTRAL_PILL,
}


def state_for(osr2: str, control: str, *, driving: str = "") -> str:
    """Who the pill names, given what the wire says has the device (*osr2*) and
    what this app is doing to it (*control*).

    One precedence wherever the line is drawn.  The device running its own
    firmware wins over everything the room does to it: no hold, no let-go and no
    handoff reaches it.  Then a hold or a let-go, because there is nobody
    driving to name and what the reader needs is why.  Only then the driver —
    *driving* where the panel has a better answer than the round-tripped one
    (the main console reads it off the trace it actually drew), the wire's
    otherwise.
    """
    if osr2 == Osr2State.AUTO:
        return osr2
    if control in (OSR2_CONTROL_OFF, OSR2_PARKED, OSR2_RETRACTED):
        return control
    return driving or osr2


_OSR2_AT_THE_PLAYHEAD = {
    DRIVEN_BY_ROBOT_HAND: Osr2State.ROBOT_HAND,
    DRIVEN_BY_FUNSCRIPT: Osr2State.FUNSCRIPT,
    DRIVEN_BY_NEUTRAL: BUFFER,
}


def driving_at_the_playhead(composed: DriveHud | None, osr2: str) -> str:
    if composed is None:
        return ""
    return _OSR2_AT_THE_PLAYHEAD.get(composed.driven, osr2)


_DRIVEN_BY_OSR2 = {
    Osr2State.ROBOT_HAND: DRIVEN_BY_ROBOT_HAND,
    Osr2State.FUNSCRIPT: DRIVEN_BY_FUNSCRIPT,
    Osr2State.AUTO: DRIVEN_BY_AUTO,
}


class ReadoutResolver:
    """The readout under the line, drawn by the same precedence as the pill."""

    def __init__(self) -> None:
        self._still: tuple[tuple[float, ...], int, float, float | None] | None = None

    def resolve(self, drive: DriveHud | None, *, osr2: str, control: str,
                composed: bool) -> DriveHud | None:
        if drive is None:
            self._still = None
            return None
        # Genau cannot see the handoff, so whoever draws the readout tells it
        # who has the device.  Anything but Genau dims every control on it:
        # adjusting a motion Genau is not sending is what woke it against the
        # funscript.
        # Not where a composed trace already names who has the device at the
        # playhead — set by the same function that drew the line under the dot —
        # since the round trip lags the arbiter, and the arbiter itself decides
        # seconds before the device is done riding the blue.
        held = HELD_HEIGHT.get(control)
        if osr2 == Osr2State.AUTO:
            # The device is running its own firmware, and that wins over
            # everything the room does to it: a hold, a let-go, a handoff
            # between two drivers.  None of those reaches it, so none is the
            # picture — one line, the device's own, in its own color.
            drive = replace(drive, driven=DRIVEN_BY_AUTO, segments=())
        elif held is not None:
            # The device is being kept at one end, so that is the picture: a
            # flat line there with the dot on it, in the gray of a device nobody
            # is moving.  Whatever the motion or the script had planned is not
            # reaching it, and drawn it would be a picture of a device in motion.
            drive = replace(
                drive, waveform=(held,) * len(drive.waveform or (0.0,)),
                position=round(held * POSITION_MAX), segments=(), slide=0.0,
                edge=None, let_go=None, driven=DRIVEN_BY_NEUTRAL)
        elif control == OSR2_CONTROL_OFF:
            # Nothing is going out, so nobody has the device — whatever the
            # round trip or the composed trace last said had it.  The trace's own
            # names go with it: a kino-mode plan says who has the device at each
            # knot, and kept, they drew the line in the script's green under a
            # word that read "control off".
            drive = replace(drive, driven=DRIVEN_BY_NOTHING, segments=())
        elif not (composed and drive.segments):
            drive = replace(drive, driven=_DRIVEN_BY_OSR2.get(osr2, DRIVEN_BY_NOTHING))
        # A composed trace is the script's plan, computed fresh per frame from
        # the playhead: it keeps sliding through every rest and every handoff
        # whatever the OSR2 state says, because the rests ARE part of what it
        # draws — freezing it on the round-tripped "off" was the picture that
        # stopped scrolling for the length of each gap.  Anything else is
        # Genau's own resampled motion, which goes on moving while nobody is
        # sending it, and the slide freezes with it or the "still" trace would
        # go on creeping left a fraction of a sample at a time.
        if not drive.live and (control == OSR2_CONTROL_OFF or not composed):
            if self._still is None:
                self._still = (drive.waveform, drive.position, drive.slide, drive.edge)
            waveform, position, slide, edge = self._still
            return replace(drive, waveform=waveform, position=position,
                           segments=(), slide=slide, edge=edge)
        self._still = None
        return drive


@dataclass(frozen=True)
class Osr2Line:
    """What the line says: which driver has the device, and the controls a
    source put on it.

    *state* is already resolved by whoever is drawing — one of
    :class:`~funestra.modes.Osr2State`, :data:`BUFFER`, or one of the
    control states — because what has the device is a different question on
    every panel and only the host can answer it.
    """

    state: str = Osr2State.OFF
    controls: tuple[Button, ...] = ()
    max_intensity: int | None = None


class Osr2Section:
    """The line itself, drawn into whatever panel is hosting it."""

    def __init__(self) -> None:
        self._tiny = load_font(_SIZE_TINY)
        self._glyph = load_font(_SIZE_BODY, SYMBOL_FONT)

    def width(self, line: Osr2Line) -> int:
        """How wide the line runs — a floor on the panel holding it."""
        return (self._controls_width(line.controls)
                + text_width(self._tiny, LABEL) + _LABEL_GAP
                + self._widest_word + _PILL_PAD
                + self._max_intensity_width(line))

    def draw(self, image: Image.Image, draw: ImageDraw.ImageDraw, x: int, y: int,
             line: Osr2Line, *, hover: tuple[int, int] | None = None,
             ) -> list[tuple[Rect, Button]]:
        """Paint the line with its top-left corner at ``(x, y)``, and hand back
        where each control landed so a press finds exactly what was drawn."""
        placed: list[tuple[Rect, Button]] = []
        run_x = x
        for button in line.controls:
            rect = (run_x, y, button.width, HEIGHT)
            draw_button(image, draw, rect, button,
                        hovered=hover is not None and contains(rect, *hover),
                        glyph_font=self._glyph, word_font=self._tiny)
            placed.append((rect, button))
            run_x += button.width + GAP

        label_x = x + self._controls_width(line.controls)
        draw.text((label_x, y + HEIGHT / 2), LABEL, font=self._tiny, anchor="lm",
                  fill=(*TEXT_MUTED, 255))
        word = LABELS.get(line.state, line.state)
        color = COLORS.get(line.state, TEXT_PRIMARY)
        pill_x = label_x + text_width(self._tiny, LABEL) + _LABEL_GAP
        # No frame around it: what has the device is a read-out, and an outlined
        # word beside two real buttons reads as a third one you can press.
        draw.text((pill_x + _PILL_PAD // 2, y + HEIGHT / 2), word,
                  font=self._tiny, anchor="lm", fill=(*color, 255))
        for band in self.bands(x, y, line):
            self._draw_max_intensity(draw, band, line.max_intensity)
            placed.append((band.rect, Button("", "", band.tooltip)))
        return placed

    def _draw_max_intensity(self, draw: ImageDraw.ImageDraw, band: DriveTrack, max_intensity: int) -> None:
        bx, by, bw, _bh = band.rect
        mid = by + HEIGHT // 2
        number_x = bx - _LABEL_GAP - self._widest_number
        draw.text((number_x - _LABEL_GAP, mid), MAX_INTENSITY_LABEL, font=self._tiny, anchor="rm",
                  fill=(*TEXT_MUTED, 255))
        draw.text((number_x, mid), str(max_intensity), font=self._tiny, anchor="lm",
                  fill=DISABLED_INK if band.dim else (*TEXT_PRIMARY, 255))
        draw_level_bar(draw, (bx, mid - BAR_H // 2, bw, BAR_H), fill=fraction(max_intensity),
                       color=DISABLED_INK if band.dim else (*BLUE, 255))

    @staticmethod
    def _controls_width(controls: tuple[Button, ...]) -> int:
        """The controls' run and the gap after it -- nothing at all for a line
        with no controls, whose label then starts where they would have."""
        if not controls:
            return 0
        return sum(b.width for b in controls) + GAP * (len(controls) - 1) + _GROUP_GAP

    def bands(self, x: int, y: int, line: Osr2Line) -> list[DriveTrack]:
        if line.max_intensity is None:
            return []
        return [DriveTrack(
            (x + self.width(line) - _MAX_INTENSITY_W, y, _MAX_INTENSITY_W, HEIGHT), MAX_INTENSITY,
            MAX_INTENSITY_TIP, dim=line.state == Osr2State.AUTO)]

    def _max_intensity_width(self, line: Osr2Line) -> int:
        if line.max_intensity is None:
            return 0
        return (_GROUP_GAP + text_width(self._tiny, MAX_INTENSITY_LABEL) + _LABEL_GAP
                + self._widest_number + _LABEL_GAP + _MAX_INTENSITY_W)

    @property
    def _widest_number(self) -> int:
        return text_width(self._tiny, str(FULL_INTENSITY))

    @property
    def _widest_word(self) -> int:
        return max(text_width(self._tiny, word) for word in LABELS.values())
