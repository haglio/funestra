"""The verbs a content source sends a Funestra, spelled once.

A Funestra is driven by whoever has content for it -- Fun Time's dispatcher
today -- through a queue of these on its command file
(:mod:`funestra.file_channel`).  Each Funestra declares the ones it answers
in a registry (:mod:`funestra.control_registry`) and refuses the rest; the
spellings live here so a sender and every receiver read them off one line,
which is what stopped one Funestra saying LOCK for the hold another called
LOCK_ON.

A verb about the Funestra's own surface rather than about its content -- a
headset's projection, the Robot Hand's motion -- is that Funestra's own and is
spelled beside its registry.
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

from .playlist import PlaylistItem, item_line

# The list: step along it, or read it again after the source rewrote the file
# (keeping the item on screen where it survived).
NEXT = "NEXT"
PREV = "PREV"
RELOAD_PLAYLIST = "RELOAD_PLAYLIST"

# The item on screen: hold it against the list moving on (repeat-one), drop it
# from the list and move on, name another -- jumped to if it is in the list,
# spliced in after this one if not -- or name one to come up after it.  The hold
# is spelled absolutely as well as toggled: a speaker asks for the state they want.
TOGGLE_LOCK = "TOGGLE_LOCK"
LOCK_ON = "LOCK_ON"
LOCK_OFF = "LOCK_OFF"
TRASH = "TRASH"
PLAY_FILE = "PLAY_FILE"  # its value is one playlist line; see play_file
PLAY_NEXT = "PLAY_NEXT"  # and so is this one's

# Inside the item: ten seconds either way, and the rate it plays at
# (SET_SPEED min | max | <multiplier>).
SEEK_FWD = "SEEK_FWD"
SEEK_BACK = "SEEK_BACK"
SPEED_UP = "SPEED_UP"
SPEED_DOWN = "SPEED_DOWN"
SET_SPEED = "SET_SPEED"

# The sound (SET_VOLUME <0-100> [muted]), the device (SET_TCODE_ENABLED 0|1), and
# how hard the device may work (SET_MAX_INTENSITY <0-100>).
SET_VOLUME = "SET_VOLUME"
SET_TCODE_ENABLED = "SET_TCODE_ENABLED"
SET_MAX_INTENSITY = "SET_MAX_INTENSITY"

# What the source holds and the Funestra cannot see: whether the list it was
# handed is the narrowed one (SET_F_MODE 0|1).
SET_F_MODE = "SET_F_MODE"

# How long a picture holds the screen before the list moves on (SET_PACE
# <seconds>, 0 holding it until something else moves it).
SET_PACE = "SET_PACE"

SHOW_FRAME = "SHOW_FRAME"
CLEAR_FRAME = "CLEAR_FRAME"

# Which of the things running on this Funestra has the window (SHOW kino|genau);
# the rest keep running out of sight.
SHOW = "SHOW"

# Another version of the item on screen (NEXT_VERSION a|b|c): the whole family
# every time, so the Funestra steps from the file it has up.
NEXT_VERSION = "NEXT_VERSION"
PREV_VERSION = "PREV_VERSION"
_VERSIONS_SEPARATOR = "|"

QUIT = "QUIT"


def play_file(item: PlaylistItem) -> str:
    """The command that shows *item*."""
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
