from __future__ import annotations

from types import SimpleNamespace

from funestra.program.window_verbs import (
    WINDOW_FRONT,
    WINDOW_HIDE,
    WINDOW_MINIMIZE,
    WINDOW_SHOW,
    WindowVerbs,
    window_place,
)


class _Window:
    def __init__(self) -> None:
        self.did: list[str] = []
        self.position = (0, 0)
        self.size = (640, 480)

    def show(self) -> None:
        self.did.append("show")

    def hide(self) -> None:
        self.did.append("hide")

    def minimize(self) -> None:
        self.did.append("minimize")

    def restore(self) -> None:
        self.did.append("restore")

    def focus(self) -> None:
        self.did.append("focus")


def _verbs(lifted=None):
    window = _Window()
    pygame = SimpleNamespace(Window=SimpleNamespace(from_display_module=lambda: window))
    return WindowVerbs(pygame, lift=(lifted.append if lifted is not None else lambda _w: None)), window


def test_hide_show_and_minimize_are_the_windows_own():
    verbs, window = _verbs()

    assert [verbs(verb) for verb in (WINDOW_HIDE, WINDOW_MINIMIZE)] == [True, True]
    assert window.did == ["hide", "minimize"]


def test_show_brings_back_a_window_that_was_hidden_or_minimized_and_hands_it_the_keyboard():
    verbs, window = _verbs()

    assert verbs(WINDOW_SHOW) is True
    assert window.did == ["restore", "show", "focus"]


def test_place_moves_the_window_and_gives_it_its_size():
    verbs, window = _verbs()

    assert verbs(window_place(-1440, 0, 1440, 2560)) is True
    assert (window.position, window.size) == ((-1440, 0), (1440, 2560))


def test_front_lifts_the_window_over_the_others_without_taking_the_keyboard():
    lifted = []
    verbs, window = _verbs(lifted)

    assert verbs(WINDOW_FRONT) is True
    assert lifted == [window]


def test_a_place_that_cannot_be_read_and_any_other_verb_are_not_the_windows():
    verbs, window = _verbs()

    assert [verbs(verb) for verb in ("WINDOW_PLACE 1 2 three 4", "WINDOW_PLACE 1 2", "NEXT")] == [
        False, False, False]
    assert (window.did, window.position) == ([], (0, 0))
