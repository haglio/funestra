"""The OSR2 part of the console -- its aim row, its OSR2 line and its readout --
drawn by a host on a surface of its own, and pressed there."""
from __future__ import annotations

from collections.abc import Callable

from .console_hud import ConsoleHud, ConsolePainter, hud_xy


class DevicePanel:
    def __init__(self, *, post: Callable[[str], None], painter=None) -> None:
        self._post = post
        self._painter = painter if painter is not None else ConsolePainter(device_only=True)

    def drawing(self, hud: ConsoleHud) -> tuple[bytes, tuple[int, int]]:
        return self._painter.rgba(hud)

    picture = drawing

    def press(self, x: int, y: int) -> None:
        self._ask(self._painter.press_at(*_on_the_painter(x, y)))

    def move(self, x: int, y: int) -> None:
        at = _on_the_painter(x, y)
        self._painter.motion(*at)
        if self._painter.holding:
            self._ask(self._painter.drag_to(*at))

    def release(self) -> None:
        self._painter.release()

    def leave(self) -> None:
        self._painter.leave()

    def _ask(self, command: str) -> None:
        if command:
            self._post(command)


def _on_the_painter(x: int, y: int) -> tuple[int, int]:
    """The painter places its panel at the inset it keeps from a Funestra's window."""
    left, top = hud_xy()
    return x + left, y + top
