from __future__ import annotations

import random
from itertools import pairwise

import pytest

from funestra import learned_motion
from funestra.learned_model import LearnedModel, Phrase, classify
from funestra.learned_motion import (
    LearnedMotionState,
    enable_learned_motion,
    tick_learned_motion,
)
from funestra.robot_hand import MAX_TICK_SECONDS, RobotHandState, bpm_for_speed


def _phrase(duration_ms: int, low: int, high: int, swings: int = 16) -> Phrase:
    return Phrase(tuple((duration_ms, high if i % 2 == 0 else low) for i in range(swings)))


def _model(*phrases: Phrase, native_cycle_ms: float | None = None) -> LearnedModel:
    model = LearnedModel(native_cycle_ms=native_cycle_ms or 60_000 / bpm_for_speed(50))
    for phrase in phrases:
        model.phrases.setdefault(classify(phrase), []).append(phrase)
        model.seen[classify(phrase)] = model.seen.get(classify(phrase), 0) + 1
    return model


def _playing(model: LearnedModel, seed: int = 1, **bars) -> tuple[RobotHandState, LearnedMotionState]:
    hand = RobotHandState(playing=True, **bars)
    state = LearnedMotionState(model=model, rng=random.Random(seed))
    enable_learned_motion(state)
    tick_learned_motion(hand, state, now=100.0)
    return hand, state


def _run(hand, state, seconds: float, *, start: float = 100.0, dt: float = 0.05) -> float:
    now = start
    for _ in range(round(seconds / dt)):
        now = round(now + dt, 6)
        tick_learned_motion(hand, state, now=now)
    return now


class TestPlayingThePhrases:
    def test_the_motion_follows_the_phrases_swing_by_swing(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)))

        assert learned_motion.position(state, hand) == pytest.approx(0.0)
        now = _run(hand, state, 0.25)
        assert learned_motion.position(state, hand) == pytest.approx(40.0)
        now = _run(hand, state, 0.25, start=now)
        assert learned_motion.position(state, hand) == pytest.approx(80.0)
        now = _run(hand, state, 0.25, start=now)
        assert learned_motion.position(state, hand) == pytest.approx(50.0)
        _run(hand, state, 0.25, start=now)
        assert learned_motion.position(state, hand) == pytest.approx(20.0)

    def test_each_phrase_rises_from_where_the_last_one_ended(self):
        model = _model(_phrase(500, 20, 80), _phrase(200, 40, 60))
        _hand, state = _playing(model)

        assert state.positions[0] == 0.0
        lows = state.positions[2::2]
        highs = state.positions[1::2]
        assert set(lows) <= {20.0, 40.0}
        assert set(highs) <= {80.0, 60.0}
        assert all(t1 > t0 for t0, t1 in pairwise(state.times))

    def test_the_bars_are_the_envelope_the_phrases_play_inside(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)), amplitude=50, intended_center=50)
        _run(hand, state, 0.5)

        assert learned_motion.position(state, hand) == pytest.approx(25 + 0.8 * 50)

    def test_the_speed_bar_scales_the_pace(self):
        quick_hand, quick = _playing(_model(_phrase(500, 20, 80)), speed=68)
        steady_hand, steady = _playing(_model(_phrase(500, 20, 80)), speed=50)
        ratio = bpm_for_speed(68) / bpm_for_speed(50)

        _run(quick_hand, quick, 0.2)
        _run(steady_hand, steady, round(0.2 * ratio, 2))

        assert ratio == pytest.approx(2.0, abs=0.05)
        assert learned_motion.position(quick, quick_hand) == pytest.approx(
            learned_motion.position(steady, steady_hand), abs=1.0)

    def test_the_bar_means_the_same_cycles_a_minute_it_means_for_the_wave(self):
        hand, state = _playing(_model(_phrase(300, 20, 80), native_cycle_ms=600.0), speed=50)
        one_cycle_s = 60.0 / bpm_for_speed(50)

        _run(hand, state, round(one_cycle_s / 2, 2))
        assert learned_motion.position(state, hand) == pytest.approx(80.0, abs=3.0)
        _run(hand, state, round(one_cycle_s / 2, 2), start=100.0 + round(one_cycle_s / 2, 2))
        assert learned_motion.position(state, hand) == pytest.approx(20.0, abs=3.0)

    def test_nothing_moves_while_the_motion_is_not_running(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)))
        hand.playing = False

        _run(hand, state, 1.0)

        assert state.clock == 0.0
        assert learned_motion.position(state, hand) == pytest.approx(0.0)

    def test_a_move_of_the_speed_bar_changes_the_pace_from_here_on_without_a_step(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)))
        _run(hand, state, 0.3)
        before_the_move = learned_motion.position(state, hand)

        hand.speed = 90

        assert learned_motion.position(state, hand) == pytest.approx(before_the_move)

    def test_a_clock_that_stalled_owes_the_motion_one_capped_tick_and_no_more(self):
        stalled_hand, stalled = _playing(_model(_phrase(500, 20, 80)))
        steady_hand, steady = _playing(_model(_phrase(500, 20, 80)))

        tick_learned_motion(stalled_hand, stalled, now=160.0)
        tick_learned_motion(steady_hand, steady, now=100.0 + MAX_TICK_SECONDS)

        assert stalled.clock == pytest.approx(steady.clock)

    def test_the_first_phrase_begins_where_the_device_already_is(self):
        hand = RobotHandState(playing=True)
        state = LearnedMotionState(model=_model(_phrase(500, 20, 80)), rng=random.Random(1))
        enable_learned_motion(state)

        tick_learned_motion(hand, state, now=100.0, start_fraction=0.35)

        assert learned_motion.position(state, hand) == pytest.approx(35.0)


class TestHandingTheDeviceAbout:
    def test_resting_at_the_floor_begins_again_from_the_floor(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)))
        now = _run(hand, state, 0.5)
        assert learned_motion.position(state, hand) == pytest.approx(80.0)

        learned_motion.rest_at_floor(state)
        assert learned_motion.position(state, hand) == pytest.approx(0.0)
        _run(hand, state, 0.25, start=now)

        assert learned_motion.position(state, hand) == pytest.approx(40.0)

    def test_switching_off_forgets_the_phrases(self):
        _hand, state = _playing(_model(_phrase(500, 20, 80)))

        assert learned_motion.toggle_learned_motion(state) is False
        assert not state.active
        assert state.times == []
        assert learned_motion.toggle_learned_motion(state) is True

    def test_a_command_aimed_ahead_lands_where_the_motion_will_be(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)))

        ahead = learned_motion.position(state, hand, lead_s=0.25)
        _run(hand, state, 0.25)

        assert ahead == pytest.approx(learned_motion.position(state, hand))


class TestWhatTheVisualizerDraws:
    def test_the_trace_is_the_coming_motion_on_knots_from_now(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)))

        heights, slide = learned_motion.trace_window(state, hand, samples=5, span_s=1.0)

        assert heights == pytest.approx([0.0, 0.4, 0.8, 0.5, 0.2, 0.5])
        assert slide == 0.0

    def test_the_drawing_holds_still_between_knots_and_slides_by_the_leftover(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)))
        before, _ = learned_motion.trace_window(state, hand, samples=5, span_s=1.0)

        _run(hand, state, 0.1)
        heights, slide = learned_motion.trace_window(state, hand, samples=5, span_s=1.0)

        assert heights == pytest.approx(before)
        assert slide == pytest.approx(0.4)

    def test_crossing_a_knot_moves_the_window_on_by_one_sample(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)))
        before, _ = learned_motion.trace_window(state, hand, samples=5, span_s=1.0)

        _run(hand, state, 0.3)
        heights, slide = learned_motion.trace_window(state, hand, samples=5, span_s=1.0)

        assert heights[:-1] == pytest.approx(before[1:])
        assert slide == pytest.approx(0.2)

    def test_resting_at_the_floor_shows_the_phrases_that_will_resume(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)))
        _run(hand, state, 0.3)

        learned_motion.rest_at_floor(state)
        heights, slide = learned_motion.trace_window(state, hand, samples=5, span_s=1.0)

        assert heights[0] == 0.0
        assert max(heights) > 0.5
        assert slide == pytest.approx(0.2)


class TestKeepingItGoing:
    def test_the_phrases_stay_laid_out_ahead_for_the_trace_and_a_command_aimed_ahead_and_the_past_is_let_go(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)))

        _run(hand, state, 120.0)

        assert state.times[-1] >= state.clock + 30.0
        assert state.times[0] <= state.clock < state.times[1]
        assert len(state.times) < 200


class TestTheModelThatShips:
    def test_it_loads_and_holds_phrases_of_more_than_one_pace(self):
        model = learned_motion.load_default_model()

        assert model
        assert len({cls[0] for cls in model.phrases}) > 3
        assert all(len(phrase.swings) == 16 for kept in model.phrases.values() for phrase in kept)


class TestWithoutPhrasesOrABar:
    def test_a_motion_with_no_phrases_rests_at_the_floor(self):
        state = LearnedMotionState()

        assert learned_motion.position(state, RobotHandState()) == 0.0
        assert learned_motion.trace_window(state, RobotHandState(), 3, 1.0) == ([0.0] * 4, 0.0)

    def test_with_no_bar_to_ask_the_motion_is_drawn_at_full_reach(self):
        hand, state = _playing(_model(_phrase(500, 20, 80)), amplitude=50)
        _run(hand, state, 0.25)

        assert learned_motion.position(state, None) == pytest.approx(40.0)
        assert learned_motion.position(state, hand) == pytest.approx(45.0)
