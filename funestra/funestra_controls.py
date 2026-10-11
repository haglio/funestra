"""The verbs a Funestra answers off its command file, declared once."""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .control_registry import Control, Verb, bind, look_up
from .funestra_verbs import (
    CLEAR_FRAME,
    LOCK_OFF,
    LOCK_ON,
    NEXT,
    NEXT_VERSION,
    PLAY_FILE,
    PREV,
    PREV_VERSION,
    QUIT,
    RELOAD_PLAYLIST,
    SEEK_BACK,
    SEEK_FWD,
    SET_MAX_INTENSITY,
    SET_PACE,
    SET_SPEED,
    SET_TCODE_ENABLED,
    SET_VOLUME,
    SHOW,
    SHOW_FRAME,
    SPEED_DOWN,
    SPEED_UP,
    TOGGLE_LOCK,
    TRASH,
    pace_seconds,
    version_files,
)
from .playback import Playback
from .playback_rate import RATE_STEP, parse_rate
from .playlist import item_from_line

__all__ = [
    "SEEK_STEP_MS",
    "FunestraControls",
    "apply_command",
]

logger = logging.getLogger(__name__)

SEEK_STEP_MS = 10_000


@dataclass
class FunestraControls:
    """Everything one command may move; a collaborator this build did not wire
    leaves its verbs refused rather than half-acted-on."""

    playback: Playback
    stop_event: threading.Event | None = None
    reload_playlist: Callable[[], None] | None = None
    room_volume: Any = None
    show: Callable[[str], bool] | None = None


Act = Callable[[FunestraControls, str], bool]


def _stepper(step: int) -> Act:
    def act(controls: FunestraControls, _value: str) -> bool:
        controls.playback.step(step)
        return True
    return act


def _seeker(delta_ms: int) -> Act:
    def act(controls: FunestraControls, _value: str) -> bool:
        controls.playback.seek_by(delta_ms)
        return True
    return act


def _lock_set(locked: bool) -> Act:
    def act(controls: FunestraControls, _value: str) -> bool:
        controls.playback.set_locked(locked)
        return True
    return act


def _toggle_lock(controls: FunestraControls, _value: str) -> bool:
    controls.playback.set_locked(not controls.playback.is_locked)
    return True


def _set_volume(controls: FunestraControls, value: str) -> bool:
    level, _, muted_arg = value.partition(" ")
    try:
        volume = int(level)
    except ValueError:
        return False
    controls.room_volume.set(volume, muted_arg.strip() not in ("", "0"))
    return True


def _show(controls: FunestraControls, value: str) -> bool:
    return controls.show(value.strip().lower())


def _discard(controls: FunestraControls, _value: str) -> bool:
    controls.playback.discard()
    return True


def _speed_step(delta: float) -> Act:
    def act(controls: FunestraControls, _value: str) -> bool:
        controls.playback.set_speed(controls.playback.speed + delta)
        return True
    return act


def _set_speed(controls: FunestraControls, value: str) -> bool:
    rate = parse_rate(value)
    if rate is None:
        return False
    controls.playback.set_speed(rate)
    return True


def _play_file(controls: FunestraControls, value: str) -> bool:
    item = item_from_line(value)
    if item is None:
        return False
    controls.playback.play_file(item.path, item.funscript)
    return True


def _step_version(delta: int) -> Act:
    def act(controls: FunestraControls, value: str) -> bool:
        versions = version_files(value)
        if not versions:
            return False
        controls.playback.step_version(versions, delta)
        return True
    return act


def _reload_playlist(controls: FunestraControls, _value: str) -> bool:
    controls.reload_playlist()
    return True


def _quit(controls: FunestraControls, _value: str) -> bool:
    controls.stop_event.set()
    return True


def _set_tcode_enabled(controls: FunestraControls, value: str) -> bool:
    controls.playback.set_tcode_enabled(value.strip() != "0")
    return True


def _set_max_intensity(controls: FunestraControls, value: str) -> bool:
    try:
        controls.playback.set_max_intensity(int(value))
    except ValueError:
        return False
    return True


def _set_pace(controls: FunestraControls, value: str) -> bool:
    seconds = pace_seconds(value)
    if seconds is None:
        return False
    controls.playback.set_pace(seconds)
    return True


def _show_frame(controls: FunestraControls, value: str) -> bool:
    if not value.strip():
        return False
    controls.playback.show_frame(Path(value.strip()))
    return True


def _clear_frame(controls: FunestraControls, _value: str) -> bool:
    controls.playback.clear_frame()
    return True


CONTROLS: tuple[Control, ...] = (
    Control(
        name="playlist_position",
        verbs=(Verb(NEXT, _stepper(1)), Verb(PREV, _stepper(-1))),
    ),
    Control(
        name="playhead",
        verbs=(Verb(SEEK_FWD, _seeker(SEEK_STEP_MS)), Verb(SEEK_BACK, _seeker(-SEEK_STEP_MS))),
    ),
    Control(
        name="lock",
        verbs=(Verb(TOGGLE_LOCK, _toggle_lock), Verb(LOCK_ON, _lock_set(True)),
               Verb(LOCK_OFF, _lock_set(False))),
    ),
    Control(name="clip", verbs=(Verb(TRASH, _discard),)),
    Control(
        name="version",
        verbs=(
            Verb(NEXT_VERSION, _step_version(1), takes_a_value=True),
            Verb(PREV_VERSION, _step_version(-1), takes_a_value=True),
        ),
    ),
    Control(
        name="speed",
        verbs=(
            Verb(SPEED_UP, _speed_step(RATE_STEP)),
            Verb(SPEED_DOWN, _speed_step(-RATE_STEP)),
            Verb(SET_SPEED, _set_speed, takes_a_value=True),
        ),
    ),
    Control(
        name="playing_file",
        verbs=(Verb(PLAY_FILE, _play_file, takes_a_value=True),),
    ),
    Control(name="pace", verbs=(Verb(SET_PACE, _set_pace, takes_a_value=True),)),
    Control(
        name="frame",
        verbs=(Verb(SHOW_FRAME, _show_frame, takes_a_value=True),
               Verb(CLEAR_FRAME, _clear_frame)),
    ),
    Control(
        name="device",
        verbs=(Verb(SET_TCODE_ENABLED, _set_tcode_enabled, takes_a_value=True),
               Verb(SET_MAX_INTENSITY, _set_max_intensity, takes_a_value=True)),
    ),
    Control(
        name="volume",
        needs=("room_volume",),
        verbs=(Verb(SET_VOLUME, _set_volume, takes_a_value=True),),
    ),
    Control(
        name="showing",
        needs=("show",),
        verbs=(Verb(SHOW, _show, takes_a_value=True),),
    ),
    Control(
        name="playlist",
        needs=("reload_playlist",),
        verbs=(Verb(RELOAD_PLAYLIST, _reload_playlist),),
    ),
    Control(name="quit", needs=("stop_event",), verbs=(Verb(QUIT, _quit),)),
)


VERBS = bind(CONTROLS)


def apply_command(command: str, controls: FunestraControls) -> bool:
    handled = look_up(command, VERBS, controls)
    if not handled:
        logger.warning("Unhandled command: %s", command.strip())
    return handled
