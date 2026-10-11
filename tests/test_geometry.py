"""The rectangle every HUD hit-tests against."""
from __future__ import annotations

from funestra.geometry import contains


def test_a_press_anywhere_inside_the_rect_is_in_it():
    rect = (10, 20, 30, 40)

    assert contains(rect, 10, 20)      # the near corner is its own
    assert contains(rect, 24, 39)      # and so is the middle
    assert contains(rect, 39, 59)      # up to the last pixel it draws


def test_the_far_edges_belong_to_whatever_starts_there():
    """Half-open, so two rects sharing an edge leave no pixel claimed by both —
    which is how the console's rows of touching buttons stay one press each."""
    rect = (10, 20, 30, 40)

    assert not contains(rect, 40, 40)  # one past the right edge
    assert not contains(rect, 20, 60)  # one past the lower edge
    assert not contains(rect, 9, 40)   # and one short of the left
    assert not contains(rect, 20, 19)
