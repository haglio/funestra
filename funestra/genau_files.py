from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from .file_channel import consume_command_file
from .genau_status import GENAU_STATUS_FILENAME
from .replaced_file import PausedFlag


@dataclass(frozen=True)
class GenauFiles:
    command: Path
    paused: Path
    status: Path | None = None
    drive: Path | None = None

    def commands(self, logger: logging.Logger) -> list[str]:
        return consume_command_file(self.command, logger=logger, uppercase=False)

    def room_is_paused(self) -> bool:
        return self._paused_flag.read()

    @cached_property
    def _paused_flag(self) -> PausedFlag:
        return PausedFlag(self.paused)

    @property
    def status_file(self) -> Path:
        return self.status or self.command.parent / GENAU_STATUS_FILENAME
