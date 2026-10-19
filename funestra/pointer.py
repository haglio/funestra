"""What the mouse does to a Funestra's window: the panel, a corner the panel
can be sent to, or the picture.

The track, the time and the volume are a block of the panel now
(:mod:`funestra.hud_row`), and the panel places a press on them itself, so
what is left here is the panel first and the picture under it.
"""
from __future__ import annotations

from collections.abc import Callable

from .timeline import bar_track_x

OMNIPAUSE_TOGGLE = "omnipause_toggle"
NOWHERE = (-1, -1)


def time_at(mx: int, *, win_w: int, duration_ms: float,
            window: tuple[float, float] | None = None) -> float:
    """The time a press *mx* across a track *win_w* wide names.  The headset
    places a squeeze on the row under its console with it."""
    start_ms, end_ms = window or (0.0, duration_ms)
    if end_ms <= start_ms:
        end_ms = start_ms + duration_ms
    x0, x1 = bar_track_x(win_w)
    fraction = min(1.0, max(0.0, (mx - x0) / max(1, x1 - x0)))
    return start_ms + fraction * (end_ms - start_ms)


def _nothing() -> None:
    pass


class Pointer:
    def __init__(self, *, hud=None, corners=None,
                 picture: Callable[[], None] = _nothing) -> None:
        self._hud = hud
        self._corners = corners
        self._picture = picture

    def press(self, mx: int, my: int) -> None:
        if self._hud is not None and self._hud.press(mx, my):
            return
        if self._corners is not None and self._corners.press(mx, my):
            return
        self._picture()

    def wheel(self, mx: int, my: int, steps: int) -> None:
        if self._hud is not None:
            self._hud.wheel(mx, my, steps)

    def release(self) -> None:
        if self._hud is not None:
            self._hud.release()

    def leave(self) -> None:
        if self._hud is not None:
            self._hud.motion(*NOWHERE)
        if self._corners is not None:
            self._corners.leave()

    def motion(self, mx: int, my: int, *, held: bool) -> None:
        if self._hud is None:
            return
        self._hud.motion(mx, my)
        if self._corners is not None:
            self._corners.motion(mx, my)
        if not held:
            self._hud.release()
        elif self._hud.holding:
            self._hud.drag_to(mx, my)
