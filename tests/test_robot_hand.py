from __future__ import annotations

import pytest

from funestra.robot_hand import (
    MAX_TICK_SECONDS,
    MIN_SPEED,
    PARK_CENTER,
    POSITION_MAX,
    RETRACT_CENTER,
    RobotHandState,
    WaveformShape,
    adjust_amplitude,
    adjust_center,
    adjust_speed,
    bpm_for_speed,
    cycle_shape,
    phase_advanced,
    phase_for_position_fraction,
    phase_to_position,
    position_fraction,
    set_amplitude,
    set_center,
    set_dials,
    set_max_intensity,
    set_speed,
    trace_window,
    travel_cap,
    wave_travel,
)


class TestBpmForSpeed:
    def test_the_slowest_bar_setting_moves_at_the_slowest_pace(self):
        assert bpm_for_speed(5) == pytest.approx(5.0)

    def test_speed_100_returns_maximum_bpm(self):
        assert bpm_for_speed(100) == pytest.approx(200.0)

    def test_monotonically_increasing(self):
        bpms = [bpm_for_speed(i) for i in range(5, 101, 5)]
        for i in range(len(bpms) - 1):
            assert bpms[i] < bpms[i + 1]

    def test_exponential_curve_gives_finer_control_at_low_end(self):
        low_step = bpm_for_speed(10) - bpm_for_speed(5)
        high_step = bpm_for_speed(100) - bpm_for_speed(95)
        assert low_step < high_step


class TestSetSpeed:
    def test_sets_speed_and_bpm(self):
        state = RobotHandState()
        set_speed(state, 30)
        assert state.speed == 30
        assert state.bpm == pytest.approx(bpm_for_speed(30))

    def test_clamps_below_minimum_to_5(self):
        state = RobotHandState()
        set_speed(state, 0)
        assert state.speed == 5

    def test_clamps_above_100(self):
        state = RobotHandState()
        set_speed(state, 105)
        assert state.speed == 100


class TestTriangleWaveform:
    def test_the_cycle_starts_at_the_base(self):
        assert phase_to_position(0.0, shape=WaveformShape.TRIANGLE) == 0

    def test_a_quarter_through_the_cycle_the_hand_is_halfway_up(self):
        assert phase_to_position(0.25, shape=WaveformShape.TRIANGLE) == pytest.approx(5000, abs=1)

    def test_halfway_through_the_cycle_the_hand_is_at_the_tip(self):
        assert phase_to_position(0.5, shape=WaveformShape.TRIANGLE) == 9999

    def test_three_quarters_through_the_cycle_the_hand_is_halfway_back_down(self):
        assert phase_to_position(0.75, shape=WaveformShape.TRIANGLE) == pytest.approx(5000, abs=1)

    def test_the_cycle_ends_back_at_the_base(self):
        assert phase_to_position(1.0, shape=WaveformShape.TRIANGLE) == pytest.approx(0, abs=1)


class TestRoundedSquareWaveform:
    def test_the_cycle_starts_at_the_base(self):
        assert phase_to_position(0.0, shape=WaveformShape.ROUNDED_SQUARE) == 0

    def test_halfway_through_the_cycle_the_hand_is_at_the_tip(self):
        assert phase_to_position(0.5, shape=WaveformShape.ROUNDED_SQUARE) == 9999

    def test_the_cycle_ends_back_at_the_base(self):
        assert phase_to_position(1.0, shape=WaveformShape.ROUNDED_SQUARE) == pytest.approx(0, abs=1)

    def test_flatter_near_tip_than_sine(self):
        # At phase 0.4 (near tip), rounded square should be closer to 9999 than sine
        sq = phase_to_position(0.4, shape=WaveformShape.ROUNDED_SQUARE)
        sine = phase_to_position(0.4, shape=WaveformShape.SINE)
        assert sq > sine

    def test_flatter_near_base_than_sine(self):
        # At phase 0.1 (near base), rounded square should be closer to 0 than sine
        sq = phase_to_position(0.1, shape=WaveformShape.ROUNDED_SQUARE)
        sine = phase_to_position(0.1, shape=WaveformShape.SINE)
        assert sq < sine


class TestSawtoothWaveform:
    def test_the_cycle_starts_at_the_base(self):
        assert phase_to_position(0.0, shape=WaveformShape.SAWTOOTH) == 0

    def test_phase_half_is_falling(self):
        # At 0.5, sawtooth is in the slow-fall region (past the 0.3 peak)
        # raw = 1 - (0.5 - 0.3) / 0.7 ≈ 0.714
        pos = phase_to_position(0.5, shape=WaveformShape.SAWTOOTH)
        assert 6000 < pos < 8000

    def test_peak_at_rise_fraction(self):
        # Peak should be at phase 0.3 (the rise fraction)
        assert phase_to_position(0.3, shape=WaveformShape.SAWTOOTH) == 9999

    def test_the_cycle_ends_back_at_the_base(self):
        assert phase_to_position(1.0, shape=WaveformShape.SAWTOOTH) == pytest.approx(0, abs=1)

    def test_asymmetric_rise_is_faster(self):
        # At phase 0.15 (half of rise), should be ~50% up
        pos = phase_to_position(0.15, shape=WaveformShape.SAWTOOTH)
        assert 4000 < pos < 6000


class TestWaveformContinuousPhase:
    """All shapes must work with continuous phase > 1.0 (accumulated motion_phase)."""

    @pytest.mark.parametrize("shape", list(WaveformShape))
    def test_phase_1_5_matches_phase_0_5(self, shape):
        # phase 1.5 should give the same position as phase 0.5 (one full cycle later)
        assert phase_to_position(1.5, shape=shape) == pytest.approx(
            phase_to_position(0.5, shape=shape), abs=1
        )

    @pytest.mark.parametrize("shape", list(WaveformShape))
    def test_phase_2_matches_phase_0(self, shape):
        assert phase_to_position(2.0, shape=shape) == pytest.approx(
            phase_to_position(0.0, shape=shape), abs=1
        )

    @pytest.mark.parametrize("shape", list(WaveformShape))
    def test_result_always_in_range(self, shape):
        for p in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0, 1.5, 2.0]:
            pos = phase_to_position(p, shape=shape)
            assert 0 <= pos <= 9999


class TestAmplitudeAndCenter:
    def test_amplitude_50_halves_range(self):
        # At amplitude 50%, center 50%: range is 2500-7499
        tip = phase_to_position(0.5, amplitude=50)
        base = phase_to_position(0.0, amplitude=50)
        assert tip == pytest.approx(7500, abs=1)
        assert base == pytest.approx(2500, abs=1)

    def test_amplitude_100_full_range(self):
        assert phase_to_position(0.5, amplitude=100) == 9999
        assert phase_to_position(0.0, amplitude=100) == 0

    def test_amplitude_0_stays_at_center(self):
        assert phase_to_position(0.0, amplitude=0) == pytest.approx(5000, abs=1)
        assert phase_to_position(0.5, amplitude=0) == pytest.approx(5000, abs=1)

    def test_center_75_shifts_toward_tip(self):
        # amplitude=50, center=75: center at 7499, half_range=2500
        # low=4999, high=9999
        base = phase_to_position(0.0, amplitude=50, center=75)
        tip = phase_to_position(0.5, amplitude=50, center=75)
        assert base == pytest.approx(5000, abs=1)
        assert tip == 9999

    def test_center_25_shifts_toward_base(self):
        base = phase_to_position(0.0, amplitude=50, center=25)
        tip = phase_to_position(0.5, amplitude=50, center=25)
        assert base == 0
        assert tip == pytest.approx(5000, abs=1)

    def test_center_clamping_at_high_amplitude(self):
        # amplitude=100, center=75: center at 7499, half_range=5000
        # low=max(0, 2499)=2499, high=min(9999, 12499)=9999
        base = phase_to_position(0.0, amplitude=100, center=75)
        tip = phase_to_position(0.5, amplitude=100, center=75)
        assert base == pytest.approx(2500, abs=1)
        assert tip == 9999


class TestPhaseToPosition:
    def test_the_cycle_starts_at_the_base(self):
        assert phase_to_position(0.0) == 0

    def test_a_quarter_through_the_cycle_the_hand_is_halfway_up(self):
        assert phase_to_position(0.25) == pytest.approx(5000, abs=1)

    def test_halfway_through_the_cycle_the_hand_is_at_the_tip(self):
        assert phase_to_position(0.5) == 9999

    def test_three_quarters_through_the_cycle_the_hand_is_halfway_back_down(self):
        assert phase_to_position(0.75) == pytest.approx(5000, abs=1)

    def test_the_cycle_ends_back_at_the_base(self):
        assert phase_to_position(1.0) == pytest.approx(0, abs=1)

    def test_continuous_phase_1_5_returns_tip(self):
        assert phase_to_position(1.5) == 9999

    def test_continuous_phase_2_returns_base(self):
        assert phase_to_position(2.0) == pytest.approx(0, abs=1)

    def test_result_always_in_range(self):
        for p in [0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 0.999, 1.5, 2.0, 3.0]:
            pos = phase_to_position(p)
            assert 0 <= pos <= 9999


class TestRobotHandStateNewFields:
    def test_default_amplitude(self):
        state = RobotHandState()
        assert state.amplitude == 100

    def test_default_center(self):
        state = RobotHandState()
        assert state.center == 50

    def test_default_intended_center(self):
        state = RobotHandState()
        assert state.intended_center == 50

    def test_default_shape(self):
        state = RobotHandState()
        assert state.shape is WaveformShape.SINE

class TestSetAmplitude:
    def test_sets_amplitude_directly(self):
        state = RobotHandState(amplitude=30)

        set_amplitude(state, 75)

        assert state.amplitude == 75

    def test_clamps_above_100(self):
        state = RobotHandState(amplitude=50)

        set_amplitude(state, 120)

        assert state.amplitude == 100

    def test_clamps_below_0(self):
        state = RobotHandState(amplitude=50)

        set_amplitude(state, -10)

        assert state.amplitude == 0

    def test_recomputes_center(self):
        state = RobotHandState(amplitude=20, intended_center=90)
        assert state.center == 90  # within range for amp=20

        set_amplitude(state, 100)

        assert state.center == 50  # forced to center for full amplitude


class TestSetMaxIntensity:
    @pytest.mark.parametrize(("asked", "kept"), [(120, 100), (-10, 0), (35, 35)])
    def test_a_max_intensity_asked_for_is_kept_within_zero_and_full(self, asked, kept):
        state = RobotHandState()

        set_max_intensity(state, asked)

        assert state.max_intensity == kept

    def test_lowering_it_under_the_motion_pushes_amplitude_and_speed_down_alike_to_fit(self):
        state = RobotHandState(amplitude=90, speed=70)

        set_max_intensity(state, 10)

        assert wave_travel(state.amplitude, state.bpm) == pytest.approx(travel_cap(10), rel=0.05)
        assert wave_travel(state.amplitude, state.bpm) <= travel_cap(10)
        assert state.amplitude / 90 == pytest.approx(state.speed / 70, abs=0.03)

    def test_from_both_bars_at_the_top_it_leaves_both_at_the_level_it_stands_for(self):
        state = RobotHandState(amplitude=100, speed=100)

        set_max_intensity(state, 10)

        assert (state.amplitude, state.speed) == (50, 50)

    def test_lowering_it_settles_the_center_toward_the_park_as_far_as_the_amplitude_shrank(self):
        state = RobotHandState(amplitude=40, speed=90, intended_center=70)

        set_max_intensity(state, 5)

        kept = state.amplitude / 40
        assert state.center == pytest.approx(PARK_CENTER + (70 - PARK_CENTER) * kept, abs=1)
        assert state.intended_center == state.center

    @pytest.mark.parametrize(("amplitude", "speed"), [(100, 100), (60, 90), (80, 60), (10, 100)])
    def test_dragging_it_down_a_level_at_a_time_ends_where_one_move_would(self, amplitude, speed):
        jumped = RobotHandState(amplitude=amplitude, speed=speed, intended_center=50)
        set_max_intensity(jumped, 10)
        dragged = RobotHandState(amplitude=amplitude, speed=speed, intended_center=50)
        for level in range(99, 9, -1):
            set_max_intensity(dragged, level)

        assert abs(dragged.amplitude - jumped.amplitude) <= 1
        assert abs(dragged.speed - jumped.speed) <= 1
        assert abs(dragged.center - jumped.center) <= 1

    def test_at_zero_it_rests_a_moving_hand_on_the_park(self):
        state = RobotHandState(amplitude=40, speed=90, intended_center=70)

        set_max_intensity(state, 0)

        assert (state.amplitude, state.center) == (0, PARK_CENTER)

    def test_raising_it_again_leaves_the_bars_where_it_pushed_them(self):
        state = RobotHandState(amplitude=90, speed=90, intended_center=60)
        set_max_intensity(state, 20)
        pushed = (state.amplitude, state.speed, state.center)

        set_max_intensity(state, 100)

        assert (state.amplitude, state.speed, state.center) == pushed

    def test_a_motion_already_within_it_is_left_as_it_is(self):
        state = RobotHandState(amplitude=30, speed=30, intended_center=60)

        set_max_intensity(state, 60)

        assert (state.amplitude, state.speed, state.center) == (30, 30, 60)


class TestPuttingTheDialsBack:
    def test_dials_put_back_under_a_lowered_max_intensity_are_pushed_as_lowering_it_pushes(self):
        lowered = RobotHandState(amplitude=90, speed=90, intended_center=60)
        set_max_intensity(lowered, 40)
        held = RobotHandState(amplitude=0, speed=MIN_SPEED, intended_center=0)
        set_max_intensity(held, 40)

        set_dials(held, speed=90, amplitude=90, center=60)

        assert (held.speed, held.amplitude, held.center) == (
            lowered.speed, lowered.amplitude, lowered.center)


class TestTheCeilingsAMaxIntensityLeaves:
    def test_an_amplitude_asked_for_stops_at_the_widest_the_max_intensity_leaves_at_its_speed(self):
        state = RobotHandState(amplitude=20, speed=50)
        set_max_intensity(state, 5)

        set_amplitude(state, 100)

        assert wave_travel(state.amplitude, state.bpm) <= travel_cap(5)
        assert wave_travel(state.amplitude + 1, state.bpm) > travel_cap(5)

    def test_a_speed_asked_for_stops_at_the_fastest_the_max_intensity_leaves_at_its_amplitude(self):
        state = RobotHandState(amplitude=20, speed=30)
        set_max_intensity(state, 5)

        set_speed(state, 100)

        assert wave_travel(state.amplitude, state.bpm) <= travel_cap(5)
        assert wave_travel(state.amplitude, bpm_for_speed(state.speed + 1)) > travel_cap(5)

    def test_at_zero_neither_amplitude_nor_speed_can_rise_off_its_floor(self):
        state = RobotHandState(amplitude=60, speed=60)
        set_max_intensity(state, 0)

        set_speed(state, 100)
        set_amplitude(state, 100)

        assert (state.amplitude, state.speed) == (0, MIN_SPEED)


class TestAdjustAmplitude:
    def test_increase(self):
        state = RobotHandState(amplitude=70)
        adjust_amplitude(state, 10)
        assert state.amplitude == 80

    def test_decrease(self):
        state = RobotHandState(amplitude=70)
        adjust_amplitude(state, -10)
        assert state.amplitude == 60

    def test_clamps_at_100(self):
        state = RobotHandState(amplitude=100)
        adjust_amplitude(state, 10)
        assert state.amplitude == 100

    def test_clamps_at_0(self):
        state = RobotHandState(amplitude=0)
        adjust_amplitude(state, -10)
        assert state.amplitude == 0

    def test_increasing_amplitude_pushes_center_toward_50(self):
        state = RobotHandState(amplitude=40, intended_center=80)
        # range [20, 80], center=80 is valid
        adjust_amplitude(state, 10)
        # amplitude=50, range [25, 75], intended=80 is outside → center clamped to 75
        assert state.amplitude == 50
        assert state.center == 75
        assert state.intended_center == 80  # unchanged

    def test_repeated_amplitude_increase_forces_center_to_50(self):
        state = RobotHandState(amplitude=0, intended_center=80)
        for _ in range(10):
            adjust_amplitude(state, 10)
        assert state.amplitude == 100
        assert state.center == 50

    def test_decreasing_amplitude_restores_intended_center(self):
        state = RobotHandState(amplitude=40, intended_center=80)
        # Increase then decrease amplitude
        adjust_amplitude(state, 10)  # amp=50, center clamped to 75
        adjust_amplitude(state, 10)  # amp=60, center clamped to 70
        adjust_amplitude(state, -10)  # amp=50, center restores to 75
        adjust_amplitude(state, -10)  # amp=40, center restores to 80
        assert state.center == 80
        assert state.intended_center == 80


class TestSetCenter:
    def test_sets_intended_center(self):
        state = RobotHandState(amplitude=40, intended_center=50)

        set_center(state, 80)

        assert state.intended_center == 80

    def test_clamps_to_0_100(self):
        state = RobotHandState(amplitude=40)

        set_center(state, 120)

        assert state.intended_center == 100

    def test_recomputes_effective_center(self):
        state = RobotHandState(amplitude=100, intended_center=50)

        set_center(state, 90)

        # With amplitude=100, effective center is clamped to 50
        assert state.intended_center == 90
        assert state.center == 50


class TestAdjustCenter:
    def test_increase(self):
        state = RobotHandState(amplitude=60, intended_center=50)
        adjust_center(state, 10)
        assert state.center == 60
        assert state.intended_center == 60

    def test_decrease(self):
        state = RobotHandState(amplitude=60, intended_center=50)
        adjust_center(state, -10)
        assert state.center == 40
        assert state.intended_center == 40

    def test_half_step_when_5_from_edge(self):
        # amplitude=80, range [40, 60]. intended=55, try +10 → would be 65 > 60
        # 55 is 5 from edge (60), accept half → intended=60
        state = RobotHandState(amplitude=80, intended_center=55)
        adjust_center(state, 10)
        assert state.intended_center == 60
        assert state.center == 60

    def test_ignored_when_at_edge(self):
        # amplitude=80, range [40, 60]. intended=60, try +10 → at edge, ignore
        state = RobotHandState(amplitude=80, intended_center=60)
        adjust_center(state, 10)
        assert state.intended_center == 60
        assert state.center == 60

    def test_half_step_when_5_from_the_low_edge(self):
        # The low side is the same rule mirrored, and nothing was asking it —
        # amplitude=80, range [40, 60]. intended=45, try -10 → would be 35 < 40,
        # and 45 is 5 clear of the edge, so accept half → intended=40.
        state = RobotHandState(amplitude=80, intended_center=45)
        adjust_center(state, -10)
        assert state.intended_center == 40
        assert state.center == 40

    def test_ignored_when_at_the_low_edge(self):
        state = RobotHandState(amplitude=80, intended_center=40)
        adjust_center(state, -10)
        assert state.intended_center == 40
        assert state.center == 40

    def test_center_never_affects_amplitude(self):
        state = RobotHandState(amplitude=80, intended_center=50)
        adjust_center(state, 10)
        assert state.amplitude == 80


class TestCycleShape:
    def test_cycles_from_sine_to_triangle(self):
        state = RobotHandState(shape=WaveformShape.SINE)
        cycle_shape(state)
        assert state.shape is WaveformShape.TRIANGLE

    def test_wraps_from_last_to_first(self):
        state = RobotHandState(shape=WaveformShape.SAWTOOTH)
        cycle_shape(state)
        assert state.shape is WaveformShape.SINE

    def test_step_minus_one_goes_backward(self):
        state = RobotHandState(shape=WaveformShape.TRIANGLE)
        cycle_shape(state, -1)
        assert state.shape is WaveformShape.SINE

    def test_backward_wraps_from_first_to_last(self):
        state = RobotHandState(shape=WaveformShape.SINE)
        cycle_shape(state, -1)
        assert state.shape is WaveformShape.SAWTOOTH


class TestAdjustSpeed:
    def test_increase(self):
        state = RobotHandState(speed=50)
        adjust_speed(state, 5)
        assert state.speed == 55
        assert state.bpm == pytest.approx(bpm_for_speed(55))

    def test_decrease(self):
        state = RobotHandState(speed=50)
        adjust_speed(state, -5)
        assert state.speed == 45

    def test_clamps_at_max(self):
        state = RobotHandState(speed=100)
        adjust_speed(state, 5)
        assert state.speed == 100

    def test_clamps_at_min(self):
        state = RobotHandState(speed=5)
        adjust_speed(state, -5)
        assert state.speed == 5


def test_position_fraction_and_phase_to_position_are_one_curve_at_two_scales():

    for phase in (0.0, 0.17, 0.5, 0.83):
        for amplitude, center in ((100, 50), (40, 70), (0, 50)):
            frac = position_fraction(phase, amplitude=amplitude, center=center)
            assert 0.0 <= frac <= 1.0
            assert phase_to_position(phase, amplitude=amplitude, center=center) == \
                round(POSITION_MAX * frac)


def test_phase_advanced_moves_by_the_time_that_passed_and_wraps():

    assert phase_advanced(0.0, 60.0, 0.0) == 0.0
    assert phase_advanced(0.0, 60.0, 0.05) == pytest.approx(0.05)  # 60/min = 1/s
    assert phase_advanced(0.9, 60.0, 0.09) == pytest.approx(0.99)
    assert phase_advanced(0.99, 60.0, 0.02) == pytest.approx(0.01)  # wraps, not 1.01


def test_a_stalled_clock_cannot_slingshot_the_phase():
    # The app blocked, or the machine suspended: the step owed is capped, so the
    # motion slows through the gap instead of flinging the device across it.
    capped = phase_advanced(0.0, 60.0, 5.0)
    assert capped == pytest.approx(phase_advanced(0.0, 60.0, MAX_TICK_SECONDS))
    assert phase_advanced(0.0, 60.0, -1.0) == 0.0  # a clock that went backwards


class TestThePhaseForAHeight:
    """position_fraction inverted, for a seek that has to put the device at a
    named point on its axis. Every shape takes each height twice a cycle -- once
    climbing, once falling -- so the caller says which visit it means."""

    @pytest.mark.parametrize("shape", list(WaveformShape))
    @pytest.mark.parametrize("height", [0.0, 0.25, 0.5, 0.75, 1.0])
    @pytest.mark.parametrize("rising", [True, False])
    def test_it_lands_on_the_height_it_was_asked_for(self, shape, height, rising):
        phase = phase_for_position_fraction(height, shape=shape, rising=rising)

        assert position_fraction(phase, shape=shape) == pytest.approx(height, abs=0.01)

    @pytest.mark.parametrize("shape", list(WaveformShape))
    def test_climbing_and_falling_are_two_different_places_in_the_cycle(self, shape):
        up = phase_for_position_fraction(0.25, shape=shape, rising=True)
        down = phase_for_position_fraction(0.25, shape=shape, rising=False)

        assert up < down

    def test_a_height_the_amplitude_never_reaches_lands_on_the_nearest(self):
        """Turned down to the middle of the axis, the motion cannot be sent to
        the top; the top of its own travel is where the picture would be."""
        phase = phase_for_position_fraction(1.0, amplitude=40, center=50, rising=True)

        assert position_fraction(phase, amplitude=40, center=50) == pytest.approx(0.7, abs=0.01)

    def test_it_is_asked_for_past_either_end_and_answers_within_them(self):
        for height in (-3.0, 4.0):
            phase = phase_for_position_fraction(height)
            assert 0.0 <= phase < 1.0


def test_the_two_held_ends_are_the_ends_of_the_travel():
    """A hold settles the motion at one end of the axis or the other, and the
    two apps that hold it have to mean the same end by the same word."""

    for center in (PARK_CENTER, RETRACT_CENTER):
        state = RobotHandState()
        set_amplitude(state, 0)
        set_center(state, center)

        assert {phase_to_position(phase / 8, amplitude=state.amplitude,
                                 center=state.center)
                for phase in range(8)} == {center * POSITION_MAX // 100}


class TestTheWaveTracedOnKnots:
    """The single wave's picture for the readout: read on knots a fixed stretch
    of phase apart, anchored to a phase that never wraps, so it holds still
    between knots and slides rather than being redrawn at fixed columns."""

    def test_the_knots_start_at_or_before_the_phase(self):
        heights, slide = trace_window(
            WaveformShape.SINE, 100, 50, phase=0.0, bpm=60.0, samples=5, span_s=1.0)

        # A quarter second a knot at 60 a minute is a quarter cycle: floor,
        # halfway, ceiling, halfway, floor, halfway.
        assert heights == pytest.approx([0.0, 0.5, 1.0, 0.5, 0.0, 0.5], abs=1e-9)
        assert slide == 0.0

    def test_between_knots_the_heights_hold_and_the_slide_grows(self):
        at_knot, _ = trace_window(
            WaveformShape.SINE, 100, 50, phase=3.0, bpm=60.0, samples=5, span_s=1.0)

        later, slide = trace_window(
            WaveformShape.SINE, 100, 50, phase=3.1, bpm=60.0, samples=5, span_s=1.0)

        assert later == pytest.approx(at_knot, abs=1e-9)
        assert slide == pytest.approx(0.4)

    def test_crossing_a_knot_moves_the_window_on_by_one(self):
        at_knot, _ = trace_window(
            WaveformShape.SINE, 100, 50, phase=3.0, bpm=60.0, samples=5, span_s=1.0)

        later, slide = trace_window(
            WaveformShape.SINE, 100, 50, phase=3.3, bpm=60.0, samples=5, span_s=1.0)

        assert later[:-1] == pytest.approx(at_knot[1:], abs=1e-9)
        assert slide == pytest.approx(0.2)

    @pytest.mark.parametrize("shape", list(WaveformShape))
    def test_every_shape_stays_on_the_axis_and_inside_the_bars(self, shape):
        heights, _ = trace_window(shape, 50, 50, phase=0.7, bpm=45.0, samples=60, span_s=12.0)

        assert len(heights) == 61
        assert min(heights) >= 0.24
        assert max(heights) <= 0.76
