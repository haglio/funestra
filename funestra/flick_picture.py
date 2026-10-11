"""The frames a User chose, put up over the video: the Funestra's second way of playing.

Genau scrubs a flick frame by frame to wherever the OSR2 is, so what it has to
show is a frame it decoded itself rather than a file mpv could open.  mpv owns
the window's pixels, so the frame rides the overlay channel the panel already
does: a black backdrop over the paused video, then the frame scaled to the
window's height and tiled across it the way a portrait video is, under every id
the panel and the loop's frames draw with.
"""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .hud_panel import load_font, text_width, to_bgra
from .renamed import answers_to_old_names

__all__ = ["Picture"]

BACKDROP_OVERLAY_ID = 1
FIRST_TILE_OVERLAY_ID = 2
LOADING_OVERLAY_ID = 6

# Scaled frames kept between passes: a flick's frames come round again every
# cycle of the motion, and scaling one costs milliseconds on the thread that
# drives the device.  Bounded, so a long flick at a large window cannot grow it
# without end; past the bound a frame is scaled again rather than kept.
SCALED_FRAMES_BYTES = 192 * 1024 * 1024

_LOADING_PT = 13
_LOADING_PAD = 8
_LOADING_INSET = 8
_LOADING_GROUND = (0, 0, 0, 180)


def _nothing(_value: float) -> None:
    pass


@answers_to_old_names({"clip": "flick", "seek": "seek_loop"})
@dataclass(frozen=True)
class Picture:
    """A frame of a flick, with the flick's two senses of time for the row: how
    many of its frames have played of how many (the dial and the frame count;
    none before a frame is up), and how long it has been up of the time it
    gets (the track)."""

    frame: np.ndarray | None
    played: int = 0
    count: int = 0
    elapsed_ms: float = 0.0
    interval_ms: float = 0.0
    loading: str | None = None
    seek_time: Callable[[float], None] = _nothing
    seek_loop: Callable[[float], None] = _nothing
    flick: Path | None = None


def black_bgra(width: int, height: int) -> np.ndarray:
    frame = np.zeros((max(1, height), max(1, width), 4), dtype=np.uint8)
    frame[:, :, 3] = 255
    return frame


def tile_rects(frame_size: tuple[int, int], window: tuple[int, int]) -> list[tuple[int, int, int, int]]:
    frame_w, frame_h = frame_size
    window_w, window_h = window
    tile_h = window_h
    tile_w = int(frame_w * (window_h / frame_h))
    if tile_w > window_w:
        tile_w = window_w
        tile_h = int(frame_h * (window_w / frame_w))
    tiles = max(1, window_w // max(1, tile_w)) if frame_h > frame_w else 1
    margin = (window_w - tile_w * tiles) // 2
    y = (window_h - tile_h) // 2
    return [(margin + i * tile_w, y, tile_w, tile_h) for i in range(tiles)]


def scaled_bgra(frame: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    image = Image.fromarray(frame, "RGB").resize(size, Image.Resampling.BILINEAR).convert("RGBA")
    return np.ascontiguousarray(np.asarray(image)[:, :, [2, 1, 0, 3]], dtype=np.uint8)


def loading_notice_bgra(text: str) -> np.ndarray:
    font = load_font(_LOADING_PT)
    ascent, descent = font.getmetrics()
    image = Image.new("RGBA", (text_width(font, text) + 2 * _LOADING_PAD,
                               ascent + descent + 2 * _LOADING_PAD), _LOADING_GROUND)
    ImageDraw.Draw(image).text((_LOADING_PAD, _LOADING_PAD), text, font=font, fill=(255, 255, 255, 255))
    return to_bgra(image)


class _ScaledFrames:
    def __init__(self, limit_bytes: int) -> None:
        self._limit = limit_bytes
        self._kept: OrderedDict[tuple[int, tuple[int, int]], tuple[np.ndarray, np.ndarray]] = OrderedDict()
        self._bytes = 0

    def get(self, frame: np.ndarray, size: tuple[int, int]) -> np.ndarray:
        key = (id(frame), size)
        kept = self._kept.get(key)
        if kept is not None:
            self._kept.move_to_end(key)
            return kept[1]
        scaled = scaled_bgra(frame, size)
        self._kept[key] = (frame, scaled)
        self._bytes += scaled.nbytes
        while self._bytes > self._limit and len(self._kept) > 1:
            _key, (_frame, dropped) = self._kept.popitem(last=False)
            self._bytes -= dropped.nbytes
        return scaled


class FlickPicture:
    def __init__(self, engine, *, cache_bytes: int = SCALED_FRAMES_BYTES) -> None:
        self._engine = engine
        self._scaled = _ScaledFrames(cache_bytes)
        self._backdrop_at: tuple[int, int] | None = None
        self._tiles_of: tuple[int, tuple[int, int]] | None = None
        self._tiles_up = 0
        self._loading: str | None = None

    def show(self, picture: Picture, window: tuple[int, int]) -> None:
        if self._backdrop_at != window:
            self._engine.overlay(BACKDROP_OVERLAY_ID, 0, 0, black_bgra(*window))
            self._backdrop_at = window
        self._show_the_frame(picture.frame, window)
        self._show_the_loading(picture.loading, window)

    def _show_the_frame(self, frame: np.ndarray | None, window: tuple[int, int]) -> None:
        tiles_of = None if frame is None else (id(frame), window)
        if tiles_of == self._tiles_of and frame is not None:
            return
        rects = [] if frame is None else tile_rects((frame.shape[1], frame.shape[0]), window)
        for index, (x, y, w, h) in enumerate(rects):
            self._engine.overlay(FIRST_TILE_OVERLAY_ID + index, x, y, self._scaled.get(frame, (w, h)))
        for index in range(len(rects), self._tiles_up):
            self._engine.remove_overlay(FIRST_TILE_OVERLAY_ID + index)
        self._tiles_up = len(rects)
        self._tiles_of = tiles_of

    def _show_the_loading(self, loading: str | None, window: tuple[int, int]) -> None:
        if loading == self._loading and not loading:
            return
        if not loading:
            self._engine.remove_overlay(LOADING_OVERLAY_ID)
        else:
            notice = loading_notice_bgra(loading)
            self._engine.overlay(LOADING_OVERLAY_ID, window[0] - notice.shape[1] - _LOADING_INSET,
                                 _LOADING_INSET, notice)
        self._loading = loading

    def hide(self) -> None:
        for ident in (BACKDROP_OVERLAY_ID, LOADING_OVERLAY_ID,
                      *(FIRST_TILE_OVERLAY_ID + index for index in range(self._tiles_up))):
            self._engine.remove_overlay(ident)
        self._backdrop_at = None
        self._tiles_of = None
        self._tiles_up = 0
        self._loading = None
