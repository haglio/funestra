from __future__ import annotations

from typing import NamedTuple

import numpy as np
from shared_ui import palette

from funestra.volume import PLACE_W as _VOLUME_PLACE_W

RED = (*palette.RED, 245)
YELLOW = (*palette.YELLOW, 245)

BAR_INSET_Y = 3
BAR_FILL = (*palette.BG_SECONDARY, 165)
BAR_BORDER = (*palette.BORDER_DEFAULT, 235)
BAR_EDGE = (*palette.BLACK, 235)
HEATMAP_ALPHA_PRESENT_BUT_UNOBTRUSIVE_UNDER_THE_VIDEO = 178
BORDER_W = 2
CURSOR = (*palette.WHITE, 255)
CURSOR_W = 3
MARK_W = 4

SCRUBBER_HEIGHT = 24


def bar_track_x(width: int, *, left: int = 0) -> tuple[int, int]:
    inset = min(left, max(0, width - _VOLUME_PLACE_W - 1))
    return inset, max(inset + 1, width - _VOLUME_PLACE_W)


class Box(NamedTuple):
    x0: int
    x1: int
    y0: int
    y1: int


class TrackMarks(NamedTuple):
    position_ms: float
    duration_ms: float
    loop_bounds: tuple[float, float] | None = None
    record_in_ms: float | None = None


def paint_rect(bgra, box: Box, color):
    h, w = bgra.shape[:2]
    x0, x1 = max(0, box.x0), min(w, box.x1)
    y0, y1 = max(0, box.y0), min(h, box.y1)
    if x1 <= x0 or y1 <= y0:
        return
    bgra[y0:y1, x0:x1] = (color[2], color[1], color[0], color[3])


def _ring(bgra, box: Box, t, color):
    x0, x1, y0, y1 = box
    paint_rect(bgra, Box(x0, x1, y0, y0 + t), color)
    paint_rect(bgra, Box(x0, x1, y1 - t, y1), color)
    paint_rect(bgra, Box(x0, x0 + t, y0, y1), color)
    paint_rect(bgra, Box(x1 - t, x1, y0, y1), color)


def draw_border(bgra, box: Box, bw, color):
    x0, x1, y0, y1 = box
    _ring(bgra, box, 1, BAR_EDGE)
    _ring(bgra, Box(x0 + 1, x1 - 1, y0 + 1, y1 - 1), bw - 1, color)


def _paint_mark(bgra, box: Box, x_center, mark_w, color):
    left = max(box.x0, x_center - mark_w // 2)
    right = min(box.x1, left + mark_w)
    paint_rect(bgra, Box(left, right, box.y0, box.y1), color)


def bar_x(ms, duration_ms, x0, x1):
    frac = min(1.0, max(0.0, ms / max(1.0, duration_ms)))
    return x0 + int(frac * (x1 - x0 - 1))


def framed_track(width, height, track=None):
    bar = np.zeros((height, width, 4), dtype=np.uint8)
    x0, x1 = track or bar_track_x(width)
    return bar, Box(x0, x1, BAR_INSET_Y, height - BAR_INSET_Y)


def draw_track_marks(bgra, box: Box, marks: TrackMarks):
    def mark(ms, mark_w, color):
        x = bar_x(ms, marks.duration_ms, box.x0, box.x1)
        _paint_mark(bgra, box, x, mark_w, (*color[:3], 255))

    if marks.record_in_ms is not None:
        mark(marks.record_in_ms, MARK_W, RED)
    if marks.loop_bounds is not None:
        mark(marks.loop_bounds[0], MARK_W, YELLOW)
        mark(marks.loop_bounds[1], MARK_W, YELLOW)
    mark(marks.position_ms, CURSOR_W, CURSOR)


def progress_bar_bgra(marks: TrackMarks, width, height=SCRUBBER_HEIGHT, *, heatmap=None,
                      track=None):
    bar, box = framed_track(width, height, track)
    if heatmap is None or not len(heatmap):
        paint_rect(bar, box, BAR_FILL)
    else:
        bar[box.y0:box.y1, box.x0:box.x1, :3] = np.asarray(heatmap, dtype=np.uint8)[np.newaxis, :, ::-1]
        bar[box.y0:box.y1, box.x0:box.x1, 3] = HEATMAP_ALPHA_PRESENT_BUT_UNOBTRUSIVE_UNDER_THE_VIDEO
    draw_border(bar, box, BORDER_W, BAR_BORDER)
    draw_track_marks(bar, box, marks)
    return bar
