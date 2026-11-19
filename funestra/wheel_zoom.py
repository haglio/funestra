from __future__ import annotations

import math

from .ken_burns import CLOSEST, Fit, View

NOTCH = 1.25


def zoomed_at(view: View, fit: Fit, point: tuple[float, float], steps: int) -> View:
    zoom = min(max(view.zoom * NOTCH ** steps, 1.0), CLOSEST)
    return _placed(view, fit, zoom, lambda at, start, was, now: at - (at - start) * now / was, point)


def panned_by(view: View, fit: Fit, moved: tuple[float, float]) -> View:
    return _placed(view, fit, view.zoom, lambda by, start, _was, _now: start + by, moved)


def _placed(view: View, fit: Fit, zoom: float, new_start, along: tuple[float, float]) -> View:
    fitted = fit.fitted()
    if fitted is None:
        return view
    aligns = []
    for room, size, align, at in zip(fit.viewport, fitted, (view.align_x, view.align_y), along,
                                     strict=True):
        was, now = size * view.zoom, size * zoom
        aligns.append(_align(room, now, new_start(at, _start(room, was, align), was, now)))
    return View(zoom, *aligns)


def _start(room: float, size: float, align: float) -> float:
    return (room - size) * (align + 1.0) / 2.0


def _align(room: float, size: float, start: float) -> float:
    if size <= room or math.isclose(size, room):
        return 0.0
    return max(-1.0, min(1.0, 2.0 * start / (room - size) - 1.0))
