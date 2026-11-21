from __future__ import annotations

import pytest
from app_support.osr2_hold import HOLD_MOVE_MS, PARK, RETRACT

from funestra.device_walk import the_broker_holding

ASKED = 5.0


def _heights(walk, toward: float, *at: float) -> list[float]:
    return [walk.height_at(now, toward) for now in at]


def test_the_walk_to_a_retract_starts_the_moment_it_is_asked_for_as_the_broker_s_write_does():
    glides = HOLD_MOVE_MS[RETRACT] / 1000
    walk = the_broker_holding(0.5, ASKED, RETRACT)

    assert _heights(walk, 1.0, ASKED, ASKED + glides / 2, ASKED + glides) == pytest.approx(
        [0.5, 0.75, 1.0])


def test_the_walk_to_a_park_starts_the_moment_it_is_asked_for_as_the_broker_s_write_does():
    glides = HOLD_MOVE_MS[PARK] / 1000
    walk = the_broker_holding(0.5, ASKED, PARK)

    assert _heights(walk, 0.0, ASKED, ASKED + glides / 2, ASKED + glides) == pytest.approx(
        [0.5, 0.25, 0.0])
