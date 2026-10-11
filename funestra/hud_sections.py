from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__: list[str] = []

SECTION_GAP = 6
DIVIDER_H = 1


@dataclass(frozen=True)
class Stacked:
    tops: tuple[int, ...]
    dividers: tuple[int, ...]
    end: int


def blocks_height(heights: Sequence[int], gap: int) -> int:
    present = [height for height in heights if height]
    return sum(present) + gap * max(0, len(present) - 1)


def stack(top: int, heights: Sequence[int]) -> Stacked:
    tops: list[int] = []
    dividers: list[int] = []
    y = top
    for height in heights:
        if height and y > top:
            dividers.append(y + SECTION_GAP)
            y += 2 * SECTION_GAP + DIVIDER_H
        tops.append(y)
        y += height
    return Stacked(tuple(tops), tuple(dividers), y)
