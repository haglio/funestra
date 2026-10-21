"""Every verb Genau answers, driven through the dispatcher one at a time."""
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from funestra.flag import Flag
from funestra.flick_advance import MAX_INTERVAL_S, MIN_INTERVAL_S, FlickAdvanceState
from funestra.flick_flip import FlickFlip
from funestra.funestra_verbs import SET_MAX_INTENSITY
from funestra.genau_controls import GenauControls, apply_runtime_command
from funestra.learned_model import LearnedModel
from funestra.learned_motion import LearnedMotionState
from funestra.robot_hand import RobotHandState, WaveformShape
from funestra.robot_hand_beat import BeatEngine


@contextmanager
def _nothing_logged():
    """Collect the dispatcher's warnings for the duration of one call."""
    records: list[logging.LogRecord] = []

    class _Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    logger = logging.getLogger("funestra.genau_controls")
    handler = _Collect()
    logger.addHandler(handler)
    previous, logger.propagate = logger.propagate, False
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.propagate = previous


def _answered(command, **collaborators) -> bool:
    """Run one verb; True when the dispatcher answered it.

    The dispatcher returns nothing — an unanswered verb goes on the log, which
    is the only place production can see it — so every case below asks the log
    the same question it used to ask the return value.
    """
    with _nothing_logged() as unanswered:
        apply_runtime_command(command, GenauControls(**collaborators))
    return not unanswered



class TestApplyRuntimeCommand:
    def test_prev_steps_backward(self):
        steps: list[int] = []
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()

        handled = _answered(
            "PREV",
            engine=engine,
            paused=paused,
            step_flick=steps.append,
        )

        assert handled is True
        assert steps == [-1]

    def test_next_steps_forward(self):
        steps: list[int] = []
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()

        handled = _answered(
            "NEXT",
            engine=engine,
            paused=paused,
            step_flick=steps.append,
        )

        assert handled is True
        assert steps == [1]

    def test_a_spelling_nothing_sends_is_not_a_verb(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        ds = RobotHandState(playing=True, speed=50)

        handled = _answered(
            "SLOW_DOWN",
            engine=engine,
            paused=Flag(),
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is False
        assert engine.phase == pytest.approx(0.0)
        assert ds.speed == 50

    def test_pause_sets_paused(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()

        handled = _answered(
            "PAUSE",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
        )

        assert handled is True
        assert paused.on is True

    def test_resume_clears_paused(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag(on=True)

        handled = _answered(
            "RESUME",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
        )

        assert handled is True
        assert paused.on is False

    def test_pause_sets_direct_state_not_playing(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True)

        apply_runtime_command("PAUSE", GenauControls(
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        ))

        assert ds.playing is False

    def test_resume_sets_direct_state_playing(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag(on=True)
        ds = RobotHandState(playing=False)

        apply_runtime_command("RESUME", GenauControls(
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        ))

        assert ds.playing is True

    def test_speed_down_decreases_speed(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True, speed=50)

        handled = _answered(
            "SPEED_DOWN",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is True
        assert ds.speed == 45

    def test_speed_up_increases_speed(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True, speed=50)

        handled = _answered(
            "SPEED_UP",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is True
        assert ds.speed == 55

    def test_amplitude_down_decreases_amplitude(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True, amplitude=80)

        handled = _answered(
            "AMPLITUDE_DOWN",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is True
        assert ds.amplitude == 70

    def test_amplitude_up_increases_amplitude(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True, amplitude=80)

        handled = _answered(
            "AMPLITUDE_UP",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is True
        assert ds.amplitude == 90

    def test_center_down_decreases_center(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True, intended_center=50, amplitude=40)

        handled = _answered(
            "CENTER_DOWN",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is True
        assert ds.intended_center == 45

    def test_center_up_increases_center(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True, intended_center=50, amplitude=40)

        handled = _answered(
            "CENTER_UP",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is True
        assert ds.intended_center == 55

    def test_cycle_shape_advances_shape(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True)
        assert ds.shape == WaveformShape.SINE

        handled = _answered(
            "CYCLE_SHAPE",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is True
        assert ds.shape == WaveformShape.TRIANGLE

    def test_cycle_shape_prev_reverses_shape(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True)
        assert ds.shape == WaveformShape.SINE

        handled = _answered(
            "CYCLE_SHAPE_PREV",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is True
        assert ds.shape == WaveformShape.SAWTOOTH  # SINE wraps backward to SAWTOOTH

    def test_direct_commands_ignored_without_direct_state(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()

        for cmd in ("SPEED_DOWN", "SPEED_UP", "AMPLITUDE_DOWN", "AMPLITUDE_UP",
                     "CENTER_DOWN", "CENTER_UP", "CYCLE_SHAPE"):
            handled = _answered(
                cmd,
                engine=engine,
                paused=paused,
                step_flick=lambda _step: None,
            )
            assert handled is False, f"{cmd} should be ignored without robot_hand"

    def test_an_orchestrator_from_before_cruise_control_went_is_refused_its_verbs(self):
        for cmd in ("TOGGLE_CRUISE", "CRUISE_ON", "CRUISE_OFF"):
            handled = _answered(
                cmd,
                engine=BeatEngine(phase=0.0, last_tick=0.0),
                paused=Flag(),
                step_flick=lambda _step: None,
                robot_hand=RobotHandState(),
            )
            assert handled is False, cmd

    def test_amp_sets_amplitude(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True, amplitude=80)

        handled = _answered(
            "AMP 50",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is True
        assert ds.amplitude == 50

    def test_center_sets_center(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True, intended_center=50, amplitude=40)

        handled = _answered(
            "CENTER 80",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is True
        assert ds.intended_center == 80

    def test_speed_sets_speed(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True, speed=50)

        handled = _answered(
            "SPEED 30",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is True
        assert ds.speed == 30

    def test_the_max_intensity_is_the_hands_to_keep_under(self):
        hand = RobotHandState(playing=True)

        handled = _answered(
            f"{SET_MAX_INTENSITY} 40",
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
            robot_hand=hand,
        )

        assert handled is True
        assert hand.max_intensity == 40

    def test_numeric_commands_ignored_without_direct_state(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()

        for cmd in ("AMP 50", "CENTER 80", "SPEED 30"):
            handled = _answered(
                cmd,
                engine=engine,
                paused=paused,
                step_flick=lambda _step: None,
            )
            assert handled is False, f"{cmd} should be ignored without robot_hand"

    def test_numeric_command_with_non_integer_is_ignored(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        ds = RobotHandState(playing=True)

        handled = _answered(
            "AMP abc",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            robot_hand=ds,
        )

        assert handled is False

    def test_quit_sets_stop_event(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        stop = threading.Event()

        handled = _answered(
            "QUIT",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            stop_event=stop,
        )

        assert handled is True
        assert stop.is_set()

    def test_quit_ignored_without_stop_event(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()

        handled = _answered(
            "QUIT",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
        )

        assert handled is False

    def test_unknown_command_is_ignored(self):
        engine = BeatEngine(phase=0.4, last_tick=0.0)
        paused = Flag()
        steps: list[int] = []

        handled = _answered(
            "UNKNOWN",
            engine=engine,
            paused=paused,
            step_flick=steps.append,
        )

        assert handled is False
        assert engine.phase == 0.4
        assert paused.on is False
        assert steps == []

    def test_hud_on_raises_the_hud(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        hud = Flag()

        handled = _answered(
            "HUD_ON",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            hud=hud,
        )

        assert handled is True
        assert hud.on is True

    def test_hud_off_lowers_the_hud(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()
        hud = Flag(on=True)

        handled = _answered(
            "HUD_OFF",
            engine=engine,
            paused=paused,
            step_flick=lambda _step: None,
            hud=hud,
        )

        assert handled is True
        assert hud.on is False

    def test_hud_commands_ignored_without_a_hud_flag(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        paused = Flag()

        for cmd in ("HUD_ON", "HUD_OFF"):
            handled = _answered(
                cmd,
                engine=engine,
                paused=paused,
                step_flick=lambda _step: None,
            )
            assert handled is False, f"{cmd} should be ignored without a hud flag"



class TestFlickAdvanceCommands:
    def _apply(self, command, aa):
        return _answered(
            command,
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
            flick_advance_state=aa,
        )

    def _apply_volume(self, command, on_volume):
        return _answered(
            command,
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
            set_volume=lambda level, muted: on_volume((level, muted)),
        )

    def test_toggle_flips_the_lock(self):
        aa = FlickAdvanceState(locked=True)
        assert self._apply("TOGGLE_LOCK", aa) is True
        assert aa.locked is False

    def test_on_and_off_are_absolute(self):
        aa = FlickAdvanceState(locked=True)
        assert self._apply("LOCK_OFF", aa) is True
        assert aa.locked is False
        assert self._apply("LOCK_ON", aa) is True
        assert aa.locked is True

    def test_a_number_names_the_seconds_and_leaves_the_lock_alone(self):
        """Naming a pace used to arm the moving as well, which made it both a
        setting and a switch.  The padlock is the only switch."""
        aa = FlickAdvanceState(locked=True)
        assert self._apply("FLICK_SECONDS 30", aa) is True
        assert aa.interval == 30
        assert aa.locked is True

    def test_a_named_pace_is_clamped_to_the_usable_range(self):
        aa = FlickAdvanceState()
        self._apply("FLICK_SECONDS 0", aa)
        assert aa.interval == MIN_INTERVAL_S
        self._apply("FLICK_SECONDS 900", aa)
        assert aa.interval == MAX_INTERVAL_S

    def test_the_arrows_step_the_pace_a_second_at_a_time(self):
        aa = FlickAdvanceState(interval=10)
        assert self._apply("FLICK_SECONDS_UP", aa) is True
        assert aa.interval == 11
        assert self._apply("FLICK_SECONDS_DOWN", aa) is True
        assert aa.interval == 10

    def test_the_published_sound_level_reaches_the_chip(self):
        """Genau draws the primary display's volume but owns neither the level
        nor the audio, so Fun Time tells it what to show.  The mute comes with
        the level: a zero cannot say whether the speaker is off or turned all the
        way down, nor what unmuting would return to."""
        shown = []
        assert self._apply_volume("SET_VOLUME 40 1", shown.append) is True
        assert shown == [(40, True)]
        assert self._apply_volume("SET_VOLUME 70 0", shown.append) is True
        assert shown[-1] == (70, False)

    def test_a_level_with_no_mute_still_moves_the_slider(self):
        """An orchestrator that sends the level alone is answered rather than
        ignored — the chip has a level to show either way."""
        shown = []
        assert self._apply_volume("SET_VOLUME 55", shown.append) is True
        assert shown == [(55, False)]

    def test_an_unreadable_level_is_ignored_rather_than_drawn(self):
        shown = []
        for bad in ("SET_VOLUME", "SET_VOLUME loud", "SET_VOLUME 40 up"):
            assert self._apply_volume(bad, shown.append) is False
        assert shown == []

    def test_the_retired_advance_verbs_are_not_answered_to(self):
        """The interval is named for the number now, not for the auto-advance
        that spends it.  The old spelling is gone rather than kept alongside:
        two verbs for one setting is how the two drift into meaning different
        things."""
        aa = FlickAdvanceState(interval=10)
        for cmd in ("ADVANCE_UP", "ADVANCE_DOWN", "ADVANCE 30"):
            assert self._apply(cmd, aa) is False, f"{cmd} should no longer be answered"
        assert aa.interval == 10

    def test_ignored_without_flick_advance_state(self):
        engine = BeatEngine(phase=0.0, last_tick=0.0)
        for cmd in (
            "TOGGLE_LOCK", "LOCK_ON", "LOCK_OFF",
            "FLICK_SECONDS_UP", "FLICK_SECONDS_DOWN", "FLICK_SECONDS 30",
        ):
            handled = _answered(
                cmd,
                engine=engine,
                paused=Flag(),
                step_flick=lambda _step: None,
            )
            assert handled is False, f"{cmd} should be ignored without flick_advance_state"


class TestWeirdCommand:
    def test_weird_condemns_the_flick_on_screen(self):
        calls: list[int] = []

        handled = _answered(
            "WEIRD",
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
            condemn_flick=lambda: calls.append(1),
        )

        assert handled is True
        assert calls == [1]

    def test_weird_ignored_without_a_way_to_condemn(self):
        handled = _answered(
            "WEIRD",
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
        )

        assert handled is False


class TestFlipEndsCommand:
    def test_flip_ends_turns_the_flick_on_screen_over(self, tmp_path):
        flick = tmp_path / "flicks" / "scene one.mp4"
        flick.parent.mkdir()
        flick.touch()
        flip = FlickFlip()
        flip.follow(flick)

        handled = _answered(
            "FLIP_ENDS",
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
            flick_flip=flip,
        )

        assert (handled, flip.on) == (True, True)


class TestPlayFileCommand:
    def _asked(self, command, **collaborators) -> tuple[bool, list[Path]]:
        played: list[Path] = []
        handled = _answered(
            command,
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
            play_file=played.append,
            **collaborators,
        )
        return handled, played

    def test_it_plays_the_flick_the_line_names(self, tmp_path):
        flick = tmp_path / "Scene One.mp4"
        flick.touch()

        assert self._asked(f"PLAY_FILE {flick}") == (True, [flick])

    def test_a_funscript_after_the_flick_is_left_to_the_funestras_that_drive_by_one(self, tmp_path):
        flick = tmp_path / "scene one.mp4"
        flick.touch()

        assert self._asked(f"PLAY_FILE {flick}\t{tmp_path / 'scene one.funscript'}") == (True, [flick])

    def test_a_flick_that_is_not_on_disk_is_refused(self, tmp_path):
        assert self._asked(f"PLAY_FILE {tmp_path / 'gone.mp4'}") == (False, [])

    def test_a_genau_that_cannot_play_a_named_flick_does_not_answer_it(self, tmp_path):
        flick = tmp_path / "scene one.mp4"
        flick.touch()

        handled = _answered(
            f"PLAY_FILE {flick}",
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
        )

        assert handled is False


class TestBrowseOrderCommands:
    """The two orders every Funestra in the room browses in.  Genau owns its own
    sequence rather than being handed a playlist file, so the order arrives as a
    verb and the answer is a rescan of the flicks folder."""

    def test_latest_asks_for_newest_first(self):
        asked: list[bool] = []

        handled = _answered(
            "LATEST",
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
            reorder_flicks=asked.append,
        )

        assert handled is True
        assert asked == [True]

    def test_shuffle_asks_for_a_reshuffle(self):
        asked: list[bool] = []

        handled = _answered(
            "SHUFFLE",
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
            reorder_flicks=asked.append,
        )

        assert handled is True
        assert asked == [False]

    def test_ignored_without_a_way_to_reorder(self):
        for cmd in ("LATEST", "SHUFFLE"):
            handled = _answered(
                cmd,
                engine=BeatEngine(phase=0.0, last_tick=0.0),
                paused=Flag(),
                step_flick=lambda _step: None,
            )

            assert handled is False, f"{cmd} should be ignored without reorder_flicks"


class TestShapeCommands:
    """Which of the two shapes a flick can be mastered in Genau browses: the
    headset's VR flicks, the flat ones, or both.  A verb for the same reason the
    browse order is one: Genau owns its sequence."""

    def _asked(self, command) -> tuple[bool, list[tuple[bool, bool]]]:
        asked: list[tuple[bool, bool]] = []
        handled = _answered(
            command,
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
            keep_shapes=lambda plays_vr, plays_flat: asked.append((plays_vr, plays_flat)),
        )
        return handled, asked

    def test_it_names_the_shapes_to_keep(self):
        assert self._asked("SHAPES vr") == (True, [(True, False)])

    def test_both_is_both_named(self):
        assert self._asked("SHAPES vr flat") == (True, [(True, True)])

    def test_a_word_that_is_no_shape_is_refused_rather_than_read_as_none(self):
        assert self._asked("SHAPES round") == (False, [])

    def test_a_genau_with_one_shape_of_flick_does_not_answer_it(self):
        handled = _answered(
            "SHAPES vr",
            engine=BeatEngine(phase=0.0, last_tick=0.0),
            paused=Flag(),
            step_flick=lambda _step: None,
        )

        assert handled is False


class TestAnUnhandledCommand:
    """The dispatcher says so itself, because it is the only thing that knows.

    Genau's channel takes what Fun Time posts and what its own voice grammar
    hears; a verb from a build that has moved on, or one whose collaborator
    this app did not wire, used to be dropped without a word.
    """

    def _run(self, command, caplog, **collaborators):
        with caplog.at_level("WARNING", logger="funestra.genau_controls"):
            apply_runtime_command(command, GenauControls(
                engine=BeatEngine(phase=0.0, last_tick=0.0),
                paused=Flag(),
                step_flick=lambda _step: None,
                **collaborators,
            ))

    def test_an_unknown_verb_is_named_on_the_log(self, caplog):
        self._run("CYCLE_PROJECTION", caplog)

        assert "CYCLE_PROJECTION" in caplog.text

    def test_a_verb_this_build_did_not_wire_is_named_too(self, caplog):
        """SPEED_UP with no motion state: as unanswerable as a typo."""
        self._run("SPEED_UP", caplog)

        assert "SPEED_UP" in caplog.text

    def test_a_verb_it_acts_on_says_nothing(self, caplog):
        self._run("NEXT", caplog)

        assert caplog.records == []


class TestLearnedMotionVerbs:
    """The learned motion answers a flip and an explicit on and off."""

    def _learned(self, active: bool = False) -> LearnedMotionState:
        return LearnedMotionState(model=LearnedModel(), active=active)

    def test_toggle_learned_arms_it(self):
        learned = self._learned()

        handled = _answered("TOGGLE_LEARNED", engine=BeatEngine(phase=0.0, last_tick=0.0),
                            paused=Flag(), step_flick=lambda _step: None,
                            learned_motion_state=learned)

        assert handled is True
        assert learned.active is True

    def test_learned_on_and_off_say_which_way(self):
        learned = self._learned(active=True)
        collaborators = dict(engine=BeatEngine(phase=0.0, last_tick=0.0), paused=Flag(),
                             step_flick=lambda _step: None, learned_motion_state=learned)

        assert _answered("LEARNED_OFF", **collaborators) is True
        assert learned.active is False
        assert _answered("LEARNED_ON", **collaborators) is True
        assert learned.active is True

    def test_learned_verbs_are_refused_without_the_learned_state(self):
        assert _answered("TOGGLE_LEARNED", engine=BeatEngine(phase=0.0, last_tick=0.0),
                         paused=Flag(), step_flick=lambda _step: None) is False
