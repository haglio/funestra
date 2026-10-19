"""The beat the Robot Hand moves to.

A phase that runs round once per loop at a BPM, and two things that bend it:
the BPM it is told is smoothed into rather than jumped to, and a sync pulse eases
the phase toward the downbeat by a fraction of the error — but only ever forward.
A pulse that arrives while the loop is already past the downbeat catches it up;
one that arrives while the loop leads the beat holds rather than dragging the
phase back, because the phase is what a clip is scrubbed by and the cursor must
never run backwards.  The phase is the one clock the hand and the picture share.

Where the beat comes from is the caller's question, and :class:`Beat` is its
answer for one tick.  Under the broker it is a BPM and a pulse published over
UDP and a paused flag read off a file; on its own the hand's speed *is* the BPM
and its stopping *is* the pause.  The four numbers are the same four either way,
which is what lets one engine serve both.

Pure arithmetic: no device, no clock of its own.
"""
from __future__ import annotations

from dataclasses import dataclass

# The most wall time one tick may move the phase, the same cap
# :func:`funestra.robot_hand.phase_advanced` puts on a caller's own clock: a
# clock that stalled comes back owing a step the motion should not take at once.
_MAX_TICK_SECONDS = 0.1


@dataclass
class BeatEngine:
    phase: float = 0.0
    estimated_bpm: float | None = None
    target_bpm: float | None = None
    last_tick: float = 0.0
    seen_sync_pulse_id: int = 0


@dataclass(frozen=True)
class Beat:
    """What the engine is told this tick, and which of the two decided it.

    ``robot_hand_active`` is which of the two answered -- the hand itself, or
    the broker -- and it is the fact the rest of a tick branches on.
    """

    robot_hand_active: bool
    auto_active: bool
    raw_bpm: float | None
    paused: bool
    sync_pulse_id: int


def advance_beat(
    engine: BeatEngine,
    *,
    now: float,
    auto_active: bool,
    raw_bpm: float | None,
    sync_pulse_id: int,
    beats_per_loop: float,
    bpm_smoothing: float,
    sync_strength: float,
    paused: bool,
) -> None:
    dt = now - engine.last_tick
    engine.last_tick = now
    dt = max(0.0, min(dt, _MAX_TICK_SECONDS))

    if raw_bpm is not None:
        engine.target_bpm = float(raw_bpm)
        if engine.estimated_bpm is None:
            engine.estimated_bpm = float(raw_bpm)

    if engine.estimated_bpm is not None and engine.target_bpm is not None:
        alpha = max(0.0, min(1.0, bpm_smoothing))
        engine.estimated_bpm = engine.estimated_bpm + (engine.target_bpm - engine.estimated_bpm) * alpha

    if auto_active and engine.estimated_bpm and engine.estimated_bpm > 0 and not paused:
        loop_duration = (60.0 / engine.estimated_bpm) * beats_per_loop
        engine.phase = (engine.phase + (dt / loop_duration)) % 1.0

    if sync_pulse_id != engine.seen_sync_pulse_id:
        engine.seen_sync_pulse_id = sync_pulse_id
        phase = engine.phase
        if phase > 0.5:
            strength = max(0.0, min(1.0, sync_strength))
            engine.phase = (engine.phase + (1.0 - phase) * strength) % 1.0
