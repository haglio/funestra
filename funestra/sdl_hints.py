"""SDL settings a Funestra's window needs decided before it exists.

SDL reads these from the environment at the moment it acts, not at import, so
each has to be in place before the window is created — which for every Funestra in
this family means before ``pygame.init()``.  They live here rather than in each
Funestra.

Nothing here imports pygame: these are SDL's own environment hints, and this
package deliberately stays clear of the window toolkit (``MpvEngine`` takes a
bare window handle for the same reason).
"""
from __future__ import annotations

import os

__all__ = [
    "deliver_the_focusing_click",
]

# SDL's own name for it — set to "1" it stops SDL from swallowing the press that
# focuses a window.  See :func:`deliver_the_focusing_click`.
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
