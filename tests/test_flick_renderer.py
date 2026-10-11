from __future__ import annotations

from pathlib import Path

import numpy as np

from funestra.flick_cache import FlickCacheStore
from funestra.flick_renderer import FlickRenderController, display_index_for_phase


def _make_controller():
    flick_store = FlickCacheStore(limit=2)
    display_calls: list[object] = []

    controller = FlickRenderController(
        flick_store=flick_store,
        blit_frame=display_calls.append,
    )
    return controller, flick_store, display_calls


def test_prepare_active_flick_displays_first_frame():
    controller, flick_store, display_calls = _make_controller()
    path = Path("demo.mp4")
    flick_store.flick_cache[path] = {"frames": ["f0", "f1"]}
    controller.set_current_flick_path(path)

    controller.prepare_active_flick_for_current_size()

    assert controller.current_frame_index == 0
    assert display_calls == ["f0"]


def test_show_frame_at_blits_that_frame():
    controller, flick_store, display_calls = _make_controller()
    path = Path("demo.mp4")
    flick_store.flick_cache[path] = {"frames": ["f0", "f1", "f2"]}
    controller.set_current_flick_path(path)

    shown = controller.show_frame_at(1)

    assert shown is True
    assert controller.current_frame_index == 1
    assert display_calls == ["f1"]


def test_show_frame_at_skips_when_the_index_has_not_moved():
    controller, flick_store, display_calls = _make_controller()
    path = Path("demo.mp4")
    flick_store.flick_cache[path] = {"frames": ["f0", "f1"]}
    controller.set_current_flick_path(path)

    controller.show_frame_at(0)
    controller.show_frame_at(0)

    assert display_calls == ["f0"]


def test_nothing_is_drawn_when_no_flick_is_loaded():
    controller, _flick_store, display_calls = _make_controller()

    assert controller.show_frame_at(0) is False
    assert display_calls == []


def test_a_flick_taller_than_it_is_wide_is_portrait():
    controller, flick_store, _display_calls = _make_controller()
    path = Path("demo.mp4")
    flick_store.flick_cache[path] = {"frames": [np.zeros((640, 360, 3), np.uint8)]}
    controller.set_current_flick_path(path)

    assert controller.portrait is True


def test_the_shape_is_not_known_before_the_flick_is_up():
    controller, _flick_store, _display_calls = _make_controller()
    controller.set_current_flick_path(Path("demo.mp4"))

    assert controller.portrait is None


def test_a_flick_that_decoded_to_no_frames_has_no_shape():
    controller, flick_store, _display_calls = _make_controller()
    path = Path("demo.mp4")
    flick_store.flick_cache[path] = {"frames": []}
    controller.set_current_flick_path(path)

    assert controller.portrait is None


def test_display_index_for_phase_reverses_phase_position():
    assert display_index_for_phase(0.25, 8) == 5


def test_display_index_for_phase_clamps_past_end():
    assert display_index_for_phase(1.0, 8) == 0


class TestHowFarRoundTheLoopTheFlickIs:
    """What the dial and the frame count show: frames played of the loop,
    counted UP while the frame that is up counts DOWN, since a flick is shown
    from its last frame back (display_index_for_phase)."""

    def _showing(self, index: int | None, count: int | None):
        controller, flick_store, _calls = _make_controller()
        path = Path("demo.mp4")
        if count is not None:
            flick_store.flick_cache[path] = {"frames": [f"f{i}" for i in range(count)]}
        controller.set_current_flick_path(path)
        if index is not None:
            controller.show_frame_at(index)
        return controller

    def test_it_goes_round_once_as_the_frames_run_back_to_the_first(self):
        assert self._showing(19, 20).playhead == (0, 20)
        assert self._showing(12, 20).playhead == (7, 20)
        assert self._showing(0, 20).playhead == (19, 20)

    def test_there_is_no_playhead_before_a_frame_is_up(self):
        assert self._showing(None, 20).playhead is None
        assert self._showing(None, None).playhead is None
