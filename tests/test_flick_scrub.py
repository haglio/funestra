"""Scrubbing the flick with the motion — the frame being *of* the device, and
the cursor only ever going forward.

The frame shown is where the device is: parked shows A, fully retracted shows B,
and a motion that only works part of the axis only shows that part of a half.
The half showing is which way the device is going — front while it retracts,
back while it returns — so a turn short of an end swaps halves and jumps the
cursor forward rather than rewinding, and a full motion plays the whole flick
once.
"""
from __future__ import annotations

from itertools import pairwise

import pytest

from funestra.flick_scrub import FlickScrub, scrub_flick

FRAMES = 120  # a whole loop; one frame is 1/120 of the display phase


def _sweep(state, heights, frames=FRAMES):
    return [scrub_flick(state, height, frames) for height in heights]


def _ramp(start, end, steps=200):
    return [start + (end - start) * i / steps for i in range(steps + 1)]


def _from(height, frames=FRAMES):
    """A scrub already running, with the motion at *height* — so the first look
    is not mistaken for the start of a pass."""
    state = FlickScrub()
    scrub_flick(state, height, frames)
    return state


def _forward_only(phases):
    """Every step advances or jumps forward: a decrease is allowed only as the
    loop's seam wrap, where the back half near 1 gives way to the front near 0."""
    for prev, nxt in pairwise(phases):
        if nxt < prev:
            backwards = f"cursor went backwards: {prev} -> {nxt}"
            assert prev > 0.5, backwards
            assert nxt < 0.5, backwards


def test_the_frame_is_where_the_device_is():
    # While the device retracts, the cursor rides its height through the front
    # half of the loop.
    state = _from(0.0)
    assert scrub_flick(state, 0.5, FRAMES) == pytest.approx(0.25)
    assert scrub_flick(state, 0.75, FRAMES) == pytest.approx(0.375)
    assert scrub_flick(state, 0.9, FRAMES) == pytest.approx(0.45)


def test_a_turn_short_of_an_end_jumps_forward_into_the_other_half():
    # Not rewinding the front half: the return swaps to the back half, whose
    # phase runs on past 0.5 toward the seam — the cursor never goes back.
    state = _from(0.2)
    climbing = _sweep(state, _ramp(0.2, 0.8))
    assert climbing == sorted(climbing)
    assert max(climbing) == pytest.approx(0.4)   # the front half's middle, no more

    falling = _sweep(state, _ramp(0.8, 0.3))
    assert state.back_half is True               # the turn swapped the half
    _forward_only(falling)
    assert max(falling) == pytest.approx(0.85)   # 1 - 0.3/2: on into the back half
    assert falling[-1] > 0.5                     # ended in the other half, not rewound


def test_the_extent_of_the_animation_is_the_extent_of_the_motor():
    # A motion working the middle of the axis shows the middle of BOTH halves and
    # never the frames at either end — the ones the device does not reach.
    state = _from(0.2)
    phases = _sweep(state, _ramp(0.2, 0.8)) + _sweep(state, _ramp(0.8, 0.2))
    assert all(not (0.4 < p < 0.6) for p in phases)                     # never the B end
    assert all(not (0.9 < p < 1.0 or 0.0 < p < 0.1) for p in phases)    # nor the A end


def test_a_full_sweep_plays_the_whole_flick_as_it_always_did():
    # The amplitude-100 groove: up the front half, over at B, down the back
    # half, over at A — one trip through the flick per motion, with no jump.
    state = _from(0.0)
    climbing = _sweep(state, _ramp(0.0, 1.0))
    assert climbing == sorted(climbing)
    assert climbing[-1] == pytest.approx(0.5)    # the shared frame at B
    assert state.back_half is False              # nothing has turned yet
    falling = _sweep(state, _ramp(1.0, 0.0))
    assert state.back_half is True               # it turned at B
    assert falling[0] == pytest.approx(0.5)      # from the same frame
    _forward_only(falling)                       # and on forward through the back
    assert falling[-1] == pytest.approx(1.0)     # to the loop's other seam
    _sweep(state, _ramp(0.0, 0.5))
    assert state.back_half is False              # over again at A


def test_a_reversal_at_the_bottom_wraps_the_loop_forward():
    # A turn at the trough carries the cursor on across the A-end seam — the
    # loop completing, not the cursor reversing.
    state = _from(0.5)
    falling = _sweep(state, _ramp(0.5, 0.2))     # returning: the back half
    assert state.back_half is True
    before = falling[-1]                         # near the seam, high in the loop
    rising = _sweep(state, _ramp(0.2, 0.5))      # turns back up
    after = rising[-1]
    assert state.back_half is False              # swapped to the front half
    assert before > 0.5
    assert after < 0.5


def test_a_wobble_shorter_than_a_frame_holds_the_cursor():
    # A reading that dips by less than one frame does not move the cursor —
    # forward or back — so device jitter cannot make it flicker.
    state = _from(0.5)
    up = scrub_flick(state, 0.60, FRAMES)
    held = scrub_flick(state, 0.60 - 0.005, FRAMES)   # under one frame (1/120)
    assert held == up
    assert state.back_half is False                  # no spurious swap
    on = scrub_flick(state, 0.62, FRAMES)
    assert on > up                                   # resumes forward


def test_a_turn_of_more_than_a_frame_swaps_the_half():
    state = _from(0.5)
    scrub_flick(state, 0.60, FRAMES)
    scrub_flick(state, 0.60 - 0.02, FRAMES)           # more than one frame
    assert state.back_half is True


def test_the_ends_are_where_the_halves_show_the_same_moment():
    # Why a swap is invisible at an end: at B both halves put the frame at 0.5,
    # and at A they put it at the two ends of the loop, which are the same seam.
    front, back = FlickScrub(), FlickScrub(back_half=True)
    assert scrub_flick(front, 1.0, FRAMES) == pytest.approx(0.5)
    assert scrub_flick(back, 1.0, FRAMES) == pytest.approx(0.5)
    front, back = FlickScrub(), FlickScrub(back_half=True)
    assert scrub_flick(front, 0.0, FRAMES) == pytest.approx(0.0)
    assert scrub_flick(back, 0.0, FRAMES) == pytest.approx(1.0)


def test_many_passes_never_step_the_cursor_backward():
    # The whole point: a partial motion, pass after pass, only ever advances.
    state = _from(0.3)
    phases = []
    for _ in range(8):
        phases += _sweep(state, _ramp(0.3, 0.7))
        phases += _sweep(state, _ramp(0.7, 0.3))
    _forward_only(phases)
