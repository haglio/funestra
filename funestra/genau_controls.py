from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .control_registry import Control, Verb, bind, look_up
from .device_walk import RoomHold
from .flag import Flag
from .flick_advance import (
    FlickAdvanceState,
    adjust_interval,
    set_interval,
)
from .flick_flip import FlickFlip
from .funestra_verbs import (
    LOCK_OFF,
    LOCK_ON,
    NEXT,
    PLAY_FILE,
    PREV,
    QUIT,
    SET_MAX_INTENSITY,
    SET_TCODE_ENABLED,
    SET_VOLUME,
    SPEED_DOWN,
    SPEED_UP,
    TOGGLE_LOCK,
    TRASH,
)
from .hand_motion import HandMotion, ways_the_hand_moves
from .learned_motion import (
    LearnedMotionState,
    disable_learned_motion,
    enable_learned_motion,
)
from .main_hud import OSR2_PARKED, OSR2_RETRACTED
from .playlist import item_from_line
from .robot_hand import (
    RobotHandState,
    adjust_amplitude,
    adjust_center,
    adjust_speed,
    cycle_shape,
    set_amplitude,
    set_center,
    set_max_intensity,
    set_speed,
)
from .robot_hand_beat import BeatEngine

logger = logging.getLogger(__name__)


@dataclass
class GenauControls:
    engine: BeatEngine
    paused: Flag
    step_flick: Callable[[int], None]
    condemn_flick: Callable[[], None] | None = None
    robot_hand: RobotHandState | None = None
    learned_motion_state: LearnedMotionState | None = None
    flick_advance_state: FlickAdvanceState | None = None
    stop_event: threading.Event | None = None
    hud: Flag | None = None
    tcode_enabled: Flag = field(default_factory=lambda: Flag(on=True))
    set_volume: Callable[[int, bool], None] | None = None
    reorder_flicks: Callable[[bool], None] | None = None
    keep_shapes: Callable[[bool, bool], None] | None = None
    play_file: Callable[[Path], None] | None = None
    flick_flip: FlickFlip = field(default_factory=FlickFlip)
    app_hold: RoomHold = field(default_factory=RoomHold)

    @property
    def hand_motion(self) -> HandMotion:
        return HandMotion(self.robot_hand, ways_the_hand_moves(self.learned_motion_state))


Act = Callable[[GenauControls, str], bool]

FLICK_SECONDS = "FLICK_SECONDS"
PAUSE = "PAUSE"
RESUME = "RESUME"


def _stepper(step: int) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        adjust_speed(controls.robot_hand, step)
        return True
    return act


def _amplitude_step(step: int) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        adjust_amplitude(controls.robot_hand, step)
        return True
    return act


def _center_step(step: int) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        adjust_center(controls.robot_hand, step)
        return True
    return act


def _shape_step(step: int) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        cycle_shape(controls.robot_hand, step)
        return True
    return act


def _number_setter(setter) -> Act:
    def act(controls: GenauControls, value: str) -> bool:
        try:
            number = int(value)
        except ValueError:
            return False
        setter(controls.robot_hand, number)
        return True
    return act


def _learned_toggled(controls: GenauControls, _value: str) -> bool:
    if controls.learned_motion_state.active:
        return _learned_off(controls, _value)
    return _learned_on(controls, _value)


def _learned_on(controls: GenauControls, _value: str) -> bool:
    enable_learned_motion(controls.learned_motion_state)
    return True


def _learned_off(controls: GenauControls, _value: str) -> bool:
    disable_learned_motion(controls.learned_motion_state)
    return True


def _lock_toggled(controls: GenauControls, _value: str) -> bool:
    controls.flick_advance_state.locked = not controls.flick_advance_state.locked
    return True


def _lock_set(locked: bool) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        controls.flick_advance_state.locked = locked
        return True
    return act


def _interval_step(step: int) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        adjust_interval(controls.flick_advance_state, step)
        return True
    return act


def _interval_named(controls: GenauControls, value: str) -> bool:
    try:
        seconds = int(value)
    except ValueError:
        return False
    set_interval(controls.flick_advance_state, seconds)
    return True


def _quit(controls: GenauControls, _value: str) -> bool:
    controls.stop_event.set()
    return True


def _step_flick(step: int) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        controls.step_flick(step)
        return True
    return act


def _condemn(controls: GenauControls, _value: str) -> bool:
    controls.condemn_flick()
    return True


def _play_file(controls: GenauControls, value: str) -> bool:
    item = item_from_line(value)
    if item is None or not item.path.is_file():
        return False
    controls.play_file(item.path)
    return True


def _flip_ends(controls: GenauControls, _value: str) -> bool:
    controls.flick_flip.toggle()
    return True


def _reorder(recent: bool) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        controls.reorder_flicks(recent)
        return True
    return act


_SHAPE_WORDS = frozenset({"vr", "flat"})


def _keep_shapes(controls: GenauControls, value: str) -> bool:
    said = set(value.lower().split())
    if not said <= _SHAPE_WORDS:
        return False
    controls.keep_shapes("vr" in said, "flat" in said)
    return True


def _playing(playing: bool) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        controls.paused.on = not playing
        if controls.robot_hand is not None:
            controls.robot_hand.playing = playing
        return True
    return act


def _held(control: str) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        controls.app_hold.held = control
        return True
    return act


def _tcode_enabled(controls: GenauControls, value: str) -> bool:
    controls.tcode_enabled.on = value.strip() != "0"
    return True


def _flag_set(name: str, value: bool) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        getattr(controls, name).on = value
        return True
    return act


def _volume_shown(controls: GenauControls, value: str) -> bool:
    said = value.split()
    try:
        level = int(said[0])
        muted = bool(int(said[1])) if len(said) > 1 else False
    except (IndexError, ValueError):
        return False
    controls.set_volume(level, muted)
    return True


CONTROLS: tuple[Control, ...] = (
    Control(
        name="speed",
        needs=("robot_hand",),
        verbs=(
            Verb(SPEED_DOWN, _stepper(-5)),
            Verb(SPEED_UP, _stepper(5)),
            Verb("SPEED", _number_setter(set_speed), takes_a_value=True),
        ),
    ),
    Control(
        name="amplitude",
        needs=("robot_hand",),
        verbs=(
            Verb("AMPLITUDE_DOWN", _amplitude_step(-10)),
            Verb("AMPLITUDE_UP", _amplitude_step(10)),
            Verb("AMP", _number_setter(set_amplitude), takes_a_value=True),
        ),
    ),
    Control(
        name="center",
        needs=("robot_hand",),
        verbs=(
            Verb("CENTER_DOWN", _center_step(-5)),
            Verb("CENTER_UP", _center_step(5)),
            Verb("CENTER", _number_setter(set_center), takes_a_value=True),
        ),
    ),
    Control(
        name="max_intensity",
        needs=("robot_hand",),
        verbs=(Verb(SET_MAX_INTENSITY, _number_setter(set_max_intensity), takes_a_value=True),),
    ),
    Control(
        name="shape",
        needs=("robot_hand",),
        verbs=(
            Verb("CYCLE_SHAPE", _shape_step(1)),
            Verb("CYCLE_SHAPE_PREV", _shape_step(-1)),
        ),
    ),
    Control(
        name="learned",
        needs=("learned_motion_state",),
        verbs=(
            Verb("TOGGLE_LEARNED", _learned_toggled),
            Verb("LEARNED_ON", _learned_on),
            Verb("LEARNED_OFF", _learned_off),
        ),
    ),
    Control(
        name="lock",
        needs=("flick_advance_state",),
        verbs=(
            Verb(TOGGLE_LOCK, _lock_toggled),
            Verb(LOCK_ON, _lock_set(True)),
            Verb(LOCK_OFF, _lock_set(False)),
        ),
    ),
    Control(
        name="flick_seconds",
        needs=("flick_advance_state",),
        verbs=(
            Verb("FLICK_SECONDS_DOWN", _interval_step(-1)),
            Verb("FLICK_SECONDS_UP", _interval_step(1)),
            Verb(FLICK_SECONDS, _interval_named, takes_a_value=True),
        ),
    ),
    Control(
        name="quit",
        needs=("stop_event",),
        verbs=(Verb(QUIT, _quit),),
    ),
    Control(
        name="flick",
        verbs=(Verb(PREV, _step_flick(-1)), Verb(NEXT, _step_flick(1))),
    ),
    Control(
        name="condemn",
        needs=("condemn_flick",),
        verbs=(Verb(TRASH, _condemn),),
    ),
    Control(
        name="play_file",
        needs=("play_file",),
        verbs=(Verb(PLAY_FILE, _play_file, takes_a_value=True),),
    ),
    Control(
        name="flip_ends",
        verbs=(Verb("FLIP_ENDS", _flip_ends),),
    ),
    Control(
        name="browse_order",
        needs=("reorder_flicks",),
        verbs=(Verb("LATEST", _reorder(True)), Verb("SHUFFLE", _reorder(False))),
    ),
    Control(
        name="shapes",
        needs=("keep_shapes",),
        verbs=(Verb("SHAPES", _keep_shapes, takes_a_value=True),),
    ),
    Control(
        name="pause",
        verbs=(Verb(PAUSE, _playing(False)), Verb(RESUME, _playing(True))),
    ),
    Control(
        name="hold",
        verbs=(Verb("PARK", _held(OSR2_PARKED)),
               Verb("RETRACT", _held(OSR2_RETRACTED))),
    ),
    Control(
        name="tcode",
        verbs=(Verb(SET_TCODE_ENABLED, _tcode_enabled, takes_a_value=True),),
    ),
    Control(
        name="hud",
        needs=("hud",),
        verbs=(
            Verb("HUD_ON", _flag_set("hud", True)),
            Verb("HUD_OFF", _flag_set("hud", False)),
        ),
    ),
    Control(
        name="volume",
        needs=("set_volume",),
        verbs=(Verb(SET_VOLUME, _volume_shown, takes_a_value=True),),
    ),
)


VERBS = bind(CONTROLS)


def apply_runtime_command(command, controls: GenauControls) -> None:
    if not look_up(command, VERBS, controls):
        logger.warning("Unhandled command: %s", str(command).strip())
