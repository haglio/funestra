from __future__ import annotations

import contextlib
import ctypes
import ctypes.wintypes
import logging
import subprocess
from unittest.mock import MagicMock

import pytest

from funestra.funestra_priority import (
    D3DKMT_SCHEDULINGPRIORITYCLASS_HIGH,
    D3DKMT_SCHEDULINGPRIORITYCLASS_REALTIME,
    ahead_on_the_processor,
)

THIS_PROCESS = -1
ERROR_ACCESS_DENIED = 5
STATUS_ACCESS_DENIED = 0xC0000022
D3DKMT_SCHEDULINGPRIORITYCLASS_NORMAL = 2


def _kernel32(*, found: int = subprocess.NORMAL_PRIORITY_CLASS, allowed: bool = True):
    kernel32 = MagicMock()
    kernel32.GetPriorityClass.return_value = found
    kernel32.SetPriorityClass.return_value = 1 if allowed else 0
    return kernel32


class _Function:
    def __init__(self, call) -> None:
        self._call = call
        self.argtypes: object = None
        self.restype: object = None

    def __call__(self, *args):
        return self._call(*args)


class _Gdi32:
    def __init__(self, *, found: int = D3DKMT_SCHEDULINGPRIORITYCLASS_NORMAL, status: int = 0) -> None:
        self._found, self._status = found, status
        self.classes_set: list[int] = []
        self.D3DKMTGetProcessSchedulingPriorityClass = _Function(self._read)
        self.D3DKMTSetProcessSchedulingPriorityClass = _Function(self._set)

    def _read(self, process, found) -> int:
        found._obj.value = self._found
        return 0

    def _set(self, process, priority_class: int) -> int:
        self.classes_set.append(priority_class)
        return self._status


class _LiveSession:
    def __init__(self) -> None:
        self.held = False
        self.times_held = 0

    @contextlib.contextmanager
    def __call__(self):
        self.held, self.times_held = True, self.times_held + 1
        try:
            yield
        finally:
            self.held = False


def _ahead(kernel32=None, last_error=None, *, gdi32=None, live_session=None, **chosen):
    return ahead_on_the_processor(kernel32 or _kernel32(), last_error, gdi32=gdi32 or _Gdi32(),
                                  live_session=live_session or _LiveSession(), **chosen)


def _priority_set_last(kernel32) -> tuple[int, int]:
    (handle, priority), _kwargs = kernel32.SetPriorityClass.call_args
    return handle, priority


def _this_processes_priority() -> int:
    kernel32 = ctypes.WinDLL("kernel32")
    kernel32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
    kernel32.GetPriorityClass.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.GetPriorityClass.restype = ctypes.wintypes.DWORD
    return kernel32.GetPriorityClass(kernel32.GetCurrentProcess())


def test_the_funestra_plays_above_normal_priority():
    kernel32 = _kernel32()

    with _ahead(kernel32):
        assert _priority_set_last(kernel32) == (
            THIS_PROCESS, subprocess.ABOVE_NORMAL_PRIORITY_CLASS)


def test_leaving_the_block_puts_the_priority_back_as_it_was_found():
    kernel32 = _kernel32(found=subprocess.BELOW_NORMAL_PRIORITY_CLASS)

    with _ahead(kernel32):
        pass

    assert _priority_set_last(kernel32) == (THIS_PROCESS, subprocess.BELOW_NORMAL_PRIORITY_CLASS)


def test_a_funestra_that_dies_still_puts_the_priority_back():
    kernel32 = _kernel32(found=subprocess.BELOW_NORMAL_PRIORITY_CLASS)

    with pytest.raises(RuntimeError), _ahead(kernel32):
        raise RuntimeError("the Funestra died")

    assert _priority_set_last(kernel32) == (THIS_PROCESS, subprocess.BELOW_NORMAL_PRIORITY_CLASS)


def test_a_refusal_is_said_with_windows_reason(caplog):
    with (caplog.at_level(logging.WARNING, logger="funestra.funestra_priority"),
          _ahead(_kernel32(allowed=False), lambda: ERROR_ACCESS_DENIED)):
        pass

    assert f"error {ERROR_ACCESS_DENIED}" in caplog.text


def test_a_refused_priority_still_plays_and_puts_nothing_back():
    kernel32 = _kernel32(allowed=False)
    played = []

    with _ahead(kernel32, lambda: ERROR_ACCESS_DENIED):
        played.append(True)

    assert played == [True]
    assert kernel32.SetPriorityClass.call_count == 1


def test_the_funestra_draws_ahead_of_background_work_on_the_graphics_card_and_puts_it_back():
    gdi32 = _Gdi32(found=D3DKMT_SCHEDULINGPRIORITYCLASS_NORMAL)

    with _ahead(gdi32=gdi32):
        while_playing = list(gdi32.classes_set)

    assert while_playing == [D3DKMT_SCHEDULINGPRIORITYCLASS_HIGH]
    assert gdi32.classes_set == [D3DKMT_SCHEDULINGPRIORITYCLASS_HIGH, D3DKMT_SCHEDULINGPRIORITYCLASS_NORMAL]


def test_the_headset_can_ask_to_go_first_on_the_graphics_card():
    gdi32 = _Gdi32()

    with _ahead(gdi32=gdi32, graphics_card_class=D3DKMT_SCHEDULINGPRIORITYCLASS_REALTIME):
        while_playing = list(gdi32.classes_set)

    assert while_playing == [D3DKMT_SCHEDULINGPRIORITYCLASS_REALTIME]


def test_a_graphics_card_refusal_is_said_and_nothing_is_put_back(caplog):
    gdi32 = _Gdi32(status=STATUS_ACCESS_DENIED)

    with caplog.at_level(logging.WARNING, logger="funestra.funestra_priority"), _ahead(gdi32=gdi32):
        pass

    assert "status 0xc0000022" in caplog.text
    assert gdi32.classes_set == [D3DKMT_SCHEDULINGPRIORITYCLASS_HIGH]


def test_a_playing_funestra_holds_the_live_session_mark_and_lets_it_go_after():
    live_session = _LiveSession()

    with _ahead(live_session=live_session):
        held_while_playing = live_session.held

    assert (held_while_playing, live_session.held, live_session.times_held) == (True, False, 1)


def test_windows_runs_this_process_above_normal_inside_the_block_and_as_it_was_after():
    found = _this_processes_priority()

    with ahead_on_the_processor(live_session=_LiveSession()):
        inside = _this_processes_priority()

    assert (inside, _this_processes_priority()) == (subprocess.ABOVE_NORMAL_PRIORITY_CLASS, found)
