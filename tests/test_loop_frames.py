from __future__ import annotations

import numpy as np
from funestra_fakes import make_playback

from funestra.items_row import ItemsRow
from funestra.loop_frames import IN_FRAME_OVERLAY_ID, OUT_FRAME_OVERLAY_ID, LoopFrames
from funestra.volume import VolumeHud

TRACK = (20, 220, 400)
WIDTH = 640


def _frames(tmp_path):
    playback, engine = make_playback(tmp_path, duration_ms=10_000.0)
    engine.screenshot = np.zeros((36, 64, 4), dtype=np.uint8)
    items = ItemsRow(playback, engine)
    items.row(VolumeHud(volume=40, muted=False), TRACK[1] - TRACK[0])
    return LoopFrames(engine), playback, engine, items.strip


def test_with_no_loop_running_nothing_is_put_up_or_asked_of_the_engine(tmp_path):
    frames, playback, engine, strip = _frames(tmp_path)

    frames.paint(playback, strip, TRACK, WIDTH)
    frames.take_down()

    assert (engine.overlays, engine.screenshots) == ({}, 0)


def test_a_running_loop_hangs_the_frame_it_starts_on_under_the_track(tmp_path):
    frames, playback, engine, strip = _frames(tmp_path)
    playback.set_ab_loop(2_000, 4_000)
    engine.position_ms = 2_000.0

    frames.paint(playback, strip, TRACK, WIDTH)

    _x, top, thumb = engine.overlays[IN_FRAME_OVERLAY_ID]
    assert (top, thumb is engine.screenshot) == (TRACK[2], True)
    assert OUT_FRAME_OVERLAY_ID not in engine.overlays


def test_the_frame_it_ends_on_is_taken_once_the_playhead_nears_the_end(tmp_path):
    frames, playback, engine, strip = _frames(tmp_path)
    playback.set_ab_loop(2_000, 4_000)
    engine.position_ms = 2_000.0
    frames.paint(playback, strip, TRACK, WIDTH)

    engine.position_ms = 3_900.0
    frames.paint(playback, strip, TRACK, WIDTH)

    assert {IN_FRAME_OVERLAY_ID, OUT_FRAME_OVERLAY_ID} <= set(engine.overlays)
    assert engine.screenshots == 2


def test_the_end_of_the_loop_takes_both_frames_down(tmp_path):
    frames, playback, engine, strip = _frames(tmp_path)
    playback.set_ab_loop(2_000, 4_000)
    frames.paint(playback, strip, TRACK, WIDTH)

    playback.clear_ab_loop()
    frames.paint(playback, strip, TRACK, WIDTH)

    assert engine.overlays == {}


def test_with_no_track_drawn_there_is_nowhere_to_hang_them(tmp_path):
    frames, playback, engine, strip = _frames(tmp_path)
    playback.set_ab_loop(2_000, 4_000)

    frames.paint(playback, strip, None, WIDTH)

    assert engine.overlays == {}
