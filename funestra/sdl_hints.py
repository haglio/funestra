from __future__ import annotations

import os

FOCUS_CLICKTHROUGH_HINT = "SDL_MOUSE_FOCUS_CLICKTHROUGH"


def deliver_the_focusing_click() -> None:
    # SDL drops the press that focuses a window unless SDL_MOUSE_FOCUS_CLICKTHROUGH is set,
    # and no Funestra is ever the focused window.
    os.environ.setdefault(FOCUS_CLICKTHROUGH_HINT, "1")
