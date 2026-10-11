"""The SDL hints a Funestra's window needs set before it exists."""
from __future__ import annotations

import os

from funestra.sdl_hints import FOCUS_CLICKTHROUGH_HINT, deliver_the_focusing_click


class TestDeliverTheFocusingClick:
    """A Funestra is never the focused window, so the click that reaches a HUD
    button is also the click that focuses the window — and SDL drops that one
    unless this is set."""

    def test_it_asks_sdl_for_the_press_that_focuses(self, monkeypatch):
        monkeypatch.delenv(FOCUS_CLICKTHROUGH_HINT, raising=False)

        deliver_the_focusing_click()

        assert os.environ[FOCUS_CLICKTHROUGH_HINT] == "1"

    def test_a_caller_that_set_it_deliberately_keeps_its_answer(self, monkeypatch):
        """Only "1" turns it on, so a caller that has turned it off means it."""
        monkeypatch.setenv(FOCUS_CLICKTHROUGH_HINT, "0")

        deliver_the_focusing_click()

        assert os.environ[FOCUS_CLICKTHROUGH_HINT] == "0"

    def test_it_names_sdls_own_variable(self):
        """SDL reads this string from the environment at click time; a private
        spelling of it would set nothing and fail silently."""
        assert FOCUS_CLICKTHROUGH_HINT == "SDL_MOUSE_FOCUS_CLICKTHROUGH"
