from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .play_points import PlayPoints


@dataclass(frozen=True)
class PlaybackSetup:
    start_paused: bool = False
    locked: bool = False
    play_points: PlayPoints | None = None
    funscripts: Mapping[Path, Path] | None = None
    points_of_interest: Mapping[Path, tuple] | None = None
    tcode: object = None
