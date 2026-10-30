"""What the mouse does to a Funestra's window: the HUD, a corner the HUD
can be sent to, or the item.

The track, the time and the volume are a block of the HUD now
(:mod:`funestra.hud_row`), and the HUD places a press on them itself, so
what is left here is the HUD first and the item under it.
"""
from __future__ import annotations

from collections.abc import Callable

OMNIPAUSE_TOGGLE = "omnipause_toggle"
NOWHERE = (-1, -1)


def _nothing() -> None:
    pass


class Pointer:
    def __init__(self, *, hud=None, corners=None,
                 item: Callable[[], None] = _nothing) -> None:
        self._hud = hud
        self._corners = corners
        self._item = item

    def press(self, mx: int, my: int) -> None:
        if self._hud is not None and self._hud.press(mx, my):
            return
        if self._corners is not None and self._corners.press(mx, my):
            return
        self._item()

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
