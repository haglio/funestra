"""A funscript's colors across the scrubber: how fast the script moves in each pixel of the track."""
from __future__ import annotations

from itertools import pairwise

from .funscript import Funscript

__all__: list[str] = []

_GRADIENT: list[tuple[float, tuple[int, int, int]]] = [
    (0.0, (10, 14, 30)),
    (100.0, (30, 70, 230)),
    (200.0, (20, 210, 210)),
    (300.0, (40, 220, 50)),
    (400.0, (235, 220, 40)),
    (500.0, (240, 40, 30)),
]


def _speed_to_color(speed: float) -> tuple[int, int, int]:
    for (s0, c0), (s1, c1) in pairwise(_GRADIENT):
        if speed <= s1:
            frac = (speed - s0) / (s1 - s0)
            return tuple(round(lo + (hi - lo) * frac) for lo, hi in zip(c0, c1))
    return _GRADIENT[-1][1]


def bin_speeds(
    fs: Funscript, buckets: int, *, start_ms: float, end_ms: float,
) -> list[float]:
    if end_ms <= start_ms:
        return []
    bin_ms = (end_ms - start_ms) / buckets
    travel = [0.0] * buckets
    for (t0, p0), (t1, p1) in zip(fs.actions, fs.actions[1:]):
        if t1 <= t0:
            continue
        delta = abs(p1 - p0)
        first = max(0, int((t0 - start_ms) // bin_ms))
        last = min(buckets - 1, int((t1 - start_ms) // bin_ms))
        for b in range(first, last + 1):
            bin_start = start_ms + b * bin_ms
            overlap_ms = min(t1, bin_start + bin_ms) - max(t0, bin_start)
            travel[b] += delta * overlap_ms / (t1 - t0)
    bin_s = bin_ms / 1000.0
    return [units / bin_s for units in travel]


def build_heatmap(
    fs: Funscript, buckets: int, *, start_ms: float, end_ms: float,
) -> list[tuple[int, int, int]]:
    return [_speed_to_color(speed)
            for speed in bin_speeds(fs, buckets, start_ms=start_ms, end_ms=end_ms)]

