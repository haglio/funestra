from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, replace

from PIL import Image, ImageDraw
from shared_ui.palette import (
    BLUE,
    GREEN,
    MAGENTA,
    TEXT_MUTED,
    TEXT_PRIMARY,
)
from shared_ui.spacing import BUTTON_GROUP_GAP, BUTTON_PAD_H_TIGHT, GAP_SMALL
from shared_ui.type_scale import SIZE_BODY, SIZE_TINY

from .device_walk import Walk, the_broker_holding, the_hand_taking_back
from .drive_layout import BAR_H, MAX_INTENSITY, DriveTrack, fraction
from .geometry import Rect, contains
from .hud import SYMBOL_FONT, draw_button, load_font, text_width
from .hud_button import BUTTON, Button
from .main_hud import GAP, HELD_HEIGHT, HOLD_VERB, OSR2_PARKED, OSR2_RETRACTED
from .modes import UNHEARD, Osr2State
from .osr2_visualizer import (
    DISABLED_INK,
    DRIVEN_BY_AUTO,
    DRIVEN_BY_FUNSCRIPT,
    DRIVEN_BY_NEUTRAL,
    DRIVEN_BY_NOTHING,
    DRIVEN_BY_ROBOT_HAND,
    DriveHud,
    draw_level_bar,
    trace_ink,
)
from .robot_hand import FULL_INTENSITY, POSITION_MAX

HEIGHT = BUTTON
LABEL = "OSR2"
_LABEL_GAP = GAP_SMALL
_GROUP_GAP = BUTTON_GROUP_GAP
_PILL_PAD = BUTTON_PAD_H_TIGHT

MAX_INTENSITY_LABEL = "Max intensity"
MAX_INTENSITY_TIP = ("Max intensity: all the way up puts no limit on the OSR2; lower, "
                     "its motion gets shorter and slower; all the way down, it stops")
_MAX_INTENSITY_W = 72

BUFFER = "buffer"
_NEUTRAL_PILL = trace_ink(DRIVEN_BY_NEUTRAL)

LABELS = {
    Osr2State.OFF: "Off", Osr2State.AUTO: "Auto", Osr2State.FUNSCRIPT: "FunScript",
    Osr2State.ROBOT_HAND: "Robot Hand", BUFFER: "Buffer",
    Osr2State.UNPLUGGED: "Unplugged", Osr2State.NO_ANSWER: "No answer",
    OSR2_PARKED: "Parked", OSR2_RETRACTED: "Retracted",
}
COLORS = {
    Osr2State.FUNSCRIPT: GREEN, Osr2State.ROBOT_HAND: BLUE, Osr2State.AUTO: MAGENTA,
    Osr2State.OFF: TEXT_MUTED, Osr2State.UNPLUGGED: TEXT_MUTED, Osr2State.NO_ANSWER: TEXT_MUTED,
    BUFFER: _NEUTRAL_PILL,
    OSR2_PARKED: _NEUTRAL_PILL, OSR2_RETRACTED: _NEUTRAL_PILL,
}


def state_for(osr2: str, control: str, *, driving: str = "", paused: bool = False) -> str:
    if osr2 == Osr2State.AUTO or osr2 in UNHEARD:
        return osr2
    return _held_by(control, paused=paused) or driving or osr2


_HELD = (OSR2_PARKED, OSR2_RETRACTED)


def _held_by(control: str, *, paused: bool) -> str | None:
    if control in _HELD:
        return control
    return OSR2_PARKED if paused else None


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


class VisualizerResolver:
    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._still: tuple[tuple[float, ...], int, float, float | None] | None = None
        self._device = _DeviceDot()

    def resolve(self, drive: DriveHud | None, *, osr2: str, control: str,
                composed: bool, paused: bool = False) -> DriveHud | None:
        if drive is None:
            self._still = None
            self._device = _DeviceDot()
            return None
        unheard = osr2 in UNHEARD
        if osr2 == Osr2State.AUTO:
            drive = replace(drive, driven=DRIVEN_BY_AUTO, segments=())
        elif unheard:
            drive = replace(drive, driven=DRIVEN_BY_NOTHING, segments=())
        elif control in _HELD:
            drive = replace(drive, segments=(), driven=DRIVEN_BY_NEUTRAL)
        elif not (composed and drive.segments):
            drive = replace(drive, driven=_DRIVEN_BY_OSR2.get(osr2, DRIVEN_BY_NOTHING))
        held_or_off = osr2 != Osr2State.AUTO and (control in _HELD or unheard)
        if held_or_off or not (drive.live or composed):
            if self._still is None:
                self._still = (drive.waveform, drive.position, drive.slide, drive.edge)
            waveform, position, slide, edge = self._still
            drive = replace(drive, waveform=waveform, position=position,
                            segments=(), slide=slide, edge=edge)
        else:
            self._still = None
        if osr2 == Osr2State.AUTO:
            self._device = _DeviceDot()
            return drive
        held = None if unheard else _held_by(control, paused=paused)
        return replace(drive, position=self._device.at(
            self._clock(), drive.position, held=held, switched_on=not unheard))


class _DeviceDot:
    def __init__(self) -> None:
        self._height: float | None = None
        self._held: str | None = None
        self._walk: Walk | None = None

    def at(self, now: float, drawn: int, *, held: str | None, switched_on: bool) -> int:
        line = drawn / POSITION_MAX
        if not switched_on:
            self._held, self._walk = None, None
            height = line if self._height is None else self._height
        elif held is not None:
            if held != self._held:
                start = line if self._height is None else self._height
                self._walk = the_broker_holding(start, now, HOLD_VERB[held])
                self._held = held
            height = self._walk.height_at(now, HELD_HEIGHT[held])
        else:
            if self._held is not None:
                start = HELD_HEIGHT[self._held] if self._height is None else self._height
                self._walk = the_hand_taking_back(start, now)
                self._held = None
            if self._walk is not None and now >= self._walk.began + self._walk.wait_s + self._walk.over_s:
                self._walk = None
            height = line if self._walk is None else self._walk.height_at(now, line)
        self._height = height
        return round(height * POSITION_MAX)


@dataclass(frozen=True)
class Osr2Line:
    state: str = Osr2State.OFF
    controls: tuple[Button, ...] = ()
    max_intensity: int | None = None


class Osr2Section:
    def __init__(self) -> None:
        self._tiny = load_font(SIZE_TINY)
        self._icon = load_font(SIZE_BODY, SYMBOL_FONT)

    def width(self, line: Osr2Line) -> int:
        return (self._controls_width(line.controls)
                + text_width(self._tiny, LABEL) + _LABEL_GAP
                + self._widest_word + _PILL_PAD
                + self._max_intensity_width(line))

    def draw(self, image: Image.Image, draw: ImageDraw.ImageDraw, at: tuple[int, int],
             line: Osr2Line, *, hover: tuple[int, int] | None = None,
             ) -> list[tuple[Rect, Button]]:
        x, y = at
        placed: list[tuple[Rect, Button]] = []
        run_x = x
        for button in line.controls:
            rect = (run_x, y, button.width, HEIGHT)
            draw_button(image, draw, rect, button,
                        hovered=hover is not None and contains(rect, *hover),
                        icon_font=self._icon, word_font=self._tiny)
            placed.append((rect, button))
            run_x += button.width + GAP

        label_x = x + self._controls_width(line.controls)
        draw.text((label_x, y + HEIGHT / 2), LABEL, font=self._tiny, anchor="lm",
                  fill=(*TEXT_MUTED, 255))
        word = LABELS.get(line.state, line.state)
        color = COLORS.get(line.state, TEXT_PRIMARY)
        pill_x = label_x + text_width(self._tiny, LABEL) + _LABEL_GAP
        draw.text((pill_x + _PILL_PAD // 2, y + HEIGHT / 2), word,
                  font=self._tiny, anchor="lm", fill=(*color, 255))
        for bar in self.bars(x, y, line):
            self._draw_max_intensity(draw, bar, line.max_intensity)
            placed.append((bar.rect, Button("", "", bar.tooltip)))
        return placed

    def _draw_max_intensity(self, draw: ImageDraw.ImageDraw, bar: DriveTrack, max_intensity: int) -> None:
        bx, by, bw, _bh = bar.rect
        mid = by + HEIGHT // 2
        number_x = bx - _LABEL_GAP - self._widest_number
        draw.text((number_x - _LABEL_GAP, mid), MAX_INTENSITY_LABEL, font=self._tiny, anchor="rm",
                  fill=(*TEXT_MUTED, 255))
        draw.text((number_x, mid), str(max_intensity), font=self._tiny, anchor="lm",
                  fill=DISABLED_INK if bar.dim else (*TEXT_PRIMARY, 255))
        draw_level_bar(draw, (bx, mid - BAR_H // 2, bw, BAR_H), fill=fraction(max_intensity),
                       color=DISABLED_INK if bar.dim else (*BLUE, 255))

    @staticmethod
    def _controls_width(controls: tuple[Button, ...]) -> int:
        if not controls:
            return 0
        return sum(b.width for b in controls) + GAP * (len(controls) - 1) + _GROUP_GAP

    def bars(self, x: int, y: int, line: Osr2Line) -> list[DriveTrack]:
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
