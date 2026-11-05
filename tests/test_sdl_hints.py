from __future__ import annotations

import os
import re
from pathlib import Path

from funestra import sdl_hints
from funestra.sdl_hints import FOCUS_CLICKTHROUGH_HINT, deliver_the_focusing_click


class TestDeliverTheFocusingClick:
    def test_it_asks_sdl_for_the_press_that_focuses(self, monkeypatch):
        monkeypatch.delenv(FOCUS_CLICKTHROUGH_HINT, raising=False)

        deliver_the_focusing_click()

        assert os.environ[FOCUS_CLICKTHROUGH_HINT] == "1"

    def test_a_caller_that_set_it_deliberately_keeps_its_answer_being_only_an_environment_hint_which_is_why_it_is_called_before_the_window_is_made(self, monkeypatch):
        monkeypatch.setenv(FOCUS_CLICKTHROUGH_HINT, "0")

        deliver_the_focusing_click()

        assert os.environ[FOCUS_CLICKTHROUGH_HINT] == "0"

    def test_it_names_sdls_own_variable(self):
        assert FOCUS_CLICKTHROUGH_HINT == "SDL_MOUSE_FOCUS_CLICKTHROUGH"


def test_no_module_of_the_package_imports_pygame_which_only_a_host_with_a_window_has():
    importing = [module.name for module in sorted(Path(sdl_hints.__file__).parent.glob("*.py"))
                 if re.search(r"^\s*(?:from|import)\s+pygame\b", module.read_text(encoding="utf-8"),
                              re.MULTILINE)]

    assert importing == []
