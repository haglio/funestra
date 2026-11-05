from __future__ import annotations

from collections import OrderedDict
from collections.abc import Callable
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

SCALED_FRAMES_BYTES = 192 * 1024 * 1024

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
    return np.ascontiguousarray(np.asarray(image)[:, :, [2, 1, 0, 3]], dtype=np.uint8)


def loading_message_bgra(text: str) -> np.ndarray:
    font = load_font(SIZE_HEADING)
    ascent, descent = font.getmetrics()
    image = Image.new("RGBA", (text_width(font, text) + 2 * _LOADING_PAD,
                               ascent + descent + 2 * _LOADING_PAD), _LOADING_GROUND)
    ImageDraw.Draw(image).text((_LOADING_PAD, _LOADING_PAD), text, font=font, fill=(*WHITE, 255))
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


# mpv owns the window, so a flick's frames go up as mpv overlays.
class FlickOverlay:
    def __init__(self, engine, *, cache_bytes: int = SCALED_FRAMES_BYTES) -> None:
        self._engine = engine
        self._scaled = _ScaledFrames(cache_bytes)
        self._backdrop_at: tuple[int, int] | None = None
        self._tiles_of: tuple[int, tuple[int, int]] | None = None
        self._tiles_up = 0
        self._loading: str | None = None

    def show(self, frame: FlickFrame, viewport: tuple[int, int]) -> None:
        if self._backdrop_at != viewport:
            self._engine.overlay(BACKDROP_OVERLAY_ID, 0, 0, black_bgra(*viewport))
            self._backdrop_at = viewport
        self._show_the_frame(frame.frame, viewport)
        self._show_the_loading(frame.loading, viewport)

    def _show_the_frame(self, frame: np.ndarray | None, viewport: tuple[int, int]) -> None:
        tiles_of = None if frame is None else (id(frame), viewport)
        if tiles_of == self._tiles_of and frame is not None:
            return
        rects = [] if frame is None else tile_rects((frame.shape[1], frame.shape[0]), viewport)
        for index, (x, y, w, h) in enumerate(rects):
            self._engine.overlay(FIRST_TILE_OVERLAY_ID + index, x, y, self._scaled.get(frame, (w, h)))
        for index in range(len(rects), self._tiles_up):
            self._engine.remove_overlay(FIRST_TILE_OVERLAY_ID + index)
        self._tiles_up = len(rects)
        self._tiles_of = tiles_of

    def _show_the_loading(self, loading: str | None, viewport: tuple[int, int]) -> None:
        if loading == self._loading and not loading:
            return
        if not loading:
            self._engine.remove_overlay(LOADING_OVERLAY_ID)
        else:
            message = loading_message_bgra(loading)
            self._engine.overlay(LOADING_OVERLAY_ID, viewport[0] - message.shape[1] - _LOADING_INSET,
                                 _LOADING_INSET, message)
        self._loading = loading

    def hide(self) -> None:
        for ident in (BACKDROP_OVERLAY_ID, LOADING_OVERLAY_ID,
                      *(FIRST_TILE_OVERLAY_ID + index for index in range(self._tiles_up))):
            self._engine.remove_overlay(ident)
        self._backdrop_at = None
        self._tiles_of = None
        self._tiles_up = 0
        self._loading = None
