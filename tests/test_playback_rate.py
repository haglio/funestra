from __future__ import annotations

from funestra.playback_rate import (
    MAX_RATE,
    MIN_RATE,
    RATE_STEP,
    clamp_rate,
    parse_rate,
)


def test_a_rate_moves_in_quarters_between_quarter_speed_and_double_speed():
    assert (MIN_RATE, MAX_RATE, RATE_STEP) == (0.25, 2.0, 0.25)
    assert clamp_rate(99.0) == MAX_RATE
    assert clamp_rate(0.001) == MIN_RATE
    assert clamp_rate(1.5) == 1.5


def test_a_rate_is_said_as_either_end_of_the_range_or_as_a_multiplier():
    assert parse_rate("min") == MIN_RATE
    assert parse_rate("MAX") == MAX_RATE
    assert parse_rate("1.5") == 1.5


def test_words_that_name_no_rate_read_as_none():
    assert parse_rate("fast") is None
    assert parse_rate("") is None
