"""The scrubber every Funestra in this family draws along the lower edge of its video.

An inset, floated, bordered track with a full-height playcursor and loop/record
marks, filled with the colors of the video's funscript where it has one and
with a dark translucent fill where it has none.  Every Funestra draws it, in
separate processes and separate repos, so the whole of it lives here.

The track starts where the row's visualizer and dial end (``bar_track_x`` is told
how far in by the row that lays them out) and stops short of the volume control
that shares its row — it subtracts :data:`funestra.volume.SLOT_W` — so none
of them overlap and click-to-seek maps onto exactly the drawn track.  These
are plain numpy arrays (BGRA, mpv's overlay format); no pygame.
"""
from __future__ import annotations

import numpy as np
from shared_ui import palette

from funestra.volume import PLACE_W as _VOLUME_PLACE_W

RED = (*palette.RED, 245)
YELLOW = (*palette.YELLOW, 245)

BAR_INSET_Y = 3
BAR_FILL = (*palette.BG_SECONDARY, 165)
BAR_BORDER = (*palette.BORDER_DEFAULT, 235)
BAR_EDGE = (*palette.BLACK, 235)
HEATMAP_ALPHA = 178
BORDER_W = 2
CURSOR = (*palette.WHITE, 255)
CURSOR_W = 3
MARK_W = 4

SCRUBBER_HEIGHT = 24


def bar_track_x(width: int, *, left: int = 0) -> tuple[int, int]:
    inset = min(left, max(0, width - _VOLUME_PLACE_W - 1))
    return inset, max(inset + 1, width - _VOLUME_PLACE_W)


def paint_rect(bgra, x0, x1, y0, y1, color):
    """Fill rows [y0:y1], cols [x0:x1] with an RGBA ``color``, clamped to the
    array (stored BGRA for mpv)."""
    h, w = bgra.shape[:2]
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 <= x0 or y1 <= y0:
        return
    bgra[y0:y1, x0:x1] = (color[2], color[1], color[0], color[3])


def _ring(bgra, x0, x1, y0, y1, t, color):
    paint_rect(bgra, x0, x1, y0, y0 + t, color)
    paint_rect(bgra, x0, x1, y1 - t, y1, color)
    paint_rect(bgra, x0, x0 + t, y0, y1, color)
    paint_rect(bgra, x1 - t, x1, y0, y1, color)


def draw_border(bgra, x0, x1, y0, y1, bw, color):
    _ring(bgra, x0, x1, y0, y1, 1, BAR_EDGE)
    _ring(bgra, x0 + 1, x1 - 1, y0 + 1, y1 - 1, bw - 1, color)


def _paint_mark(bgra, x_center, mark_w, y0, y1, color, *, x_lo, x_hi):
    left = max(x_lo, x_center - mark_w // 2)
    right = min(x_hi, left + mark_w)
    paint_rect(bgra, left, right, y0, y1, color)


def bar_x(ms, duration_ms, x0, x1):
    frac = min(1.0, max(0.0, ms / max(1.0, duration_ms)))
    return x0 + int(frac * (x1 - x0 - 1))


def framed_track(width, height, track=None):
    bar = np.zeros((height, width, 4), dtype=np.uint8)
    x0, x1 = track or bar_track_x(width)
    return bar, x0, x1, BAR_INSET_Y, height - BAR_INSET_Y


def draw_track_marks(bgra, *, x0, x1, y0, y1, to_x, position_ms,
                     loop_bounds, record_in_ms):
    def mark(ms, mark_w, color):
        _paint_mark(bgra, to_x(ms), mark_w, y0, y1, (*color[:3], 255),
                    x_lo=x0, x_hi=x1)

    if record_in_ms is not None:
        mark(record_in_ms, MARK_W, RED)
    if loop_bounds is not None:
        mark(loop_bounds[0], MARK_W, YELLOW)
        mark(loop_bounds[1], MARK_W, YELLOW)
    mark(position_ms, CURSOR_W, CURSOR)


def progress_bar_bgra(position_ms, duration_ms, loop_bounds, width,
                      record_in_ms=None, height=SCRUBBER_HEIGHT, *, heatmap=None,
                      track=None):
    bar, x0, x1, y0, y1 = framed_track(width, height, track)
    if heatmap is None or not len(heatmap):
        paint_rect(bar, x0, x1, y0, y1, BAR_FILL)
    else:
        bar[y0:y1, x0:x1, :3] = np.asarray(heatmap, dtype=np.uint8)[np.newaxis, :, ::-1]
        bar[y0:y1, x0:x1, 3] = HEATMAP_ALPHA
    draw_border(bar, x0, x1, y0, y1, BORDER_W, BAR_BORDER)
    draw_track_marks(
        bar, x0=x0, x1=x1, y0=y0, y1=y1,
        to_x=lambda ms: bar_x(ms, duration_ms, x0, x1),
        position_ms=position_ms, loop_bounds=loop_bounds, record_in_ms=record_in_ms,
    )
    return bar
