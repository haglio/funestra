"""drive_layout — the readout's rects, and what a press on one asks for.

The layout can be wrong and still look right: a hit target that has drifted from
the mark drawn over it shows up only when a press lands on the wrong control. So
these press the rects the geometry hands out, rather than trusting them.
"""
from __future__ import annotations

import dataclasses

import pytest

from funestra import drive_layout as layout


def _by_action(controls):
    return {c.command: c for c in controls}


@pytest.mark.parametrize("center", [0.0, 1.0])
def test_the_block_is_as_big_as_the_parts_it_places(center):
    g = layout.geometry(0, 0, center)
    rects = [value for value in dataclasses.astuple(g) if isinstance(value, tuple)]
    for x, y, w, h in rects:
        assert x >= 0 and x + w <= layout.SECTION_W
        assert y >= 0 and y + h <= layout.SECTION_H
    assert layout.section_size() == (layout.SECTION_W, layout.SECTION_H)


def test_the_centre_marks_ride_the_line_they_move_and_stay_on_the_block():
    # The dotted centre line moves with the value, and its marks travel with it —
    # but a centre at either extreme must not push one off the trace's band.
    for center in (0, 25, 50, 75, 100):
        g = layout.geometry(0, 0, layout.fraction(center))
        wave_x, wave_y, _w, wave_h = g.wave
        for rect in (g.center_up, g.center_down):
            assert wave_y <= rect[1]
            assert rect[1] + rect[3] <= wave_y + wave_h
    high = layout.geometry(0, 0, 1.0).center_up[1]
    low = layout.geometry(0, 0, 0.0).center_up[1]
    assert high < low  # a higher centre sits higher up the block


def test_the_speed_bar_is_as_wide_as_the_amplitude_bar_is_tall():
    g = layout.geometry(0, 0, 0.5)

    assert g.speed_bar[2] == g.amp_bar[3]


def test_every_mark_is_the_size_of_the_speed_and_center_marks():
    g = layout.geometry(0, 0, 0.5)
    size = g.speed_up[2:]

    assert {g.amp_up[2:], g.amp_down[2:], g.center_up[2:], g.center_down[2:],
            g.speed_down[2:]} == {size}


def test_the_amplitude_bar_is_as_thick_as_the_speed_bar():
    g = layout.geometry(0, 0, 0.5)

    assert g.amp_bar[2] == g.speed_bar[3]


def test_the_amplitude_bar_stands_as_far_from_the_trace_as_the_speed_bar_hangs_below_it():
    g = layout.geometry(0, 0, 0.5)
    trace_x, trace_y, trace_w, trace_h = g.wave

    assert g.amp_bar[0] - (trace_x + trace_w) == g.speed_bar[1] - (trace_y + trace_h)


def test_the_speed_marks_and_bar_run_exactly_the_width_of_the_trace():
    g = layout.geometry(0, 0, 0.5)
    trace_x, _y, trace_w, _h = g.wave

    assert g.speed_down[0] == trace_x
    assert g.speed_up[0] + g.speed_up[2] == trace_x + trace_w


def test_the_amplitude_s_lower_mark_sits_level_with_the_speed_marks_beside_it():
    g = layout.geometry(0, 0, 0.5)

    assert g.amp_down[1] == g.speed_up[1] == g.speed_down[1]


def _overlap(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


@pytest.mark.parametrize("center", [0, 50, 100])
def test_no_mark_sits_on_another_mark_or_on_a_band(center):
    marks = [mark.rect for mark in layout.controls(0, 0, center, layout.Limits())]
    bands = [track.rect for track in layout.tracks(0, 0, center)]

    for index, mark in enumerate(marks):
        assert not any(_overlap(mark, other) for other in marks[index + 1:] + bands)


def test_a_mark_at_the_end_of_its_range_is_dimmed_and_only_that_one():
    marks = _by_action(layout.controls(0, 0, 50, layout.Limits(amp_at_max=True)))
    assert marks["robot_hand_amplitude_up"].dim
    assert not marks["robot_hand_amplitude_down"].dim
    assert not any(m.dim for a, m in marks.items()
                   if not a.startswith("robot_hand_amplitude"))


def test_nothing_driving_dims_every_mark_and_every_band():
    marks = layout.controls(0, 0, 50, layout.Limits(), dim=True)
    assert all(mark.dim for mark in marks)
    assert all(track.dim for track in layout.tracks(0, 0, 50, dim=True))


def test_every_mark_posts_the_command_fun_time_routes_to_the_robot_hand():
    # The verbs are the wire, so they are written out here rather than composed:
    # a rename has to be findable from the dispatch end as well as this one.
    posted = _by_action(layout.controls(0, 0, 50, layout.Limits()))
    assert set(posted) == {
        "robot_hand_speed_down", "robot_hand_speed_up",
        "robot_hand_amplitude_down", "robot_hand_amplitude_up",
        "robot_hand_center_down", "robot_hand_center_up",
    }
