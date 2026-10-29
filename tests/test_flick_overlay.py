"""The frames a User chose, put up over the video: the Funestra's second way of playing."""
from __future__ import annotations

import numpy as np
from funestra_fakes import FakeEngine

import funestra.flick_overlay as module
from funestra.flick_overlay import (
    BACKDROP_OVERLAY_ID,
    FIRST_TILE_OVERLAY_ID,
    LOADING_OVERLAY_ID,
    FlickFrame,
    FlickOverlay,
)
from funestra.funestra import Funestra
from funestra.hud_corners import CORNER_PLUS_OVERLAY_ID
from funestra.hud_overlay import HUD_OVERLAY_ID


def _frame(width: int, height: int, rgb=(10, 20, 30)) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :] = rgb
    return frame


def test_a_frame_is_put_up_over_a_black_backdrop_scaled_to_the_window():
    engine = FakeEngine()

    FlickOverlay(engine).show(FlickFrame(frame=_frame(16, 8)), window=(64, 32))

    assert list(engine.overlays) == [BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID]
    x, y, backdrop = engine.overlays[BACKDROP_OVERLAY_ID]
    assert (x, y, backdrop.shape) == (0, 0, (32, 64, 4))
    assert backdrop[0, 0].tolist() == [0, 0, 0, 255]
    x, y, tile = engine.overlays[FIRST_TILE_OVERLAY_ID]
    assert (x, y, tile.shape) == (0, 0, (32, 64, 4))
    assert tile[0, 0].tolist() == [30, 20, 10, 255]


def test_a_portrait_frame_is_tiled_across_the_window_as_a_portrait_video_is():
    engine = FakeEngine()

    FlickOverlay(engine).show(FlickFrame(frame=_frame(8, 16)), window=(64, 32))

    tiles = [engine.overlays[FIRST_TILE_OVERLAY_ID + i] for i in range(4)]
    assert [(x, y, bgra.shape) for x, y, bgra in tiles] == [
        (0, 0, (32, 16, 4)), (16, 0, (32, 16, 4)), (32, 0, (32, 16, 4)), (48, 0, (32, 16, 4))]
    assert FIRST_TILE_OVERLAY_ID + 4 not in engine.overlays


def test_a_frame_wider_than_the_window_fits_its_width_and_sits_in_the_middle():
    engine = FakeEngine()

    FlickOverlay(engine).show(FlickFrame(frame=_frame(32, 8)), window=(32, 32))

    x, y, tile = engine.overlays[FIRST_TILE_OVERLAY_ID]
    assert (x, y, tile.shape) == (0, 12, (8, 32, 4))


def test_hidden_it_takes_down_everything_it_put_up():
    engine = FakeEngine()
    overlay = FlickOverlay(engine)
    overlay.show(FlickFrame(frame=_frame(8, 16)), window=(64, 32))

    overlay.hide()

    assert engine.overlays == {}


def test_fewer_tiles_than_before_take_the_stale_ones_down():
    engine = FakeEngine()
    overlay = FlickOverlay(engine)
    overlay.show(FlickFrame(frame=_frame(8, 16)), window=(64, 32))

    overlay.show(FlickFrame(frame=_frame(8, 16)), window=(32, 32))

    assert sorted(engine.overlays) == [BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID, FIRST_TILE_OVERLAY_ID + 1]


class SpyEngine(FakeEngine):
    def __init__(self) -> None:
        super().__init__()
        self.put_up: list[int] = []

    def overlay(self, ident: int, x: int, y: int, bgra) -> None:
        super().overlay(ident, x, y, bgra)
        self.put_up.append(ident)


def test_the_same_frame_in_the_same_window_is_not_put_up_twice():
    engine = SpyEngine()
    overlay = FlickOverlay(engine)
    frame = _frame(16, 8)

    overlay.show(FlickFrame(frame=frame), window=(64, 32))
    overlay.show(FlickFrame(frame=frame), window=(64, 32))

    assert engine.put_up == [BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID]


def test_a_frame_shown_before_at_this_size_is_scaled_once(monkeypatch):
    scaled: list[tuple[int, int]] = []
    real = module.scaled_bgra
    monkeypatch.setattr(module, "scaled_bgra",
                        lambda frame, size: scaled.append(size) or real(frame, size))
    overlay = FlickOverlay(FakeEngine())
    first, second = _frame(16, 8), _frame(16, 8, rgb=(1, 2, 3))

    for frame in (first, second, first):
        overlay.show(FlickFrame(frame=frame), window=(64, 32))

    assert len(scaled) == 2


def test_the_scaled_frames_kept_are_bounded_so_a_long_flick_cannot_eat_the_memory(monkeypatch):
    scaled: list[tuple[int, int]] = []
    real = module.scaled_bgra
    monkeypatch.setattr(module, "scaled_bgra",
                        lambda frame, size: scaled.append(size) or real(frame, size))
    overlay = FlickOverlay(FakeEngine(), cache_bytes=64 * 32 * 4)
    first, second = _frame(16, 8), _frame(16, 8, rgb=(1, 2, 3))

    for frame in (first, second, first):
        overlay.show(FlickFrame(frame=frame), window=(64, 32))

    assert len(scaled) == 3


def test_nothing_decoded_yet_shows_the_backdrop_and_what_is_loading():
    engine = FakeEngine()

    FlickOverlay(engine).show(FlickFrame(frame=None, loading="Loading alpha.mp4"), window=(640, 480))

    assert sorted(engine.overlays) == [BACKDROP_OVERLAY_ID, LOADING_OVERLAY_ID]
    x, y, notice = engine.overlays[LOADING_OVERLAY_ID]
    assert y == 8
    assert x + notice.shape[1] <= 640 - 8
    assert notice[:, :, 3].max() > 0


def test_the_loading_notice_comes_down_with_the_flick_decoded():
    engine = FakeEngine()
    overlay = FlickOverlay(engine)
    overlay.show(FlickFrame(frame=None, loading="Loading alpha.mp4"), window=(640, 480))

    overlay.show(FlickFrame(frame=_frame(16, 8)), window=(640, 480))

    assert LOADING_OVERLAY_ID not in engine.overlays


def test_every_id_it_draws_with_is_under_the_panels():
    panels = (Funestra.IN_FRAME_OVERLAY_ID, Funestra.OUT_FRAME_OVERLAY_ID,
              HUD_OVERLAY_ID, CORNER_PLUS_OVERLAY_ID)

    assert max(BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID + 3, LOADING_OVERLAY_ID) < min(panels)
