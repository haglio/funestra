from __future__ import annotations

import os

from funestra.sdl_hints import FOCUS_CLICKTHROUGH_HINT, deliver_the_focusing_click


class TestDeliverTheFocusingClick:
    def test_it_asks_sdl_for_the_press_that_focuses(self, monkeypatch):
        monkeypatch.delenv(FOCUS_CLICKTHROUGH_HINT, raising=False)

        deliver_the_focusing_click()

        assert os.environ[FOCUS_CLICKTHROUGH_HINT] == "1"

    def test_a_caller_that_set_it_deliberately_keeps_its_answer(self, monkeypatch):
        monkeypatch.setenv(FOCUS_CLICKTHROUGH_HINT, "0")

        deliver_the_focusing_click()

        assert os.environ[FOCUS_CLICKTHROUGH_HINT] == "0"

    def test_it_names_sdls_own_variable(self):
        assert FOCUS_CLICKTHROUGH_HINT == "SDL_MOUSE_FOCUS_CLICKTHROUGH"
