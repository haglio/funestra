"""Leases that keep an engine's mpv from being freed under a live call from another thread."""
from __future__ import annotations

import functools
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager


class CallGate:
    """Leases on one mpv instance: any number of callers in, one closer.

    Not reusable: once :meth:`close` has drained the gate, it stays shut, so a
    handle can never be freed twice however many times ``close()`` is called
    (python-mpv's ``MpvRenderContext.free`` has no guard of its own).
    """

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
        """How many calls are in mpv right now (a test seam and a log field)."""
        with self._idle:
            return self._inside

    @contextmanager
    def entered(self) -> Iterator[bool]:
        """Hold mpv open for the body; yields False once the gate is barred.

        The body must not touch mpv on a False lease: that handle is being
        freed, or is already gone.
        """
        with self._idle:
            admitted = not self._closing
            if admitted:
                self._inside += 1
        try:
            yield admitted
        finally:
            if admitted:
                with self._idle:
                    self._inside -= 1
                    if not self._inside:
                        self._idle.notify_all()

    def close(self, timeout: float) -> bool:
        """Bar new calls, wait out the ones inside, and say whether to free.

        True exactly once, and only when nothing is inside mpv: the caller that
        gets it owns the teardown.  False means either that somebody already
        holds that answer, or that a call did not come back within *timeout* —
        in which case the handle must be left alone, however tempting it is to
        free it anyway.  A caller may ask again later; a call that eventually
        returns leaves the gate drainable.
        """
        with self._idle:
            if self._freed:
                return False
            self._closing = True
            drained = self._idle.wait_for(lambda: not self._inside, timeout)
            self._freed = drained
            return drained


def mpv_call(when_closed=None) -> Callable:
    """Wrap an engine method so mpv cannot be freed while it runs.

    A call arriving after the gate is barred returns *when_closed* instead of
    reaching a handle that is on its way out.  It returns rather than raises
    because losing this race is the ordinary case at shutdown, not a fault: a
    worker thread that raised on its last turn would bury the real reason the
    session ended under a traceback about an engine nobody wanted any more.
    """
    def decorate(method):
        @functools.wraps(method)
        def guarded(self, *args, **kwargs):
            with self._gate.entered() as live:
                return method(self, *args, **kwargs) if live else when_closed
        return guarded
    return decorate
