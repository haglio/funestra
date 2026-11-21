from __future__ import annotations

import ast
import random
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from app_support.osr2_hold import HOLD_MOVE_MS, PARK, RETRACT
from funestra_fakes import holds_of_the_lock
from genau_fakes import FakeLoader, FakeNotifier, FakeRenderer, FakeSelection, FakeTCodeSender

from funestra.broker_feed import BrokerFeed
from funestra.file_channel import append_command
from funestra.flag import Flag
from funestra.flick_advance import FlickAdvanceState
from funestra.flick_flip import FlickFlip
from funestra.flicks_on_screen import FlicksOnScreen
from funestra.genau_controls import GenauControls
from funestra.genau_files import GenauFiles
from funestra.genau_refresh import SEND_THREAD, GenauRefreshController
from funestra.genau_status import GENAU_STATUS_FILENAME
from funestra.learned_model import LearnedModel, Phrase, classify
from funestra.learned_motion import LearnedMotionState
from funestra.robot_hand import RobotHandState, position_fraction
from funestra.robot_hand_beat import BeatEngine, BeatTuning
from funestra.robot_hand_driver import RobotHandTCodeDriver
from funestra.tcode import HANDOFF_MS

_COMMAND_DIR: Path | None = None


@pytest.fixture(autouse=True)
def _commands_in_the_tests_own_scratch(tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), "_COMMAND_DIR", tmp_path)


@dataclass(frozen=True)
class _OnScreen:
    loading: bool = False
    path: str | None = "demo.mp4"
    entry: object = None
    current_frame_index: int | None = None
    pending_flick_name: str | None = None


@dataclass(frozen=True)
class _Commands:
    command: str | None = None
    commands: list[str] | None = None
    paused_state: bool = False


@dataclass(frozen=True)
class _HandsOn:
    robot_hand: RobotHandState | None = None
    learned: LearnedMotionState | None = None
    flick_advance: FlickAdvanceState | None = None
    hud: Flag | None = None
    flick_flip: FlickFlip | None = None


@dataclass(frozen=True)
class _Files:
    command_file: Path | None = None
    status_file: Path | None = None
    drive_file: Path | None = None


def _taken(kind, choices):
    return kind(**{name: choices.pop(name) for name in kind.__dataclass_fields__
                   if name in choices})


def _build_controller(*, broker: BrokerFeed | None = None,
                      tcode_sender: FakeTCodeSender | None = None, now_source=None,
                      start_thread=None, **choices):
    screen = _taken(_OnScreen, choices)
    said = _taken(_Commands, choices)
    hands = _taken(_HandsOn, choices)
    files = _taken(_Files, choices)
    assert not choices, choices
    loading_texts: list[str | None] = []
    command_file = files.command_file or _COMMAND_DIR / "command.txt"
    for line in said.commands if said.commands is not None else filter(None, [said.command]):
        append_command(command_file, line)
    paused_file = _COMMAND_DIR / "paused.txt"
    paused_file.write_text("1" if said.paused_state else "0", encoding="utf-8")

    loader = FakeLoader(loading=screen.loading)
    notifier = FakeNotifier()
    renderer = FakeRenderer(
        path=Path(screen.path) if screen.path is not None else None,
        entry=screen.entry,
        current_frame_index=screen.current_frame_index,
    )
    selection = FakeSelection(pending_flick_name=screen.pending_flick_name)
    engine = BeatEngine(phase=0.25, last_tick=5.0)
    logger = MagicMock()
    controls = GenauControls(
        engine=engine,
        paused=Flag(),
        step_flick=selection.step,
        condemn_flick=selection.condemn_current,
        robot_hand=hands.robot_hand if hands.robot_hand is not None else RobotHandState(),
        learned_motion_state=hands.learned,
        flick_advance_state=hands.flick_advance,
        hud=hands.hud,
        set_volume=lambda _level, _muted: None,
        flick_flip=hands.flick_flip if hands.flick_flip is not None else FlickFlip(),
    )
    controller = GenauRefreshController(
        controls,
        FlicksOnScreen(loader, renderer, selection, notifier, loading_texts.append),
        broker=broker or BrokerFeed(),
        files=GenauFiles(command_file, paused_file, files.status_file, files.drive_file),
        tuning=BeatTuning(beats_per_loop=4.0, bpm_smoothing=0.5, sync_strength=0.5),
        tcode_sender=tcode_sender,
        logger=logger,
        now_source=now_source or (lambda: 5.0),
        start_thread=start_thread,
    )
    return {
        "controller": controller,
        "say": lambda line: append_command(command_file, line),
        "loader": loader,
        "notifier": notifier,
        "renderer": renderer,
        "selection": selection,
        "engine": engine,
        "logger": logger,
        "loading_texts": loading_texts,
    }


def test_a_tick_reads_the_broker_s_feed_in_one_hold_of_its_lock_never_a_field_at_a_time():
    state = BrokerFeed(auto_active=True, raw_bpm=120.0)
    held = holds_of_the_lock(state)
    built = _build_controller(broker=state, entry={"frames": [object() for _ in range(8)]})

    built["controller"].refresh()

    assert held == ["taken", "given back"]


def test_refresh_displays_active_frame():
    state = BrokerFeed(auto_active=True, raw_bpm=120.0)
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(broker=state, entry=entry)

    built["controller"].refresh()

    assert built["loader"].loaded_adopt_calls == 1
    assert built["loader"].prefetch_adopt_calls == 1
    assert built["renderer"].display_calls == [5]
    assert built["selection"].prefetch_calls == 1


def test_under_the_broker_the_line_is_the_device_s_own_swing():
    state = BrokerFeed(auto_active=True, raw_bpm=120.0)
    entry = {"frames": [object() for _ in range(8)]}
    clock = [5.0]
    built = _build_controller(broker=state, entry=entry,
                              now_source=lambda: clock[0])

    built["controller"].refresh()
    first = built["controller"].visualizer.drive
    clock[0] += 0.5
    built["controller"].refresh()
    second = built["controller"].visualizer.drive

    assert len(first.waveform) == 80
    assert (second.waveform, second.slide) != (first.waveform, first.slide)


def test_refresh_skips_display_when_no_frames_are_ready():
    built = _build_controller(loading=True, entry=None)

    built["controller"].refresh()

    assert built["renderer"].display_calls == []
    assert built["selection"].prefetch_calls == 1


def test_refresh_applies_runtime_commands_through_selection_step():
    built = _build_controller(command="NEXT", entry=None)

    built["controller"].refresh()

    assert built["selection"].step_calls == [1]


def test_refresh_reads_paused_state_file_each_tick():
    entry = {"frames": [object() for _ in range(4)]}
    built = _build_controller(
        broker=BrokerFeed(auto_active=True), entry=entry, paused_state=True)

    built["controller"].refresh()

    assert built["controller"].controls.paused.on is True


def test_refresh_reports_exceptions():
    built = _build_controller(entry=None)
    built["renderer"].current_flick_entry = MagicMock(side_effect=RuntimeError("kaboom"))

    built["controller"].refresh()

    said = built["logger"].error.call_args
    assert said[0][0] % said[0][1:] == "refresh failed"
    assert isinstance(said[1]["exc_info"], RuntimeError)


def test_a_fault_that_repeats_every_frame_is_said_once():
    built = _build_controller(entry=None)
    built["renderer"].current_flick_entry = MagicMock(side_effect=RuntimeError("kaboom"))

    for _ in range(100):
        built["controller"].refresh()

    assert built["logger"].error.call_count == 1
    assert built["logger"].debug.call_count == 99


def test_refresh_sets_loading_text_when_pending_flick():
    entry = {"frames": [object() for _ in range(4)]}
    built = _build_controller(entry=entry, pending_flick_name="next.mp4")

    built["controller"].refresh()

    assert built["loading_texts"][-1] == "Loading next.mp4"


def test_refresh_clears_loading_text_when_no_pending_flick():
    entry = {"frames": [object() for _ in range(4)]}
    built = _build_controller(entry=entry, pending_flick_name=None)

    built["controller"].refresh()

    assert built["loading_texts"][-1] is None


def test_refresh_calls_adopt_pending_flick():
    entry = {"frames": [object() for _ in range(4)]}
    built = _build_controller(entry=entry)

    built["controller"].refresh()

    assert built["selection"].adopt_calls == 1


def test_a_hand_whose_output_is_switched_off_plays_on_unheard_since_the_hud_draws_that_motion_in_gray():
    dc = RobotHandState(playing=True, bpm=120.0)
    sink = MagicMock()
    clock = [5.0]
    built = _build_controller(entry={"frames": [object() for _ in range(8)]}, robot_hand=dc,
                              tcode_sender=RobotHandTCodeDriver(sink, robot_hand=dc),
                              command="SET_TCODE_ENABLED 0", now_source=lambda: clock[0])
    built["controller"].refresh()
    first = built["controller"].visualizer.drive

    clock[0] = 5.5
    built["controller"].refresh()
    then = built["controller"].visualizer.drive

    assert (sink.send.call_count, first.position != then.position) == (0, True)


def test_direct_mode_playing_advances_phase():
    dc = RobotHandState(playing=True, bpm=120.0)
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc)
    built["controller"].now_source = lambda: 5.05

    built["controller"].refresh()

    assert built["engine"].phase != 0.25


def test_direct_mode_not_playing_freezes_phase():
    dc = RobotHandState(playing=False, bpm=120.0)
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc)

    built["controller"].refresh()

    assert built["engine"].phase == 0.25


def test_direct_mode_calls_tcode_sender():
    dc = RobotHandState(playing=True, bpm=120.0)
    tcode = FakeTCodeSender()
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc, tcode_sender=tcode)

    built["controller"].refresh()

    assert len(tcode.sends) == 1
    _phase, now = tcode.sends[0]
    assert now == 5.0


def test_a_hand_that_plays_and_is_heard_wants_the_osr2():
    tcode = FakeTCodeSender()
    built = _build_controller(entry={"frames": [object() for _ in range(8)]},
                              robot_hand=RobotHandState(playing=True, bpm=120.0), tcode_sender=tcode)

    built["controller"].refresh()

    assert tcode.wanted is True


def test_a_paused_hand_lets_the_osr2_go():
    tcode = FakeTCodeSender()
    built = _build_controller(entry={"frames": [object() for _ in range(8)]},
                              robot_hand=RobotHandState(playing=False, bpm=120.0), tcode_sender=tcode)

    built["controller"].refresh()

    assert tcode.wanted is False


def test_a_hand_whose_output_is_switched_off_lets_the_osr2_go():
    tcode = FakeTCodeSender()
    built = _build_controller(entry={"frames": [object() for _ in range(8)]},
                              robot_hand=RobotHandState(playing=True, bpm=120.0), tcode_sender=tcode,
                              command="SET_TCODE_ENABLED 0")

    built["controller"].refresh()

    assert tcode.wanted is False


def test_the_osr2_running_itself_leaves_the_hand_off_it():
    tcode = FakeTCodeSender()
    built = _build_controller(broker=BrokerFeed(auto_active=True, raw_bpm=120.0),
                              entry={"frames": [object() for _ in range(8)]},
                              robot_hand=RobotHandState(playing=True, bpm=120.0), tcode_sender=tcode)

    built["controller"].refresh()

    assert tcode.wanted is False


def test_direct_mode_paused_does_not_send_tcode():
    dc = RobotHandState(playing=False, bpm=120.0)
    tcode = FakeTCodeSender()
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc, tcode_sender=tcode)

    built["controller"].refresh()

    assert tcode.sends == []


def test_direct_mode_publishes_the_drive_visualizer():
    dc = RobotHandState(playing=True, bpm=120.0, amplitude=70, intended_center=60)
    tcode = FakeTCodeSender()
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc, tcode_sender=tcode)

    built["controller"].refresh()

    hud = built["controller"].visualizer.drive
    assert (hud.amplitude, hud.center, hud.speed) == (70, 60, 50)
    assert hud.shape == "sine"
    assert len(hud.waveform) == 80


def test_pause_command_stops_direct_mode_playback():
    dc = RobotHandState(playing=True, bpm=120.0)
    tcode = FakeTCodeSender()
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc, tcode_sender=tcode, command="PAUSE")

    built["controller"].refresh()

    assert dc.playing is False


def test_losing_the_device_walks_it_down_and_rests_the_motion():
    dc = RobotHandState(playing=True, bpm=120.0)
    tcode = FakeTCodeSender()
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc, tcode_sender=tcode, command="PAUSE")

    built["controller"].refresh()

    assert tcode.rests == 1


def test_staying_paused_hands_over_only_once():
    dc = RobotHandState(playing=True, bpm=120.0)
    tcode = FakeTCodeSender()
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc, tcode_sender=tcode, command="PAUSE")

    built["controller"].refresh()
    built["controller"].refresh()

    assert tcode.rests == 1


def test_resume_command_starts_direct_mode_playback():
    dc = RobotHandState(playing=False, bpm=120.0)
    tcode = FakeTCodeSender()
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc, tcode_sender=tcode, command="RESUME")

    built["controller"].refresh()

    assert dc.playing is True


def test_speed_up_command_via_refresh():
    dc = RobotHandState(playing=True, bpm=120.0, speed=50)
    tcode = FakeTCodeSender()
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc, tcode_sender=tcode, command="SPEED_UP")

    built["controller"].refresh()

    assert dc.speed == 55


def test_toggle_lock_command_via_refresh():
    dc = RobotHandState(playing=True, bpm=120.0)
    aa = FlickAdvanceState(locked=True)
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(
        entry=entry, robot_hand=dc, tcode_sender=FakeTCodeSender(),
        flick_advance=aa, command="TOGGLE_LOCK",
    )

    built["controller"].refresh()

    assert aa.locked is False


def _run_flick_advance(*, playing: bool, seconds: float = 15.0, locked: bool = False):
    dc = RobotHandState(playing=playing, bpm=120.0)
    aa = FlickAdvanceState(locked=locked, interval=10)
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(
        entry=entry, robot_hand=dc, tcode_sender=FakeTCodeSender(), flick_advance=aa
    )
    tick = 0.0
    for _ in range(int(seconds / 0.1)):
        tick += 0.1
        built["controller"].now_source = lambda t=tick: 5.0 + t
        built["controller"].refresh()
    return built["selection"].step_calls


def test_an_unlocked_genau_advances_its_flick_during_refresh():
    steps = _run_flick_advance(playing=True)
    assert len(steps) >= 1
    assert all(c == 1 for c in steps)


def test_a_locked_genau_stays_on_its_flick():
    assert _run_flick_advance(playing=True, seconds=60.0, locked=True) == []


def test_the_flick_is_held_while_the_room_is_paused():
    assert _run_flick_advance(playing=False, seconds=60.0) == []


def test_broker_auto_uses_broker_bpm_for_phase():
    dc = RobotHandState(playing=False, bpm=60.0)
    state = BrokerFeed(auto_active=True, raw_bpm=120.0)
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(broker=state, entry=entry, robot_hand=dc)
    built["controller"].now_source = lambda: 5.05

    built["controller"].refresh()

    assert abs(built["engine"].phase - 0.275) < 0.001


def test_broker_auto_does_not_send_tcode():
    dc = RobotHandState(playing=True, bpm=120.0)
    state = BrokerFeed(auto_active=True, raw_bpm=120.0)
    tcode = FakeTCodeSender()
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(broker=state, entry=entry, robot_hand=dc, tcode_sender=tcode)

    built["controller"].refresh()

    assert tcode.sends == []


def test_broker_auto_uses_linear_display_phase():
    dc = RobotHandState(playing=False, bpm=60.0)
    state = BrokerFeed(auto_active=True, raw_bpm=120.0)
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(broker=state, entry=entry, robot_hand=dc)

    built["controller"].refresh()

    assert built["renderer"].display_calls == [5]


def test_broker_auto_sync_pulses_never_move_the_cursor_backward():
    dc = RobotHandState(playing=False, bpm=60.0)
    state = BrokerFeed(auto_active=True, raw_bpm=120.0, sync_pulse_id=1)
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(broker=state, entry=entry, robot_hand=dc)

    built["controller"].refresh()

    assert built["engine"].phase >= 0.25


def test_broker_auto_cleared_resumes_direct_control():
    dc = RobotHandState(playing=True, bpm=120.0)
    state = BrokerFeed(auto_active=False, raw_bpm=0.0)
    tcode = FakeTCodeSender()
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(broker=state, entry=entry, robot_hand=dc, tcode_sender=tcode)

    built["controller"].refresh()

    assert len(tcode.sends) == 1
    assert built["controller"].visualizer.drive is not None


def test_multiline_commands_all_applied():
    dc = RobotHandState(playing=False, bpm=120.0)
    tcode = FakeTCodeSender()
    entry = {"frames": [object() for _ in range(8)]}
    hud = Flag()
    built = _build_controller(
        entry=entry, robot_hand=dc, tcode_sender=tcode,
        commands=["RESUME", "HUD_ON"],
        hud=hud,
    )

    built["controller"].refresh()

    assert dc.playing is True
    assert hud.on is True


@pytest.mark.parametrize(("hud_on", "heard"), [(True, False), (False, True)])
def test_the_flick_is_heard_only_while_it_has_the_main_screen(hud_on, heard):
    built = _build_controller(
        entry={"frames": [object() for _ in range(8)]}, hud=Flag(on=hud_on))

    built["controller"].refresh()

    assert built["notifier"].visible_updates[-1] is heard


def test_no_flick_is_adopted_drawn_or_fetched_while_a_video_has_the_main_screen():
    built = _build_controller(
        entry={"frames": [object() for _ in range(8)]}, hud=Flag(on=True), pending_flick_name="next")

    built["controller"].refresh()

    assert (built["loader"].loaded_adopt_calls, built["loader"].prefetch_adopt_calls,
            built["renderer"].display_calls, built["selection"].prefetch_calls,
            built["loading_texts"]) == (0, 0, [], 0, [])


def test_the_flick_waits_where_it_was_while_a_video_has_the_main_screen_and_takes_up_its_time_from_there():
    hud = Flag(on=False)
    built = _build_controller(
        entry={"frames": [object() for _ in range(8)]}, hud=hud, tcode_sender=FakeTCodeSender(),
        robot_hand=RobotHandState(playing=True, bpm=120.0),
        flick_advance=FlickAdvanceState(locked=False, interval=10))
    clock = [5.0]
    built["controller"].now_source = lambda: clock[0]

    def run_for(seconds: float) -> list[int]:
        for _ in range(round(seconds / 0.1)):
            clock[0] += 0.1
            built["controller"].refresh()
        return list(built["selection"].step_calls)

    run_for(6.0)
    hud.on = True
    behind_the_video = run_for(30.0)
    hud.on = False

    assert (behind_the_video, run_for(3.0), run_for(2.0)) == ([], [], [1])


def test_the_hand_goes_on_driving_the_device_while_a_video_has_the_main_screen():
    tcode = FakeTCodeSender()
    built = _build_controller(
        entry={"frames": [object() for _ in range(8)]}, hud=Flag(on=True), tcode_sender=tcode,
        robot_hand=RobotHandState(playing=True, bpm=120.0))
    clock = [5.0]
    built["controller"].now_source = lambda: clock[0]

    for _ in range(5):
        clock[0] += 0.1
        built["controller"].refresh()

    phases = [phase for phase, _at in tcode.sends]
    assert len(phases) == 5
    assert len(set(phases)) == 5


def test_the_flick_is_drawn_on_the_first_turn_after_it_takes_the_main_screen_back():
    hud = Flag(on=True)
    built = _build_controller(entry={"frames": [object() for _ in range(8)]}, hud=hud)
    built["controller"].refresh()

    hud.on = False
    built["controller"].refresh()

    assert len(built["renderer"].display_calls) == 1


def test_the_flick_is_heard_again_once_it_takes_the_main_screen_back():
    hud = Flag(on=True)
    built = _build_controller(
        entry={"frames": [object() for _ in range(8)]}, hud=hud, commands=[])
    built["controller"].refresh()

    hud.on = False
    built["controller"].refresh()

    assert built["notifier"].visible_updates[-2:] == [False, True]


def test_the_frame_shown_is_where_the_device_is():
    dc = RobotHandState(playing=True, bpm=120.0)
    tcode = FakeTCodeSender()
    tcode._position = 5000
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc, tcode_sender=tcode)

    built["controller"].refresh()

    assert built["renderer"].display_calls[-1] == 5


def test_turning_at_the_top_puts_the_other_half_of_the_flick_on_the_way_down():
    dc = RobotHandState(playing=True, bpm=120.0)
    tcode = FakeTCodeSender()
    tcode._position = 5000
    entry = {"frames": [object() for _ in range(8)]}
    built = _build_controller(entry=entry, robot_hand=dc, tcode_sender=tcode)
    controller = built["controller"]

    controller.refresh()
    tcode._position = 9999
    controller.refresh()
    tcode._position = 9000
    controller.refresh()
    tcode._position = 5000
    controller.refresh()

    assert built["renderer"].display_calls[-1] == 2


def test_a_motion_short_of_the_ends_swaps_halves_on_a_turn():
    dc = RobotHandState(playing=True, bpm=120.0)
    tcode = FakeTCodeSender()
    tcode._position = 3000
    entry = {"frames": [object() for _ in range(120)]}
    built = _build_controller(entry=entry, robot_hand=dc, tcode_sender=tcode)
    controller = built["controller"]

    for position in (3000, 5000, 7000, 5000, 3000):
        tcode._position = position
        controller.refresh()

    assert controller.under_the_device.on_the_way_down is True


def _resumed_by_the_room(tick, _hand, at):
    return tick(at, "RESUME")


def _switched_back_on(tick, _hand, at):
    return tick(at, "SET_TCODE_ENABLED 1")


_FRAMES = 1000


def _height_framed(index: int) -> float:
    phase = ((_FRAMES - 1) - index + 0.5) / _FRAMES
    return 2 * phase if phase <= 0.5 else 2 * (1 - phase)


def _heights(*heights: float):
    return pytest.approx(list(heights), abs=0.005)


class TestTheRoomHoldingTheDevice:
    ASKED = 5.1
    GLIDES = HOLD_MOVE_MS[PARK] / 1000
    RETRACT_GLIDES = HOLD_MOVE_MS[RETRACT] / 1000
    SETTLED = ASKED + GLIDES

    @staticmethod
    def _room(position: int = 5000):
        tcode = FakeTCodeSender()
        tcode._position = position
        hand = RobotHandState(playing=True, bpm=120.0)
        clock = [5.0]
        built = _build_controller(
            entry={"frames": [object() for _ in range(_FRAMES)]}, robot_hand=hand,
            tcode_sender=tcode, now_source=lambda: clock[0])

        def tick(at: float, *said: str) -> float:
            clock[0] = at
            for line in said:
                built["say"](line)
            built["controller"].refresh()
            return _height_framed(built["renderer"].current_frame_index)

        return tick, hand, tcode

    def test_the_frame_goes_home_with_the_device(self):
        tick, _hand, _tcode = self._room(position=5000)

        shown = [tick(5.0), tick(self.ASKED, "PAUSE", "PARK"),
                 tick(self.ASKED + self.GLIDES / 2), tick(self.SETTLED)]

        assert shown == _heights(0.5, 0.5, 0.25, 0.0)

    def test_the_frame_goes_to_the_far_end_with_the_device(self):
        tick, _hand, _tcode = self._room(position=5000)

        shown = [tick(5.0), tick(self.ASKED, "PAUSE", "RETRACT"),
                 tick(self.ASKED + self.RETRACT_GLIDES / 2),
                 tick(self.ASKED + self.RETRACT_GLIDES), tick(self.SETTLED)]

        assert shown == _heights(0.5, 0.5, 0.75, 1.0, 1.0)

    def test_a_hold_the_hand_plays_on_under_unheard_keeps_the_frame_with_the_device(self):
        tick, hand, tcode = self._room(position=5000)
        tick(5.0)
        tick(self.ASKED, "RESUME", "SET_TCODE_ENABLED 0", "PARK")
        tcode._position = 8000

        shown = [tick(self.ASKED + self.GLIDES / 2), tick(self.SETTLED + 1.0)]

        assert (hand.playing, shown) == (True, _heights(0.25, 0.0))

    @pytest.mark.parametrize(("held_by", "taken_back_by", "held_at"), [
        (("PAUSE", "PARK"), _resumed_by_the_room, 0.0),
        (("PAUSE", "RETRACT"), _resumed_by_the_room, 1.0),
        (("RESUME", "SET_TCODE_ENABLED 0", "PARK"), _switched_back_on, 0.0),
    ])
    def test_the_frame_eases_back_onto_the_hand_as_the_device_does(
            self, held_by, taken_back_by, held_at):
        tick, hand, _tcode = self._room(position=5000)
        tick(5.0)
        tick(self.ASKED, *held_by)
        tick(self.SETTLED)
        back, eases = self.SETTLED + 0.1, HANDOFF_MS / 1000

        shown = [taken_back_by(tick, hand, back), tick(back + eases / 2), tick(back + eases)]

        assert shown == _heights(held_at, (held_at + 0.5) / 2, 0.5)

    def test_after_a_pause_with_no_hold_the_frame_eases_on_from_where_it_stopped(self):
        tick, _hand, tcode = self._room(position=5000)
        tick(5.0)
        tick(5.05, "PAUSE")
        tcode._position = 2000
        tick(6.0)
        eases = HANDOFF_MS / 1000

        shown = [tick(6.1, "RESUME"), tick(6.1 + eases / 2), tick(6.1 + eases)]

        assert shown == _heights(0.5, 0.35, 0.2)

    def test_a_hold_moved_to_the_other_end_walks_there_from_where_the_frame_is(self):
        tick, _hand, _tcode = self._room(position=5000)
        tick(5.0)
        tick(self.ASKED, "PAUSE", "PARK")
        tick(self.SETTLED)
        moved = self.SETTLED + 1.0

        shown = [tick(moved, "PAUSE", "RETRACT"), tick(moved + self.RETRACT_GLIDES / 2),
                 tick(moved + self.RETRACT_GLIDES)]

        assert shown == _heights(0.0, 0.5, 1.0)

    def test_a_park_asked_again_on_the_way_home_keeps_its_own_schedule(self):
        tick, _hand, _tcode = self._room(position=5000)
        tick(5.0)
        tick(self.ASKED, "PAUSE", "PARK")
        tick(self.ASKED + self.GLIDES / 2, "PAUSE", "PARK")

        assert [tick(self.SETTLED)] == _heights(0.0)

    def test_a_pause_after_the_hand_took_the_device_back_is_not_a_park(self):
        tick, _hand, _tcode = self._room(position=5000)
        tick(5.0)
        tick(self.ASKED, "PAUSE", "PARK")
        tick(self.SETTLED)
        tick(self.SETTLED + 0.1, "RESUME")
        tick(self.SETTLED + 0.1 + HANDOFF_MS / 1000)
        tick(self.SETTLED + 0.5, "PAUSE")

        assert [tick(self.SETTLED + 5.0)] == _heights(0.5)

    def test_a_pause_without_a_park_leaves_the_frame_where_the_hand_let_go(self):
        tick, _hand, tcode = self._room(position=5000)
        tick(5.0)
        tick(5.05, "PAUSE")
        tcode._position = 2000

        assert [tick(self.SETTLED)] == _heights(0.5)

    def test_a_park_asked_after_the_frame_stopped_starts_where_the_frame_stopped(self):
        tick, _hand, tcode = self._room(position=5000)
        tick(5.0)
        tick(5.05, "PAUSE")
        tcode._position = 2000
        tick(self.ASKED - 0.01)

        shown = [tick(self.ASKED, "PARK"), tick(self.ASKED + self.GLIDES / 2),
                 tick(self.SETTLED)]

        assert shown == _heights(0.5, 0.25, 0.0)


def _calls_in_the_order_written(body: ast.AST) -> list[str]:
    calls = [n for n in ast.walk(body) if isinstance(n, ast.Call)]
    calls.sort(key=lambda n: (n.lineno, n.col_offset))
    return [ast.unparse(n.func) for n in calls]


class TestTheOrderOfTheTicksStepsWhichNoUnitTestCanTell:
    def test_a_call_inside_a_branch_keeps_its_place_though_ast_walk_goes_breadth_first(self):
        assert _calls_in_the_order_written(ast.parse("if x:\n    a()\nb()\n")) == ["a", "b"]

    @staticmethod
    def _steps_in_the_order_written() -> list[str]:
        source = (Path(__file__).resolve().parents[1]
                  / "funestra" / "genau_refresh.py").read_text(encoding="utf-8")
        body = next(n for n in ast.walk(ast.parse(source))
                    if isinstance(n, ast.FunctionDef) and n.name == "_refresh_once")
        return _calls_in_the_order_written(body)

    def _before(self, first: str, second: str) -> None:
        steps = self._steps_in_the_order_written()
        assert first in steps, f"{first} is not in the tick"
        assert second in steps, f"{second} is not in the tick"
        assert steps.index(first) < steps.index(second), f"{first} must precede {second}"

    def test_commands_are_drained_before_anything_reads_what_they_moved_or_a_pause_lands_a_tick_late_and_the_motion_goes_out_once_more_after_the_hand_stopped(self):
        self._before("self._drain_commands", "self._who_is_driving")
        self._before("self._drain_commands", "self.device.drive")

    def test_the_flick_that_finished_decoding_is_adopted_before_it_is_drawn_or_it_is_a_tick_late_on_screen_and_the_advance_times_its_interval_against_the_old_one(self):
        self._before("self.flicks.adopt_whatever_finished_decoding", "self._show_the_frame")

    def test_the_flip_knows_the_flick_on_screen_before_a_command_can_flip_it(self):
        self._before("self.flicks.adopt_whatever_finished_decoding", "self.controls.flick_flip.follow")
        self._before("self.controls.flick_flip.follow", "self._drain_commands")

    def test_who_is_driving_is_settled_before_the_engine_is_told_anything(self):
        self._before("self._who_is_driving", "advance_beat")

    def test_the_engine_moves_before_the_frame_is_chosen_from_its_phase_or_every_frame_is_the_one_the_phase_had_last_tick(self):
        self._before("advance_beat", "self._show_the_frame")

    def test_the_status_file_goes_out_last_saying_what_this_tick_did(self):
        steps = self._steps_in_the_order_written()

        assert steps[-1] == "self._publish_status"


class TestSeekingTheFlick:
    def _built(self, *, frames=20):
        return _build_controller(
            entry={"frames": [object()] * frames},
            robot_hand=RobotHandState(playing=True, speed=50, bpm=60.0),
            tcode_sender=FakeTCodeSender(),
        )

    @staticmethod
    def _height(controller) -> float:
        return position_fraction(
            controller.visualizer.tcode_sender.motion_phase,
            shape=controller.controls.robot_hand.shape,
            amplitude=controller.controls.robot_hand.amplitude,
            center=controller.controls.robot_hand.center,
        )

    def test_the_front_half_of_the_bar_is_the_device_on_its_way_up(self):
        controller = self._built()["controller"]

        controller.seek_the_flick(0.25)

        assert controller.under_the_device.on_the_way_down is False
        assert self._height(controller) == pytest.approx(0.5, abs=0.01)

    def test_the_back_half_is_the_same_heights_on_the_way_down(self):
        controller = self._built()["controller"]

        controller.seek_the_flick(0.75)

        assert controller.under_the_device.on_the_way_down is True
        assert self._height(controller) == pytest.approx(0.5, abs=0.01)

    def test_the_ends_of_the_bar_are_the_ends_of_the_stroke(self):
        parked, retracted = self._built()["controller"], self._built()["controller"]

        parked.seek_the_flick(0.0)
        retracted.seek_the_flick(0.5)

        assert self._height(parked) == pytest.approx(0.0, abs=0.01)
        assert self._height(retracted) == pytest.approx(1.0, abs=0.01)

    def test_a_press_past_either_end_lands_on_that_end(self):
        controller = self._built()["controller"]

        controller.seek_the_flick(-2.0)
        assert self._height(controller) == pytest.approx(0.0, abs=0.01)

        controller.seek_the_flick(9.0)
        assert self._height(controller) == pytest.approx(0.0, abs=0.01)

    def test_the_next_tick_does_not_swap_the_half_back(self):
        controller = self._built()["controller"]

        controller.seek_the_flick(0.6)
        controller.refresh()

        assert controller.under_the_device.on_the_way_down is True

    def test_a_flick_still_decoding_is_not_seekable(self):
        built = _build_controller(entry=None, tcode_sender=FakeTCodeSender())

        built["controller"].seek_the_flick(0.5)

        assert built["controller"].visualizer.tcode_sender.motion_phase == 0.0


def _learned_model() -> LearnedModel:
    phrase = Phrase(tuple((500, 80 if i % 2 == 0 else 20) for i in range(16)))
    return LearnedModel(phrases={classify(phrase): [phrase]}, seen={classify(phrase): 1})


def test_toggle_learned_command_via_refresh():
    dc = RobotHandState(playing=True, bpm=120.0)
    learned = LearnedMotionState(model=_learned_model())
    built = _build_controller(
        entry={"frames": [object() for _ in range(8)]}, robot_hand=dc,
        tcode_sender=FakeTCodeSender(), learned=learned, command="TOGGLE_LEARNED",
    )

    built["controller"].refresh()

    assert learned.active is True


def test_the_learned_motion_ticks_during_refresh(tmp_path):
    dc = RobotHandState(playing=True, bpm=120.0)
    learned = LearnedMotionState(model=_learned_model(), rng=random.Random(1), active=True)
    built = _build_controller(
        entry={"frames": [object() for _ in range(8)]}, robot_hand=dc,
        tcode_sender=FakeTCodeSender(), learned=learned,
        status_file=tmp_path / "status.txt",
    )

    built["controller"].refresh()

    assert learned.times, "no phrases laid out"
    assert learned.times[-1] >= learned.clock + 30.0
    assert "learned=1" in (tmp_path / "status.txt").read_text(encoding="utf-8")


def _learned_start(*, sender, amplitude=100):
    dc = RobotHandState(playing=True, bpm=120.0, amplitude=amplitude)
    learned = LearnedMotionState(model=_learned_model(), rng=random.Random(1), active=True)
    built = _build_controller(
        entry={"frames": [object() for _ in range(8)]}, robot_hand=dc,
        tcode_sender=sender, learned=learned,
    )
    built["controller"].refresh()
    return learned.positions[0]


def test_the_learned_motion_begins_where_the_device_already_is():
    tcode = FakeTCodeSender()
    tcode._position = 5000

    assert _learned_start(sender=tcode) == pytest.approx(50.0, abs=1.0)


def test_with_no_sender_the_learned_motion_begins_at_the_floor():
    assert _learned_start(sender=None) == 0.0


def test_with_no_travel_in_the_bars_the_learned_motion_begins_at_the_floor():
    tcode = FakeTCodeSender()
    tcode._position = 5000

    assert _learned_start(sender=tcode, amplitude=0) == 0.0


class TestAFlippedFlick:
    @staticmethod
    def _metadata_root(tmp_path) -> Path:
        return tmp_path / "videos" / "metadata"

    @classmethod
    def _record(cls, tmp_path) -> Path:
        return cls._metadata_root(tmp_path) / "genau" / "flicks" / "scene one.json"

    @classmethod
    def _flick(cls, tmp_path, *, flipped: bool = True) -> Path:
        flick = tmp_path / "videos" / "genau" / "flicks" / "scene one.mp4"
        flick.parent.mkdir(parents=True)
        flick.touch()
        if flipped:
            cls._record(tmp_path).parent.mkdir(parents=True)
            cls._record(tmp_path).write_text('{"genau": {"flipped": true}}', encoding="utf-8")
        return flick

    @classmethod
    def _flip(cls, tmp_path) -> FlickFlip:
        return FlickFlip(cls._metadata_root(tmp_path))

    def test_the_frame_shown_is_half_a_loop_over_from_where_the_device_is(self, tmp_path):
        tcode = FakeTCodeSender()
        tcode._position = 5000
        built = _build_controller(
            path=str(self._flick(tmp_path)),
            entry={"frames": [object() for _ in range(8)]},
            robot_hand=RobotHandState(playing=True, bpm=120.0), tcode_sender=tcode,
            flick_flip=self._flip(tmp_path),
        )

        built["controller"].refresh()

        assert built["renderer"].display_calls[-1] == 1

    def test_under_the_broker_it_is_half_a_loop_over_from_the_beat(self, tmp_path):
        built = _build_controller(
            path=str(self._flick(tmp_path)),
            broker=BrokerFeed(auto_active=True, raw_bpm=120.0),
            entry={"frames": [object() for _ in range(8)]},
            robot_hand=RobotHandState(playing=False, bpm=60.0),
            flick_flip=self._flip(tmp_path),
        )

        built["controller"].refresh()

        assert built["renderer"].display_calls == [1]

    def test_flip_ends_turns_over_the_flick_up_when_it_arrives(self, tmp_path):
        flick = self._flick(tmp_path, flipped=False)
        tcode = FakeTCodeSender()
        tcode._position = 5000
        built = _build_controller(
            path=str(flick), command="FLIP_ENDS",
            entry={"frames": [object() for _ in range(8)]},
            robot_hand=RobotHandState(playing=True, bpm=120.0), tcode_sender=tcode,
            flick_flip=self._flip(tmp_path),
        )

        built["controller"].refresh()

        assert built["renderer"].display_calls == [1]
        assert '"flipped": true' in self._record(tmp_path).read_text(encoding="utf-8")

    def test_its_bar_starts_where_its_own_first_frame_puts_the_device(self, tmp_path):
        built = _build_controller(
            path=str(self._flick(tmp_path)),
            entry={"frames": [object()] * 20},
            robot_hand=RobotHandState(playing=True, speed=50, bpm=60.0),
            tcode_sender=FakeTCodeSender(),
            flick_flip=self._flip(tmp_path),
        )
        controller = built["controller"]
        controller.refresh()

        controller.seek_the_flick(0.0)
        at_the_start = TestSeekingTheFlick._height(controller)
        controller.seek_the_flick(0.25)

        assert at_the_start == pytest.approx(1.0, abs=0.01)
        assert (controller.under_the_device.on_the_way_down, TestSeekingTheFlick._height(controller)) == (
            True, pytest.approx(0.5, abs=0.01))

    def test_the_status_says_the_flick_up_is_flipped(self, tmp_path):
        built = _build_controller(
            path=str(self._flick(tmp_path)),
            entry={"frames": [object() for _ in range(8)]},
            robot_hand=RobotHandState(playing=True, bpm=120.0),
            tcode_sender=FakeTCodeSender(),
            status_file=tmp_path / "genau_status.txt",
            flick_flip=self._flip(tmp_path),
        )

        built["controller"].refresh()

        assert "flipped=1" in (tmp_path / "genau_status.txt").read_text(encoding="utf-8")


def test_the_status_says_whether_the_flick_up_is_portrait(tmp_path):
    built = _build_controller(
        entry={"frames": [object() for _ in range(8)]},
        status_file=tmp_path / "genau_status.txt",
    )
    built["renderer"].portrait = True

    built["controller"].refresh()

    assert "portrait=1" in (tmp_path / "genau_status.txt").read_text(encoding="utf-8")


def test_the_status_goes_out_with_nothing_but_the_hand_wired(tmp_path):
    built = _build_controller(
        entry={"frames": [object() for _ in range(8)]},
        status_file=tmp_path / "genau_status.txt",
    )

    built["controller"].refresh()

    status = (tmp_path / "genau_status.txt").read_text(encoding="utf-8")
    assert "shape=sine" in status


class TestSeekingTheFlicksTimeOnScreen:
    def test_it_puts_the_flick_that_far_into_its_interval(self):
        advance = FlickAdvanceState(locked=False, interval=10)
        controller = _build_controller(flick_advance=advance)["controller"]

        controller.seek_the_time_on_screen(7.0)

        assert advance.elapsed == 7.0


def test_with_no_status_file_named_the_status_goes_beside_the_command_file_where_every_release_has_looked_for_it(
        tmp_path):
    built = _build_controller(command_file=tmp_path / "genau_cmd.txt")

    assert built["controller"].files.status_file == tmp_path / GENAU_STATUS_FILENAME


def test_the_controller_refuses_to_be_built_without_the_hands_state_so_no_hand_less_mode_can_come_back(
        tmp_path):
    built = _build_controller(command_file=tmp_path / "genau_cmd.txt")["controller"]
    hand_less = GenauControls(
        engine=BeatEngine(phase=0.0, last_tick=0.0), paused=Flag(), step_flick=lambda _step: None)

    with pytest.raises(ValueError, match="hand"):
        GenauRefreshController(hand_less, built.flicks, broker=built.broker, files=built.files,
                               tuning=built.tuning, logger=built.logger)


def test_the_status_says_when_the_flick_on_screen_went_up_so_a_late_reader_can_date_a_change(
        tmp_path):
    status = tmp_path / "genau_status.txt"
    clock = [5.0]
    built = _build_controller(status_file=status, now_source=lambda: clock[0])

    built["controller"].refresh()
    clock[0] = 6.0
    built["controller"].refresh()
    assert "up_at=5.000\n" in status.read_text(encoding="utf-8")

    built["renderer"].current_flick_path = Path("other.mp4")
    clock[0] = 7.0
    built["controller"].refresh()
    assert "up_at=7.000\n" in status.read_text(encoding="utf-8")


class _ThreadsStarted:
    def __init__(self) -> None:
        self.named: list[str] = []

    def __call__(self, *, target, name: str) -> None:
        self.named.append(name)


def _sending_between_passes(clock: list[float], **choices):
    hand = RobotHandState(playing=True, bpm=120.0)
    tcode = FakeTCodeSender()
    threads = _ThreadsStarted()
    built = _build_controller(entry={"frames": [object() for _ in range(8)]}, robot_hand=hand,
                              tcode_sender=tcode, now_source=lambda: clock[0],
                              start_thread=threads, **choices)
    return built["controller"], tcode, threads, hand


def test_given_a_way_to_start_a_thread_the_osr2_s_positions_get_a_thread_of_their_own():
    _controller, _tcode, threads, _hand = _sending_between_passes([5.0])

    assert threads.named == [SEND_THREAD]


def test_passes_of_the_window_then_send_no_position_since_a_late_pass_would_be_a_late_position():
    clock = [5.0]
    controller, tcode, _threads, _hand = _sending_between_passes(clock)

    for _pass in range(4):
        clock[0] += 0.016
        controller.refresh()

    assert tcode.sends == []
    assert tcode.wanted is True


def test_between_passes_the_motion_goes_on_and_each_beat_of_the_send_clock_sends_where_it_has_got_to():
    clock = [5.0]
    controller, tcode, _threads, _hand = _sending_between_passes(clock)
    controller.refresh()

    for beat in range(1, 4):
        controller.send_between_passes(5.0 + beat / 30)

    phases = [phase for phase, _now in tcode.sends]
    assert [now for _phase, now in tcode.sends] == [5.0 + beat / 30 for beat in range(1, 4)]
    assert phases == sorted(set(phases))


def test_a_pass_after_the_send_clock_s_beats_does_not_count_their_time_twice():
    clock = [5.0]
    controller, _tcode, _threads, _hand = _sending_between_passes(clock)
    controller.refresh()
    alone = _sending_between_passes([5.0])[0]
    alone.refresh()

    controller.send_between_passes(5.02)
    controller.send_between_passes(5.05)
    clock[0] = 5.1
    controller.refresh()
    alone.now_source = lambda: 5.1
    alone.refresh()

    assert controller.controls.engine.phase == pytest.approx(alone.controls.engine.phase)


def test_before_the_first_pass_and_while_the_osr2_runs_itself_the_send_clock_sends_nothing():
    clock = [5.0]
    controller, tcode, _threads, _hand = _sending_between_passes(clock)

    controller.send_between_passes(5.01)
    controller.broker.auto_active = True
    controller.refresh()
    controller.send_between_passes(5.03)

    assert tcode.sends == []


def test_a_hand_paused_since_the_last_pass_is_sent_nothing_between_passes():
    clock = [5.0]
    controller, tcode, _threads, hand = _sending_between_passes(clock)
    controller.refresh()
    hand.playing = False

    controller.send_between_passes(5.03)

    assert tcode.sends == []


def test_given_no_way_to_start_a_thread_the_window_s_pass_sends_as_it_always_did():
    tcode = FakeTCodeSender()
    built = _build_controller(entry={"frames": [object() for _ in range(8)]},
                              robot_hand=RobotHandState(playing=True, bpm=120.0), tcode_sender=tcode)

    built["controller"].refresh()

    assert len(tcode.sends) == 1


def test_a_flick_s_flip_is_read_beside_its_decode_and_not_on_the_window_s_pass_when_it_comes_up():
    flip = FlickFlip()
    built = _build_controller(entry={"frames": [object() for _ in range(8)]}, flick_flip=flip)

    assert built["loader"].read_beside_the_frames == flip.read_ahead


def test_the_status_says_whether_the_whole_flick_named_is_read_so_a_reader_can_wait_for_it(tmp_path):
    status = tmp_path / "genau_status.txt"
    built = _build_controller(status_file=status, entry=None)

    built["controller"].refresh()
    assert "whole=0\n" in status.read_text(encoding="utf-8")

    built["renderer"]._entry = {"frames": [object() for _ in range(8)]}
    built["controller"].refresh()
    assert "whole=1\n" in status.read_text(encoding="utf-8")


def test_the_status_says_when_the_flick_named_could_not_be_read_so_a_reader_stops_waiting_for_it(
        tmp_path):
    status = tmp_path / "genau_status.txt"
    built = _build_controller(status_file=status, path="broken.mp4", entry=None)

    built["controller"].refresh()
    assert "unreadable=0\n" in status.read_text(encoding="utf-8")

    built["loader"].undecodable.add(Path("broken.mp4"))
    built["controller"].refresh()
    assert "unreadable=1\n" in status.read_text(encoding="utf-8")
