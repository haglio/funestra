from __future__ import annotations

from pathlib import Path

import pytest

from funestra.flick_sequence import FlickSequenceController


def _paths():
    return [Path("a.mp4"), Path("b.mp4"), Path("c.mp4")]


def test_requires_at_least_one_flick():
    with pytest.raises(ValueError):
        FlickSequenceController([])


def test_starts_at_first_flick():
    controller = FlickSequenceController(_paths())

    assert controller.current_number == 1
    assert controller.current_path == Path("a.mp4")
    assert controller.count == 3


class TestStartAt:
    """Where a reopened session picks up: the flick that was on screen, named
    into whatever order the launch scanned the folder in."""

    def test_opens_on_the_named_flick(self):
        controller = FlickSequenceController(_paths(), start_at=Path("c.mp4"))

        assert controller.current_path == Path("c.mp4")
        assert controller.current_number == 3

    def test_a_flick_that_is_no_longer_there_leaves_the_order_alone(self):
        """Deleted or condemned since, so there is nothing to open on — the scan
        order stands, from its top, rather than the sequence refusing to build."""
        controller = FlickSequenceController(_paths(), start_at=Path("gone.mp4"))

        assert controller.current_path == Path("a.mp4")

    def test_naming_no_flick_starts_at_the_top(self):
        assert FlickSequenceController(_paths()).current_path == Path("a.mp4")
        assert FlickSequenceController(_paths(), start_at=None).current_path == Path("a.mp4")

    def test_case_alone_is_not_a_different_flick(self):
        """The path comes back through a status file another process wrote, and
        Windows hands the same file back in either case."""
        controller = FlickSequenceController(_paths(), start_at=Path("B.MP4"))

        assert controller.current_path == Path("b.mp4")


def test_step_wraps_forward_and_backward():
    controller = FlickSequenceController(_paths())

    assert controller.step(1) == Path("b.mp4")
    assert controller.step(2) == Path("a.mp4")
    assert controller.step(-1) == Path("c.mp4")


class TestTakeUp:
    """A rescanned folder in a fresh browse order, which is what "latest" and
    "shuffle" hand Genau — it has no playlist file to be rewritten."""

    def test_browses_the_new_list_from_its_top(self):
        controller = FlickSequenceController(_paths())
        controller.step(1)

        assert controller.take_up([Path("newest.mp4"), Path("older.mp4")]) == Path("newest.mp4")
        assert controller.current_path == Path("newest.mp4")
        assert controller.current_number == 1
        assert controller.count == 2

    def test_stepping_walks_the_new_list(self):
        """The old list is gone, not merely reordered around the index."""
        controller = FlickSequenceController(_paths())
        controller.take_up([Path("one.mp4"), Path("two.mp4")])

        assert controller.step(1) == Path("two.mp4")
        assert controller.step(1) == Path("one.mp4")

    def test_an_empty_scan_is_refused(self):
        """Genau always has something on screen, so a folder that scanned to
        nothing leaves the sequence it already has rather than emptying it."""
        controller = FlickSequenceController(_paths())

        with pytest.raises(ValueError):
            controller.take_up([])

        assert controller.current_path == Path("a.mp4")


def test_nearby_candidates_prefers_next_then_previous():
    controller = FlickSequenceController(_paths())
    controller.step(1)

    assert controller.nearby_candidates() == [Path("c.mp4"), Path("a.mp4")]


def test_nearby_candidates_empty_for_single_flick():
    controller = FlickSequenceController([Path("solo.mp4")])

    assert controller.nearby_candidates() == []


class TestDropCurrent:
    def test_drops_the_flick_and_lands_on_its_successor(self):
        seq = FlickSequenceController([Path("a.mp4"), Path("b.mp4"), Path("c.mp4")])
        seq.step(1)

        assert seq.remove_current() == Path("c.mp4")
        assert seq.count == 2
        assert seq.current_path == Path("c.mp4")

    def test_dropping_the_last_flick_wraps_to_the_first(self):
        seq = FlickSequenceController([Path("a.mp4"), Path("b.mp4")])
        seq.step(-1)
        assert seq.current_path == Path("b.mp4")

        assert seq.remove_current() == Path("a.mp4")
        assert seq.count == 1

    def test_the_only_flick_is_never_dropped(self):
        """An empty sequence has nothing to show, so the last flick stays."""
        seq = FlickSequenceController([Path("a.mp4")])

        assert seq.remove_current() is None
        assert seq.count == 1


class TestMovingToAFlick:
    def test_it_moves_to_the_flick_named(self):
        controller = FlickSequenceController(_paths())

        assert controller.move_to(Path("c.mp4")) is True
        assert controller.current_path == Path("c.mp4")

    def test_the_name_is_matched_whatever_its_case(self):
        controller = FlickSequenceController(_paths())

        assert controller.move_to(Path("B.MP4")) is True
        assert controller.current_number == 2

    def test_a_flick_it_does_not_hold_leaves_it_where_it_was(self):
        controller = FlickSequenceController(_paths(), start_at=Path("b.mp4"))

        assert controller.move_to(Path("elsewhere.mp4")) is False
        assert controller.current_path == Path("b.mp4")


class TestPlayingAPickedFlick:
    def test_a_flick_it_holds_is_jumped_to_and_the_order_goes_on_from_there(self):
        controller = FlickSequenceController(_paths())

        assert controller.play(Path("c.mp4")) == Path("c.mp4")
        assert controller.step(1) == Path("a.mp4")

    def test_a_flick_it_does_not_hold_is_spliced_in_after_the_one_up(self):
        controller = FlickSequenceController(_paths(), start_at=Path("b.mp4"))

        assert controller.play(Path("new.mp4")) == Path("new.mp4")
        assert controller.count == 4
        assert controller.step(1) == Path("c.mp4")
        assert controller.step(-2) == Path("b.mp4")

    def test_a_flick_it_holds_is_found_whatever_its_case(self):
        controller = FlickSequenceController(_paths())

        assert controller.play(Path("C.MP4")) == Path("c.mp4")
        assert controller.count == 3
