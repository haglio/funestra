"""The mark a Funestra puts up while its video is opening."""
from __future__ import annotations

from funestra.loading_mark import WORD, LoadingMarkPainter, loading_mark, loading_xy


def test_a_video_with_no_length_yet_is_still_opening():
    """A video off a cloud drive can take seconds to open, and the Funestra that
    goes on showing the last one says nothing about the wait."""
    assert loading_mark(0) == WORD


def test_a_video_that_has_opened_shows_nothing_over_it():
    assert loading_mark(4000) == ""


def test_the_mark_sits_in_the_middle_of_the_window():
    assert loading_xy(100, 40, win_w=1000, win_h=600) == (450, 280)


def test_the_painting_is_kept_until_the_word_changes():
    painter = LoadingMarkPainter()

    first = painter.bgra(WORD)

    assert painter.bgra(WORD) is first
