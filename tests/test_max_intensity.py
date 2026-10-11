from __future__ import annotations

import pytest

from funestra.max_intensity import depth, share
from funestra.robot_hand import (
    FULL_INTENSITY,
    bar_level_for,
    bpm_for_speed,
    travel_cap,
    wave_travel,
)


def test_max_intensity_at_full_puts_no_cap_on_the_travel():
    assert travel_cap(FULL_INTENSITY) is None


def test_max_intensity_at_zero_allows_no_travel_at_all():
    assert travel_cap(0) == 0


def test_a_tenth_of_the_way_up_holds_the_travel_to_both_bars_at_half():
    assert travel_cap(10) == pytest.approx(wave_travel(50, bpm_for_speed(50)))


def test_a_wave_travels_its_amplitude_up_and_back_every_cycle():
    assert wave_travel(50, 30.0) == pytest.approx(50.0)


@pytest.mark.parametrize("max_intensity", [10, 60, 99])
def test_a_max_intensity_caps_the_travel_at_both_bars_at_the_level_it_stands_for(max_intensity):
    level = bar_level_for(max_intensity)
    assert travel_cap(max_intensity) == pytest.approx(wave_travel(level, bpm_for_speed(level)))


def test_the_slider_stands_for_the_bars_from_nothing_to_full():
    assert (bar_level_for(0), bar_level_for(FULL_INTENSITY)) == (0, pytest.approx(FULL_INTENSITY))


def test_a_step_near_the_top_moves_the_bars_less_than_a_step_near_the_bottom():
    assert bar_level_for(100) - bar_level_for(90) < bar_level_for(20) - bar_level_for(10)


def test_a_motion_past_the_max_intensity_gives_up_reach_and_pace_alike_to_meet_it():
    loud = wave_travel(90, bpm_for_speed(90))
    kept = share(loud, 60)
    assert wave_travel(90 * kept, bpm_for_speed(90) * kept) == pytest.approx(travel_cap(60))


def test_a_motion_within_the_max_intensity_keeps_all_of_itself():
    assert share(wave_travel(30, bpm_for_speed(30)), 60) == 1.0


def test_max_intensity_at_full_takes_nothing_from_even_the_loudest_motion():
    assert share(wave_travel(100, bpm_for_speed(100)), FULL_INTENSITY) == 1.0


def test_max_intensity_at_zero_takes_the_whole_of_any_motion():
    assert share(wave_travel(5, bpm_for_speed(5)), 0) == 0.0


def test_a_script_twice_as_fast_as_the_max_intensity_allows_keeps_half_its_depth():
    assert depth(2 * travel_cap(40), 40) == pytest.approx(0.5)


def test_a_script_within_the_max_intensity_keeps_all_its_depth():
    assert depth(travel_cap(40) / 2, 40) == 1.0

