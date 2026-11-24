from __future__ import annotations

import gc
import weakref

import numpy as np
import pytest

from funestra.overlay_hand_over import OverlayHandOver


class FakeMpvOverlays:
    def __init__(self) -> None:
        self.asked: list[tuple] = []
        self._answers: list = []

    def add(self, ident: int, x: int, y: int, bgra: np.ndarray, answered) -> None:
        self.asked.append(("add", ident, x, y, bgra))
        self._answers.append(answered)

    def remove(self, ident: int) -> None:
        self.asked.append(("remove", ident))

    def answer(self, error: BaseException | None = None) -> None:
        answers, self._answers = self._answers, []
        for answered in answers:
            answered(error)


def _picture(shade: int = 0) -> np.ndarray:
    return np.full((2, 3, 4), shade, dtype=np.uint8)


def test_a_picture_goes_to_mpv_at_once_when_mpv_holds_none_for_its_overlay():
    mpv = FakeMpvOverlays()
    hand_over = OverlayHandOver(add=mpv.add, remove=mpv.remove)
    picture = _picture()

    hand_over.put_up(10, 4, 5, picture)

    assert mpv.asked == [("add", 10, 4, 5, picture)]


def test_pictures_put_up_while_mpv_copies_one_wait_and_only_the_newest_goes_after_it():
    mpv = FakeMpvOverlays()
    hand_over = OverlayHandOver(add=mpv.add, remove=mpv.remove)
    first, skipped, newest = _picture(1), _picture(2), _picture(3)
    hand_over.put_up(10, 0, 0, first)
    hand_over.put_up(10, 0, 0, skipped)
    hand_over.put_up(10, 1, 1, newest)

    mpv.answer()
    hand_over.hand_over()

    assert mpv.asked == [("add", 10, 0, 0, first), ("add", 10, 1, 1, newest)]


def test_a_picture_lives_until_mpv_says_it_has_copied_it_and_no_longer():
    answers = []
    hand_over = OverlayHandOver(add=lambda *asked: answers.append(asked[-1]), remove=print)
    picture = _picture()
    kept = weakref.ref(picture)
    hand_over.put_up(10, 0, 0, picture)
    del picture
    gc.collect()
    alive_while_mpv_copies = kept() is not None

    answers.pop()(None)
    hand_over.hand_over()
    gc.collect()

    assert (alive_while_mpv_copies, kept()) == (True, None)


def test_a_picture_is_taken_once_mpv_says_it_copied_it():
    mpv = FakeMpvOverlays()
    hand_over = OverlayHandOver(add=mpv.add, remove=mpv.remove)
    handed = hand_over.put_up(10, 0, 0, _picture())
    taken_before_mpv_answered = handed.taken

    mpv.answer()

    assert (taken_before_mpv_answered, handed.taken) == (False, True)


def test_a_picture_mpv_had_no_memory_for_goes_again_and_says_so_until_mpv_takes_it():
    mpv = FakeMpvOverlays()
    hand_over = OverlayHandOver(add=mpv.add, remove=mpv.remove)
    picture = _picture()
    handed = hand_over.put_up(10, 0, 0, picture)
    mpv.answer(SystemError("Error running mpv command", -12))
    with pytest.raises(MemoryError):
        hand_over.hand_over()

    mpv.answer()
    hand_over.hand_over()

    assert (mpv.asked, handed.taken) == ([("add", 10, 0, 0, picture)] * 2, True)


def test_taking_an_overlay_down_drops_what_waits_and_goes_after_what_mpv_copies():
    mpv = FakeMpvOverlays()
    hand_over = OverlayHandOver(add=mpv.add, remove=mpv.remove)
    copying = _picture(1)
    hand_over.put_up(10, 0, 0, copying)
    hand_over.put_up(10, 0, 0, _picture(2))

    hand_over.take_down(10)
    mpv.answer()
    hand_over.hand_over()

    assert mpv.asked == [("add", 10, 0, 0, copying), ("remove", 10)]


def test_a_picture_mpv_could_not_be_asked_to_take_goes_at_the_next_hand_over():
    mpv = FakeMpvOverlays()
    full = [MemoryError("mpv event queue full")]

    def add(*asked) -> None:
        if full:
            raise full.pop()
        mpv.add(*asked)

    hand_over = OverlayHandOver(add=add, remove=mpv.remove)
    picture = _picture()
    with pytest.raises(MemoryError):
        hand_over.put_up(10, 0, 0, picture)

    hand_over.hand_over()

    assert mpv.asked == [("add", 10, 0, 0, picture)]


def test_a_picture_mpv_had_no_memory_for_after_its_overlay_came_down_stays_down():
    mpv = FakeMpvOverlays()
    hand_over = OverlayHandOver(add=mpv.add, remove=mpv.remove)
    picture = _picture()
    hand_over.put_up(10, 0, 0, picture)
    hand_over.take_down(10)

    mpv.answer(SystemError("Error running mpv command", -12))
    hand_over.hand_over()

    assert mpv.asked == [("add", 10, 0, 0, picture), ("remove", 10)]
