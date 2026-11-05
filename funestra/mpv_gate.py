from __future__ import annotations

import functools
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class CallGate:
    # python-mpv's terminate() nulls its handle before destroying the core, so a read in flight dereferences NULL.

    def __init__(self) -> None:
        self._idle = threading.Condition()
        self._inside = 0
        self._closing = False
        self._freed = False

    @property
    def closing(self) -> bool:
        with self._idle:
            return self._closing

    @property
    def inside(self) -> int:
        with self._idle:
            return self._inside

    @contextmanager
    def entered(self) -> Iterator[bool]:
        with self._idle:
            admitted_and_so_may_touch_mpv = not self._closing
            if admitted_and_so_may_touch_mpv:
                self._inside += 1
        try:
            yield admitted_and_so_may_touch_mpv
        finally:
            if admitted_and_so_may_touch_mpv:
                with self._idle:
                    self._inside -= 1
                    if not self._inside:
                        self._idle.notify_all()

    def close(self, timeout: float) -> bool:
        with self._idle:
            if self._freed:
                return False
            self._closing = True
            drained = self._idle.wait_for(lambda: not self._inside, timeout)
            self._freed = drained
            return drained


def mpv_call(when_closed=None) -> Callable:
    def decorate(method):
        @functools.wraps(method)
        def guarded(self, *args, **kwargs):
            with self._gate.entered() as live:
                return method(self, *args, **kwargs) if live else when_closed
        return guarded
    return decorate
