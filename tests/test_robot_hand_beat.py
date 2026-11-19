from __future__ import annotations

import pytest

from funestra.robot_hand_beat import Beat, BeatEngine, BeatTuning, advance_beat, advance_phase


class TestUpdateEngine:
    def test_initial_raw_bpm_sets_estimated_and_target_bpm(self):
        engine = BeatEngine(last_tick=100.0)

        returned = advance_beat(
            engine,
            Beat(robot_hand_active=True, auto_active=False, raw_bpm=120.0,
                 paused=False, sync_pulse_id=0),
            BeatTuning(4.0, 0.2, 0.35),
            now=100.05,
        )

        assert returned is None, "advance_beat is a command, not a query"
        assert engine.target_bpm == pytest.approx(120.0)
        assert engine.estimated_bpm == pytest.approx(120.0)

    def test_smoothing_moves_estimated_bpm_toward_target(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=100.0, target_bpm=100.0)

        advance_beat(
            engine,
            Beat(robot_hand_active=True, auto_active=False, raw_bpm=130.0,
                 paused=False, sync_pulse_id=0),
            BeatTuning(4.0, 0.25, 0.35),
            now=100.05,
        )

        assert engine.target_bpm == pytest.approx(130.0)
        assert engine.estimated_bpm == pytest.approx(107.5)

    def test_auto_active_advances_phase_by_one_tick_of_the_loop(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=120.0, target_bpm=120.0, phase=0.1)

        returned = advance_beat(
            engine,
            Beat(robot_hand_active=True, auto_active=True, raw_bpm=None,
                 paused=False, sync_pulse_id=0),
            BeatTuning(4.0, 0.2, 0.35),
            now=100.05,
        )

        assert returned is None
        assert engine.phase == pytest.approx(0.125)

    def test_paused_does_not_advance_phase_even_when_auto_active(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=120.0, target_bpm=120.0, phase=0.4)

        returned = advance_beat(
            engine,
            Beat(robot_hand_active=True, auto_active=True, raw_bpm=None,
                 paused=True, sync_pulse_id=0),
            BeatTuning(4.0, 0.2, 0.35),
            now=100.05,
        )

        assert returned is None
        assert engine.phase == pytest.approx(0.4)

    def test_a_sync_pulse_never_pulls_the_phase_backward_since_a_video_is_scrubbed_by_it_and_must_never_run_backward(self):
        engine = BeatEngine(last_tick=100.0, phase=0.4, seen_sync_pulse_id=1)

        advance_beat(
            engine,
            Beat(robot_hand_active=True, auto_active=False, raw_bpm=None,
                 paused=False, sync_pulse_id=2),
            BeatTuning(4.0, 0.2, 0.5),
            now=100.01,
        )

        assert engine.seen_sync_pulse_id == 2
        assert engine.phase == pytest.approx(0.4)

    def test_a_sync_pulse_pulls_a_lagging_phase_forward(self):
        engine = BeatEngine(last_tick=100.0, phase=0.8, seen_sync_pulse_id=1)

        advance_beat(
            engine,
            Beat(robot_hand_active=True, auto_active=False, raw_bpm=None,
                 paused=False, sync_pulse_id=2),
            BeatTuning(4.0, 0.2, 0.5),
            now=100.01,
        )

        assert engine.seen_sync_pulse_id == 2
        assert engine.phase == pytest.approx(0.9)

    def test_dt_is_clamped_to_avoid_large_phase_jumps(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=120.0, target_bpm=120.0, phase=0.0)

        advance_beat(
            engine,
            Beat(robot_hand_active=True, auto_active=True, raw_bpm=None,
                 paused=False, sync_pulse_id=0),
            BeatTuning(4.0, 0.2, 0.35),
            now=101.0,
        )

        assert engine.phase == pytest.approx(0.05)


class TestAdvancingThePhaseBetweenPasses:
    _PLAYING = Beat(robot_hand_active=True, auto_active=True, raw_bpm=130.0,
                    paused=False, sync_pulse_id=0)
    _TUNING = BeatTuning(4.0, 0.25, 0.35)

    def test_the_phase_turns_by_the_time_since_the_last_tick(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=120.0, target_bpm=120.0, phase=0.1)

        advance_phase(engine, self._PLAYING, self._TUNING, now=100.05)

        assert engine.phase == pytest.approx(0.125)

    def test_the_speed_is_left_alone_since_it_closes_on_its_target_once_a_pass_of_the_window(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=100.0, target_bpm=100.0)

        advance_phase(engine, self._PLAYING, self._TUNING, now=100.05)

        assert (engine.estimated_bpm, engine.target_bpm) == (100.0, 100.0)

    def test_a_pass_that_follows_turns_the_phase_only_by_the_time_since(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=120.0, target_bpm=120.0, phase=0.1)
        steady = Beat(robot_hand_active=True, auto_active=True, raw_bpm=120.0,
                      paused=False, sync_pulse_id=0)

        advance_phase(engine, steady, self._TUNING, now=100.03)
        advance_beat(engine, steady, self._TUNING, now=100.05)

        assert engine.phase == pytest.approx(0.125)

    def test_a_paused_hand_s_phase_stands_still(self):
        engine = BeatEngine(last_tick=100.0, estimated_bpm=120.0, target_bpm=120.0, phase=0.1)
        paused = Beat(robot_hand_active=True, auto_active=False, raw_bpm=120.0,
                      paused=True, sync_pulse_id=0)

        advance_phase(engine, paused, self._TUNING, now=100.05)

        assert engine.phase == 0.1
