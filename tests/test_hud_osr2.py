"""The device's own line, drawn the same wherever a panel says who has the OSR2."""
from __future__ import annotations

import numpy as np
from shared_ui.palette import BLUE, GREEN, RED, TEXT_MUTED

from funestra.drive_readout import DriveHud, track_command
from funestra.hud_button import Button
from funestra.hud_osr2 import (
    BUFFER,
    COLORS,
    HEIGHT,
    LABELS,
    MAX_INTENSITY_TIP,
    Osr2Line,
    Osr2Section,
    driving_at_the_playhead,
    state_for,
)
from funestra.hud_panel import HudPanel
from funestra.modes import Osr2State


def _drawn(line: Osr2Line) -> tuple[HudPanel, list]:
    section = Osr2Section()
    panel = HudPanel(section.width(line) + 20, HEIGHT + 20)
    placed = section.draw(panel.image, panel.draw, 10, 10, line)
    return panel, placed


def _has(panel: HudPanel, color) -> bool:
    pixels = np.array(panel.image.convert("RGB"))
    return bool((pixels == np.array(color)).all(axis=-1).any())


class TestTheLine:
    def test_it_names_who_has_the_device(self):
        assert LABELS[Osr2State.FUNSCRIPT] == "FunScript"
        assert LABELS[Osr2State.ROBOT_HAND] == "Robot Hand"

    def test_a_funscript_driving_is_said_in_green(self):
        panel, _ = _drawn(Osr2Line(state=Osr2State.FUNSCRIPT))
        assert _has(panel, GREEN)

    def test_the_motion_driving_is_said_in_blue(self):
        panel, _ = _drawn(Osr2Line(state=Osr2State.ROBOT_HAND))
        assert _has(panel, BLUE)

    def test_nothing_driving_is_said_in_the_muted_gray(self):
        panel, _ = _drawn(Osr2Line(state=Osr2State.OFF))
        assert _has(panel, TEXT_MUTED)

    def test_the_app_having_let_go_is_said_in_red(self):
        panel, _ = _drawn(Osr2Line(state="control_off"))
        assert _has(panel, RED)

    def test_the_word_starts_in_one_place_whatever_it_says(self):
        def where_it_starts(state: str) -> int:
            panel, _ = _drawn(Osr2Line(state=state))
            pixels = np.array(panel.image.convert("RGB"))
            inked = (pixels == np.array(COLORS[state])).all(axis=-1).any(axis=0)
            return int(np.flatnonzero(inked)[0])

        told_from_the_label = [state for state in LABELS if COLORS[state] != TEXT_MUTED]
        assert len({where_it_starts(state) for state in told_from_the_label}) == 1


class TestTheControlsOnIt:
    def test_a_line_with_no_controls_is_just_the_label_and_the_pill(self):
        section = Osr2Section()
        bare = Osr2Line(state=Osr2State.OFF)
        assert section.width(bare) < section.width(
            Osr2Line(state=Osr2State.OFF, controls=(_park(),)))

    def test_each_control_comes_back_as_a_target_where_it_was_drawn(self):
        park = _park()
        _panel, placed = _drawn(Osr2Line(state=Osr2State.OFF, controls=(park,)))
        assert [button for _rect, button in placed] == [park]
        (x, y, w, h), _button = placed[0]
        assert (x, y, w, h) == (10, 10, park.width, HEIGHT)


class TestTheMaxIntensityOnIt:
    def test_a_line_carrying_the_max_intensity_is_wider_by_its_slider(self):
        bare = Osr2Line(state=Osr2State.ROBOT_HAND)
        assert Osr2Section().width(bare) < Osr2Section().width(
            Osr2Line(state=Osr2State.ROBOT_HAND, max_intensity=60))


    def test_a_press_along_the_slider_asks_for_the_max_intensity_under_it(self):
        line = Osr2Line(state=Osr2State.ROBOT_HAND, max_intensity=60)
        (band,) = Osr2Section().bands(10, 10, line)
        x, y, w, h = band.rect

        assert track_command(band, x, y + h // 2) == "max_intensity_0"
        assert track_command(band, x + w - 1, y + h // 2) == "max_intensity_100"
        assert 10 + Osr2Section().width(Osr2Line(state=Osr2State.ROBOT_HAND)) < x
        assert (y, h) == (10, HEIGHT)

    def test_the_slider_holds_still_whatever_word_the_line_shows(self):
        section = Osr2Section()
        lines = [Osr2Line(state=state, max_intensity=60) for state in LABELS]

        assert len({section.width(line) for line in lines}) == 1
        assert len({section.bands(10, 10, line)[0].rect for line in lines}) == 1

    def test_a_line_with_no_max_intensity_has_no_slider_to_press(self):
        assert Osr2Section().bands(10, 10, Osr2Line(state=Osr2State.ROBOT_HAND)) == []


    def test_the_slider_is_filled_in_blue_as_far_as_the_max_intensity_goes(self):
        def filled(max_intensity: int) -> int:
            line = Osr2Line(state=Osr2State.ROBOT_HAND, max_intensity=max_intensity)
            panel, _ = _drawn(line)
            (band,) = Osr2Section().bands(10, 10, line)
            x, y, w, h = band.rect
            pixels = np.array(panel.image.convert("RGB"))[y:y + h, x:x + w]
            return int((pixels == np.array(BLUE)).all(axis=-1).sum())

        assert 0 < filled(20) < filled(80)

    def test_the_slider_says_its_level_as_a_number_beside_it(self):
        def left_of_the_bar(max_intensity: int) -> np.ndarray:
            line = Osr2Line(state=Osr2State.ROBOT_HAND, max_intensity=max_intensity)
            panel, _ = _drawn(line)
            (band,) = Osr2Section().bands(10, 10, line)
            x, y, _w, h = band.rect
            return np.array(panel.image.convert("RGB"))[y:y + h, :x]

        assert (left_of_the_bar(23) > 200).all(axis=-1).any()
        assert not np.array_equal(left_of_the_bar(23), left_of_the_bar(87))

    def test_the_slider_names_itself_where_it_was_drawn(self):
        line = Osr2Line(state=Osr2State.ROBOT_HAND, max_intensity=60)
        _panel, placed = _drawn(line)
        (band,) = Osr2Section().bands(10, 10, line)

        assert (band.rect, Button("", "", MAX_INTENSITY_TIP)) in placed


    def test_the_device_running_itself_leaves_nothing_for_the_max_intensity_to_hold(self):
        (band,) = Osr2Section().bands(10, 10, Osr2Line(state=Osr2State.AUTO, max_intensity=60))

        assert band.dim is True


def _park() -> Button:
    return Button("robot_hand_park", "P", "Parked")


class TestWhoTheLineNames:
    """One precedence, wherever the line is drawn: the device running itself
    beats anything the room is doing to it, a hold or a let-go beats whoever
    would otherwise be driving, and only then does the driver get named."""

    def test_the_driver_is_named_when_nothing_is_holding_the_device(self):
        assert state_for(Osr2State.ROBOT_HAND, "") == Osr2State.ROBOT_HAND

    def test_a_hold_is_named_ahead_of_whoever_would_have_been_driving(self):
        for control in ("control_off", "parked", "retracted"):
            assert state_for(Osr2State.FUNSCRIPT, control) == control

    def test_the_device_running_itself_beats_even_a_hold(self):
        assert state_for(Osr2State.AUTO, "parked") == Osr2State.AUTO

    def test_a_panel_that_knows_better_says_who_is_driving(self):
        assert state_for(Osr2State.OFF, "", driving=Osr2State.FUNSCRIPT) == Osr2State.FUNSCRIPT

    def test_a_composed_trace_names_whoever_it_drew_at_the_playhead(self):
        handoff = ((0, "funscript"), (40, "robot_hand"))
        for driven, word in (("funscript", Osr2State.FUNSCRIPT),
                             ("robot_hand", Osr2State.ROBOT_HAND), ("neutral", BUFFER)):
            drive = DriveHud(driven=driven, segments=handoff)
            assert driving_at_the_playhead(drive, Osr2State.OFF) == word

    def test_no_composed_trace_leaves_the_wire_to_say_it(self):
        assert driving_at_the_playhead(None, Osr2State.ROBOT_HAND) == ""
