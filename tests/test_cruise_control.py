"""Cruise control's waves — the dice, and what they are not allowed to do.

Two techniques are on trial. Waves are summed, so the motion is the pace you set
with a much slower swell of its own size carrying it from base to tip and back;
and every parameter of every wave is a ramp rather than a number, so the motion
is plainly somewhere different from where it was a minute ago. A ramp too small
or too quick to feel is the failure this is tuned against, so the tests here
measure how far things actually move, not merely that they moved.
"""
from __future__ import annotations

import copy
import random

import pytest

from funestra import wave_stack
from funestra.cruise_control import (
    _BASE_SWING,
    _TRAVEL_BAND,
    CruiseControlState,
    disable_cruise_control,
    enable_cruise_control,
    tick_cruise_control,
)
from funestra.robot_hand import (
    MAX_TICK_SECONDS,
    RobotHandState,
    WaveformShape,
    bpm_for_speed,
    position_fraction,
    set_amplitude,
)


def _cruising(seed, **bars):
    """A motion running under cruise control, one tick in."""
    direct = RobotHandState(playing=True, **bars)
    cc = CruiseControlState(rng=random.Random(seed))
    enable_cruise_control(cc)
    tick_cruise_control(direct, cc, now=1000.0)
    return direct, cc


def _run(direct, cc, seconds, *, dt=0.05, start=1000.0, watch=None):
    """Carry the motion forward, handing each tick to *watch* if there is one."""
    now = start
    for _ in range(int(seconds / dt)):
        now += dt
        tick_cruise_control(direct, cc, now)
        if watch is not None:
            watch(direct, cc)
    return now


def _bpm(wave, cc):
    return bpm_for_speed(wave.speed.at(cc.clock))


class TestArming:
    def test_enable_and_disable_are_idempotent(self):
        cc = CruiseControlState(rng=random.Random(42))
        enable_cruise_control(cc)
        enable_cruise_control(cc)
        assert cc.active is True
        disable_cruise_control(cc)
        disable_cruise_control(cc)
        assert cc.active is False

    def test_arming_alone_moves_nothing(self):
        # The waves are drawn on the first tick, from whatever the bars say
        # then — so arming against a parked device cannot change the motion.
        direct = RobotHandState(speed=50, amplitude=80, intended_center=50)
        cc = CruiseControlState(rng=random.Random(42))
        enable_cruise_control(cc)
        assert not cc.stack
        tick_cruise_control(direct, cc, now=10.0)  # not playing
        assert (direct.speed, direct.amplitude, direct.center) == (50, 80, 50)
        assert not cc.stack

    def test_an_unarmed_tick_changes_nothing(self):
        direct = RobotHandState(speed=50, amplitude=80, intended_center=50)
        cc = CruiseControlState(active=False, rng=random.Random(42))
        tick_cruise_control(direct, cc, now=10.0)
        assert (direct.speed, direct.amplitude, direct.center) == (50, 80, 50)


class TestTakingTheMotionOver:
    def test_the_takeover_cannot_be_felt(self):
        # The bar's travel is divided among the waves in the shares they keep,
        # its center evenly, and every ramp is born already arrived, so the sum
        # is the bars to the point — and with every wave at the phase the
        # motion is already at and running the same speed, the sum is the single
        # wave. Anything else is a step on the wire the device has to lurch
        # through.
        for seed in range(8):
            direct = RobotHandState(playing=True, speed=35, amplitude=70,
                                        intended_center=40)
            cc = CruiseControlState(rng=random.Random(seed))
            enable_cruise_control(cc)
            tick_cruise_control(direct, cc, now=1000.0, phase=0.42)
            assert (direct.amplitude, direct.center) == (70, 40)
            assert direct.speed == 35
            assert all(wave.shape is WaveformShape.SINE
                       for wave in cc.stack.waves)
            assert all(wave.phase == 0.42 for wave in cc.stack.waves)
            assert wave_stack.position(cc.stack, cc.clock) == pytest.approx(
                100 * _single_wave_fraction(0.42, 70, 40))

    def test_handing_it_back_says_where_the_single_wave_picks_up(self):
        direct, cc = _cruising(2)
        _run(direct, cc, seconds=45)
        expected = wave_stack.biggest(cc.stack, cc.clock).phase
        assert disable_cruise_control(cc) == expected
        assert not cc.active and not cc.stack


def _single_wave_fraction(phase, amplitude, center):
    return position_fraction(phase, amplitude=amplitude, center=center)


class TestTheMotionItMakes:
    @pytest.mark.parametrize("bar", [100, 70, 40])
    def test_the_travel_it_settles_at_is_most_of_the_travel_you_set(self, bar):
        # What the bar says is the top of the band, not a starting point the
        # dice wander away from: the whole motion's travel is drawn as a
        # fraction of it, so a session asking for 100 gets four fifths of 100
        # rather than the 55 an unanchored draw from the axis averaged whatever
        # was asked for. The center comes out where it was set for the same
        # reason.
        centers, travels, positions = [], [], []

        def watch(direct, cc):
            centers.append(direct.center)
            travels.append(direct.amplitude)
            positions.append(wave_stack.position(cc.stack, cc.clock))

        # Ten sessions of ten minutes: the center ramps are slow enough that a
        # shorter sample is mostly noise rather than the average asked after.
        for seed in range(10):
            direct, cc = _cruising(seed, amplitude=bar)
            _run(direct, cc, seconds=600, watch=watch)
        middle_of_the_band = bar * (_TRAVEL_BAND[0] + 1.0) / 2
        assert sum(travels) / len(travels) == pytest.approx(
            middle_of_the_band, rel=0.1)
        assert sum(centers) / len(centers) == pytest.approx(50, abs=3)
        assert all(0.0 <= where <= 100.0 for where in positions)

    def test_the_motion_still_reaches_both_ends_of_the_axis(self):
        positions = []

        def watch(direct, cc):
            positions.append(wave_stack.position(cc.stack, cc.clock))

        for seed in range(10):
            direct, cc = _cruising(seed)
            _run(direct, cc, seconds=600, watch=watch)
        assert min(positions) < 5 and max(positions) > 95

    @pytest.mark.parametrize(("speed", "slowest"), [(50, 2.0), (90, 3.0)])
    def test_what_rides_the_motion_is_a_swell_and_not_a_vibration(
            self, speed, slowest):
        # A wave at half the main pace carrying as much travel is not a swell —
        # it is a second motion interfering with the first, and interference is
        # what made the stack feel like a mess at any speed. Everything after
        # the main wave runs far slower than it, so what it adds is the motion
        # being carried from base to tip and back while the motion goes on.
        #
        # How much slower a swell can get is the floor of the bar's to say: a
        # motion at 50 is only four times the slowest the device will run, so
        # the swells under it pile up on MIN_SPEED. There is room to spare at
        # the speeds the complaint was about.
        ratios = []

        def watch(direct, cc):
            main, *under = cc.stack.waves
            for wave in under:
                assert _bpm(wave, cc) <= _bpm(main, cc)
                ratios.append(_bpm(main, cc) / _bpm(wave, cc))

        for seed in range(12):
            direct, cc = _cruising(seed, speed=speed)
            if len(cc.stack.waves) < 2:
                continue
            # Past the takeover first: every wave starts at the pace the bar
            # was set to, because that is what makes taking over unfeelable, and
            # the ramp that carries the swells down under it takes its time.
            now = _run(direct, cc, seconds=60, dt=0.25)
            _run(direct, cc, seconds=200, dt=0.25, start=now, watch=watch)
        assert min(ratios) > slowest
        assert sum(ratios) / len(ratios) > 5.0

    def test_the_wave_the_bar_names_keeps_the_travel(self):
        # The swell used to be as often the bigger wave, which meant the pace
        # the pace the Speed bar read had a minority of the travel under it,
        # so the swing you felt was a third of the one you asked for and
        # turning cruise off at the same numbers doubled the motion on the
        # spot. The first wave is the motion; the swells only carry it.
        shares = []

        def watch(direct, cc):
            travels = [wave.amplitude.at(cc.clock) for wave in cc.stack.waves]
            shares.append(travels[0] / sum(travels))

        for seed in range(12):
            direct, cc = _cruising(seed)
            if len(cc.stack.waves) < 2:
                continue
            _run(direct, cc, seconds=300, dt=0.25, watch=watch)
        assert min(shares) > 0.5
        assert sum(shares) / len(shares) > 0.65

    def test_the_bars_move_far_enough_to_notice(self):
        # The complaint this is tuned against: ramps that are there in the code
        # and cannot be felt on the device. Over a few minutes the motion has to
        # open and close a good part of its travel, walk from base to tip, and
        # speed up and slow down by more than a nudge. The travel now swings the
        # width of its band rather than the width of the axis, because the band
        # is measured off the bar — the old fifty points were bought by
        # forgetting what was asked for.
        for seed in range(4):
            direct, cc = _cruising(seed)
            travels, centers, bpms = [], [], []

            def watch(direct, cc, travels=travels, centers=centers, bpms=bpms):
                travels.append(direct.amplitude)
                centers.append(direct.center)
                bpms.append(_bpm(cc.stack.waves[0], cc))

            _run(direct, cc, seconds=400, watch=watch)
            assert max(travels) - min(travels) > 25
            assert max(centers) - min(centers) > 15
            assert max(bpms) / min(bpms) > 2.0

    def test_every_bar_it_claims_to_move_moves(self):
        # It moved only speed for years: a tick stepped a bar by a twentieth of
        # the gap to its target and the result was snapped to fives, so any
        # target nearer than about fifty points rounded back to where it
        # started.
        seen = {"amplitude": set(), "center": set(), "speed": set(),
                "shape": set()}

        def watch(direct, cc):
            for bar in seen:
                seen[bar].add(getattr(direct, bar))

        direct, cc = _cruising(5)
        _run(direct, cc, seconds=300, watch=watch)
        assert len(seen["amplitude"]) > 20
        # The center has as much room as the swing leaves it, and the swing is
        # bigger than it used to be, so this is a narrower walk than before.
        assert len(seen["center"]) > 10
        assert len(seen["speed"]) > 5
        assert len(seen["shape"]) > 1


class TestAnHourOfIt:
    """The complaint this class exists for: cruise control left on wanders off.

    The motion an hour in used to be nothing like the one that was asked for —
    the pace had walked to half the bar and stayed there, and the travel had
    settled at a number drawn from the axis rather than from the bar. Every
    range here is measured off an anchor now, so the tenth minute is drawn from
    the same ranges as the first and the hour has no direction to drift in.
    """

    def test_the_pace_stays_within_sight_of_the_one_you_set(self):
        # The base used to be a free random walk over the whole bar: started
        # at the top it could only come down, and an hour of it landed at half
        # the pace asked for with no way back short of switching cruise off.
        for seed in range(6):
            direct, cc = _cruising(seed, speed=90)
            bases = []
            _run(direct, cc, seconds=3600, dt=0.5,
                 watch=lambda direct, cc, bases=bases:
                     bases.append(cc.base_speed))
            assert cc.anchor_speed == 90
            assert min(bases) >= 90 - _BASE_SWING
            assert max(bases) <= 90 + _BASE_SWING
            assert max(bases) - min(bases) > 5   # it still drifts

    def test_the_hour_is_drawn_from_the_ranges_the_first_minute_was(self):
        # Same measurement early and late: how hard the device is being
        # worked, which is how deep the swings are and how often they come. A
        # drift shows up as the late window being a different motion from the
        # early one; the ranges are fixed, so it is the same one.
        early, late = [], []
        for seed in range(8):
            direct, cc = _cruising(seed)
            now = _run(direct, cc, seconds=120)
            worked, now = _how_hard_it_works(direct, cc, 180, now)
            early.append(worked)
            now = _run(direct, cc, seconds=3000, dt=0.5, start=now)
            worked, now = _how_hard_it_works(direct, cc, 180, now)
            late.append(worked)
        assert (sum(late) / len(late)
                == pytest.approx(sum(early) / len(early), rel=0.15))


def _how_hard_it_works(direct, cc, seconds, start, dt=1 / 60):
    """The mean speed of the position the device is sent — how deep the swings
    are and how often they come, in one number — and the wall clock it left
    off at."""
    where = []
    now = _run(direct, cc, seconds=seconds, dt=dt, start=start,
               watch=lambda direct, cc: where.append(
                   wave_stack.position(cc.stack, cc.clock)))
    moved = sum(abs(where[i + 1] - where[i]) for i in range(len(where) - 1))
    return moved / ((len(where) - 1) * dt), now


class TestPausing:
    """Armed but not moving — paused by hand, frozen under OmniPause, or
    sitting out a funscript's turn in Hybrid. Auto advance has always sat still
    then; this used to go on moving the motion, so a session came back from a
    pause to a motion it never asked for."""

    def test_a_paused_hand_freezes_the_motion(self):
        direct, cc = _cruising(3)
        _run(direct, cc, seconds=30)
        direct.playing = False
        was = (cc.clock, wave_stack.position(cc.stack, cc.clock),
               direct.amplitude, direct.center, direct.speed, direct.shape)
        now = _run(direct, cc, seconds=60)
        assert (cc.clock, wave_stack.position(cc.stack, cc.clock),
                direct.amplitude, direct.center, direct.speed,
                direct.shape) == was
        assert cc._last_tick == pytest.approx(now)  # the wall clock kept up

    def test_it_picks_up_where_it_left_off_rather_than_lurching_on_resume(self):
        direct, cc = _cruising(3)
        _run(direct, cc, seconds=30)
        direct.playing = False
        _run(direct, cc, seconds=300)   # five minutes of pause
        held = cc.clock
        direct.playing = True
        _run(direct, cc, seconds=1)
        assert cc.clock == pytest.approx(held + 1, abs=0.1)

    def test_a_stalled_clock_comes_back_by_one_capped_step_not_by_the_gap(self):
        """A pause is a clock that keeps up while the motion stands still; a stall
        is one that stops arriving at all — the app blocked, the machine suspended
        — and it comes back owing an hour.  The motion's clock takes the same cap
        the phase takes, so the waves and every ramp under them move by a step
        rather than landing wherever an hour would have put them."""
        direct, cc = _cruising(3)
        now = _run(direct, cc, seconds=30)
        held = cc.clock

        tick_cruise_control(direct, cc, now + 3600)

        assert cc.clock - held == pytest.approx(MAX_TICK_SECONDS)


def test_a_hand_held_down_by_its_max_intensity_carries_its_waves_at_the_pace_it_leaves_them():
    direct, cc = _cruising(4, amplitude=100, speed=90, max_intensity=25)
    now = _run(direct, cc, 1.0)
    expected = copy.deepcopy(cc.stack)
    wave_stack.advance(expected, cc.clock + 0.05, 0.05, max_intensity=25)

    tick_cruise_control(direct, cc, now + 0.05)

    assert [wave.phase for wave in cc.stack.waves] == pytest.approx(
        [wave.phase for wave in expected.waves])


class TestAHandOnTheBars:
    def test_a_bar_moved_by_hand_is_carried_on_from_not_yanked_back(self):
        direct, cc = _cruising(5)
        _run(direct, cc, seconds=20)
        speeds = [wave.speed.at(cc.clock) for wave in cc.stack.waves]
        parts = [wave.amplitude.at(cc.clock) for wave in cc.stack.waves]

        set_amplitude(direct, 40)
        direct.intended_center = 70
        direct.speed += 10
        turned_to = direct.speed
        tick_cruise_control(direct, cc, now=1000.0 + 20 + 0.05)

        assert direct.amplitude == 40
        assert direct.center == 70
        assert direct.speed == turned_to
        assert [wave.speed.at(cc.clock) for wave in cc.stack.waves] == \
            pytest.approx([speed + 10 for speed in speeds], abs=0.15)
        # the travel was spread in proportion, so the balance survives the turn
        # (to within the tick's own drift — every ramp moved on while it ran)
        now = [wave.amplitude.at(cc.clock) for wave in cc.stack.waves]
        assert [part / sum(parts) for part in parts] == \
            pytest.approx([part / sum(now) for part in now], abs=0.01)

    def test_a_turn_moves_the_anchor_so_it_does_not_wash_out(self):
        # Every range is measured off an anchor, so a turn that only moved the
        # waves would be undone by the next ramp: a minute later the motion
        # would be back at the travel and the pace the anchors still named, and
        # the hand would have to keep asking for the same thing.
        direct, cc = _cruising(5, speed=60, amplitude=90)
        now = _run(direct, cc, seconds=20)
        was_speed, was_travel = cc.anchor_speed, cc.anchor_travel

        direct.speed += 12
        set_amplitude(direct, direct.amplitude - 20)
        now = _run(direct, cc, seconds=0.1, start=now)

        assert cc.anchor_speed == was_speed + 12
        assert cc.anchor_travel == was_travel - 20
        # and it holds. Past the ramps that were already in flight — those
        # finish the journey they were on, which is the carrying-on above —
        # every draw after them comes out of the band the turn moved.
        now = _run(direct, cc, seconds=60, start=now)
        travels = []
        _run(direct, cc, seconds=300, start=now,
             watch=lambda direct, cc, travels=travels:
                 travels.append(direct.amplitude))
        assert max(travels) <= cc.anchor_travel + 1
        assert sum(travels) / len(travels) > cc.anchor_travel * _TRAVEL_BAND[0]


class TestTheBarsStayInRange:
    @pytest.mark.parametrize("seed", range(4))
    def test_nothing_leaves_the_axis_or_the_bar(self, seed):
        direct, cc = _cruising(seed)

        def watch(direct, cc):
            assert 0 <= direct.amplitude <= 100
            assert 0 <= direct.center <= 100
            assert 5 <= direct.speed <= 100
            assert direct.shape in list(WaveformShape)
            assert 0.0 <= wave_stack.position(cc.stack, cc.clock) <= 100.0

        _run(direct, cc, seconds=300, watch=watch)


class TestTheFutureIsWrittenOnce:
    """He watched the readout's line rewrite its far end as ramps arrived and
    drew their successors.  Every ramp now has the next chained on a minute
    ahead, so the coming motion is decided before it is shown and the picture
    only slides."""

    def test_every_ramp_has_the_next_decided_a_minute_ahead(self):
        direct, cc = _cruising(3)
        _run(direct, cc, seconds=5)

        for wave in cc.stack.waves:
            for ramp in (wave.speed, wave.amplitude, wave.center):
                assert ramp.last().ends_at >= cc.clock + 60.0 - 1.0

    def test_the_picture_a_window_ahead_is_the_one_that_arrives(self):
        # The knots read now, and the same knots read three seconds later,
        # agree wherever they overlap: nothing in the window was rewritten.
        for seed in range(6):
            direct, cc = _cruising(seed)
            now = _run(direct, cc, seconds=30)
            early, _ = wave_stack.trace_window(cc.stack, cc.clock, 80, 12.0)
            step = 12.0 / 79
            knots_on = round(3.0 / step)
            _run(direct, cc, seconds=knots_on * step, start=now)
            late, _ = wave_stack.trace_window(cc.stack, cc.clock, 80, 12.0)

            assert late[:81 - knots_on] == pytest.approx(early[knots_on:], abs=2e-3)

    def test_a_shape_swap_is_scheduled_with_the_ramp_it_rides(self):
        direct, cc = _cruising(4)
        _run(direct, cc, seconds=5)

        scheduled = [ramp.shape for wave in cc.stack.waves
                     for ramp in _chain(wave.speed) if ramp.shape is not None]
        assert scheduled, "no swap decided ahead"
        assert all(ramp.begun > cc.clock for wave in cc.stack.waves
                   for ramp in _chain(wave.speed) if ramp.shape is not None)


def _chain(ramp):
    while ramp is not None:
        yield ramp
        ramp = ramp.then
