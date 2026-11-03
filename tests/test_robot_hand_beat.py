from __future__ import annotations

import pytest

from funestra.robot_hand_beat import BeatEngine, advance_beat


class TestUpdateEngine:
    def test_initial_raw_bpm_sets_estimated_and_target_bpm(self):
        engine = BeatEngine(last_tick=100.0)

        returned = advance_beat(
            engine,
            now=100.05,
            auto_active=False,
            raw_bpm=120.0,
            sync_pulse_id=0,
            beats_per_loop=4.0,
            bpm_smoothing=0.2,
            sync_strength=0.35,
            paused=False,
        )

        assert returned is None, "advance_beat is a command, not a query"
        assert engine.target_bpm == pytest.approx(120.0)
        assert engine.estimated_bpm == pytest.approx(120.0)

    def test_smoothing_moves_estimated_bpm_toward_target(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=100.0, target_bpm=100.0)

        advance_beat(
            engine,
            now=100.05,
            auto_active=False,
            raw_bpm=130.0,
            sync_pulse_id=0,
            beats_per_loop=4.0,
            bpm_smoothing=0.25,
            sync_strength=0.35,
            paused=False,
        )

        assert engine.target_bpm == pytest.approx(130.0)
        assert engine.estimated_bpm == pytest.approx(107.5)

    def test_auto_active_advances_phase_by_one_tick_of_the_loop(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=120.0, target_bpm=120.0, phase=0.1)

        returned = advance_beat(
            engine,
            now=100.05,
            auto_active=True,
            raw_bpm=None,
            sync_pulse_id=0,
            beats_per_loop=4.0,
            bpm_smoothing=0.2,
            sync_strength=0.35,
            paused=False,
        )

        assert returned is None
        assert engine.phase == pytest.approx(0.125)

    def test_paused_does_not_advance_phase_even_when_auto_active(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=120.0, target_bpm=120.0, phase=0.4)

        returned = advance_beat(
            engine,
            now=100.05,
            auto_active=True,
            raw_bpm=None,
            sync_pulse_id=0,
            beats_per_loop=4.0,
            bpm_smoothing=0.2,
            sync_strength=0.35,
            paused=True,
        )

        assert returned is None
        assert engine.phase == pytest.approx(0.4)

    def test_a_sync_pulse_never_pulls_the_phase_backward(self):
        engine = BeatEngine(last_tick=100.0, phase=0.4, seen_sync_pulse_id=1)

        advance_beat(
            engine,
            now=100.01,
            auto_active=False,
            raw_bpm=None,
            sync_pulse_id=2,
            beats_per_loop=4.0,
            bpm_smoothing=0.2,
            sync_strength=0.5,
            paused=False,
        )

        assert engine.seen_sync_pulse_id == 2
        assert engine.phase == pytest.approx(0.4)

    def test_a_sync_pulse_pulls_a_lagging_phase_forward(self):
        engine = BeatEngine(last_tick=100.0, phase=0.8, seen_sync_pulse_id=1)

        advance_beat(
            engine,
            now=100.01,
            auto_active=False,
            raw_bpm=None,
            sync_pulse_id=2,
            beats_per_loop=4.0,
            bpm_smoothing=0.2,
            sync_strength=0.5,
            paused=False,
        )

        assert engine.seen_sync_pulse_id == 2
        assert engine.phase == pytest.approx(0.9)

    def test_dt_is_clamped_to_avoid_large_phase_jumps(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=120.0, target_bpm=120.0, phase=0.0)

        advance_beat(
            engine,
            now=101.0,
            auto_active=True,
            raw_bpm=None,
            sync_pulse_id=0,
            beats_per_loop=4.0,
            bpm_smoothing=0.2,
            sync_strength=0.35,
            paused=False,
        )

        assert engine.phase == pytest.approx(0.05)
