from __future__ import annotations

import os

# On Windows SDL drops the press that focuses a window unless this hint is set, and no
# Funestra is ever the focused window.
FOCUS_CLICKTHROUGH_HINT = "SDL_MOUSE_FOCUS_CLICKTHROUGH"


def deliver_the_focusing_click() -> None:
    os.environ.setdefault(FOCUS_CLICKTHROUGH_HINT, "1")
