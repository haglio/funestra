"""The 40 ms grid the trace reads the playhead on.

:mod:`funestra.drive_trace` snaps the playhead onto it before it finds the
turn in play, so the stable trace slides under a fixed set of knots at the
cadence Genau's own publishes repaint at.  :func:`funestra.drive_gate.next_handoff_touch`
snaps the same way before it looks up what the trace chose: read raw, the
status crossed a boundary up to a quantum before the trace did and asked for a
choice the trace had not made yet, and the published field went empty for a
frame.  One grid, read by both, so the two name the same turn on every frame.
"""
from __future__ import annotations

SLIDE_QUANTUM_MS = 40


def on_the_grid(position_ms: int) -> int:
    """*position_ms* snapped down onto the grid."""
    return position_ms - position_ms % SLIDE_QUANTUM_MS
