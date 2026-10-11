"""A rectangle, and the one question every HUD asks of one.

Its own module because ``console`` and ``satellite_hud`` are deliberately free
of Pillow, so this cannot live beside the painters that also want it.
"""
from __future__ import annotations

__all__: list[str] = []  # package-internal: no sibling reaches anything here

Rect = tuple[int, int, int, int]  # (x, y, w, h)


def contains(rect: Rect, px: int, py: int) -> bool:
    """Whether ``(px, py)`` is in *rect* — near edges inside, far edges out."""
    x, y, w, h = rect
    return x <= px < x + w and y <= py < y + h
