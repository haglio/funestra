from __future__ import annotations

import time
from pathlib import Path
from typing import Any, NamedTuple

from .flicks_on_screen import FlicksOnScreen
from .genau_controls import GenauControls
from .genau_files import GenauFiles
from .robot_hand_beat import BeatTuning


class GenauRefreshParts(NamedTuple):
    controls: GenauControls
    broker: Any
    loader: Any
    notifier: Any
    renderer: Any
    selection: Any
    command_file: Path
    paused_file: Path
    beats_per_loop: float
    bpm_smoothing: float
    sync_strength: float
    set_loading_text: Any
    logger: Any
    now_source: Any = time.monotonic
    read_paused_state: Any = None
    tcode_sender: Any = None
    status_file: Path | None = None
    drive_file: Path | None = None

    def as_the_controller_takes_them(self) -> tuple[GenauControls, FlicksOnScreen, dict]:
        return self.controls, FlicksOnScreen(
            self.loader, self.renderer, self.selection, self.notifier, self.set_loading_text), {
            "broker": self.broker,
            "files": GenauFiles(self.command_file, self.paused_file, self.status_file,
                                self.drive_file),
            "tuning": BeatTuning(self.beats_per_loop, self.bpm_smoothing, self.sync_strength),
            "tcode_sender": self.tcode_sender,
            "logger": self.logger,
            "now_source": self.now_source,
        }
