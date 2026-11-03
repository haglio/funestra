from __future__ import annotations

Rect = tuple[int, int, int, int]


def contains(rect: Rect, px: int, py: int) -> bool:
    x, y, w, h = rect
    return x <= px < x + w and y <= py < y + h
