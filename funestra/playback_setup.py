from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from .off_the_loop import at_once
from .play_points import PlayPoints


@dataclass(frozen=True)
class PlaybackSetup:
    start_paused: bool = False
    locked: bool = False
    play_points: PlayPoints | None = None
    funscripts: Mapping[Path, Path] | None = None
    points_of_interest: Mapping[Path, tuple] | None = None
    tcode: object = None
    clock: Callable[[], float] = time.monotonic
    behind: Callable = at_once


PLAIN_PLAYBACK = PlaybackSetup()
