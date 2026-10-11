"""The summed motion's arithmetic — the part with no dice in it.

Two promises are what matter here. Every wave carries its own travel and its own
center, so one can drift while another holds and the console's numbers are read
back off what they came to rather than handed down to them. And however many
waves there are and whatever their parameters are doing, the sum lands on the
axis: the motion the device is sent can never run off either end of it.
"""
from __future__ import annotations

import math
import random

import pytest

from funestra import wave_stack
from funestra.robot_hand import (
    PARK_CENTER,
    WaveformShape,
    bpm_for_speed,
    position_fraction,
    travel_cap,
    wave_travel,
)
from funestra.wave_stack import Ramp, Wave, WaveStack


def _stack(rng, count):
    return WaveStack(waves=[
        Wave(shape=rng.choice(list(WaveformShape)),
             speed=Ramp(rng.uniform(10, 90), rng.uniform(10, 90), 0.0, 30.0),
             amplitude=Ramp(rng.uniform(5, 100 / count),
                            rng.uniform(5, 100 / count), 0.0, 30.0),
             center=Ramp(rng.uniform(10, 90) / count,
                         rng.uniform(10, 90) / count, 0.0, 30.0),
             phase=rng.random())
        for _ in range(count)
    ])


def test_a_ramp_reads_where_it_has_got_to():
    ramp = Ramp(40.0, 20.0, begun=100.0, seconds=10.0)
    assert ramp.at(99.0) == 40.0     # before it starts
    assert ramp.at(100.0) == 40.0
    assert ramp.at(105.0) == 30.0    # halfway
    assert ramp.at(110.0) == 20.0
    assert ramp.at(999.0) == 20.0    # and holds until it is drawn a new one
    assert not ramp.finished(109.0) and ramp.finished(110.0)


def test_a_ramp_with_no_time_to_take_is_simply_its_end():
    # How engaging seeds every ramp: born holding one value and already arrived,
    # so the first tick is what gives it somewhere to go.
    assert Ramp(7.0, 7.0, 0.0, 0.0).at(0.0) == 7.0
    assert Ramp(7.0, 7.0, 0.0, 0.0).finished(0.0)


def test_a_ramp_picked_up_by_hand_carries_on_from_there():
    ramp = Ramp(40.0, 20.0, begun=0.0, seconds=10.0)
    moved = ramp.resumed(80.0, now=4.0)
    assert moved.at(4.0) == 80.0     # where the hand put it
    assert moved.at(10.0) == 20.0    # same destination, in the time that was left
    assert moved.seconds == pytest.approx(6.0)


def test_one_wave_is_the_plain_single_motion():
    # The stack is not a different kind of motion — with one wave it is exactly
    # the wave the bars have always described.
    stack = WaveStack(waves=[Wave(shape=WaveformShape.TRIANGLE, phase=0.3,
                                  amplitude=Ramp(60.0, 60.0),
                                  center=Ramp(40.0, 40.0))])
    assert wave_stack.position(stack, 0.0) == pytest.approx(
        100 * position_fraction(0.3, shape=WaveformShape.TRIANGLE,
                                amplitude=60, center=40))


def _loud_pair() -> WaveStack:
    return WaveStack(waves=[
        Wave(phase=0.2, speed=Ramp(80.0, 80.0), amplitude=Ramp(60.0, 60.0),
             center=Ramp(25.0, 25.0)),
        Wave(phase=0.7, speed=Ramp(30.0, 30.0), amplitude=Ramp(20.0, 20.0),
             center=Ramp(25.0, 25.0)),
    ])


def _kept_by(max_intensity: int) -> float:
    travel = (wave_travel(60, bpm_for_speed(80)) + wave_travel(20, bpm_for_speed(30)))
    return math.sqrt(travel_cap(max_intensity) / travel)


def test_a_stack_past_its_max_intensity_settles_toward_the_park_by_what_it_keeps():
    stack = _loud_pair()

    capped = wave_stack.position(stack, 0.0, max_intensity=30)

    assert capped - PARK_CENTER == pytest.approx(
        _kept_by(30) * (wave_stack.position(stack, 0.0) - PARK_CENTER))


def test_a_stack_past_its_max_intensity_runs_each_wave_only_as_fast_as_it_lets():
    stack = _loud_pair()

    wave_stack.advance(stack, 0.05, 0.05, max_intensity=30)

    assert [wave.phase for wave in stack.waves] == pytest.approx([
        0.2 + 0.05 * bpm_for_speed(80) * _kept_by(30) / 60,
        0.7 + 0.05 * bpm_for_speed(30) * _kept_by(30) / 60,
    ])


def test_every_wave_carries_its_own_center():
    # The motion's center is what the waves' centers came to, not something they
    # were each handed a share of: move one wave's center and the motion moves
    # with it, while the other wave stays exactly where it was sitting.
    slow = Wave(amplitude=Ramp(20.0, 20.0), center=Ramp(20.0, 20.0))
    main = Wave(amplitude=Ramp(30.0, 30.0), center=Ramp(30.0, 30.0), phase=0.25)
    stack = WaveStack(waves=[slow, main])
    assert wave_stack.bars(stack, 0.0).center == 50.0
    was = wave_stack.position(stack, 0.0)

    slow.center = Ramp(35.0, 35.0)
    assert wave_stack.bars(stack, 0.0).center == 65.0
    assert wave_stack.position(stack, 0.0) == pytest.approx(was + 15.0)
    assert main.center.at(0.0) == 30.0  # the other wave never moved


def test_the_summed_motion_never_leaves_the_axis():
    # Summed carelessly, waves climb: two each swinging 50 around 50 reach 150,
    # and the device spends its evening pinned at the top.
    rng = random.Random(11)
    for count in (1, 2, 3, 5):
        for _ in range(40):
            stack = _stack(rng, count)
            for now in (0.0, 7.0, 30.0, 100.0):
                for wave in stack.waves:
                    wave.phase = rng.random()
                assert 0.0 <= wave_stack.position(stack, now) <= 100.0


def test_the_swing_gives_way_only_when_the_waves_ask_for_more_than_the_axis():
    ordinary = WaveStack(waves=[Wave(amplitude=Ramp(30.0, 30.0)),
                                Wave(amplitude=Ramp(50.0, 50.0))])
    assert wave_stack.fit(ordinary, 0.0).scale == 1.0
    assert wave_stack.fit(ordinary, 0.0).travel == 80.0

    greedy = WaveStack(waves=[Wave(amplitude=Ramp(60.0, 60.0)),
                              Wave(amplitude=Ramp(100.0, 100.0))])
    landed = wave_stack.fit(greedy, 0.0)
    assert landed.travel == 100.0
    assert landed.scale == pytest.approx(100 / 160)  # both shrink by the same
    # and the big wave is still the big one afterwards
    assert wave_stack.biggest(greedy, 0.0) is greedy.waves[1]


def test_the_center_gives_way_when_the_swing_will_not_fit():
    # A motion 90 wide cannot sit at 25 with a quarter of it under the floor.
    assert wave_stack.room(90.0, 25.0) == 45.0
    assert wave_stack.room(90.0, 75.0) == 55.0
    assert wave_stack.room(40.0, 25.0) == 25.0   # room to spare: left alone
    assert wave_stack.room(100.0, 10.0) == 50.0  # no room at all: pinned


def test_aiming_ahead_by_nothing_is_where_the_motion_is():
    rng = random.Random(2)
    stack = _stack(rng, 2)
    assert wave_stack.position_ahead(stack, 5.0, 0.0) == pytest.approx(
        wave_stack.position(stack, 5.0))


def test_aiming_ahead_lands_where_carrying_the_motion_forward_gets_to():
    # The claim every command on the wire makes: be at this place in this long.
    stack = WaveStack(waves=[
        Wave(speed=Ramp(60.0, 60.0), amplitude=Ramp(40.0, 40.0),
             center=Ramp(30.0, 30.0)),
        Wave(shape=WaveformShape.TRIANGLE, speed=Ramp(20.0, 20.0),
             amplitude=Ramp(20.0, 20.0), center=Ramp(20.0, 20.0)),
    ])
    aimed = wave_stack.position_ahead(stack, 0.0, 0.04)
    wave_stack.advance(stack, 0.0, 0.04)
    assert aimed == pytest.approx(wave_stack.position(stack, 0.04), abs=1e-9)


def test_aiming_a_stack_held_down_by_its_max_intensity_lands_where_carrying_it_forward_gets_to():
    stack = _loud_pair()
    aimed = wave_stack.position_ahead(stack, 0.0, 0.04, max_intensity=30)
    wave_stack.advance(stack, 0.04, 0.04, max_intensity=30)
    assert aimed == pytest.approx(wave_stack.position(stack, 0.04, max_intensity=30), abs=1e-9)


def test_the_console_is_told_the_whole_motion_and_the_wave_you_can_feel():
    stack = WaveStack(waves=[
        Wave(shape=WaveformShape.SAWTOOTH, speed=Ramp(30.0, 30.0),
             amplitude=Ramp(14.0, 14.0), center=Ramp(14.0, 14.0)),
        Wave(shape=WaveformShape.TRIANGLE, speed=Ramp(70.0, 70.0),
             amplitude=Ramp(50.0, 50.0), center=Ramp(30.0, 30.0)),
    ])
    bars = wave_stack.bars(stack, 0.0)
    assert (bars.travel, bars.center) == (64.0, 44.0)   # what they came to
    assert bars.speed == 30.0                            # the main wave's
    assert bars.shape is WaveformShape.SAWTOOTH
    # and the wave the device is mostly following is still the bigger one
    assert wave_stack.biggest(stack, 0.0) is stack.waves[1]


class TestTheTraceOnKnots:
    """The readout's picture of the sum, read on knots a fixed stretch of the
    motion's clock apart, so it holds still between knots and slides."""

    def _stack(self):
        return WaveStack(waves=[Wave(speed=Ramp(50.0, 50.0), amplitude=Ramp(60.0, 60.0),
                                     center=Ramp(50.0, 50.0), phase=0.2)])

    def test_the_first_knot_is_at_or_before_the_clock_and_the_rest_follow(self):
        stack = self._stack()

        heights, slide = wave_stack.trace_window(stack, 10.0, samples=5, span_s=2.0)

        assert len(heights) == 6
        assert slide == 0.0
        assert heights == pytest.approx([
            wave_stack.position_ahead(stack, 10.0, i * 0.5) / 100 for i in range(6)])

    def test_a_stack_held_down_by_its_max_intensity_is_drawn_as_the_motion_it_sends(self):
        stack = _loud_pair()

        heights, _ = wave_stack.trace_window(stack, 10.0, samples=5, span_s=2.0, max_intensity=30)

        assert heights == pytest.approx([
            wave_stack.position_ahead(stack, 10.0, i * 0.5, max_intensity=30) / 100
            for i in range(6)])

    def test_a_moving_stacks_trace_stays_on_the_axis_and_moves(self):
        heights, _ = wave_stack.trace_window(
            _stack(random.Random(7), 2), 3.0, samples=80, span_s=12.0)

        assert all(0.0 <= height <= 1.0 for height in heights)
        assert not all(math.isclose(height, heights[0]) for height in heights)

    def test_between_knots_the_heights_hold_and_the_slide_grows(self):
        stack = self._stack()
        at_knot, _ = wave_stack.trace_window(stack, 10.0, samples=5, span_s=2.0)

        # A fifth of a knot later: the same phases carried on that far.
        wave_stack.advance(stack, 10.1, 0.1)
        later, slide = wave_stack.trace_window(stack, 10.1, samples=5, span_s=2.0)

        assert later == pytest.approx(at_knot, abs=1e-6)
        assert slide == pytest.approx(0.2)

    def test_crossing_a_knot_moves_the_window_on_by_one(self):
        stack = self._stack()
        at_knot, _ = wave_stack.trace_window(stack, 10.0, samples=5, span_s=2.0)

        # Carried on a tick at a time: a step is capped at a tenth of a second.
        for tick in range(1, 13):
            wave_stack.advance(stack, 10.0 + tick * 0.05, 0.05)
        later, slide = wave_stack.trace_window(stack, 10.6, samples=5, span_s=2.0)

        assert later[:-1] == pytest.approx(at_knot[1:], abs=1e-6)
        assert slide == pytest.approx(0.2)


class TestARampWithTheNextChainedOn:
    def test_past_its_end_it_reads_the_one_that_follows(self):
        ramp = Ramp(10.0, 20.0, begun=0.0, seconds=10.0,
                    then=Ramp(20.0, 60.0, begun=10.0, seconds=10.0))

        assert ramp.at(5.0) == 15.0
        assert ramp.at(15.0) == 40.0
        assert ramp.at(30.0) == 60.0
        assert ramp.last().end == 60.0

    def test_a_hand_on_the_bar_keeps_what_follows(self):
        ramp = Ramp(10.0, 20.0, begun=0.0, seconds=10.0,
                    then=Ramp(20.0, 60.0, begun=10.0, seconds=10.0))

        assert ramp.resumed(14.0, 5.0).then is ramp.then
        assert ramp.shifted(5.0).then.end == 65.0
        assert ramp.shifted(50.0).clamped(0.0, 100.0).then.end == 100.0

    def test_the_shape_a_speed_ramp_brings_shows_from_when_it_begins(self):
        wave = Wave(shape=WaveformShape.SINE, speed=Ramp(
            50.0, 50.0, begun=0.0, seconds=10.0,
            then=Ramp(50.0, 50.0, begun=10.0, seconds=10.0, shape=WaveformShape.TRIANGLE)))

        assert wave_stack.shape_at(wave, 5.0) is WaveformShape.SINE
        assert wave_stack.shape_at(wave, 10.0) is WaveformShape.TRIANGLE
        assert wave_stack.shape_at(wave, 25.0) is WaveformShape.TRIANGLE
