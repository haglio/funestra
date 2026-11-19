from __future__ import annotations

from dataclasses import dataclass

from .flick_flip import HALF_A_LOOP

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
    robot_hand_active: bool
    auto_active: bool
    raw_bpm: float | None
    paused: bool
    sync_pulse_id: int


@dataclass(frozen=True)
class BeatTuning:
    beats_per_loop: float
    bpm_smoothing: float
    sync_strength: float


def _seconds_since_its_last_tick(engine: BeatEngine, now: float) -> float:
    dt = now - engine.last_tick
    engine.last_tick = now
    return max(0.0, min(dt, _MAX_TICK_SECONDS))


def _turn_the_phase(engine: BeatEngine, beat: Beat, tuning: BeatTuning, dt: float) -> None:
    if beat.auto_active and engine.estimated_bpm and engine.estimated_bpm > 0 and not beat.paused:
        loop_duration = (60.0 / engine.estimated_bpm) * tuning.beats_per_loop
        engine.phase = (engine.phase + (dt / loop_duration)) % 1.0


def advance_phase(engine: BeatEngine, beat: Beat, tuning: BeatTuning, *, now: float) -> None:
    _turn_the_phase(engine, beat, tuning, _seconds_since_its_last_tick(engine, now))


def advance_beat(engine: BeatEngine, beat: Beat, tuning: BeatTuning, *, now: float) -> None:
    dt = _seconds_since_its_last_tick(engine, now)

    if beat.raw_bpm is not None:
        engine.target_bpm = float(beat.raw_bpm)
        if engine.estimated_bpm is None:
            engine.estimated_bpm = float(beat.raw_bpm)

    if engine.estimated_bpm is not None and engine.target_bpm is not None:
        alpha = max(0.0, min(1.0, tuning.bpm_smoothing))
        engine.estimated_bpm = engine.estimated_bpm + (engine.target_bpm - engine.estimated_bpm) * alpha

    _turn_the_phase(engine, beat, tuning, dt)

    if beat.sync_pulse_id != engine.seen_sync_pulse_id:
        engine.seen_sync_pulse_id = beat.sync_pulse_id
        phase = engine.phase
        if phase > HALF_A_LOOP:
            strength = max(0.0, min(1.0, tuning.sync_strength))
            engine.phase = (engine.phase + (1.0 - phase) * strength) % 1.0
