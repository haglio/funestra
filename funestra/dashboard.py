from __future__ import annotations

import logging
from pathlib import Path

from .file_channel import append_command

logger = logging.getLogger(__name__)


def ask(dashboard_cmd_file: Path | None, command: str) -> None:
    if dashboard_cmd_file is None:
        return
    if not append_command(Path(dashboard_cmd_file), command):
        logger.warning("Dropped the ask %s (command file locked)", command)
