from __future__ import annotations

import sys

import pytest
from app_support.haglio_settings import SETTINGS_ENV, THE_EXAMPLE
from app_support.pcloud.library import PLAY_FROM_PCLOUD

from funestra.cloud_playback import the_library


@pytest.fixture(autouse=True)
def no_test_here_loads_libmpv_since_a_real_engine_takes_the_dll_and_a_window_and_fun_time_s_hidden_desktop_suite_is_what_builds_one():
    yield
    assert "mpv" not in sys.modules


@pytest.fixture(autouse=True)
def every_test_plays_from_disk_whatever_the_settings_of_the_computer_it_runs_on_say(monkeypatch):
    monkeypatch.setenv(SETTINGS_ENV, THE_EXAMPLE)
    monkeypatch.delenv(PLAY_FROM_PCLOUD, raising=False)
    the_library.cache_clear()
    yield
    the_library.cache_clear()
