from __future__ import annotations

import weakref
from pathlib import Path

import numpy as np
import pytest
from app_support.threading_utils import wait_until

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
from funestra.testing import FakeEngine


def _frame(width: int, height: int, rgb=(10, 20, 30)) -> np.ndarray:
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    frame[:, :] = rgb
    return frame


def test_a_frame_is_put_up_over_a_black_backdrop_scaled_to_the_window():
    engine = FakeEngine()

    FlickOverlay(engine).show(FlickFrame(frame=_frame(16, 8)), viewport=(64, 32))

    assert list(engine.overlays) == [BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID]
    x, y, backdrop = engine.overlays[BACKDROP_OVERLAY_ID]
    assert (x, y, backdrop.shape) == (0, 0, (32, 64, 4))
    assert backdrop[0, 0].tolist() == [0, 0, 0, 255]
    x, y, tile = engine.overlays[FIRST_TILE_OVERLAY_ID]
    assert (x, y, tile.shape) == (0, 0, (32, 64, 4))
    assert tile[0, 0].tolist() == [30, 20, 10, 255]


def test_a_portrait_frame_is_tiled_across_the_window_as_a_portrait_video_is():
    engine = FakeEngine()

    FlickOverlay(engine).show(FlickFrame(frame=_frame(8, 16)), viewport=(64, 32))

    tiles = [engine.overlays[FIRST_TILE_OVERLAY_ID + i] for i in range(4)]
    assert [(x, y, bgra.shape) for x, y, bgra in tiles] == [
        (0, 0, (32, 16, 4)), (16, 0, (32, 16, 4)), (32, 0, (32, 16, 4)), (48, 0, (32, 16, 4))]
    assert FIRST_TILE_OVERLAY_ID + 4 not in engine.overlays


def test_a_frame_wider_than_the_window_fits_its_width_and_sits_in_the_middle():
    engine = FakeEngine()

    FlickOverlay(engine).show(FlickFrame(frame=_frame(32, 8)), viewport=(32, 32))

    x, y, tile = engine.overlays[FIRST_TILE_OVERLAY_ID]
    assert (x, y, tile.shape) == (0, 12, (8, 32, 4))


def test_hidden_it_takes_down_everything_it_put_up():
    engine = FakeEngine()
    overlay = FlickOverlay(engine)
    overlay.show(FlickFrame(frame=_frame(8, 16)), viewport=(64, 32))

    overlay.hide()

    assert engine.overlays == {}


def test_fewer_tiles_than_before_take_the_stale_ones_down():
    engine = FakeEngine()
    overlay = FlickOverlay(engine)
    overlay.show(FlickFrame(frame=_frame(8, 16)), viewport=(64, 32))

    overlay.show(FlickFrame(frame=_frame(8, 16)), viewport=(32, 32))

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

    overlay.show(FlickFrame(frame=frame), viewport=(64, 32))
    overlay.show(FlickFrame(frame=frame), viewport=(64, 32))

    assert engine.put_up == [BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID]


@pytest.fixture
def scaled(monkeypatch) -> list[int]:
    made: list[int] = []
    real = module.scaled_bgra
    monkeypatch.setattr(module, "scaled_bgra",
                        lambda frame, size: made.append(int(frame[0, 0, 0])) or real(frame, size))
    return made


_ALPHA = Path("alpha.mp4")
_ONE_SCALED_FRAME = 64 * 32 * 4


def _flick(length: int) -> list[np.ndarray]:
    return [_frame(16, 8, rgb=(index, 0, 0)) for index in range(length)]


def test_a_flick_played_round_and_back_scales_each_frame_once_since_scaling_costs_more_than_a_pass_on_the_thread_that_draws(scaled):
    overlay = FlickOverlay(FakeEngine())
    frames = _flick(4)

    for index in (0, 1, 2, 3, 2, 1, 0, 1, 2, 3):
        overlay.show(FlickFrame(frame=frames[index], count=4, flick=_ALPHA), viewport=(64, 32))

    assert scaled == [0, 1, 2, 3]


def test_a_flick_too_long_for_the_room_keeps_none_of_its_scaled_frames_since_a_part_of_one_would_never_be_met_again_before_it_was_dropped(scaled):
    overlay = FlickOverlay(FakeEngine(), cache_bytes=2 * _ONE_SCALED_FRAME)
    frames = _flick(3)

    for index in (0, 1, 2, 1, 0):
        overlay.show(FlickFrame(frame=frames[index], count=3, flick=_ALPHA), viewport=(64, 32))

    assert scaled == [0, 1, 2, 1, 0]
    assert overlay.scaled_frames_kept == 0


def test_frames_whose_flick_is_not_named_are_kept_only_while_there_is_room(scaled):
    overlay = FlickOverlay(FakeEngine(), cache_bytes=2 * _ONE_SCALED_FRAME)
    frames = _flick(3)

    for index in (0, 1, 0, 2, 0, 2):
        overlay.show(FlickFrame(frame=frames[index]), viewport=(64, 32))

    assert scaled == [0, 1, 2, 2]


def test_the_next_flick_coming_up_lets_go_of_the_last_one_s_frames():
    overlay = FlickOverlay(FakeEngine())
    frames = _flick(2)
    for frame in frames:
        overlay.show(FlickFrame(frame=frame, count=2, flick=_ALPHA), viewport=(64, 32))
    last_flick_s_frame = weakref.ref(frames[0])
    del frames, frame

    overlay.show(FlickFrame(frame=_frame(16, 8), count=1, flick=Path("beta.mp4")), viewport=(64, 32))

    assert last_flick_s_frame() is None
    assert overlay.scaled_frames_kept == 1


def test_a_window_of_another_size_lets_go_of_the_frames_scaled_for_the_old_one(scaled):
    overlay = FlickOverlay(FakeEngine())
    frames = _flick(2)
    for frame in frames:
        overlay.show(FlickFrame(frame=frame, count=2, flick=_ALPHA), viewport=(64, 32))

    overlay.show(FlickFrame(frame=frames[0], count=2, flick=_ALPHA), viewport=(32, 16))

    assert overlay.scaled_frames_kept == 1


def test_a_flick_handed_over_whole_is_scaled_ahead_off_the_window_s_thread_so_no_frame_but_the_first_is_scaled_on_it(scaled):
    ahead: list = []
    overlay = FlickOverlay(FakeEngine(), off_the_window_s_thread=ahead.append)
    frames = _flick(4)

    def show(index: int) -> None:
        overlay.show(FlickFrame(frame=frames[index], count=4, flick=_ALPHA, frames=frames),
                     viewport=(64, 32))

    show(3)
    on_the_window_s_thread = list(scaled)
    for job in ahead:
        job()
    for index in (2, 1, 0, 1, 2, 3):
        show(index)

    assert on_the_window_s_thread == [3]
    assert scaled == [3, 2, 1, 0]


def test_frames_are_scaled_ahead_nearest_the_one_on_screen_first_since_the_flick_is_scrubbed_from_there():
    ahead: list = []
    overlay = FlickOverlay(FakeEngine(), off_the_window_s_thread=ahead.append)
    frames = _flick(5)

    overlay.show(FlickFrame(frame=frames[2], count=5, flick=_ALPHA, frames=frames), viewport=(64, 32))
    for job in ahead[:2]:
        job()

    assert overlay.scaled_frames_kept == 3
    for index in (1, 3):
        assert overlay.holds_scaled(frames[index])


def test_a_flick_is_asked_to_be_scaled_ahead_once_and_not_on_every_pass():
    ahead: list = []
    overlay = FlickOverlay(FakeEngine(), off_the_window_s_thread=ahead.append)
    frames = _flick(3)

    for _pass in range(4):
        overlay.show(FlickFrame(frame=frames[0], count=3, flick=_ALPHA, frames=frames), viewport=(64, 32))

    assert len(ahead) == 2


def test_scaling_ahead_for_a_flick_that_has_left_the_screen_does_nothing(scaled):
    ahead: list = []
    overlay = FlickOverlay(FakeEngine(), off_the_window_s_thread=ahead.append)
    frames = _flick(3)
    overlay.show(FlickFrame(frame=frames[0], count=3, flick=_ALPHA, frames=frames), viewport=(64, 32))

    overlay.show(FlickFrame(frame=_frame(16, 8, rgb=(9, 0, 0)), count=1, flick=Path("beta.mp4")),
                 viewport=(64, 32))
    for job in ahead:
        job()

    assert scaled == [0, 9]
    assert overlay.scaled_frames_kept == 1


def test_a_flick_too_long_for_the_room_is_not_scaled_ahead():
    ahead: list = []
    overlay = FlickOverlay(FakeEngine(), cache_bytes=2 * _ONE_SCALED_FRAME,
                           off_the_window_s_thread=ahead.append)
    frames = _flick(3)

    overlay.show(FlickFrame(frame=frames[0], count=3, flick=_ALPHA, frames=frames), viewport=(64, 32))

    assert ahead == []


def test_left_to_itself_it_scales_ahead_on_threads_of_its_own():
    overlay = FlickOverlay(FakeEngine())
    frames = _flick(3)

    overlay.show(FlickFrame(frame=frames[0], count=3, flick=_ALPHA, frames=frames), viewport=(64, 32))

    wait_until(lambda: overlay.scaled_frames_kept == 3)


def test_nothing_decoded_yet_shows_the_backdrop_and_what_is_loading():
    engine = FakeEngine()

    FlickOverlay(engine).show(FlickFrame(frame=None, loading="Loading alpha.mp4"), viewport=(640, 480))

    assert sorted(engine.overlays) == [BACKDROP_OVERLAY_ID, LOADING_OVERLAY_ID]
    x, y, message = engine.overlays[LOADING_OVERLAY_ID]
    assert y == 8
    assert x + message.shape[1] <= 640 - 8
    assert message[:, :, 3].max() > 0


def test_the_loading_notice_comes_down_with_the_flick_decoded():
    engine = FakeEngine()
    overlay = FlickOverlay(engine)
    overlay.show(FlickFrame(frame=None, loading="Loading alpha.mp4"), viewport=(640, 480))

    overlay.show(FlickFrame(frame=_frame(16, 8)), viewport=(640, 480))

    assert LOADING_OVERLAY_ID not in engine.overlays


def test_every_id_it_draws_with_is_under_the_huds():
    huds = (Funestra.IN_FRAME_OVERLAY_ID, Funestra.OUT_FRAME_OVERLAY_ID,
            HUD_OVERLAY_ID, CORNER_PLUS_OVERLAY_ID)

    assert max(BACKDROP_OVERLAY_ID, FIRST_TILE_OVERLAY_ID + 3, LOADING_OVERLAY_ID) < min(huds)


def test_a_loading_notice_that_has_not_changed_is_not_drawn_or_put_up_again(monkeypatch):
    drawn: list[str] = []
    real = module.loading_message_bgra
    monkeypatch.setattr(module, "loading_message_bgra",
                        lambda text: drawn.append(text) or real(text))
    engine = SpyEngine()
    overlay = FlickOverlay(engine)

    for _pass in range(3):
        overlay.show(FlickFrame(frame=None, loading="Loading alpha.mp4"), viewport=(640, 480))

    assert drawn == ["Loading alpha.mp4"]
    assert engine.put_up == [BACKDROP_OVERLAY_ID, LOADING_OVERLAY_ID]


def test_a_loading_notice_follows_the_window_to_its_new_right_edge():
    engine = FakeEngine()
    overlay = FlickOverlay(engine)
    overlay.show(FlickFrame(frame=None, loading="Loading alpha.mp4"), viewport=(640, 480))
    x_before = engine.overlays[LOADING_OVERLAY_ID][0]

    overlay.show(FlickFrame(frame=None, loading="Loading alpha.mp4"), viewport=(800, 480))

    assert engine.overlays[LOADING_OVERLAY_ID][0] == x_before + 160
