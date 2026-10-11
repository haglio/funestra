"""The scrubber a Funestra draws along its lower edge, and the loop frames above it.

The track is the whole item, filled with its script's colors where it has one;
while a stretch is being marked out it is a taller strip zoomed into the section
around the mark, so the end of the stretch can be judged.  The frames a running
A/B range starts and ends on sit above their marks.  Pure decisions here, no
pygame: the Funestra turns them into mpv overlays.
"""
from __future__ import annotations

from .heatmap import build_heatmap
from .timeline import TIMELINE_HEIGHT, bar_track_x, bar_x, progress_bar_bgra

__all__: list[str] = []

_ZOOM_SPAN_START_MS = 20_000.0
_ZOOM_LEAD_FRAC = 0.10
_ZOOM_GROW_FRAC = 0.85


class ZoomWindow:
    def __init__(self, *, in_ms: float) -> None:
        self._in_ms = in_ms
        self._span = _ZOOM_SPAN_START_MS

    @property
    def in_ms(self) -> float:
        return self._in_ms

    @property
    def bounds(self) -> tuple[float, float]:
        return self._in_ms - self._span * _ZOOM_LEAD_FRAC, self._in_ms + self._span

    def update(self, position_ms: float) -> None:
        while position_ms > self._grow_at():
            self._span *= 2

    def _grow_at(self) -> float:
        start, end = self.bounds
        return start + (end - start) * _ZOOM_GROW_FRAC


_IDLE_HEIGHT = TIMELINE_HEIGHT
_MARKING_HEIGHT = 48


class HeatmapStrip:
    def __init__(self) -> None:
        self._key: tuple | None = None
        self._colors: list[tuple[int, int, int]] = []
        self._duration_ms = 0.0
        self._zoom: ZoomWindow | None = None

    @property
    def colors(self) -> list[tuple[int, int, int]]:
        return self._colors

    @property
    def height(self) -> int:
        if not self._colors:
            return 0
        return _MARKING_HEIGHT if self._zoom is not None else _IDLE_HEIGHT

    @property
    def window(self) -> tuple[float, float]:
        if self._zoom is not None:
            return self._zoom.bounds
        return 0.0, self._duration_ms

    @property
    def mark_in_ms(self) -> float | None:
        return self._zoom.in_ms if self._zoom is not None else None

    def update(
        self,
        video_key,
        funscript,
        duration_ms: float,
        track_w: int,
        *,
        mark_in_ms: float | None = None,
        position_ms: float = 0.0,
    ) -> None:
        """The colors across a track *track_w* pixels wide, for *video_key*'s
        *funscript*; 0 while no host has measured a track yet, which leaves
        the first row plain."""
        if mark_in_ms is not None and funscript is not None:
            if self._zoom is None:
                self._zoom = ZoomWindow(in_ms=mark_in_ms)
            self._zoom.update(position_ms)
        else:
            self._zoom = None
        self._duration_ms = duration_ms
        if track_w <= 0:
            self._key, self._colors = None, []
            return
        key = (video_key, track_w, self.window)
        if key == self._key:
            return
        self._key = key
        if funscript is None:
            self._colors = []
        else:
            start, end = self.window
            self._colors = build_heatmap(funscript, track_w, start_ms=start, end_ms=end)


def timeline_height(heatmap: HeatmapStrip) -> int:
    return heatmap.height or TIMELINE_HEIGHT


_OUT_CAPTURE_LEAD_MS = 400.0


class LoopThumbCapture:
    def __init__(self) -> None:
        self._bounds: tuple[int, int] | None = None
        self.in_thumb = None
        self.out_thumb = None

    def needed(self, ab_loop: tuple[int, int] | None, position_ms: float) -> str | None:
        if ab_loop is None:
            self._bounds = None
            self.in_thumb = None
            self.out_thumb = None
            return None
        if ab_loop != self._bounds:
            self._bounds = ab_loop
            self.in_thumb = None
            self.out_thumb = None
        if self.in_thumb is None:
            return "in"
        if self.out_thumb is None and position_ms >= ab_loop[1] - _OUT_CAPTURE_LEAD_MS:
            return "out"
        return None

    def set(self, which: str, thumb) -> None:
        if which == "in":
            self.in_thumb = thumb
        elif which == "out":
            self.out_thumb = thumb


def label_xs(in_x: int, out_x: int, in_w: int, out_w: int, win_w: int) -> tuple[int, int]:
    ix = max(0, min(win_w - in_w, in_x - in_w // 2))
    ox = max(0, min(win_w - out_w, out_x - out_w // 2))
    if ox < ix + in_w:
        ox = min(win_w - out_w, ix + in_w + 2)
    return ix, ox


def time_to_x(ms: float, start_ms: float, end_ms: float, width: int) -> int:
    span = end_ms - start_ms
    if span <= 0:
        return 0
    return max(0, min(width - 1, int((ms - start_ms) / span * width)))


def loop_thumbnail_xys(
    heatmap: HeatmapStrip,
    thumbs: LoopThumbCapture,
    bounds: tuple[int, int],
    *,
    track: tuple[int, int],
    win_w: int,
    top: int,
) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
    """Where the loop's in and out frames go: ``(in_xy, out_xy)``, either None
    until that frame has been grabbed.  Each hangs at *top*, lined up with its
    own mark on the inset *track*, kept on screen and stepped apart where they
    would overlap.
    """
    start_ms, end_ms = heatmap.window
    tx0, tx1 = track
    track_w = tx1 - tx0
    in_x = tx0 + time_to_x(bounds[0], start_ms, end_ms, track_w)
    out_x = tx0 + time_to_x(bounds[1], start_ms, end_ms, track_w)
    in_t, out_t = thumbs.in_thumb, thumbs.out_thumb
    ix, ox = label_xs(
        in_x, out_x,
        in_t.shape[1] if in_t is not None else 1,
        out_t.shape[1] if out_t is not None else 1,
        win_w,
    )
    return (
        (ix, top) if in_t is not None else None,
        (ox, top) if out_t is not None else None,
    )


# timeline_x and timeline_bgra are reached only by the headset's old copies of
# the row, in the checkouts from before haglio/fun_time#391; they keep the
# signatures those copies call until none of them is open.
def timeline_x(heatmap: HeatmapStrip, ms: float, width: int) -> int:
    start_ms, end_ms = heatmap.window
    return bar_x(ms - start_ms, end_ms - start_ms, *bar_track_x(width))


def timeline_bgra(heatmap: HeatmapStrip, position_ms: float, loop_bounds, width: int, *,
                  record_in_ms=None):
    start_ms, end_ms = heatmap.window
    return progress_bar_bgra(
        position_ms - start_ms, end_ms - start_ms,
        None if loop_bounds is None else (loop_bounds[0] - start_ms, loop_bounds[1] - start_ms),
        width,
        record_in_ms=None if record_in_ms is None else record_in_ms - start_ms,
        height=timeline_height(heatmap), heatmap=heatmap.colors,
    )
