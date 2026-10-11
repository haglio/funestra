from __future__ import annotations

from enum import StrEnum

# What the siblings reach: a consumer declares its need by landing the code that
# imports it, and this gate is what holds the two in step -- so a name joins this
# list in the landing after the app half that reaches it, never before.
__all__ = ["HudCorner", "HudEdge"]

_SIDES = {"left": False, "right": True}
_ENDS = {"up": False, "down": True}


class HudCorner(StrEnum):
    UPPER_LEFT = "upper_left"
    UPPER_RIGHT = "upper_right"
    LOWER_RIGHT = "lower_right"
    LOWER_LEFT = "lower_left"

    @property
    def right(self) -> bool:
        return self in (HudCorner.UPPER_RIGHT, HudCorner.LOWER_RIGHT)

    @property
    def lower(self) -> bool:
        return self in (HudCorner.LOWER_RIGHT, HudCorner.LOWER_LEFT)

    def toward(self, direction: str) -> HudCorner:
        if direction in _SIDES:
            return corner_at(right=_SIDES[direction], lower=self.lower)
        if direction in _ENDS:
            return corner_at(right=self.right, lower=_ENDS[direction])
        return self

    def turned(self, *, clockwise: bool) -> HudCorner:
        return _next_round(_CORNERS_ROUND, self, clockwise=clockwise)


class HudEdge(StrEnum):
    UPPER = "upper"
    RIGHT = "right"
    LOWER = "lower"
    LEFT = "left"

    def toward(self, direction: str) -> HudEdge:
        return _EDGE_TOWARD.get(direction, self)

    def turned(self, *, clockwise: bool) -> HudEdge:
        return _next_round(tuple(HudEdge), self, clockwise=clockwise)


_EDGE_TOWARD = {"up": HudEdge.UPPER, "down": HudEdge.LOWER,
                "left": HudEdge.LEFT, "right": HudEdge.RIGHT}


def corner_at(*, right: bool, lower: bool) -> HudCorner:
    if lower:
        return HudCorner.LOWER_RIGHT if right else HudCorner.LOWER_LEFT
    return HudCorner.UPPER_RIGHT if right else HudCorner.UPPER_LEFT


_CORNERS_ROUND = (HudCorner.UPPER_LEFT, HudCorner.UPPER_RIGHT,
                  HudCorner.LOWER_RIGHT, HudCorner.LOWER_LEFT)


def _next_round(ring, place, *, clockwise: bool):
    order = ring if clockwise else ring[::-1]
    return order[(order.index(place) + 1) % len(order)]


class PointerReading[R]:
    def __init__(self, nowhere: R) -> None:
        self._nowhere = nowhere
        self.reading: R = nowhere
        self._place: tuple[HudCorner, bool] | None = None

    def take(self, reading: R) -> None:
        self.reading = reading

    def on(self, panel) -> R:
        place = None if panel is None else (panel.hud_corner, panel.hud_minimized)
        if place != self._place:
            self._place, self.reading = place, self._nowhere
        return self.reading


def block_x(corner: HudCorner, *, panel_width: int, extent: int, pad: int,
            reserve: int = 0) -> int:
    if not corner.right:
        return pad + reserve
    return max(pad, panel_width - pad - reserve - extent)


def hud_origin(corner: HudCorner, *, panel: tuple[int, int], window: tuple[int, int],
               margin: int, lower_edge: int = 0,
               inset: tuple[int, int] = (0, 0)) -> tuple[int, int]:
    panel_w, panel_h = panel
    win_w, win_h = window
    across, down = margin + inset[0], margin + inset[1]
    x = win_w - across - panel_w if corner.right else across
    y = win_h - lower_edge - down - panel_h if corner.lower else down
    return max(0, x), max(0, y)
