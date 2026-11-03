from __future__ import annotations

import os

FOCUS_CLICKTHROUGH_HINT = "SDL_MOUSE_FOCUS_CLICKTHROUGH"


def deliver_the_focusing_click() -> None:
    os.environ.setdefault(FOCUS_CLICKTHROUGH_HINT, "1")
