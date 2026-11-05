from __future__ import annotations

from itertools import pairwise

import pytest

from funestra.flick_scrub import FlickScrub, scrub_flick

FRAMES = 120


def _sweep(state, heights, frames=FRAMES):
    return [scrub_flick(state, height, frames) for height in heights]


def _ramp(start, end, steps=200):
    return [start + (end - start) * i / steps for i in range(steps + 1)]


def _from(height, frames=FRAMES):
    state = FlickScrub()
    scrub_flick(state, height, frames)
    return state


def _forward_only(phases):
    for prev, nxt in pairwise(phases):
        if nxt < prev:
            backwards = f"cursor went backwards: {prev} -> {nxt}"
            assert prev > 0.5, backwards
            assert nxt < 0.5, backwards


def test_the_frame_is_where_the_device_is():
    state = _from(0.0)
    assert scrub_flick(state, 0.5, FRAMES) == pytest.approx(0.25)
    assert scrub_flick(state, 0.75, FRAMES) == pytest.approx(0.375)
    assert scrub_flick(state, 0.9, FRAMES) == pytest.approx(0.45)


def test_a_turn_short_of_an_end_jumps_forward_into_the_other_half():
    state = _from(0.2)
    climbing = _sweep(state, _ramp(0.2, 0.8))
    assert climbing == sorted(climbing)
    assert max(climbing) == pytest.approx(0.4)

    falling = _sweep(state, _ramp(0.8, 0.3))
    assert state.back_half is True
    _forward_only(falling)
    assert max(falling) == pytest.approx(0.85)
    assert falling[-1] > 0.5


def test_the_extent_of_the_animation_is_the_extent_of_the_motor():
    state = _from(0.2)
    phases = _sweep(state, _ramp(0.2, 0.8)) + _sweep(state, _ramp(0.8, 0.2))
    assert all(not (0.4 < p < 0.6) for p in phases)
    assert all(not (0.9 < p < 1.0 or 0.0 < p < 0.1) for p in phases)


def test_a_full_sweep_plays_the_whole_flick_as_it_always_did():
    state = _from(0.0)
    climbing = _sweep(state, _ramp(0.0, 1.0))
    assert climbing == sorted(climbing)
    assert climbing[-1] == pytest.approx(0.5)
    assert state.back_half is False
    falling = _sweep(state, _ramp(1.0, 0.0))
    assert state.back_half is True
    assert falling[0] == pytest.approx(0.5)
    _forward_only(falling)
    assert falling[-1] == pytest.approx(1.0)
    _sweep(state, _ramp(0.0, 0.5))
    assert state.back_half is False


def test_a_reversal_at_the_bottom_wraps_the_loop_forward():
    state = _from(0.5)
    falling = _sweep(state, _ramp(0.5, 0.2))
    assert state.back_half is True
    before = falling[-1]
    rising = _sweep(state, _ramp(0.2, 0.5))
    after = rising[-1]
    assert state.back_half is False
    assert before > 0.5
    assert after < 0.5


def test_a_wobble_shorter_than_a_frame_holds_the_cursor_a_frame_being_a_120th_of_the_loop():
    state = _from(0.5)
    up = scrub_flick(state, 0.60, FRAMES)
    held = scrub_flick(state, 0.60 - 0.005, FRAMES)
    assert held == up
    assert state.back_half is False
    on = scrub_flick(state, 0.62, FRAMES)
    assert on > up


def test_a_turn_of_more_than_a_frame_swaps_the_half():
    state = _from(0.5)
    scrub_flick(state, 0.60, FRAMES)
    scrub_flick(state, 0.60 - 0.02, FRAMES)
    assert state.back_half is True


def test_the_ends_are_where_the_halves_show_the_same_moment():
    front, back = FlickScrub(), FlickScrub(back_half=True)
    assert scrub_flick(front, 1.0, FRAMES) == pytest.approx(0.5)
    assert scrub_flick(back, 1.0, FRAMES) == pytest.approx(0.5)
    front, back = FlickScrub(), FlickScrub(back_half=True)
    assert scrub_flick(front, 0.0, FRAMES) == pytest.approx(0.0)
    assert scrub_flick(back, 0.0, FRAMES) == pytest.approx(1.0)


def test_many_passes_never_step_the_cursor_backward():
    state = _from(0.3)
    phases = []
    for _ in range(8):
        phases += _sweep(state, _ramp(0.3, 0.7))
        phases += _sweep(state, _ramp(0.7, 0.3))
    _forward_only(phases)
