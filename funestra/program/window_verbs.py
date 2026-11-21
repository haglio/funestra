from __future__ import annotations

import ctypes
import warnings
from collections.abc import Callable

WINDOW_SHOW = "WINDOW_SHOW"
WINDOW_HIDE = "WINDOW_HIDE"
WINDOW_MINIMIZE = "WINDOW_MINIMIZE"
WINDOW_ON_TOP = "WINDOW_ON_TOP"
WINDOW_NOT_ON_TOP = "WINDOW_NOT_ON_TOP"
WINDOW_PLACE = "WINDOW_PLACE"

HWND_TOPMOST, HWND_NOTOPMOST = -1, -2
_SWP_NOSIZE, _SWP_NOMOVE, _SWP_NOACTIVATE = 0x0001, 0x0002, 0x0010


def window_place(x: int, y: int, width: int, height: int) -> str:
    return f"{WINDOW_PLACE} {x} {y} {width} {height}"


def stack_without_the_keyboard(pygame, after: int) -> None:
    hwnd = pygame.display.get_wm_info()["window"]
    ctypes.WinDLL("user32").SetWindowPos(
        ctypes.c_void_p(hwnd), ctypes.c_void_p(after),
        0, 0, 0, 0, _SWP_NOSIZE | _SWP_NOMOVE | _SWP_NOACTIVATE)


class WindowVerbs:
    def __init__(self, pygame, *, stack: Callable[[object, int], None] | None = None) -> None:
        self._pygame = pygame
        self._stack = stack if stack is not None else (
            lambda _window, after: stack_without_the_keyboard(pygame, after))

    def __call__(self, command: str) -> bool:
        verb, *values = command.split()
        if verb == WINDOW_PLACE:
            return self._place(values)
        answer = {WINDOW_SHOW: self._show, WINDOW_HIDE: self._hide,
                  WINDOW_MINIMIZE: self._minimize,
                  WINDOW_ON_TOP: lambda: self._stack(self._window(), HWND_TOPMOST),
                  WINDOW_NOT_ON_TOP: lambda: self._stack(self._window(), HWND_NOTOPMOST)}.get(verb)
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
        window.focus()

    def _hide(self) -> None:
        self._window().hide()

    def _minimize(self) -> None:
        self._window().minimize()

    def _place(self, values: list[str]) -> bool:
        try:
            x, y, width, height = (int(value) for value in values)
        except ValueError:
            return False
        window = self._window()
        window.position = (x, y)
        window.size = (width, height)
        return True
