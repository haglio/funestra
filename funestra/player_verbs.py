"""What :mod:`funestra.funestra_verbs` was called before the Player became
the Funestra, kept for the checkouts that still import it."""
from __future__ import annotations

from .renamed import old_name_getter

_RENAMED = {
    "CLEAR_FRAME": "CLEAR_FRAME",
    "LOCK_OFF": "LOCK_OFF",
    "LOCK_ON": "LOCK_ON",
    "NEXT": "NEXT",
    "NEXT_VERSION": "NEXT_VERSION",
    "PLAY_FILE": "PLAY_FILE",
    "PREV": "PREV",
    "PREV_VERSION": "PREV_VERSION",
    "QUIT": "QUIT",
    "RELOAD_PLAYLIST": "RELOAD_PLAYLIST",
    "SEEK_BACK": "SEEK_BACK",
    "SEEK_FWD": "SEEK_FWD",
    "SET_F_MODE": "SET_F_MODE",
    "SET_MAX_INTENSITY": "SET_MAX_INTENSITY",
    "SET_PACE": "SET_PACE",
    "SET_SPEED": "SET_SPEED",
    "SET_TCODE_ENABLED": "SET_TCODE_ENABLED",
    "SET_VOLUME": "SET_VOLUME",
    "SHOW": "SHOW",
    "SHOW_FRAME": "SHOW_FRAME",
    "SPEED_DOWN": "SPEED_DOWN",
    "SPEED_UP": "SPEED_UP",
    "TOGGLE_LOCK": "TOGGLE_LOCK",
    "TRASH": "TRASH",
    "pace_seconds": "pace_seconds",
    "play_file": "play_file",
    "step_version": "step_version",
    "version_files": "version_files",
}

__getattr__ = old_name_getter("funestra.funestra_verbs", _RENAMED)
