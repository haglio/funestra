from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from shared_ui.palette import BLACK, WHITE
from shared_ui.spacing import MARGIN_STANDARD
from shared_ui.type_scale import SIZE_HEADING

from .hud import load_font, text_width, to_bgra

BACKDROP_OVERLAY_ID = 1
FIRST_TILE_OVERLAY_ID = 2
LOADING_OVERLAY_ID = 6

SCALED_FRAMES_BYTES = 3 * 1024 * 1024 * 1024
_SCALING_THREADS = 3

_LOADING_PAD = MARGIN_STANDARD
_LOADING_INSET = MARGIN_STANDARD
_LOADING_GROUND = (*BLACK, 180)


def _nothing(_value: float) -> None:
    pass


@dataclass(frozen=True)
class FlickFrame:
    frame: np.ndarray | None
    played: int = 0
    count: int = 0
    elapsed_ms: float = 0.0
    interval_ms: float = 0.0
    loading: str | None = None
    seek_time: Callable[[float], None] = _nothing
    seek_loop: Callable[[float], None] = _nothing
    flick: Path | None = None
    frames: Sequence[np.ndarray] = ()


def black_bgra(width: int, height: int) -> np.ndarray:
    frame = np.zeros((max(1, height), max(1, width), 4), dtype=np.uint8)
    frame[:, :, 3] = 255
    return frame


def tile_rects(frame_size: tuple[int, int], viewport: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    frame_w, frame_h = frame_size
    viewport_w, viewport_h = viewport
    tile_h = viewport_h
    tile_w = int(frame_w * (viewport_h / frame_h))
    if tile_w > viewport_w:
        tile_w = viewport_w
        tile_h = int(frame_h * (viewport_w / frame_w))
    tiles = max(1, viewport_w // max(1, tile_w)) if frame_h > frame_w else 1
    margin = (viewport_w - tile_w * tiles) // 2
    y = (viewport_h - tile_h) // 2
    return [(margin + i * tile_w, y, tile_w, tile_h) for i in range(tiles)]


def scaled_bgra(frame: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    image = Image.fromarray(frame, "RGB").resize(size, Image.Resampling.BILINEAR).convert("RGBA")
    return np.frombuffer(image.tobytes("raw", "BGRA"), dtype=np.uint8).reshape(size[1], size[0], 4)


def loading_message_bgra(text: str) -> np.ndarray:
    font = load_font(SIZE_HEADING)
    ascent, descent = font.getmetrics()
    image = Image.new("RGBA", (text_width(font, text) + 2 * _LOADING_PAD,
                               ascent + descent + 2 * _LOADING_PAD), _LOADING_GROUND)
    ImageDraw.Draw(image).text((_LOADING_PAD, _LOADING_PAD), text, font=font, fill=(*WHITE, 255))
    return to_bgra(image)


class _ScalingThreads:
    def __init__(self) -> None:
        self._threads: ThreadPoolExecutor | None = None

    def __call__(self, job: Callable[[], None]) -> None:
        if self._threads is None:
            self._threads = ThreadPoolExecutor(_SCALING_THREADS, thread_name_prefix="genau-scale")
        self._threads.submit(job)


@dataclass(frozen=True)
class _Showing:
    flick: Path | None
    count: int
    size: tuple[int, int]


class _ScaledFrames:
    def __init__(self, limit_bytes: int, off_the_window_s_thread: Callable[[Callable[[], None]], None]) -> None:
        self._limit = limit_bytes
        self._off_the_window_s_thread = off_the_window_s_thread
        self._lock = threading.Lock()
        self._showing: _Showing | None = None
        self._kept: dict[int, tuple[np.ndarray, np.ndarray]] = {}
        self._asked_ahead = False

    def __len__(self) -> int:
        return len(self._kept)

    def holds(self, frame: np.ndarray) -> bool:
        return id(frame) in self._kept

    def let_go(self) -> None:
        if self._showing is None:
            return
        with self._lock:
            self._showing, self._kept, self._asked_ahead = None, {}, False

    def get(self, flick_frame: FlickFrame, size: tuple[int, int]) -> np.ndarray:
        frame = flick_frame.frame
        showing = _Showing(flick_frame.flick, flick_frame.count, size)
        with self._lock:
            if showing != self._showing:
                self._showing, self._kept, self._asked_ahead = showing, {}, False
            kept = self._kept.get(id(frame))
        scaled = self._scale_and_keep(frame, showing) if kept is None else kept[1]
        if flick_frame.frames and not self._asked_ahead:
            self._asked_ahead = True
            self._scale_ahead(flick_frame, showing, scaled.nbytes)
        return scaled

    def _scale_and_keep(self, frame: np.ndarray, showing: _Showing) -> np.ndarray:
        scaled = scaled_bgra(frame, showing.size)
        with self._lock:
            if showing == self._showing and self._has_room_for(scaled.nbytes, showing.count):
                self._kept.setdefault(id(frame), (frame, scaled))
        return scaled

    def _has_room_for(self, frame_bytes: int, count: int) -> bool:
        return max(count, len(self._kept) + 1) * frame_bytes <= self._limit

    def _scale_ahead(self, flick_frame: FlickFrame, showing: _Showing, frame_bytes: int) -> None:
        frames = flick_frame.frames
        if len(frames) * frame_bytes > self._limit:
            return
        on_screen = next((index for index, frame in enumerate(frames) if frame is flick_frame.frame), 0)
        for index in sorted(range(len(frames)), key=lambda index: abs(index - on_screen)):
            if frames[index] is not flick_frame.frame:
                self._off_the_window_s_thread(
                    lambda frame=frames[index]: self._scale_unless_it_left(frame, showing))

    def _scale_unless_it_left(self, frame: np.ndarray, showing: _Showing) -> None:
        with self._lock:
            if showing != self._showing or id(frame) in self._kept:
                return
        self._scale_and_keep(frame, showing)


# mpv owns the window, so a flick's frames go up as mpv overlays.
class FlickOverlay:
    def __init__(self, engine, *, cache_bytes: int = SCALED_FRAMES_BYTES,
                 off_the_window_s_thread: Callable[[Callable[[], None]], None] | None = None,
                 ) -> None:
        self._engine = engine
        self._scaled = _ScaledFrames(cache_bytes, off_the_window_s_thread or _ScalingThreads())
        self._backdrop_at: tuple[int, int] | None = None
        self._tiles_of: tuple[int, tuple[int, int]] | None = None
        self._tiles_up = 0
        self._loading: str | None = None
        self._loading_at: tuple[int, int] | None = None

    def show(self, frame: FlickFrame, viewport: tuple[int, int]) -> None:
        if self._backdrop_at != viewport:
            self._engine.overlay(BACKDROP_OVERLAY_ID, 0, 0, black_bgra(*viewport))
            self._backdrop_at = viewport
        self._show_the_frame(frame, viewport)
        self._show_the_loading(frame.loading, viewport)

    @property
    def scaled_frames_kept(self) -> int:
        return len(self._scaled)

    def holds_scaled(self, frame: np.ndarray) -> bool:
        return self._scaled.holds(frame)

    def let_go_of_the_scaled_frames(self) -> None:
        self._scaled.let_go()

    def _show_the_frame(self, flick_frame: FlickFrame, viewport: tuple[int, int]) -> None:
        frame = flick_frame.frame
        tiles_of = None if frame is None else (id(frame), viewport)
        if tiles_of == self._tiles_of and frame is not None:
            return
        rects = [] if frame is None else tile_rects((frame.shape[1], frame.shape[0]), viewport)
        for index, (x, y, w, h) in enumerate(rects):
            self._engine.overlay(FIRST_TILE_OVERLAY_ID + index, x, y, self._scaled.get(flick_frame, (w, h)))
        for index in range(len(rects), self._tiles_up):
            self._engine.remove_overlay(FIRST_TILE_OVERLAY_ID + index)
        self._tiles_up = len(rects)
        self._tiles_of = tiles_of

    def _show_the_loading(self, loading: str | None, viewport: tuple[int, int]) -> None:
        if loading == self._loading and (not loading or viewport == self._loading_at):
            return
        if not loading:
            self._engine.remove_overlay(LOADING_OVERLAY_ID)
        else:
            message = loading_message_bgra(loading)
            self._engine.overlay(LOADING_OVERLAY_ID, viewport[0] - message.shape[1] - _LOADING_INSET,
                                 _LOADING_INSET, message)
        self._loading, self._loading_at = loading, viewport

    def hide(self) -> None:
        if self._backdrop_at is None and not self._tiles_up and not self._loading:
            return
        for ident in (BACKDROP_OVERLAY_ID, LOADING_OVERLAY_ID,
                      *(FIRST_TILE_OVERLAY_ID + index for index in range(self._tiles_up))):
            self._engine.remove_overlay(ident)
        self._backdrop_at = None
        self._tiles_of = None
        self._tiles_up = 0
        self._loading = None
