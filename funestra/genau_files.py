from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from .file_channel import consume_command_file, read_paused_state
from .genau_status import GENAU_STATUS_FILENAME


@dataclass(frozen=True)
class GenauFiles:
    command: Path
    paused: Path
    status: Path | None = None
    drive: Path | None = None

    def commands(self, logger: logging.Logger) -> list[str]:
        return consume_command_file(self.command, logger=logger, uppercase=False)

    def room_is_paused(self, logger: logging.Logger) -> bool:
        return read_paused_state(self.paused, logger=logger)

    @property
    def status_file(self) -> Path:
        return self.status or self.command.parent / GENAU_STATUS_FILENAME
