"""A funscript's colors across the scrubber: how fast the script moves in each pixel of the track."""
from __future__ import annotations

from shared_ui.heat import heat_at

from .funscript import Funscript


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
    return [heat_at(speed)
            for speed in bin_speeds(fs, buckets, start_ms=start_ms, end_ms=end_ms)]
