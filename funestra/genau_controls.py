"""What Genau's controls can reach, and every verb that moves one.

Genau -- on the Main Funestra, whether on the desktop or in the headset --
is spoken to from two places: a verb in ``genau_cmd.txt`` and a press on the
console.  Both of them have to be able to move the same
handful of things: the hand's own state, the cruise stack, the learned motion,
the flick advance, the two flags an orchestrator flips, the flick sequence.

Passing those one at a time is what made adding a control a four-to-six file
edit: a keyword parameter on the dispatcher, another on the refresh controller,
an attribute to store it and a line to hand it on.  They travel together here
instead, built once where the app is wired and handed whole.

Optional means *this build did not wire it* -- a Genau launched without a cruise
stack, a test that only cares about the flick sequence.  A verb whose collaborator
is absent is refused and logged rather than half-acted-on, which is the behavior
:func:`apply_runtime_command` documents.
"""
from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .console import HELD_HEIGHT, OSR2_PARKED, OSR2_RETRACTED
from .control_registry import Control, Verb, bind, look_up
from .cruise_control import (
    CruiseControlState,
    disable_cruise_control,
    enable_cruise_control,
)
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
)
from .learned_motion import (
    LearnedMotionState,
    disable_learned_motion,
    enable_learned_motion,
)
from .playlist import item_from_line
from .renamed import answers_to_old_names
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

__all__ = [
    "VERBS",
    "GenauControls",
]

logger = logging.getLogger(__name__)


@answers_to_old_names({
    "clip_advance_state": "flick_advance_state",
    "clip_flip": "flick_flip",
    "condemn_clip": "condemn_flick",
    "reorder_clips": "reorder_flicks",
    "step_clip": "step_flick",
})
@dataclass
class GenauControls:
    """Everything one command or console press may move."""

    engine: BeatEngine
    paused: Flag
    step_flick: Callable[[int], None]
    condemn_flick: Callable[[], None] | None = None
    robot_hand: RobotHandState | None = None
    cruise_control_state: CruiseControlState | None = None
    learned_motion_state: LearnedMotionState | None = None
    set_motion_phase: Callable[[float], None] | None = None
    flick_advance_state: FlickAdvanceState | None = None
    stop_event: threading.Event | None = None
    hud: Flag | None = None
    tcode_enabled: Flag = field(default_factory=lambda: Flag(on=True))
    set_volume: Callable[[int, bool], None] | None = None
    reorder_flicks: Callable[[bool], None] | None = None
    keep_shapes: Callable[[bool, bool], None] | None = None
    play_file: Callable[[Path], None] | None = None
    flick_flip: FlickFlip = field(default_factory=FlickFlip)
    room_hold: RoomHold = field(default_factory=RoomHold)


# The acts below all take these controls and the rest of the line, and say
# whether they could.
Act = Callable[[GenauControls, str], bool]

# The verbs that name a value or a state outright, which a Genau taking over
# another's room says to itself to take up what the room was doing.
HAND_SPEED = "SPEED"
HAND_AMP = "AMP"
HAND_CENTER = "CENTER"
CRUISE_ON = "CRUISE_ON"
CRUISE_OFF = "CRUISE_OFF"
LEARNED_ON = "LEARNED_ON"
LEARNED_OFF = "LEARNED_OFF"
FLICK_SECONDS = "FLICK_SECONDS"
PAUSE = "PAUSE"
RESUME = "RESUME"

# Fun Time's spelling for the quarter-turn of the motion's phase.  Named because
# two spellings of it once shipped side by side, which is the drift a literal per
# branch invites.
QUARTER_CYCLE_OFFSET_COMMAND = "OFFSET_QUARTER_CYCLE"


def _stepper(step: int) -> Act:
    """A verb that nudges the hand's speed by a fixed amount."""
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
    """A verb that names the value outright: ``AMP 50``, ``SPEED 90``.

    A value that is not a whole number is refused rather than rounded or
    defaulted -- what arrived was not the command it looked like.
    """
    def act(controls: GenauControls, value: str) -> bool:
        try:
            number = int(value)
        except ValueError:
            return False
        setter(controls.robot_hand, number)
        return True
    return act


def _handed_back(controls: GenauControls, phase) -> None:
    """Cruise control letting go says where the single wave should pick up — at
    the phase of the wave that had most of the travel, which is the one the
    device was mostly following.  Nowhere to put it (a build with no driver) and
    the motion simply resumes on its own free-running phase."""
    if phase is not None and controls.set_motion_phase is not None:
        controls.set_motion_phase(phase)


def _cruise_toggled(controls: GenauControls, _value: str) -> bool:
    if controls.cruise_control_state.active:
        return _cruise_off(controls, _value)
    return _cruise_on(controls, _value)


def _cruise_on(controls: GenauControls, _value: str) -> bool:
    """Hands off to the dice -- and away from the learned motion, which cannot
    hold the hand at the same time."""
    if controls.learned_motion_state is not None:
        disable_learned_motion(controls.learned_motion_state)
    enable_cruise_control(controls.cruise_control_state)
    return True


def _cruise_off(controls: GenauControls, _value: str) -> bool:
    _handed_back(controls, disable_cruise_control(controls.cruise_control_state))
    return True


def _learned_toggled(controls: GenauControls, _value: str) -> bool:
    if controls.learned_motion_state.active:
        return _learned_off(controls, _value)
    return _learned_on(controls, _value)


def _learned_on(controls: GenauControls, _value: str) -> bool:
    """Hands off to the scripts -- and away from cruise control, which lets go
    of the motion the way it always does."""
    if controls.cruise_control_state is not None:
        _cruise_off(controls, _value)
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
    """"flick seconds thirty" names the seconds a flick holds the screen.  It says
    nothing about the lock: a held flick stays held, and this is the pace it will
    move at once it is let go."""
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


def _offset_quarter_cycle(controls: GenauControls, _value: str) -> bool:
    controls.engine.phase = (controls.engine.phase + 0.25) % 1.0
    return True


def _playing(playing: bool) -> Act:
    """PAUSE and RESUME move both halves of one fact.

    The flag is what an orchestrator's paused file feeds and what the tick reads;
    the hand's own flag is what the motion follows.  A build with no hand still
    answers -- the room is paused either way.
    """
    def act(controls: GenauControls, _value: str) -> bool:
        controls.paused.on = not playing
        if controls.robot_hand is not None:
            controls.robot_hand.playing = playing
        return True
    return act


def _held_at(height: float) -> Act:
    def act(controls: GenauControls, _value: str) -> bool:
        controls.room_hold.height = height
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
    """``SET_VOLUME <level> [muted]`` — the sound level the orchestrator is
    publishing.

    Genau neither owns the level (the orchestrator does, for the whole primary
    display) nor plays the audio: a companion process carries the flick music.
    What arrives here is only what the chip Genau draws should show, which is why
    the mute rides alongside the level — a level of zero cannot say whether the
    speaker is off or turned all the way down, nor what unmuting returns to.

    The mute is optional so an orchestrator that sends the level alone still
    moves the slider rather than being ignored outright.
    """
    said = value.split()
    try:
        level = int(said[0])
        muted = bool(int(said[1])) if len(said) > 1 else False
    except (IndexError, ValueError):
        return False
    controls.set_volume(level, muted)
    return True


# One entry per thing a person can move.  Add a control by adding a record here;
# nothing else in the app needs to learn its name.
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
        name="cruise",
        needs=("cruise_control_state",),
        verbs=(
            Verb("TOGGLE_CRUISE", _cruise_toggled),
            Verb("CRUISE_ON", _cruise_on),
            Verb("CRUISE_OFF", _cruise_off),
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
    # The lock, under the same three verbs Kino answers to, because
    # it is the same thing on both: hold what is on screen, or let it move on.
    Control(
        name="lock",
        needs=("flick_advance_state",),
        verbs=(
            Verb(TOGGLE_LOCK, _lock_toggled),
            Verb(LOCK_ON, _lock_set(True)),
            Verb(LOCK_OFF, _lock_set(False)),
        ),
    ),
    # How long a flick holds the screen, a second at a time.  Named for the number
    # rather than for the auto-advance that spends it, so the verb reads as what
    # the orchestrator's reference shows and what its speaker says aloud.
    Control(
        name="flick_seconds",
        needs=("flick_advance_state",),
        verbs=(
            Verb("FLICK_SECONDS_DOWN", _interval_step(-1)),
            Verb("FLICK_SECONDS_UP", _interval_step(1)),
            Verb(FLICK_SECONDS, _interval_named, takes_a_value=True),
            # The spellings from before the flicks were renamed, which an
            # orchestrator from before the rename still sends.
            Verb("CLIP_SECONDS_DOWN", _interval_step(-1)),
            Verb("CLIP_SECONDS_UP", _interval_step(1)),
            Verb("CLIP_SECONDS", _interval_named, takes_a_value=True),
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
        verbs=(Verb("WEIRD", _condemn),),
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
    # The two browse orders every Funestra in the room has, said to Genau, the one
    # with no playlist file to hand it: Genau owns its own sequence, so the order
    # is a verb rather than a rewritten list, and answering it rescans the flicks
    # folder — which is most of what Latest is for.
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
        name="quarter_cycle",
        verbs=(Verb(QUARTER_CYCLE_OFFSET_COMMAND, _offset_quarter_cycle),),
    ),
    Control(
        name="pause",
        verbs=(Verb(PAUSE, _playing(False)), Verb(RESUME, _playing(True))),
    ),
    Control(
        name="hold",
        verbs=(Verb("PARK", _held_at(HELD_HEIGHT[OSR2_PARKED])),
               Verb("RETRACT", _held_at(HELD_HEIGHT[OSR2_RETRACTED]))),
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
    """Act on one command, or say on the log that we cannot.

    The dispatcher reports an unanswered verb itself rather than returning a
    flag for a caller to check: it is the only thing that knows, and there is
    one of it rather than one per call site. Two kinds land here — a verb no
    branch matches, and a verb whose collaborator this build did not wire —
    and both mean the same thing to whoever sent it, which is that nothing
    happened.
    """
    if not look_up(command, VERBS, controls):
        logger.warning("Unhandled command: %s", str(command).strip())
