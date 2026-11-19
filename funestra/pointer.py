from __future__ import annotations

from collections.abc import Callable

OMNIPAUSE_TOGGLE = "omnipause_toggle"
PRESSED_AGAIN = "pressed_again"
NOWHERE = (-1, -1)


def _nothing(*_where: int) -> None:
    pass


class Pointer:
    def __init__(self, *, hud=None, corners=None,
                 item: Callable[[], None] = _nothing,
                 item_again: Callable[[], None] = _nothing,
                 zoom: Callable[[int, int, int], None] = _nothing,
                 pan: Callable[[int, int], None] = _nothing) -> None:
        self._hud = hud
        self._corners = corners
        self._item = item
        self._item_again = item_again
        self._zoom = zoom
        self._pan = pan
        self._dragging_from: tuple[int, int] | None = None

    def press(self, mx: int, my: int) -> None:
        self._press(mx, my)

    def press_again(self, mx: int, my: int) -> None:
        if self._press(mx, my):
            self._item_again()

    def _press(self, mx: int, my: int) -> bool:
        if self._hud is not None and self._hud.press(mx, my):
            return False
        if self._corners is not None and self._corners.press(mx, my):
            return False
        self._item()
        return True

    def wheel(self, mx: int, my: int, steps: int) -> None:
        if self._hud is None or not self._hud.wheel(mx, my, steps):
            self._zoom(mx, my, steps)

    def wheel_press(self, mx: int, my: int) -> None:
        if self._hud is None or not self._hud.covers(mx, my):
            self._dragging_from = (mx, my)

    def wheel_release(self) -> None:
        self._dragging_from = None

    def right_press(self, mx: int, my: int) -> None:
        if self._hud is not None:
            self._hud.right_press(mx, my)

    def release(self) -> None:
        if self._hud is not None:
            self._hud.release()

    def leave(self) -> None:
        if self._hud is not None:
            self._hud.motion(*NOWHERE)
        if self._corners is not None:
            self._corners.leave()

    def motion(self, mx: int, my: int, *, held: bool) -> None:
        if self._dragging_from is not None:
            fx, fy = self._dragging_from
            self._dragging_from = (mx, my)
            self._pan(mx - fx, my - fy)
        if self._hud is None:
            return
        self._hud.motion(mx, my)
        if self._corners is not None:
            self._corners.motion(mx, my)
        if not held:
            self._hud.release()
        elif self._hud.holding:
            self._hud.drag_to(mx, my)
