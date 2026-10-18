"""When the graphics card goes out from under a window's video output, and when to build a new one.

A graphics driver restart takes every Direct3D device away from the programs using it, and
mpv's d3d11 output never gets its device back: every frame after it fails with
DXGI_ERROR_DEVICE_REMOVED, and the window shows nothing for the rest of the session.
A new output, though, builds a new device on the card that came back.
"""
from __future__ import annotations

import logging
import re
import threading
import time
from collections.abc import Callable

logger = logging.getLogger(__name__)

# DXGI's three codes for a device that is gone, 0x887A0005 to 7, which mpv and FFmpeg print
# with and without the 0x.
_GONE = re.compile(r"887a000[567]", re.IGNORECASE)

FIRST_WAIT_S = 2.0
LONGEST_WAIT_S = 30.0
QUIET_S = 1.0
LASTED_S = 30.0


def _after(seconds: float, then: Callable[[], None]) -> Callable[[], None]:
    timer = threading.Timer(seconds, then)
    timer.daemon = True
    timer.name = "gpu-rebuild"
    timer.start()
    return timer.cancel


def _under_way() -> None:
    return


class LostGpu:
    def __init__(self, rebuild: Callable[[], bool], *, now: Callable[[], float] = time.monotonic,
                 later: Callable[[float, Callable[[], None]], Callable[[], None]] = _after) -> None:
        self._rebuild = rebuild
        self._now = now
        self._later = later
        self._lock = threading.Lock()
        self._call_off: Callable[[], None] | None = None
        self._rebuilt_at = float("-inf")
        self._short_lived = 0
        self._stopped = False

    def heard(self, text: str) -> None:
        if not _GONE.search(text):
            return
        with self._lock:
            if self._now() - self._rebuilt_at >= QUIET_S:
                self._lost(f"The video output lost the graphics card (mpv: {text.strip()})")

    def stop(self) -> None:
        with self._lock:
            self._stopped = True
            if self._call_off is not None:
                self._call_off()
                self._call_off = None

    def _lost(self, why: str) -> None:
        if self._stopped or self._call_off is not None:
            return
        self._short_lived = self._short_lived + 1 if self._now() - self._rebuilt_at < LASTED_S else 0
        wait = min(FIRST_WAIT_S * 2 ** self._short_lived, LONGEST_WAIT_S)
        logger.warning("%s; building a new one in %.0fs", why, wait)
        self._call_off = self._later(wait, self._rebuild_now)

    def _rebuild_now(self) -> None:
        with self._lock:
            if self._stopped:
                return
            self._call_off = _under_way
        came_up = self._rebuild()
        with self._lock:
            self._call_off = None
            self._rebuilt_at = self._now()
            if came_up:
                logger.info("A new video output came up on the graphics card")
            else:
                self._lost("The new video output did not come up")
