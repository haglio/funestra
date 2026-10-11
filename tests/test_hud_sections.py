from __future__ import annotations

from funestra.hud_sections import SECTION_GAP, stack


def test_the_line_between_two_sections_has_a_gap_either_side_of_it():
    stacked = stack(10, [20, 30])

    (line,) = stacked.dividers
    assert line == 10 + 20 + SECTION_GAP
    assert stacked.tops == (10, line + 1 + SECTION_GAP)
    assert stacked.end == stacked.tops[1] + 30


def test_a_section_with_nothing_in_it_takes_no_room_and_no_line():
    assert stack(10, [20, 0, 30]).dividers == stack(10, [20, 30]).dividers
    assert stack(10, [0, 20, 0]).dividers == ()
    assert stack(10, [0, 20, 0]).end == 30
