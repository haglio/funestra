from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager

logger = logging.getLogger(__name__)

_ABOVE_NORMAL_PRIORITY_CLASS = 0x8000
_THIS_PROCESS = ctypes.wintypes.HANDLE(-1)


def _kernel32():
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetPriorityClass.argtypes = [ctypes.wintypes.HANDLE]
    kernel32.GetPriorityClass.restype = ctypes.wintypes.DWORD
    kernel32.SetPriorityClass.argtypes = [ctypes.wintypes.HANDLE, ctypes.wintypes.DWORD]
    kernel32.SetPriorityClass.restype = ctypes.wintypes.BOOL
    return kernel32


@contextmanager
def ahead_on_the_processor(kernel32=None,
                           last_error: Callable[[], int] | None = None) -> Iterator[None]:
    kernel32 = _kernel32() if kernel32 is None else kernel32
    found = kernel32.GetPriorityClass(_THIS_PROCESS)
    raised = kernel32.SetPriorityClass(_THIS_PROCESS, _ABOVE_NORMAL_PRIORITY_CLASS)
    if not raised:
        logger.warning(
            "Windows would not put this Funestra ahead of background work (error %d), so a "
            "busy computer can make what it shows and the OSR2's motion uneven",
            (last_error or ctypes.get_last_error)())
    try:
        yield
    finally:
        if raised:
            kernel32.SetPriorityClass(_THIS_PROCESS, found)
