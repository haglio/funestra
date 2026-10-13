"""The main console: the panel whichever Funestra holds the slot draws, and where
a press on it lands."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from shared_ui.icon_geometry import glyph_names

from funestra.console import (
    BUTTON,
    GAP,
    GROUP_GAP,
    OSR2_CONTROL_BUTTONS,
    OSR2_CONTROL_OFF,
    OSR2_CONTROL_UNANSWERED,
    OSR2_DRIVING,
    OSR2_PARKED,
    OSR2_RETRACTED,
    ROW_LABEL_W,
    VALUE_W,
    ConsoleModel,
    aim_row,
    console_text,
    hit_test,
    kino_shows,
    parse_console,
    place_rows,
    read_console,
    rows_height,
    shape_label,
    tooltip_at,
)
from funestra.hud_button import FIT_THE_WORD, Button
from funestra.hud_marks import (
    BROKER_ICON,
    MINIMIZE_ICON,
    TOGGLE_SWITCH,
    shared_mark,
    shared_mark_name,
)
from funestra.hud_placement import HudCorner, HudEdge
from funestra.modes import MainMode, Osr2State
from funestra.robot_hand import WaveformShape

# A source's rows, made up: a mode pair with minimize standing apart, and a
# named read-out between two arrows.
ROWS = (
    (Button("go_kino", "Kino", "Kino mode", width=40, lit=True),
     Button("go_other", "Other", "The other mode", width=40),
     Button("park", MINIMIZE_ICON, "Park the window", group_break=True)),
    (Button("", "Playback speed", "", width=ROW_LABEL_W),
     Button("slower", "−", "Slower", group_break=True),
     Button("", "", "", width=VALUE_W, host_value="playback_speed"),
     Button("faster", "+", "Faster"),
     Button("spent", "⏭", "Nothing left to step to", dim=True)),
)


def _placed() -> list:
    return place_rows([list(row) for row in ROWS], x=0, y=0)


def _rect(command: str):
    return next(rect for rect, button in _placed() if button.command == command)


class TestShapeLabel:
    """The control that cycles the waveform names it on hover, so the name lives
    with the console rather than with the readout that no longer prints it."""

    def test_names_the_waveform_instead_of_leaving_it_to_the_curve(self):
        assert shape_label("sine") == "Sine"
        assert shape_label("rounded_square") == "Square"
        assert shape_label("sawtooth") == "Sawtooth"

    def test_an_unknown_shape_is_titled_rather_than_dropped(self):
        assert shape_label("half_moon") == "Half Moon"


def _aim_row(*, learned=False, shape="sine", control=OSR2_DRIVING):
    return aim_row(learned=learned, shape=shape, control=control)


def _button(row, command: str) -> Button:
    return next(button for button in row if button.command == command)


def _waveform_face(shape: str) -> str:
    return _button(_aim_row(shape=shape), "robot_hand_cycle_shape").glyph


class TestTheRowThatAimsTheDevice:
    def test_the_switch_comes_first_then_the_motion_set_apart(self):
        row = _aim_row()

        _label, _off, switch, _on = row[:4]
        assert switch.glyph == TOGGLE_SWITCH
        assert [button.command for button in row[4:]] == [
            "robot_hand_toggle_learned", "robot_hand_cycle_shape", "quarter_button"]
        assert row[4].group_break

    def test_human_inspired_wears_the_familys_human_figure(self):
        face = _button(_aim_row(), "robot_hand_toggle_learned").glyph

        assert face == shared_mark("human")
        assert shared_mark_name(face) in glyph_names()

    def test_the_switch_is_labeled_osr2_control_apart_from_the_osr2_itself(self):
        label, *_switch = _aim_row()[:4]

        assert label.glyph == "OSR2 control"
        assert not label.command
        assert label.width == FIT_THE_WORD

    def test_the_switch_says_off_on_one_side_and_on_on_the_other(self):
        _label, off, _switch, on = _aim_row()[:4]

        assert (off.glyph, on.glyph) == ("Off", "On")
        assert not off.command and not on.command

    def test_the_switch_is_on_while_driving_and_a_press_parks(self):
        _label, off, switch, on = _aim_row(control=OSR2_DRIVING)[:4]

        assert switch.lit and on.lit and not off.lit
        assert switch.command == OSR2_CONTROL_BUTTONS[OSR2_PARKED]

    @pytest.mark.parametrize("control", [OSR2_PARKED, OSR2_RETRACTED, OSR2_CONTROL_UNANSWERED,
                                         OSR2_CONTROL_OFF])
    def test_the_switch_is_off_while_held_or_unsaid_and_a_press_drives(self, control):
        _label, off, switch, on = _aim_row(control=control)[:4]

        assert off.lit and not switch.lit and not on.lit
        assert switch.command == OSR2_CONTROL_BUTTONS[OSR2_DRIVING]

    def test_the_switch_says_where_the_device_is_and_what_a_press_does(self):
        def says(control: str) -> str:
            return _aim_row(control=control)[2].tooltip

        assert says(OSR2_DRIVING).startswith("OSR2 control on")
        assert says(OSR2_PARKED).startswith("OSR2 control off")
        assert says(OSR2_RETRACTED).startswith("OSR2 control off")
        assert "far end" in says(OSR2_RETRACTED)

    def test_human_inspired_lights_while_it_has_the_motion(self):
        assert _button(_aim_row(learned=True), "robot_hand_toggle_learned").lit
        assert not _button(_aim_row(), "robot_hand_toggle_learned").lit

    def test_the_waveform_button_names_the_waveform_the_motion_is_in(self):
        row = _aim_row(shape="rounded_square")
        assert _button(row, "robot_hand_cycle_shape").tooltip == "Waveform: Square"

    def test_each_waveform_wears_a_face_of_its_own_that_the_family_draws(self):
        faces = [_waveform_face(shape.value) for shape in WaveformShape]

        assert len(set(faces)) == len(faces)
        assert {shared_mark_name(face) for face in faces} <= set(glyph_names())

    def test_the_sine_wears_the_face_every_version_of_the_family_draws(self):
        assert _waveform_face("sine") == shared_mark("wave")

    def test_a_waveform_this_version_does_not_know_wears_the_plain_wave(self):
        assert _waveform_face("half_moon") == shared_mark("wave")


class TestTheDeviceRunningItself:
    """Auto mode is the OSR2 on its own firmware: the broker stops forwarding
    the script's T-Code and Genau is not sending either.  Asked of the model
    rather than compared against the word, because two apps outside this
    package draw a picture that depends on the answer."""

    def test_auto_is_the_device_driving_itself(self):
        assert ConsoleModel(osr2=Osr2State.AUTO).device_drives_itself is True

    @pytest.mark.parametrize("osr2", [Osr2State.OFF, Osr2State.FUNSCRIPT,
                                      Osr2State.ROBOT_HAND])
    def test_nothing_else_is(self, osr2):
        assert ConsoleModel(osr2=osr2).device_drives_itself is False


class TestModePredicates:
    def test_kino_shows_in_kino_mode_alone(self):
        assert kino_shows(MainMode.KINO)
        assert not kino_shows(MainMode.GENAU)


class TestReadConsole:
    def test_it_reads_back_what_fun_time_published(self, tmp_path: Path):
        path = tmp_path / "main_player_console.json"
        path.write_text(json.dumps({
            "main_mode": MainMode.KINO, "active": True, "osr2": Osr2State.ROBOT_HAND,
            "osr2_control": OSR2_RETRACTED, "locked": False, "latest": True,
        }), encoding="utf-8")

        model = read_console(path)

        assert model == ConsoleModel(main_mode=MainMode.KINO, active=True,
                                     osr2=Osr2State.ROBOT_HAND,
                                     osr2_control=OSR2_RETRACTED, locked=False,
                                     latest=True)

    def test_a_panel_that_says_nothing_about_the_lock_reads_as_locked(self, tmp_path: Path):
        """Which is where both Funestras open, and what a Fun Time too old to
        publish the flag is still describing."""
        path = tmp_path / "main_player_console.json"
        path.write_text(json.dumps({"main_mode": MainMode.KINO}), encoding="utf-8")

        assert read_console(path).locked is True
        assert ConsoleModel().locked is True

    def test_a_panel_that_says_nothing_about_the_order_names_none(self, tmp_path: Path):
        """Fun Time publishes the flag every tick; a file that says nothing
        about it is from a host with no browse order to name."""
        path = tmp_path / "main_player_console.json"
        path.write_text(json.dumps({"main_mode": MainMode.KINO}), encoding="utf-8")

        assert read_console(path).latest is None

    def test_a_panel_from_a_fun_time_that_still_says_video_reads_as_kino(self):
        assert parse_console(json.dumps({"main_mode": "video"})).main_mode is MainMode.KINO

    def test_a_key_the_panel_no_longer_carries_is_passed_over(self):
        """The switches the console's buttons were once lit from still come
        from a publisher on an older release; the panel reads the same without
        them."""
        parsed = parse_console(json.dumps({
            "main_mode": MainMode.GENAU, "scripted_filter": True, "broker": True,
            "loop_state": "looping", "cruise": True, "learned": True,
            "shape": "sawtooth", "plays_vr": True}))

        assert parsed == ConsoleModel(main_mode=MainMode.GENAU)

    def test_a_torn_or_missing_file_keeps_the_console_you_have(self, tmp_path: Path):
        path = tmp_path / "main_player_console.json"
        assert read_console(path) is None

        path.write_text('{"main_mode": "kino"', encoding="utf-8")
        assert read_console(path) is None


class TestLayout:
    def test_rows_stack_down_at_the_declared_size(self):
        placed = _placed()

        assert all(rect[3] == BUTTON for rect, _b in placed)
        assert {rect[1] for rect, _b in placed} == {0, _rect("slower")[1]}
        assert rows_height([list(row) for row in ROWS]) == _rect("slower")[1] + BUTTON

    def test_a_group_break_opens_the_wider_gap_and_nothing_else_does(self):
        go_kino, go_other, park = _rect("go_kino"), _rect("go_other"), _rect("park")

        assert go_other[0] - (go_kino[0] + go_kino[2]) == GAP
        assert park[0] - (go_other[0] + go_other[2]) == GROUP_GAP

    def test_a_press_finds_the_button_under_it(self):
        x, y, _w, _h = _rect("faster")

        assert hit_test(_placed(), x + 1, y + 1) == "faster"
        assert tooltip_at(_placed(), x + 1, y + 1) == "Faster"

    def test_a_press_off_every_button_posts_nothing(self):
        assert hit_test(_placed(), 5000, 5000) == ""

    def test_a_read_out_is_not_a_hit_target(self):
        rect = next(r for r, b in _placed() if b.host_value == "playback_speed")

        assert hit_test(_placed(), rect[0] + 1, rect[1] + 1) == ""

    def test_a_dimmed_button_posts_nothing_but_still_names_itself(self):
        """Knowing why it cannot be pressed is the point of hovering it."""
        x, y, _w, _h = _rect("spent")

        assert hit_test(_placed(), x + 1, y + 1) == ""
        assert tooltip_at(_placed(), x + 1, y + 1) == "Nothing left to step to"

    def test_a_button_wearing_a_mark_this_version_lacks_says_why_on_hover(self):
        button = Button("auto", shared_mark("a_mark_from_another_version"),
                        "Generate on its own")

        assert tooltip_at(place_rows([[button]], x=0, y=0), 1, 1) == button.tooltip_on_hover


class TestThePublishedConsoleIsWrittenWhereItIsRead:
    """Fun Time publishes a ConsoleModel as text and the Main Funestra parses it
    back; the keys are spelled once, here."""

    def test_every_published_field_survives_the_round_trip(self):
        model = ConsoleModel(
            main_mode=MainMode.GENAU, active=True, osr2=Osr2State.AUTO,
            osr2_control=OSR2_RETRACTED, paused=True, locked=False, latest=True,
        )

        assert parse_console(console_text(model)) == model

    def test_the_rows_a_source_declares_survive_it_too(self):
        """The buttons themselves ride the panel: what each posts, its face,
        its tooltip and its state, row by row, and the controls on the OSR2
        line beside them."""
        model = ConsoleModel(
            rows=ROWS,
            osr2_controls=(Button("broker_panel", BROKER_ICON, "Broker", warn=True),),
        )

        assert parse_console(console_text(model)) == model

    def test_the_rows_that_aim_the_device_survive_it_apart_from_the_rest(self):
        aim = ((Button("robot_hand_park", "P", "Parked"),),)
        model = ConsoleModel(rows=ROWS, osr2_rows=aim)

        parsed = parse_console(console_text(model))

        assert (parsed.rows, parsed.osr2_rows) == (ROWS, aim)

    def test_what_the_drawing_funestra_folds_in_is_not_published(self):
        """The playback rate and the clip pace are the drawing host's own --
        Fun Time neither sets them nor hears about them -- so the text does not
        carry them and they come back at rest."""
        model = ConsoleModel(playback_speed=1.5, advance_interval=12)

        parsed = parse_console(console_text(model))

        assert parsed == ConsoleModel()
        assert "playback_speed" not in json.loads(console_text(model))

    def test_an_order_the_session_does_not_offer_stays_absent(self):
        assert parse_console(console_text(ConsoleModel(latest=None))).latest is None
        assert parse_console(console_text(ConsoleModel(latest=False))).latest is False

    def test_a_console_another_funestra_took_the_osr2_from_says_so(self):
        assert parse_console(console_text(ConsoleModel(has_osr2=False))).has_osr2 is False

    def test_the_max_intensity_a_session_holds_rides_the_panel(self):
        assert parse_console(console_text(ConsoleModel(max_intensity=35))).max_intensity == 35

    def test_a_panel_that_says_nothing_about_the_max_intensity_has_no_slider(self):
        assert parse_console(json.dumps({"main_mode": MainMode.KINO})).max_intensity is None

    def test_a_max_intensity_that_is_not_a_number_is_no_slider_rather_than_no_panel(self):
        parsed = parse_console(json.dumps({"main_mode": MainMode.KINO, "max_intensity": "loud"}))

        assert parsed is not None and parsed.max_intensity is None

    def test_a_panel_that_says_nothing_about_the_osr2_has_it(self):
        assert parse_console(json.dumps({"main_mode": MainMode.KINO})).has_osr2 is True

    def test_a_torn_read_is_no_panel(self):
        assert parse_console('{"main_mode": "kino"') is None
        assert parse_console("") is None


def test_the_published_console_carries_where_it_sits_and_whether_it_is_minimized():
    read_back = parse_console(console_text(ConsoleModel(
        hud_corner=HudCorner.UPPER_RIGHT, hud_edge=HudEdge.UPPER, hud_minimized=True)))

    assert read_back.hud_corner is HudCorner.UPPER_RIGHT
    assert read_back.hud_edge is HudEdge.UPPER
    assert read_back.hud_minimized is True
    assert read_back.funestra == "main"
