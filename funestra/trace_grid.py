from __future__ import annotations

SLIDE_QUANTUM_MS = 40


def on_the_grid(position_ms: int) -> int:
    return position_ms - position_ms % SLIDE_QUANTUM_MS
