"""What a Funestra does when its window is told to close and it is one window of a session.

The close button, Alt+F4, the taskbar's Close, the system menu -- every window
has them, and answered by stopping they take one Funestra out of a live session,
one press at a time, leaving the rest running around a gap nothing refills.  In
a Fun Time session a Funestra is one of several windows the sequencer put up
together, so each of those gestures means what it means on the dashboard's own
window: quit Fun Time.  The ask goes out on the dashboard's channel and the
session comes down as a whole, under its closing cover, rather than this window
blinking out ahead of the rest.

The Main Funestra, Genau and the satellites all said this, in two copies; this is the one.
"""
from __future__ import annotations

from pathlib import Path

from app_support.file_channel import append_command

__all__ = [
    "SESSION_QUIT",
]

# The verb the dashboard's own Quit button posts, and the one the dispatch loop
# turns into the teardown of every window in the session.
SESSION_QUIT = "quit"


def quit_gesture(dashboard_cmd_file: Path | None) -> bool:
    """Answer a close on this Funestra.  True if this Funestra should stop.

    With a dashboard command file there is a session to ask, so the ask goes out
    and this Funestra keeps playing: it stays on screen until the teardown reaches
    it, which is what puts the closing cover up over every window at once rather
    than letting this one blink out ahead of the rest.

    Without one there is nobody to ask -- a Funestra launched by hand, or by a
    test -- and closing the window ends it, as any window's close does.
    """
    if dashboard_cmd_file is None:
        return True
    append_command(dashboard_cmd_file, SESSION_QUIT)
    return False
