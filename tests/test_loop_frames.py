from __future__ import annotations

import numpy as np
from funestra_fakes import make_playback

from funestra.items_row import ItemsRow
from funestra.loop_frames import (
    IN_FRAME_OVERLAY_ID,
    OUT_FRAME_OVERLAY_ID,
    PASSES_BEFORE_ASKING_AGAIN,
    LoopFrames,
)
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


def test_frames_already_up_where_they_belong_are_not_sent_to_mpv_again(tmp_path):
    frames, playback, engine, strip = _frames(tmp_path)
    playback.set_ab_loop(2_000, 4_000)
    engine.position_ms = 3_900.0
    frames.paint(playback, strip, TRACK, WIDTH)
    frames.paint(playback, strip, TRACK, WIDTH)
    sent = list(engine.overlays_sent)

    for _ in range(5):
        frames.paint(playback, strip, TRACK, WIDTH)

    assert (sent, engine.overlays_sent[len(sent):]) == (
        [IN_FRAME_OVERLAY_ID, OUT_FRAME_OVERLAY_ID], [])


def test_frames_taken_down_go_up_again_when_the_loop_is_drawn_again(tmp_path):
    frames, playback, engine, strip = _frames(tmp_path)
    playback.set_ab_loop(2_000, 4_000)
    frames.paint(playback, strip, TRACK, WIDTH)

    frames.paint(playback, strip, None, WIDTH)
    frames.paint(playback, strip, TRACK, WIDTH)

    assert IN_FRAME_OVERLAY_ID in engine.overlays


def test_a_frame_mpv_would_not_give_is_not_asked_for_on_every_pass(tmp_path):
    frames, playback, engine, strip = _frames(tmp_path)
    engine.screenshot = None
    playback.set_ab_loop(2_000, 4_000)

    for _ in range(PASSES_BEFORE_ASKING_AGAIN + 1):
        frames.paint(playback, strip, TRACK, WIDTH)
    asked_while_waiting = engine.screenshots
    engine.screenshot = np.zeros((36, 64, 4), dtype=np.uint8)
    frames.paint(playback, strip, TRACK, WIDTH)

    assert (asked_while_waiting, engine.screenshots) == (1, 2)
    assert IN_FRAME_OVERLAY_ID in engine.overlays


class _Later:
    def __init__(self) -> None:
        self.jobs: list[tuple] = []

    def __call__(self, work, then=None) -> None:
        self.jobs.append((work, then))

    def run(self) -> None:
        jobs, self.jobs = self.jobs, []
        for work, then in jobs:
            then(work())


def _frames_taken_later(tmp_path):
    _taken_at_once, playback, engine, strip = _frames(tmp_path)
    later = _Later()
    return LoopFrames(engine, behind=later), later, playback, engine, strip


def test_a_loops_frame_is_taken_off_the_loop_and_goes_up_once_it_is_handed_back(tmp_path):
    frames, later, playback, engine, strip = _frames_taken_later(tmp_path)
    playback.set_ab_loop(2_000, 4_000)

    for _ in range(3):
        frames.paint(playback, strip, TRACK, WIDTH)
    taken_on_the_loop, asked = engine.screenshots, len(later.jobs)
    later.run()
    frames.paint(playback, strip, TRACK, WIDTH)

    assert (taken_on_the_loop, asked) == (0, 1)
    assert IN_FRAME_OVERLAY_ID in engine.overlays


def test_a_frame_handed_back_after_its_loop_was_replaced_is_not_put_up_for_the_new_one(tmp_path):
    frames, later, playback, engine, strip = _frames_taken_later(tmp_path)
    playback.set_ab_loop(2_000, 4_000)
    frames.paint(playback, strip, TRACK, WIDTH)

    playback.set_ab_loop(6_000, 8_000)
    frames.paint(playback, strip, TRACK, WIDTH)
    later.run()
    frames.paint(playback, strip, TRACK, WIDTH)

    assert engine.overlays == {}
    assert len(later.jobs) == 1
