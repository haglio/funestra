from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from app_support.haglio_settings import SETTINGS_ENV, THE_EXAMPLE
from app_support.pcloud.fetching import Entry
from app_support.pcloud.library import PLAY_FROM_PCLOUD

from funestra.cloud_playback import (
    PLAYS_FROM_DISK,
    UNTIMED_OPENING_BYTES,
    WHOLE_BELOW_BYTES,
    LookAhead,
    open_the_sign_in_window,
    opening_spans,
    the_library,
)
from funestra.funestra import Channels
from funestra.funestra_setup import FunestraSetup

_MEGABYTE = 1024 * 1024


def _video(size: int, duration_s: float | None = 100.0) -> Entry:
    return Entry(path="/library/video one.mp4", fileid=1, size=size, key="1-1", duration_s=duration_s)


def test_a_video_small_enough_is_fetched_whole_since_its_index_may_sit_at_its_end():
    assert opening_spans(None)(_video(WHOLE_BELOW_BYTES)) == [(0, WHOLE_BELOW_BYTES)]


def test_a_bigger_video_opening_at_its_start_has_its_first_twenty_seconds_and_its_last_bytes_fetched():
    video = _video(200 * _MEGABYTE, duration_s=100.0)

    assert opening_spans(None)(video) == [(0, 40 * _MEGABYTE), (video.size - 1, video.size)]


def test_a_video_reopening_where_it_was_left_has_its_first_bytes_twenty_seconds_from_there_and_its_last_bytes_fetched():
    video = _video(200 * _MEGABYTE, duration_s=100.0)

    assert opening_spans(50_000)(video) == [
        (0, 1), (100 * _MEGABYTE, 140 * _MEGABYTE), (video.size - 1, video.size)]


def test_a_video_whose_running_time_pcloud_does_not_know_has_a_fixed_opening_fetched_and_its_last_bytes():
    video = _video(200 * _MEGABYTE, duration_s=None)

    assert opening_spans(50_000)(video) == [(0, UNTIMED_OPENING_BYTES), (video.size - 1, video.size)]


def test_a_video_shorter_than_its_opening_has_its_opening_end_where_the_video_ends():
    video = _video(40 * _MEGABYTE, duration_s=10.0)

    assert opening_spans(None)(video) == [(0, video.size), (video.size - 1, video.size)]


class _Library:
    def __init__(self) -> None:
        self.wished: list[tuple[str, list]] = []

    def prefetch(self, owner: str, wishes: list) -> None:
        self.wished.append((owner, list(wishes)))


def test_a_look_ahead_wishes_for_the_opening_of_each_video_coming_up_from_where_it_will_open():
    library = _Library()
    video = _video(200 * _MEGABYTE)

    LookAhead(library).see([(Path("made-up one.mp4"), None), (Path("made-up two.mp4"), 50_000)])

    [(_, wishes)] = library.wished
    assert [(wish.path, wish.spans(video)) for wish in wishes] == [
        (Path("made-up one.mp4"), opening_spans(None)(video)), (Path("made-up two.mp4"), opening_spans(50_000)(video))]


def test_two_look_aheads_wish_apart_so_one_funestras_plan_never_replaces_anothers():
    library = _Library()

    LookAhead(library).see([(Path("made-up one.mp4"), None)])
    LookAhead(library).see([(Path("made-up two.mp4"), None)])

    assert len({owner for owner, _ in library.wished}) == 2


def test_a_funestras_setup_hands_its_playback_the_look_ahead_it_was_given():
    look_ahead = LookAhead(_Library())

    setup = FunestraSetup(channels=Channels(), playlist=[], look_ahead=look_ahead)

    assert setup.playback_setup(start_paused=False, lap=lambda _step: None).look_ahead is look_ahead


def test_with_playing_from_pcloud_not_asked_for_files_play_from_where_they_are(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv(SETTINGS_ENV, THE_EXAMPLE)
    monkeypatch.delenv(PLAY_FROM_PCLOUD, raising=False)
    the_library.cache_clear()
    try:
        assert (the_library(), the_library().playable(Path("made-up one.mp4"))) == (PLAYS_FROM_DISK, "made-up one.mp4")
    finally:
        the_library.cache_clear()


def test_looking_ahead_while_files_play_from_where_they_are_asks_for_nothing():
    LookAhead(PLAYS_FROM_DISK).see([(Path("made-up one.mp4"), None)])


def test_the_sign_in_window_opens_as_a_program_of_its_own_with_no_console_window():
    started: list[tuple[list[str], dict]] = []

    open_the_sign_in_window(popen=lambda argv, **how: started.append((argv, how)))

    [(argv, how)] = started
    assert (argv[1:], how) == (["-m", "shared_ui.pcloud_sign_in"],
                               {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)})
