from __future__ import annotations

import numpy as np
from funestra_fakes import make_playback

from funestra.flick_overlay import FlickFrame
from funestra.items_row import ItemsRow, frame_row
from funestra.volume import VolumeHud

VOLUME = VolumeHud(volume=40, muted=False)


def _row(tmp_path, *, duration_ms: float = 100_000.0):
    playback, engine = make_playback(tmp_path, duration_ms=duration_ms)
    return ItemsRow(playback, engine), playback, engine


def test_a_video_s_row_says_where_it_is_and_how_long_it_runs(tmp_path):
    items, _playback, engine = _row(tmp_path)
    engine.position_ms = 25_000.0

    row = items.row(VOLUME, 200)

    assert (row.position_ms, row.duration_ms, row.volume) == (25_000.0, 100_000.0, VOLUME)
    assert (row.loop_bounds, row.record_in_ms) == (None, None)


def test_an_image_s_row_says_how_far_into_its_time_on_screen_it_is(tmp_path):
    items, _playback, engine = _row(tmp_path)
    engine.showing_image = True
    engine.image_time = (1_000.0, 4_000.0)

    row = items.row(VOLUME, 200)

    assert (row.position_ms, row.duration_ms) == (1_000.0, 4_000.0)


def test_an_image_with_no_time_yet_starts_its_row_at_nothing(tmp_path):
    items, _playback, engine = _row(tmp_path)
    engine.showing_image = True

    row = items.row(VOLUME, 200)

    assert (row.position_ms, row.duration_ms) == (0.0, 0.0)


def test_a_loop_s_ends_are_placed_on_the_row(tmp_path):
    items, playback, _engine = _row(tmp_path)
    playback.set_ab_loop(10_000, 30_000)

    assert items.row(VOLUME, 200).loop_bounds == (10_000, 30_000)


def test_a_mark_is_placed_on_the_row_from_where_the_stretch_it_shows_starts(tmp_path):
    items, playback, engine = _row(tmp_path)
    playback.set_mark(50_000)
    engine.position_ms = 51_000.0

    row = items.row(VOLUME, 200)

    assert row.record_in_ms == 50_000 - items.strip.window[0]


class TestAPressAlongTheTrack:
    def test_it_seeks_the_video_to_that_place_in_the_stretch_the_row_shows(self, tmp_path):
        items, _playback, engine = _row(tmp_path)
        items.row(VOLUME, 200)

        items.seek_along_the_track(2_000.0)

        assert engine.seeks == [items.strip.window[0] + 2_000.0]

    def test_over_an_image_it_seeks_the_image_s_time_on_screen(self, tmp_path):
        items, _playback, engine = _row(tmp_path)
        engine.showing_image = True

        items.seek_along_the_track(2_000.0)

        assert (engine.image_seeks, engine.seeks) == ([2_000.0], [])


class TestAFramesRow:
    @staticmethod
    def _frame(count: int) -> FlickFrame:
        return FlickFrame(frame=np.zeros((2, 2, 3), dtype=np.uint8), played=6, count=count,
                          elapsed_ms=4_000.0, interval_ms=10_000.0)

    def test_it_runs_the_frame_s_time_on_screen_and_turns_its_dial(self):
        row = frame_row(self._frame(20), VOLUME)

        assert (row.position_ms, row.duration_ms, row.loop, row.volume) == (
            4_000.0, 10_000.0, (6, 20), VOLUME)

    def test_a_flick_with_no_frames_yet_has_no_row(self):
        assert frame_row(self._frame(0), VOLUME) is None
