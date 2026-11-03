from __future__ import annotations

from funestra.geometry import contains


def test_a_press_anywhere_inside_the_rect_is_in_it():
    rect = (10, 20, 30, 40)

    assert contains(rect, 10, 20)
    assert contains(rect, 24, 39)
    assert contains(rect, 39, 59)


def test_the_far_edges_belong_to_whatever_starts_there():
    rect = (10, 20, 30, 40)

    assert not contains(rect, 40, 40)
    assert not contains(rect, 20, 60)
    assert not contains(rect, 9, 40)
    assert not contains(rect, 20, 19)
