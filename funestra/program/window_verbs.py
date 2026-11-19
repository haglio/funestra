from __future__ import annotations

import ctypes
import warnings
from collections.abc import Callable

WINDOW_SHOW = "WINDOW_SHOW"
WINDOW_HIDE = "WINDOW_HIDE"
WINDOW_MINIMIZE = "WINDOW_MINIMIZE"
WINDOW_FRONT = "WINDOW_FRONT"
WINDOW_PLACE = "WINDOW_PLACE"

_HWND_TOP = 0
_SWP_NOSIZE, _SWP_NOMOVE, _SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010


def window_place(x: int, y: int, width: int, height: int) -> str:
    return f"{WINDOW_PLACE} {x} {y} {width} {height}"


def lift_without_the_keyboard(pygame) -> None:
    hwnd = pygame.display.get_wm_info()["window"]
    ctypes.WinDLL("user32").SetWindowPos(
        hwnd, _HWND_TOP, 0, 0, 0, 0, _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE)


class WindowVerbs:
    def __init__(self, pygame, *, lift: Callable[[object], None] | None = None) -> None:
        self._pygame = pygame
        self._lift = lift if lift is not None else (lambda _window: lift_without_the_keyboard(pygame))

    def __call__(self, command: str) -> bool:
        verb, *values = command.split()
        if verb == WINDOW_PLACE:
            return self._place(values)
        answer = {WINDOW_SHOW: self._show, WINDOW_HIDE: self._hide,
                  WINDOW_MINIMIZE: self._minimize, WINDOW_FRONT: self._front}.get(verb)
        if answer is None or values:
            return False
        answer()
        return True

    def _window(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            return self._pygame.Window.from_display_module()

    def _show(self) -> None:
        window = self._window()
        window.restore()
        window.show()

    def _hide(self) -> None:
        self._window().hide()

    def _minimize(self) -> None:
        self._window().minimize()

    def _front(self) -> None:
        self._lift(self._window())

    def _place(self, values: list[str]) -> bool:
        try:
            x, y, width, height = (int(value) for value in values)
        except ValueError:
            return False
        window = self._window()
        window.position = (x, y)
        window.size = (width, height)
        return True
