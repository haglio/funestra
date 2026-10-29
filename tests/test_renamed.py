"""A checkout from before a rename still imports and runs: from before Genau's
clips became flicks, and from before the Player became the Funestra.

Every open branch of an app runs out of that app's one venv, so these are the
names those branches spell until they are rebased. Each test is one thing such a
checkout does; when no checkout does it any more, the test goes with the name.
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest
from funestra_fakes import FakeEngine

from funestra import (
    clip_picture,
    cruise_control,
    flick_folder,
    flick_picture,
    mpv_engine,
    playhead,
    status,
)
from funestra import funestra as funestra_module
from funestra.console import OSR2_DRIVING, ConsoleModel, aim_row, console_text, parse_console
from funestra.device_panel import DevicePanel
from funestra.flag import Flag
from funestra.flick_cache import FlickCacheStore
from funestra.flick_overlay import FlickFrame, FlickOverlay
from funestra.flick_picture import Picture
from funestra.flick_renderer import FlickRenderController
from funestra.genau_controls import GenauControls, apply_runtime_command
from funestra.genau_notifier import GenauNotifier
from funestra.genau_status import build_status_text
from funestra.hud_overlay import HudOverlay
from funestra.playback import Playback
from funestra.renamed import method_of
from funestra.render_engine import MpvRenderEngine
from funestra.robot_hand import RobotHandState
from funestra.robot_hand_beat import BeatEngine
from funestra.robot_hand_driver import RobotHandTCodeDriver
from funestra.satellite_hud import HudModel, hud_text, parse_hud


def test_an_old_module_path_gives_the_renamed_function():
    from funestra.clip_folder import flat_clips_in  # noqa: PLC0415

    assert flat_clips_in is flick_folder.flat_flicks_in


def test_an_old_module_path_refuses_a_name_it_never_had():
    with pytest.raises(ImportError):
        from funestra.clip_folder import a_name_funestra_never_had  # noqa: F401, PLC0415


def test_a_function_renamed_in_place_answers_to_its_old_name():
    assert playhead.clip_playhead is playhead.flick_playhead


def test_a_class_takes_its_old_keyword_names_and_answers_to_its_old_attribute_names():
    store = FlickCacheStore(limit=1)
    renderer = FlickRenderController(clip_store=store, blit_frame=lambda _frame: None)

    renderer.set_current_flick_path(Path("C:/flicks/alpha.mp4"))

    assert renderer.flick_store is store
    assert renderer.current_clip_path == Path("C:/flicks/alpha.mp4")


def test_a_picture_takes_its_old_seek_for_the_seek_round_its_loop():
    turns = []

    picture = Picture(frame=None, seek=turns.append, clip=Path("C:/flicks/alpha.mp4"))
    picture.seek(0.25)

    assert turns == [0.25] and picture.seek_loop == turns.append
    assert picture.flick == Path("C:/flicks/alpha.mp4")


def test_genaus_controls_take_the_collaborators_an_old_orchestrator_names():
    stepped = []
    controls = GenauControls(engine=BeatEngine(last_tick=0.0), paused=Flag(), step_clip=stepped.append)

    controls.step_flick(1)

    assert stepped == [1]


def test_an_old_seconds_verb_still_sets_the_pace():
    from funestra.flick_advance import FlickAdvanceState  # noqa: PLC0415

    controls = GenauControls(engine=BeatEngine(last_tick=0.0), paused=Flag(), step_flick=lambda _step: None,
                             flick_advance_state=FlickAdvanceState())

    apply_runtime_command("CLIP_SECONDS 30", controls)

    assert controls.flick_advance_state.interval == 30


def test_the_status_says_the_flick_under_both_keys():
    text = build_status_text(RobotHandState(), flick=Path("C:/flicks/alpha.mp4"))

    assert {line.split("=", 1)[0] for line in text.splitlines()} >= {"flick", "clip"}


class TestACheckoutFromBeforeCruiseControlWent:
    """Fun Time built a CruiseControlState and handed it, with the driver's
    set_motion_phase, to Genau's controls and driver; Origenerator ticked one
    and read its stack; both named it on the row that aims the device."""

    def test_genaus_controls_and_driver_take_what_it_handed_them_and_drop_it(self):
        sink = type("Sink", (), {"send": lambda _self, _line: None, "close": lambda _self: None})()
        driver = RobotHandTCodeDriver(sink, robot_hand=RobotHandState(),
                                      cruise=cruise_control.CruiseControlState())
        controls = GenauControls(engine=BeatEngine(last_tick=0.0), paused=Flag(),
                                 step_flick=lambda _step: None,
                                 cruise_control_state=cruise_control.CruiseControlState(),
                                 set_motion_phase=driver.set_motion_phase)

        assert not hasattr(controls, "cruise_control_state")
        assert not hasattr(controls, "set_motion_phase")

    def test_the_row_it_names_cruise_on_draws_none(self):
        commands = [button.command for button in
                    aim_row(cruise=True, learned=False, shape="sine", control=OSR2_DRIVING)]

        assert "robot_hand_toggle_learned" in commands
        assert "robot_hand_toggle_cruise" not in commands

    def test_the_cruise_it_ticks_never_moves(self):
        state = cruise_control.CruiseControlState()

        cruise_control.enable_cruise_control(state)
        cruise_control.tick_cruise_control(RobotHandState(playing=True), state, 1.0, phase=0.25)

        assert (state.active, bool(state.stack), list(state.stack.waves), state.clock) == (
            False, False, [], 0.0)
        assert cruise_control.disable_cruise_control(state) is None


def test_a_collaborator_from_before_the_rename_is_asked_by_its_old_method_name():
    heard = []

    class OldNotifier:
        def notify_clip(self, path):
            heard.append(path)

    method_of(OldNotifier(), "notify_flick", old_name="notify_clip")(Path("alpha.mp4"))

    assert heard == [Path("alpha.mp4")]


def test_the_notifier_answers_to_its_old_method_name():
    class Socket:
        def __init__(self):
            self.sent = []

        def sendto(self, data, _address):
            self.sent.append(data)

    sock = Socket()
    GenauNotifier("127.0.0.1", 9999, sock=sock).notify_clip(Path("alpha.mp4"))

    assert sock.sent == [b"FLICK alpha", b"CLIP alpha"]


def test_the_engines_old_module_paths_give_the_engines():
    from funestra.mpv_player import MpvPlayer  # noqa: PLC0415
    from funestra.render_player import MpvRenderPlayer  # noqa: PLC0415

    assert MpvPlayer is mpv_engine.MpvEngine
    assert MpvRenderPlayer is MpvRenderEngine


def test_the_check_fun_time_runs_for_the_engine_still_reaches_its_loader():
    from funestra.mpv_player import _import_mpv  # noqa: PLC0415

    assert _import_mpv is mpv_engine._import_mpv


def test_a_playback_takes_its_engine_under_the_old_keyword(tmp_path):
    engine = FakeEngine()

    Playback([tmp_path / "v0.mp4"], player=engine)

    assert engine.opened == [tmp_path / "v0.mp4"]


def test_a_hud_overlay_takes_its_engine_under_the_old_keyword(tmp_path):
    hud_file = tmp_path / "portrait_hud.json"
    hud_file.write_text('{"player": "portrait"}', encoding="utf-8")
    engine = FakeEngine()

    HudOverlay(player=engine, hud_file=hud_file, command_file=tmp_path / "cmd.txt",
               clock=lambda: 0.0).tick()

    assert len(engine.overlays) == 1


def test_the_verbs_old_module_path_gives_every_verb():
    from funestra import funestra_verbs  # noqa: PLC0415
    from funestra.player_verbs import TOGGLE_LOCK, play_file  # noqa: PLC0415

    assert (TOGGLE_LOCK, play_file) == (funestra_verbs.TOGGLE_LOCK, funestra_verbs.play_file)


def test_the_status_record_answers_to_its_old_name():
    assert status.PlayerStatus is status.FunestraStatus


def test_a_panel_takes_its_funestra_under_the_old_keyword_and_answers_to_it():
    model = HudModel(player="landscape")

    assert (model.funestra, model.player) == ("landscape", "landscape")


def test_a_panel_replaced_by_the_old_keyword_changes_its_funestra():
    assert replace(HudModel(funestra="portrait"), player="landscape").funestra == "landscape"


def test_a_panel_written_before_the_rename_still_reads():
    assert parse_hud('{"player": "landscape"}').funestra == "landscape"


def test_the_published_panel_names_its_funestra_under_both_keys():
    raw = json.loads(hud_text(HudModel(funestra="portrait")))

    assert (raw["funestra"], raw["player"]) == ("portrait", "portrait")


def test_a_console_takes_and_publishes_its_funestra_the_old_way_too():
    model = ConsoleModel(player="main")

    assert model.funestra == "main"
    assert json.loads(console_text(model))["player"] == "main"
    assert parse_console('{"main_mode": "kino", "player": "main"}').funestra == "main"


def test_the_flick_overlays_old_module_and_names_give_the_frame_and_the_overlay():
    assert (flick_picture.Picture, flick_picture.FlickPicture) == (FlickFrame, FlickOverlay)
    assert (clip_picture.Picture, clip_picture.ClipPicture) == (FlickFrame, FlickOverlay)


def test_where_a_users_own_frames_go_answers_to_its_old_name():
    assert funestra_module.UsersPicture is funestra_module.UsersFrames


def test_a_status_takes_and_answers_to_its_old_word_for_an_image_on_screen():
    shown = status.FunestraStatus(picture=True)

    assert (shown.image, shown.picture) == (True, True)


def test_a_device_panel_still_draws_under_its_old_name():
    assert DevicePanel.picture is DevicePanel.drawing


def test_the_offscreen_engine_still_says_it_has_a_frame_to_draw_under_its_old_name():
    assert MpvRenderEngine.has_picture_to_draw is MpvRenderEngine.has_frame_to_draw


class _AnEngineFromBeforeImages(FakeEngine):
    hold_image_for = None

    def __init__(self) -> None:
        super().__init__()
        del self.showing_image
        self.showing_picture = True
        self.held_for: list[float] = []

    def hold_picture_for(self, seconds: float | None) -> None:
        self.held_for.append(seconds)


def test_a_playback_holds_and_reads_the_image_on_an_engine_from_before_images(tmp_path):
    engine = _AnEngineFromBeforeImages()
    playback = Playback([tmp_path / "v0.mp4"], engine=engine)

    playback.hold_image_for(2.0)

    assert (playback.showing_image, engine.held_for) == (True, [2.0])

