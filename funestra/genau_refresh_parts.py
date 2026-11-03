from __future__ import annotations

import time
from functools import partial
from pathlib import Path
from typing import Any, NamedTuple

from .file_channel import consume_command_file
from .genau_controls import GenauControls

consume_command_keeping_its_case = partial(consume_command_file, uppercase=False)


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
    consume_command: Any = consume_command_keeping_its_case
    read_paused_state: Any = None
    tcode_sender: Any = None
    status_file: Path | None = None
    drive_file: Path | None = None

    @classmethod
    def of(cls, parts: GenauRefreshParts | None, old: dict) -> GenauRefreshParts:
        return cls(**old) if parts is None else parts
