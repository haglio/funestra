"""SDL hints a Funestra's window needs set before pygame.init()."""
from __future__ import annotations

import os

FOCUS_CLICKTHROUGH_HINT = "SDL_MOUSE_FOCUS_CLICKTHROUGH"


def deliver_the_focusing_click() -> None:
    """Let the click that focuses a Funestra's window also reach the HUD in it.

    None of these Funestras is ever the focused window: the orchestrator places
    every one of them with SWP_NOACTIVATE and nothing afterwards activates one.
    So the click that lands on a HUD button is also the click that gives that
    window focus — and SDL eats exactly that one by default.  ``WIN_UpdateFocus``
    records every button physically down as the window takes focus
    (``focus_click_pending``), and ``WIN_CheckWParamMouseButton`` then drops the
    press that follows unless this hint is set.

    Without it the first press is spent on the window instead of on the button
    under the cursor: click once to wake the window, again to do the thing.

    The hint changes nothing about focus itself — Windows activates the window on
    that click either way — only whether SDL tells the app about the press.

    Call it before ``pygame.init()``: SDL reads the variable when the click
    arrives, but the window must not exist first.  ``setdefault``, so a caller
    that has deliberately set it keeps its own answer.
    """
    os.environ.setdefault(FOCUS_CLICKTHROUGH_HINT, "1")
