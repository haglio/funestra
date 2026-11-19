from __future__ import annotations

import math
from dataclasses import dataclass

from .ken_burns import CLOSEST, Fit, View

NOTCH = 1.25


@dataclass(frozen=True)
class WheelZoom:
    factor: float = 1.0
    shift: tuple[float, float] = (0.0, 0.0)

    def zoomed_at(self, under: View, fit: Fit, point: tuple[float, float],
                  steps: int) -> WheelZoom:
        closest = max(1.0, CLOSEST / under.zoom)
        factor = max(1.0, min(self.factor * NOTCH ** steps, closest))
        if math.isclose(factor, 1.0):
            return WheelZoom()
        grown = factor / self.factor
        shift = tuple(at - (at - by) * grown for at, by in zip(point, self.shift, strict=True))
        return WheelZoom(factor, shift).kept_on_screen(under, fit)

    def panned_by(self, under: View, fit: Fit, moved: tuple[float, float]) -> WheelZoom:
        if math.isclose(self.factor, 1.0):
            return self
        shift = tuple(by + more for by, more in zip(self.shift, moved, strict=True))
        return WheelZoom(self.factor, shift).kept_on_screen(under, fit)

    def over(self, under: View, fit: Fit) -> View:
        sides = self._sides(under, fit)
        if sides is None:
            return under
        return View(under.zoom * self.factor,
                    *(_align(room, size, start) for room, size, start in sides))

    def kept_on_screen(self, under: View, fit: Fit) -> WheelZoom:
        sides = self._sides(under, fit)
        if sides is None:
            return self
        shift = tuple(by + _kept(room, size, start) - start
                      for by, (room, size, start) in zip(self.shift, sides, strict=True))
        return WheelZoom(self.factor, shift)

    def _sides(self, under: View, fit: Fit) -> list[tuple[float, float, float]] | None:
        fitted = fit.fitted()
        if fitted is None:
            return None
        sides = []
        for room, side, align, by in zip(fit.viewport, fitted, (under.align_x, under.align_y),
                                         self.shift, strict=True):
            size = side * under.zoom
            sides.append((room, size * self.factor,
                          _start(room, size, align) * self.factor + by))
        return sides


def _start(room: float, size: float, align: float) -> float:
    return (room - size) * (align + 1.0) / 2.0


def _kept(room: float, size: float, start: float) -> float:
    if size <= room or math.isclose(size, room):
        return (room - size) / 2.0
    return max(room - size, min(0.0, start))


def _align(room: float, size: float, start: float) -> float:
    if size <= room or math.isclose(size, room):
        return 0.0
    return max(-1.0, min(1.0, 2.0 * start / (room - size) - 1.0))
