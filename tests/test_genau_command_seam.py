from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from test_genau_refresh import (
    FakeLoader,
    FakeNotifier,
    FakeRenderer,
    FakeSelection,
    FakeTCodeSender,
)

from funestra.broker_feed import BrokerFeed
from funestra.flag import Flag
from funestra.flick_advance import FlickAdvanceState
from funestra.genau_controls import VERBS, GenauControls
from funestra.genau_refresh import GenauRefreshController
from funestra.genau_refresh_parts import GenauRefreshParts
from funestra.learned_model import LearnedModel
from funestra.learned_motion import LearnedMotionState
from funestra.main_hud import OSR2_PARKED, OSR2_RETRACTED
from funestra.robot_hand import RobotHandState, WaveformShape
from funestra.robot_hand_beat import BeatEngine

NOW_FROZEN_SO_ONLY_A_VERB_MOVES_THE_PHASE = 5.0


class Seam:
    def __init__(self, tmp_path: Path, **start):
        self.paused = Flag(on=bool(start.get("paused", False)))
        self.hud = Flag(on=bool(start.get("hud", False)))
        self.tcode_enabled = Flag(on=bool(start.get("tcode_enabled", True)))
        self.direct = RobotHandState(
            playing=bool(start.get("playing", False)),
            speed=start.get("speed", 50),
            amplitude=start.get("amplitude", 60),
            center=start.get("center", 40),
            intended_center=start.get("center", 40),
            shape=start.get("shape", WaveformShape.TRIANGLE),
        )
        self.learned = LearnedMotionState(model=LearnedModel(),
                                          active=bool(start.get("learned", False)))
        self.advance = FlickAdvanceState(
            locked=bool(start.get("locked", False)),
            interval=start.get("interval", 20),
        )
        self.engine = BeatEngine(phase=0.0, last_tick=NOW_FROZEN_SO_ONLY_A_VERB_MOVES_THE_PHASE)
        self.selection = FakeSelection()
        self.tcode = FakeTCodeSender()
        self.volumes: list[tuple[int, bool]] = []
        self.reorders: list[bool] = []
        self.kept_shapes: list[tuple[bool, bool]] = []
        self.played: list[Path] = []
        self.picked = tmp_path / "flicks" / "Picked Scene.mp4"
        self.picked.parent.mkdir(exist_ok=True)
        self.picked.touch()
        self.stop_event = _Stop()
        self.command_file = tmp_path / "genau_cmd.txt"

        self.controller = GenauRefreshController(GenauRefreshParts(
            controls=GenauControls(
                engine=self.engine,
                paused=self.paused,
                step_flick=self.selection.step,
                condemn_flick=self.selection.condemn_current,
                robot_hand=self.direct,
                learned_motion_state=self.learned,
                flick_advance_state=self.advance,
                stop_event=self.stop_event,
                hud=self.hud,
                tcode_enabled=self.tcode_enabled,
                set_volume=lambda level, muted: self.volumes.append((level, muted)),
                reorder_flicks=self.reorders.append,
                keep_shapes=lambda plays_vr, plays_flat: self.kept_shapes.append(
                    (plays_vr, plays_flat)),
                play_file=self.played.append,
            ),
            broker=BrokerFeed(),
            loader=FakeLoader(),
            notifier=FakeNotifier(),
            renderer=FakeRenderer(path=tmp_path / "flicks" / "example.mp4"),
            selection=self.selection,
            command_file=self.command_file,
            paused_file=tmp_path / "genau_paused.txt",
            beats_per_loop=4.0,
            bpm_smoothing=0.5,
            sync_strength=0.5,
            set_loading_text=lambda _text: None,
            logger=MagicMock(),
            now_source=lambda: NOW_FROZEN_SO_ONLY_A_VERB_MOVES_THE_PHASE,
            read_paused_state=lambda _path, logger=None: self.paused.on,
            tcode_sender=self.tcode,
        ))

    def send(self, line: str) -> None:
        line = line.replace(PICKED_WHOSE_NAME_HAS_CAPITALS_TO_CATCH_A_READER_THAT_LOWER_CASES_THE_PATH, str(self.picked))
        self.command_file.write_text(line + "\n", encoding="utf-8")
        self.controller.refresh()

    def state(self) -> dict:
        return {
            "paused": self.paused.on,
            "playing": self.direct.playing,
            "speed": self.direct.speed,
            "amplitude": self.direct.amplitude,
            "center": self.direct.center,
            "intended_center": self.direct.intended_center,
            "shape": self.direct.shape,
            "phase": round(self.engine.phase, 6),
            "learned": self.learned.active,
            "locked": self.advance.locked,
            "interval": self.advance.interval,
            "steps": tuple(self.selection.step_calls),
            "condemned": self.selection.discard_calls,
            "flipped": self.controller.flip.on,
            "held": self.controller.app_hold.held,
            "reorders": tuple(self.reorders),
            "kept_shapes": tuple(self.kept_shapes),
            "played": tuple(path.name for path in self.played),
            "volumes": tuple(self.volumes),
            "max_intensity": self.direct.max_intensity,
            "hud": self.hud.on,
            "tcode_enabled": self.tcode_enabled.on,
            "stopping": self.stop_event.is_set(),
        }


class _Stop:
    def __init__(self) -> None:
        self._set = False

    def set(self) -> None:
        self._set = True

    def is_set(self) -> bool:
        return self._set


PICKED_WHOSE_NAME_HAS_CAPITALS_TO_CATCH_A_READER_THAT_LOWER_CASES_THE_PATH = "<picked flick>"

SEAM = [
    ("QUIT", {}, {"stopping": True}),
    ("PREV", {}, {"steps": (-1,)}),
    ("NEXT", {}, {"steps": (1,)}),
    ("TRASH", {}, {"condemned": 1}),
    ("FLIP_ENDS", {}, {"flipped": True}),
    ("LATEST", {}, {"reorders": (True,)}),
    ("SHUFFLE", {}, {"reorders": (False,)}),
    ("PAUSE", {"playing": True}, {"paused": True, "playing": False}),
    ("PARK", {}, {"held": OSR2_PARKED}),
    ("RETRACT", {}, {"held": OSR2_RETRACTED}),
    ("RESUME", {"paused": True}, {"paused": False, "playing": True}),
    ("SPEED_DOWN", {}, {"speed": 45}),
    ("SPEED_UP", {}, {"speed": 55}),
    ("AMPLITUDE_DOWN", {}, {"amplitude": 50}),
    ("AMPLITUDE_UP", {}, {"amplitude": 70}),
    ("CENTER_DOWN", {}, {"center": 35, "intended_center": 35}),
    ("CENTER_UP", {}, {"center": 45, "intended_center": 45}),
    ("CYCLE_SHAPE", {}, {"shape": WaveformShape.ROUNDED_SQUARE}),
    ("CYCLE_SHAPE_PREV", {}, {"shape": WaveformShape.SINE}),
    ("TOGGLE_LEARNED", {}, {"learned": True}),
    ("TOGGLE_LEARNED", {"learned": True}, {"learned": False}),
    ("LEARNED_ON", {}, {"learned": True}),
    ("LEARNED_OFF", {"learned": True}, {"learned": False}),
    ("TOGGLE_LOCK", {}, {"locked": True}),
    ("TOGGLE_LOCK", {"locked": True}, {"locked": False}),
    ("LOCK_ON", {}, {"locked": True}),
    ("LOCK_OFF", {"locked": True}, {"locked": False}),
    ("FLICK_SECONDS_DOWN", {}, {"interval": 19}),
    ("FLICK_SECONDS_UP", {}, {"interval": 21}),
    ("HUD_ON", {}, {"hud": True}),
    ("HUD_OFF", {"hud": True}, {"hud": False}),
    (f"PLAY_FILE {PICKED_WHOSE_NAME_HAS_CAPITALS_TO_CATCH_A_READER_THAT_LOWER_CASES_THE_PATH}", {}, {"played": ("Picked Scene.mp4",)}),
    ("AMP 80", {}, {"amplitude": 80}),
    ("CENTER 65", {}, {"center": 65, "intended_center": 65}),
    ("SPEED 90", {}, {"speed": 90}),
    ("FLICK_SECONDS 30", {}, {"interval": 30}),
    ("SET_VOLUME 40 1", {}, {"volumes": ((40, True),)}),
    ("SHAPES flat", {}, {"kept_shapes": ((False, True),)}),
    ("SET_MAX_INTENSITY 5", {}, {"max_intensity": 5, "amplitude": 40, "speed": 33,
                                 "center": 27, "intended_center": 27}),
    ("SET_TCODE_ENABLED 0", {}, {"tcode_enabled": False}),
    ("SET_TCODE_ENABLED 1", {"tcode_enabled": False}, {"tcode_enabled": True}),
]


def _ids(rows):
    return [f"{verb}-from-{sorted(start)}" if start else verb for verb, start, _ in rows]


@pytest.mark.parametrize(("verb", "start", "moves"), SEAM, ids=_ids(SEAM))
def test_a_verb_reaches_its_collaborator_and_moves_nothing_else(verb, start, moves, tmp_path):
    seam = Seam(tmp_path, **start)
    before = seam.state()

    seam.send(verb)

    assert seam.state() == {**before, **moves}


def test_a_tick_with_no_command_moves_nothing(tmp_path):
    seam = Seam(tmp_path)
    before = seam.state()

    seam.controller.refresh()

    assert seam.state() == before


def test_every_verb_genau_answers_is_driven_here(tmp_path):
    driven = {verb.split()[0] for verb, _start, _moves in SEAM}
    assert driven == set(VERBS)
