from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

import numpy as np
from PIL import Image
from shared_ui.spacing import GAP_SMALL

from .loop_dial import DIAL_SIZE, LoopDialPainter, on_dial, turn_at
from .playhead import (
    PlayheadHud,
    PlayheadHudPainter,
    framed_playhead,
    time_text_width,
    video_playhead,
)
from .scrub import Scrub
from .scrubber_bar import (
    SCRUBBER_HEIGHT,
    TrackMarks,
    bar_track_x,
    progress_bar_bgra,
    time_at_x,
)
from .volume import (
    PLACE_W,
    VOLUME_CONTROL_H,
    VolumeHud,
    VolumeHudPainter,
    hit_part,
    volume_at,
    volume_control_local,
    volume_control_xy,
)

SCRUBBER = "scrubber"
TIME_TEXT = "readout"
MUTE = "mute"
VOLUME = "volume"
DIAL = "dial"

_CHIP_PARTS = {"mute": MUTE, "track": VOLUME}

ROW_H = SCRUBBER_HEIGHT
PARTS_Y = (ROW_H - VOLUME_CONTROL_H) // 2
GAP = GAP_SMALL

LEAST_TRACK = 60
FLICK_TRACK_W = 96

UNDER_THE_HUD_GAP = GAP_SMALL

_HELD_FLICK_TIME_TEXT = framed_playhead(999, 999, 599_000, 599_000)
_HELD_VIDEO_TIME_TEXT = video_playhead(3_599_000, 3_599_000, 60.0)


@dataclass(frozen=True)
class RowHud:
    position_ms: float = 0.0
    duration_ms: float = 0.0
    volume: VolumeHud | None = None
    playhead: PlayheadHud | None = None
    loop_bounds: tuple[float, float] | None = None
    record_in_ms: float | None = None
    loop: tuple[int, int] | None = None


class ScrubberRowDraw(NamedTuple):
    row: RowHud
    heatmap: object = None



@dataclass(frozen=True)
class RowLayout:
    rect: tuple[int, int, int, int]
    time_text: tuple[int, int] | None
    dial: int | None
    track: tuple[int, int]

    @property
    def width(self) -> int:
        return self.rect[2]

    def inside(self, px: int, py: int) -> bool:
        x, y, width, height = self.rect
        return x <= px < x + width and y <= py < y + height

    def local(self, px: int, py: int) -> tuple[int, int]:
        return px - self.rect[0], py - self.rect[1]


def _before_the_track(row: RowHud, *, held: bool = False) -> tuple[
        tuple[int, int] | None, int | None, int]:
    x = 0
    time_text = dial = None
    if row.loop is not None:
        dial = x
        x += DIAL_SIZE + GAP
    held_for = None
    if held:
        held_for = _HELD_VIDEO_TIME_TEXT if row.loop is None else _HELD_FLICK_TIME_TEXT
    if row.playhead is not None or held_for is not None:
        width = _width(row.playhead or held_for, held_for)
        time_text = (x, width)
        x += width + GAP
    return time_text, dial, x


def _width(time_text: PlayheadHud, held_for: PlayheadHud | None) -> int:
    width = time_text_width(time_text)
    return width if held_for is None else max(width, time_text_width(held_for))


def row_layout(row: RowHud, *, rect: tuple[int, int, int, int]) -> RowLayout:
    time_text, dial, left = _before_the_track(row)
    x0, x1 = bar_track_x(rect[2], left=left)
    if row.loop is not None:
        x1 = min(x1, x0 + FLICK_TRACK_W)
    return RowLayout(rect, time_text, dial, (x0, x1))


class RowSection:
    def __init__(self) -> None:
        self._volume = VolumeHudPainter()
        self._time_text = PlayheadHudPainter()
        self._dial = LoopDialPainter()
        self._heatmap: tuple[object, np.ndarray | None] = (None, None)

    @staticmethod
    def least_width(row: RowHud) -> int:
        before = _before_the_track(row, held=True)[2]
        if row.loop is not None:
            return before + LEAST_TRACK + PLACE_W
        return 2 * (before + PLACE_W)

    def draw(self, image: Image.Image, layout: RowLayout, row: RowHud,
             *, heatmap: np.ndarray | None = None) -> None:
        x, y, width, _height = layout.rect
        marks = TrackMarks(row.position_ms, row.duration_ms, row.loop_bounds, row.record_in_ms)
        bar = progress_bar_bgra(marks, width, heatmap=self._as_an_array(heatmap, layout.track),
                                track=layout.track)
        image.alpha_composite(_rgba(bar), (x, y))
        if row.volume is not None:
            image.alpha_composite(self._volume.image(row.volume), _offset(
                (x, y), volume_control_xy(viewport_w=width, viewport_h=ROW_H, timeline_h=ROW_H)))
        if layout.dial is not None:
            played, count = row.loop
            image.alpha_composite(self._dial.image(LoopDialPainter.hand(played / count)),
                                  (x + layout.dial, y + PARTS_Y))
        if layout.time_text is not None:
            image.alpha_composite(self._time_text.image(row.playhead),
                                  (x + layout.time_text[0], y + PARTS_Y))


    def _as_an_array(self, heatmap, track: tuple[int, int]) -> np.ndarray | None:
        if fitting(heatmap, track) is None:
            return None
        if self._heatmap[0] is not heatmap:
            self._heatmap = (heatmap, colors_as_an_array(heatmap))
        return self._heatmap[1]


def colors_as_an_array(heatmap) -> np.ndarray:
    return np.asarray(heatmap, dtype=np.uint8)


def fitting(heatmap, track: tuple[int, int]):
    if heatmap is None or not len(heatmap):
        return None
    x0, x1 = track
    return heatmap if len(heatmap) == x1 - x0 else None


def track_on_screen(layout: RowLayout | None, *, origin: tuple[int, int],
                    hud_height: int) -> tuple[int, int, int] | None:
    if layout is None:
        return None
    left, top = origin
    x0, x1 = layout.track
    return (left + layout.rect[0] + x0, left + layout.rect[0] + x1,
            top + hud_height + UNDER_THE_HUD_GAP)


def _rgba(bgra: np.ndarray) -> Image.Image:
    return Image.fromarray(np.ascontiguousarray(bgra[:, :, [2, 1, 0, 3]]), "RGBA")


def _offset(origin: tuple[int, int], place: tuple[int, int]) -> tuple[int, int]:
    return origin[0] + place[0], origin[1] + place[1]


def row_part(px: int, py: int, layout: RowLayout) -> str:
    if not 0 <= py < ROW_H:
        return ""
    part = hit_part(*volume_control_local(px, py, viewport_w=layout.width, viewport_h=ROW_H, timeline_h=ROW_H))
    if part:
        return _CHIP_PARTS[part]
    if layout.dial is not None and on_dial(px, py, at=(layout.dial, PARTS_Y)):
        return DIAL
    return TIME_TEXT if px < layout.track[0] else SCRUBBER


class RowPress:
    def __init__(self, *, seek=None, seek_loop=None, set_volume=None, toggle_mute=None,
                 hold=None) -> None:
        self._scrub = Scrub(seek=seek or _nothing, hold=hold or _nothing)
        self._seek_loop = seek_loop
        self._set_volume = set_volume
        self._toggle_mute = toggle_mute
        self._holding = ""

    @property
    def holding(self) -> bool:
        return bool(self._holding)

    def press(self, px: int, py: int, *, layout: RowLayout | None, duration_ms: float) -> bool:
        if layout is None or not layout.inside(px, py):
            return False
        self._holding = row_part(*layout.local(px, py), layout)
        if not self._holding:
            return False
        self._act(px, py, layout=layout, duration_ms=duration_ms)
        return True

    def drag_to(self, px: int, py: int, *, layout: RowLayout | None, duration_ms: float) -> bool:
        if layout is None or self._holding not in (SCRUBBER, DIAL, VOLUME):
            return False
        self._act(px, py, layout=layout, duration_ms=duration_ms)
        return True

    def release(self) -> None:
        self._holding = ""
        self._scrub.release()

    def _act(self, px: int, py: int, *, layout: RowLayout, duration_ms: float) -> None:
        px, py = layout.local(px, py)
        if self._holding == SCRUBBER:
            moment = scrub_to(px, layout, duration_ms=duration_ms)
            (self._scrub.drag if self._scrub.held else self._scrub.press)(moment)
        elif self._holding == DIAL and self._seek_loop is not None:
            self._seek_loop(turn_to(px, py, layout))
        elif self._holding == VOLUME and self._set_volume is not None:
            self._set_volume(volume_to(px, py, layout))
        elif self._holding == MUTE and self._toggle_mute is not None:
            self._toggle_mute()


def _nothing(_value) -> None:
    pass


def scrub_to(px: int, layout: RowLayout, *, duration_ms: float) -> float:
    return time_at_x(px, duration_ms, *layout.track)


def volume_to(px: int, py: int, layout: RowLayout) -> int:
    return volume_at(volume_control_local(px, py, viewport_w=layout.width, viewport_h=ROW_H, timeline_h=ROW_H)[0])


def turn_to(px: int, py: int, layout: RowLayout) -> float:
    return turn_at(px, py, at=(layout.dial, PARTS_Y))
