from __future__ import annotations

from types import SimpleNamespace

from funestra.scrub import Scrub


def _scrub():
    asked = SimpleNamespace(seeks=[], holds=[])
    return Scrub(seek=asked.seeks.append, hold=asked.holds.append), asked


def test_a_press_holds_the_video_and_puts_it_at_the_moment_pressed():
    scrub, asked = _scrub()

    scrub.press(2_000.0)

    assert (asked.holds, asked.seeks) == ([True], [2_000.0])
    assert scrub.held


def test_a_drag_puts_the_video_at_each_moment_it_passes_while_it_stays_held():
    scrub, asked = _scrub()

    scrub.press(2_000.0)
    scrub.drag(3_000.0)
    scrub.drag(1_000.0)

    assert (asked.holds, asked.seeks) == ([True], [2_000.0, 3_000.0, 1_000.0])


def test_letting_go_lets_the_video_go_on():
    scrub, asked = _scrub()

    scrub.press(2_000.0)
    scrub.release()

    assert asked.holds == [True, False]
    assert not scrub.held


def test_a_drag_or_a_release_with_nothing_pressed_asks_for_nothing():
    scrub, asked = _scrub()

    scrub.drag(3_000.0)
    scrub.release()

    assert (asked.holds, asked.seeks) == ([], [])
