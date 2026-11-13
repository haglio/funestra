from __future__ import annotations

import random

import pytest

from funestra import learned_motion
from funestra.hand_motion import HandMotion, ways_the_hand_moves
from funestra.learned_model import LearnedModel, Phrase, classify
from funestra.learned_motion import LearnedMotionState, enable_learned_motion
from funestra.robot_hand import (
    RobotHandState,
    TraceSpan,
    Waveform,
    WaveformShape,
    bpm_for_speed,
    position_fraction,
    trace_window,
)


def _learned() -> LearnedMotionState:
    phrase = Phrase(tuple((500, 80 if i % 2 == 0 else 20) for i in range(16)))
    model = LearnedModel(native_cycle_ms=60_000 / bpm_for_speed(50))
    model.phrases.setdefault(classify(phrase), []).append(phrase)
    model.seen[classify(phrase)] = 1
    return LearnedMotionState(model=model, rng=random.Random(1))


class StraightUp:
    def __init__(self, *, in_play: bool = True) -> None:
        self.in_play = in_play
        self.ticked: list[tuple[float, float]] = []
        self.rested = 0

    def tick(self, hand: RobotHandState, now: float, *, start_fraction: float) -> None:
        self.ticked.append((now, start_fraction))

    def height(self, hand: RobotHandState, phase: float, lead_s: float) -> float:
        return 100.0 * min(1.0, phase + lead_s)

    def trace(self, hand: RobotHandState, span: TraceSpan) -> tuple[list[float], float]:
        return [1.0] * (span.samples + 1), 0.5

    def rest_at_floor(self) -> None:
        self.rested += 1


class TestTheBars:
    def test_with_nothing_else_in_play_the_hand_swings_as_its_bars_and_shape_say(self):
        hand = RobotHandState(amplitude=60, intended_center=40, shape=WaveformShape.TRIANGLE)
        motion = HandMotion(hand, ways_the_hand_moves(None))

        assert motion.height(0.3) == pytest.approx(100.0 * position_fraction(
            0.3, shape=WaveformShape.TRIANGLE, amplitude=60, center=40))

    def test_aimed_ahead_it_is_where_the_swing_will_be_by_then(self):
        hand = RobotHandState(speed=50)
        motion = HandMotion(hand, ways_the_hand_moves(None))

        assert motion.height(0.1, lead_s=2.0) == pytest.approx(
            motion.height(0.1 + 2.0 * hand.bpm / 60.0))

    def test_its_trace_is_the_swing_laid_along_the_span(self):
        hand = RobotHandState(amplitude=60, intended_center=40)
        span = TraceSpan(0.25, 90.0, 8, 4.0)

        assert HandMotion(hand, ways_the_hand_moves(None)).trace(span) == trace_window(
            Waveform(hand.shape, 60, 40), span)

    def test_a_hand_nobody_named_swings_the_whole_stroke(self):
        assert HandMotion(None, ways_the_hand_moves(None)).height(0.5) == pytest.approx(100.0)


class TestTheLearnedMotion:
    def test_switched_off_it_leaves_the_swing_to_the_bars(self):
        hand, learned = RobotHandState(playing=True), _learned()
        motion = HandMotion(hand, ways_the_hand_moves(learned))

        motion.tick(100.0)

        assert motion.height(0.5) == pytest.approx(100.0)

    def test_switched_on_it_is_where_the_hand_is_and_what_the_trace_shows(self):
        hand, learned = RobotHandState(playing=True), _learned()
        enable_learned_motion(learned)
        motion = HandMotion(hand, ways_the_hand_moves(learned))

        motion.tick(100.0)
        motion.tick(100.05)

        assert motion.height(0.5) == learned_motion.position(learned, hand)
        assert motion.trace(TraceSpan(0.0, 60.0, 8, 4.0)) == learned_motion.trace_window(
            learned, hand, 8, 4.0)

    def test_it_begins_where_the_device_already_is(self):
        hand, learned = RobotHandState(playing=True), _learned()
        enable_learned_motion(learned)
        motion = HandMotion(hand, ways_the_hand_moves(learned))

        motion.tick(100.0, start_fraction=0.4)

        assert motion.height(0.0) == pytest.approx(40.0)

    def test_resting_at_the_floor_starts_its_phrases_over_from_the_floor(self):
        hand, learned = RobotHandState(playing=True), _learned()
        enable_learned_motion(learned)
        motion = HandMotion(hand, ways_the_hand_moves(learned))
        motion.tick(100.0, start_fraction=0.4)

        motion.rest_at_floor()

        assert motion.height(0.0) == pytest.approx(0.0)


class TestANewWayOfMovingTheHand:
    def test_it_is_one_object_in_a_row_ahead_of_the_bars_and_the_hand_goes_its_way(self):
        hand, new = RobotHandState(playing=True), StraightUp()
        motion = HandMotion(hand, (new, *ways_the_hand_moves(None)))

        motion.tick(7.0, start_fraction=0.25)

        assert new.ticked == [(7.0, 0.25)]
        assert motion.height(0.2, lead_s=0.1) == pytest.approx(30.0)
        assert motion.trace(TraceSpan(0.0, 60.0, 4, 2.0)) == ([1.0] * 5, 0.5)

    def test_out_of_play_it_leaves_the_hand_to_the_rows_below_it(self):
        hand = RobotHandState()
        motion = HandMotion(hand, (StraightUp(in_play=False), *ways_the_hand_moves(None)))

        assert motion.height(0.5) == pytest.approx(100.0)

    def test_resting_at_the_floor_reaches_it_too(self):
        new = StraightUp(in_play=False)

        HandMotion(RobotHandState(), (new, *ways_the_hand_moves(None))).rest_at_floor()

        assert new.rested == 1
