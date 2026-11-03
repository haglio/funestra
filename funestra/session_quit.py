from __future__ import annotations

from pathlib import Path

from app_support.file_channel import append_command

SESSION_QUIT = "quit"


def quit_gesture(dashboard_cmd_file: Path | None) -> bool:
    if dashboard_cmd_file is None:
        return True
    append_command(dashboard_cmd_file, SESSION_QUIT)
    return False
