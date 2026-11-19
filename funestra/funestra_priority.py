from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager

from app_support.live_session import holding_a_live_session
from app_support.win32 import put_this_process_at

logger = logging.getLogger(__name__)

_ABOVE_NORMAL_PRIORITY_CLASS = 0x8000
D3DKMT_SCHEDULINGPRIORITYCLASS_HIGH = 4
_THIS_PROCESS = ctypes.wintypes.HANDLE(-1)


def _kernel32():
    return ctypes.WinDLL("kernel32", use_last_error=True)


def _gdi32():
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    gdi32.D3DKMTGetProcessSchedulingPriorityClass.argtypes = [
        ctypes.wintypes.HANDLE, ctypes.POINTER(ctypes.c_int)]
    gdi32.D3DKMTGetProcessSchedulingPriorityClass.restype = ctypes.c_long
    gdi32.D3DKMTSetProcessSchedulingPriorityClass.argtypes = [ctypes.wintypes.HANDLE, ctypes.c_int]
    gdi32.D3DKMTSetProcessSchedulingPriorityClass.restype = ctypes.c_long
    return gdi32


@contextmanager
def ahead_on_the_processor(kernel32=None,
                           last_error: Callable[[], int] | None = None, *,
                           gdi32=None,
                           live_session: Callable[[], AbstractContextManager[None]] = holding_a_live_session,
                           ) -> Iterator[None]:
    with (live_session(),
          _ahead_of_background_processor_work(_kernel32() if kernel32 is None else kernel32, last_error),
          _ahead_on_the_graphics_card(_gdi32() if gdi32 is None else gdi32)):
        yield


@contextmanager
def _ahead_of_background_processor_work(kernel32, last_error: Callable[[], int] | None) -> Iterator[None]:
    found = put_this_process_at(_ABOVE_NORMAL_PRIORITY_CLASS, kernel32=lambda: kernel32)
    if found is None:
        logger.warning(
            "Windows would not put this Funestra ahead of background work (error %d), so a "
            "busy computer can make what it shows and the OSR2's motion uneven",
            (last_error or ctypes.get_last_error)())
    try:
        yield
    finally:
        if found is not None:
            put_this_process_at(found, kernel32=lambda: kernel32)


@contextmanager
def _ahead_on_the_graphics_card(gdi32) -> Iterator[None]:
    found = ctypes.c_int()
    gdi32.D3DKMTGetProcessSchedulingPriorityClass(_THIS_PROCESS, ctypes.byref(found))
    status = gdi32.D3DKMTSetProcessSchedulingPriorityClass(
        _THIS_PROCESS, D3DKMT_SCHEDULINGPRIORITYCLASS_HIGH)
    if status:
        logger.warning(
            "Windows would not put this Funestra ahead of background work on the graphics card "
            "(status 0x%08x), so a busy graphics card can hold its frames up", status & 0xFFFFFFFF)
    try:
        yield
    finally:
        if not status:
            gdi32.D3DKMTSetProcessSchedulingPriorityClass(_THIS_PROCESS, found.value)
