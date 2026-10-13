from __future__ import annotations

from funestra.host_controls import BarHud, HostControlsHud

CHOICES = ("Plain", "Curved", "The widest name of them", "Round")
BAR = BarHud("Spread", 160.0, 40.0, 180.0, unit="°")


def a_hud(chosen: str = "Curved", *, bar: BarHud | None = BAR) -> HostControlsHud:
    return HostControlsHud(chosen, CHOICES, bar=bar)


class AHost:
    def __init__(self, shows: HostControlsHud | None = None) -> None:
        self.shows = a_hud() if shows is None else shows
        self.picked: list[int] = []
        self.set_to: list[float] = []

    def hud(self) -> HostControlsHud | None:
        return self.shows

    def pick(self, index: int) -> None:
        self.picked.append(index)

    def set_bar(self, value: float) -> None:
        self.set_to.append(value)


def middle_of(rect) -> tuple[int, int]:
    x, y, width, height = rect
    return x + width // 2, y + height // 2
