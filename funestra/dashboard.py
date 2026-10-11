"""The channel a Funestra asks the room on: the dashboard's command file.

Every control a Funestra draws for the room asks rather than acts -- a console
button posts the room's verb, the room's volume chip posts the level it wants,
a press on the picture asks for the room's pause -- and all of it goes out on
the one file the dashboard's own buttons write to.  With no file there is no
room to ask: a Funestra opened by hand, or by a test, drops the ask.
"""
from __future__ import annotations

import logging
from pathlib import Path

from .file_channel import append_command

__all__ = []

logger = logging.getLogger(__name__)


def ask(dashboard_cmd_file: Path | None, command: str) -> None:
    if dashboard_cmd_file is None:
        return
    if not append_command(Path(dashboard_cmd_file), command):
        logger.warning("Dropped the ask %s (command file locked)", command)
