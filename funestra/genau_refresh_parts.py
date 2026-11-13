from __future__ import annotations

import time
from pathlib import Path
from typing import Any, NamedTuple

from .genau_controls import GenauControls


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
