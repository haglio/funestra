from __future__ import annotations

import pytest

from funestra.genau_status import build_status_text
from funestra.robot_hand import (
    MAX_SPEED,
    MIN_SPEED,
    RobotHandState,
    control_limits,
    set_amplitude,
    set_max_intensity,
    set_speed,
)


def _limits(**state):
    return control_limits(RobotHandState(**state))


class TestTheTravelEnds:
    def test_a_travel_at_the_top_dims_only_the_up_arrow(self):
        limits = _limits(amplitude=100)

        assert (limits.amp_at_max, limits.amp_at_min) == (True, False)

    def test_a_travel_at_the_floor_dims_only_the_down_arrow(self):
        limits = _limits(amplitude=0)

        assert (limits.amp_at_max, limits.amp_at_min) == (False, True)

    def test_a_travel_in_between_dims_neither(self):
        limits = _limits(amplitude=60)

        assert (limits.amp_at_max, limits.amp_at_min) == (False, False)


class TestTheCenterIsClampedByTheTravel:
    @pytest.mark.parametrize(
        "amplitude, at_max, at_min",
        [
            (60, 70, 30),
            (100, 50, 50),
            (0, 100, 0),
        ],
    )
    def test_the_range_is_half_the_travel_in_from_each_end(
        self, amplitude, at_max, at_min,
    ):
        ceiling = _limits(amplitude=amplitude, center=at_max, intended_center=at_max)
        floor = _limits(amplitude=amplitude, center=at_min, intended_center=at_min)

        assert ceiling.ctr_at_max is True
        assert floor.ctr_at_min is True

    def test_a_center_inside_that_range_dims_neither(self):
        limits = _limits(amplitude=60, center=50, intended_center=50)

        assert (limits.ctr_at_max, limits.ctr_at_min) == (False, False)

    def test_a_full_travel_dims_both_at_once(self):
        limits = _limits(amplitude=100, center=50, intended_center=50)

        assert (limits.ctr_at_max, limits.ctr_at_min) == (True, True)


class TestTheSpeed:
    def test_the_fastest_dims_only_the_up_arrow(self):
        limits = _limits(speed=MAX_SPEED)

        assert (limits.spd_at_max, limits.spd_at_min) == (True, False)

    def test_the_slowest_dims_only_the_down_arrow(self):
        limits = _limits(speed=MIN_SPEED)

        assert (limits.spd_at_max, limits.spd_at_min) == (False, True)

    def test_a_speed_between_them_dims_neither(self):
        limits = _limits(speed=(MIN_SPEED + MAX_SPEED) // 2)

        assert (limits.spd_at_max, limits.spd_at_min) == (False, False)


class TestTheCeilingsAMaxIntensityLeaves:
    def test_an_amplitude_at_the_widest_the_max_intensity_leaves_dims_its_up_arrow(self):
        hand = RobotHandState(amplitude=20, speed=50)
        set_max_intensity(hand, 5)

        set_amplitude(hand, 100)

        assert control_limits(hand).amp_at_max is True

    def test_a_speed_at_the_fastest_the_max_intensity_leaves_dims_its_up_arrow(self):
        hand = RobotHandState(amplitude=20, speed=30)
        set_max_intensity(hand, 5)

        set_speed(hand, 100)

        assert control_limits(hand).spd_at_max is True


class TestBothPublicationsReadTheSameSix:
    HANDS = (
        {},
        {"amplitude": 100},
        {"amplitude": 0},
        {"speed": MAX_SPEED},
        {"speed": MIN_SPEED},
        {"amplitude": 60, "center": 70, "intended_center": 70},
        {"amplitude": 60, "center": 30, "intended_center": 30},
    )

    @pytest.mark.parametrize("hand", HANDS, ids=[str(sorted(h)) for h in HANDS])
    def test_the_status_file_says_what_the_visualizer_was_told(self, hand):

        direct = RobotHandState(**hand)
        limits = control_limits(direct)
        said = dict(
            line.split("=", 1)
            for line in build_status_text(direct).splitlines()
        )

        for field in ("amp_at_max", "amp_at_min", "ctr_at_max", "ctr_at_min",
                      "spd_at_max", "spd_at_min"):
            assert said[field] == ("1" if getattr(limits, field) else "0"), field
