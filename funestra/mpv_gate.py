"""What keeps an engine's mpv alive while another thread is inside a call on it.

Every mpv-backed engine here is driven from more than one thread, which is
libmpv's designed usage: the client API (property reads, commands, overlays) on
one, the render API on another.  What is never safe is taking the thing away
underneath.  ``mpv_terminate_destroy`` and ``mpv_render_context_free`` both
destroy state a concurrent call is standing on, and python-mpv makes the window
wider still — its ``terminate()`` nulls ``self.handle`` *before* the destroy, so
a property read that began a moment earlier hands libmpv a NULL client and
dereferences it.

That is not a theory.  Closing an engine from one thread while a worker read
``time-pos`` from another reproduced an access violation on every attempt, the
faulting thread being the worker at ``mpv_get_property`` (reading 0x48 — NULL
plus a field offset) with the closer inside ``terminate()``.

Joining the pump thread is not enough to rest shutdown on: a join that times
out returns anyway, and even one that returns cleanly says nothing about the
*other* threads an engine is reachable from.  A lease needs no such guess.
Every call into mpv takes one; :meth:`CallGate.close` bars new leases — so a
worker that never noticed the stop flag simply gets no-ops from here on — waits
out the calls already inside, and only then says the handle may be freed.  If
they do not come back inside the timeout it declines to free at all: an mpv
left for the exiting process to reap is a leak, freeing under a live call is a
crash, and a leak at shutdown is much the cheaper of the two.  The wait is
always bounded, so a wedged decoder can never hold a session open.

Leases nest safely (the gate counts callers rather than excluding them), so a
guarded method is free to call another.  What must never take one is ``close``
itself, which would then be waiting for itself.
"""
from __future__ import annotations

import functools
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager

__all__: list[str] = []  # package-internal: no sibling reaches anything here


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
        """Whether the gate is barred — every call from here on is a no-op."""
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
