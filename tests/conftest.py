from __future__ import annotations

import sys

import pytest


@pytest.fixture(autouse=True)
def no_test_here_loads_libmpv_since_a_real_engine_takes_the_dll_and_a_window_and_fun_time_s_hidden_desktop_suite_is_what_builds_one():
    yield
    assert "mpv" not in sys.modules
