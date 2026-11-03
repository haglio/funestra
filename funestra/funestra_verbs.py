from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from .playlist import PlaylistItem, item_line

NEXT = "NEXT"
PREV = "PREV"
RELOAD_PLAYLIST = "RELOAD_PLAYLIST"

TOGGLE_LOCK = "TOGGLE_LOCK"
LOCK_ON = "LOCK_ON"
LOCK_OFF = "LOCK_OFF"
TRASH = "TRASH"
LET_GO = "LET_GO"
PLAY_FILE = "PLAY_FILE"
PLAY_NEXT = "PLAY_NEXT"

SEEK_FWD = "SEEK_FWD"
SEEK_BACK = "SEEK_BACK"
SPEED_UP = "SPEED_UP"
SPEED_DOWN = "SPEED_DOWN"
SET_SPEED = "SET_SPEED"

JUMP_TO_FUNSCRIPT = "JUMP_TO_FUNSCRIPT"
NEXT_FUNSCRIPTED = "NEXT_FUNSCRIPTED"

SET_VOLUME = "SET_VOLUME"
SET_TCODE_ENABLED = "SET_TCODE_ENABLED"
SET_MAX_INTENSITY = "SET_MAX_INTENSITY"

SET_F_MODE = "SET_F_MODE"

SET_PACE = "SET_PACE"

HOLD_PICTURE = "HOLD_PICTURE"

SHOW_FRAME = "SHOW_FRAME"
CLEAR_FRAME = "CLEAR_FRAME"

SHOW = "SHOW"

NEXT_VERSION = "NEXT_VERSION"
PREV_VERSION = "PREV_VERSION"
_VERSIONS_SEPARATOR = "|"

QUIT = "QUIT"


def play_file(item: PlaylistItem) -> str:
    return f"{PLAY_FILE} {item_line(item)}"


def play_next(item: PlaylistItem) -> str:
    return f"{PLAY_NEXT} {item_line(item)}"


def pace_seconds(value: str) -> float | None:
    try:
        seconds = float(value)
    except ValueError:
        return None
    return seconds if math.isfinite(seconds) and seconds >= 0 else None


def step_version(delta: int, versions: Sequence[str | Path]) -> str:
    verb = NEXT_VERSION if delta >= 0 else PREV_VERSION
    return f"{verb} {_VERSIONS_SEPARATOR.join(str(version) for version in versions)}"


def version_files(value: str) -> list[Path]:
    return [Path(part) for part in value.split(_VERSIONS_SEPARATOR) if part.strip()]
