from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from shared_ui.palette import BLUE, GREEN, TEXT_MUTED

from funestra import hud_osr2
from funestra.hud import Hud
from funestra.hud_button import Button
from funestra.hud_osr2 import (
    BUFFER,
    COLORS,
    HEIGHT,
    LABELS,
    MAX_INTENSITY_TIP,
    Osr2Line,
    Osr2Section,
    VisualizerResolver,
    driving_at_the_playhead,
    line_shown_for,
    state_for,
)
from funestra.main_hud import OSR2_DRIVING, OSR2_PARKED, OSR2_RETRACTED, MainHudModel
from funestra.modes import Osr2State
from funestra.osr2_visualizer import (
    DRIVEN_BY_AUTO,
    DRIVEN_BY_FUNSCRIPT,
    DRIVEN_BY_NOTHING,
    DRIVEN_BY_ROBOT_HAND,
    DriveHud,
    trace_ink,
    track_command,
)
from funestra.satellite_hud import HudModel


def _drawn(line: Osr2Line) -> tuple[Hud, list]:
    section = Osr2Section()
    hud = Hud(section.width(line) + 20, HEIGHT + 20)
    placed = section.draw(hud.image, hud.draw, (10, 10), line)
    return hud, placed


def _has(hud: Hud, color) -> bool:
    pixels = np.array(hud.image.convert("RGB"))
    return bool((pixels == np.array(color)).all(axis=-1).any())


def test_only_the_two_hud_painters_in_this_package_draw_the_device_line_a_host_saying_what_its_line_shows_through_its_model():
    users = {module.name for module in Path(hud_osr2.__file__).parent.glob("*.py")
             if module.name != "hud_osr2.py" and "Osr2Section" in module.read_text(encoding="utf-8")}

    assert users == {"main_hud_painter.py", "satellite_hud_paint.py"}


def test_each_drivers_word_is_written_in_the_ink_its_stretch_of_the_trace_is_drawn_in():
    assert COLORS[Osr2State.AUTO] == trace_ink(DRIVEN_BY_AUTO)
    assert COLORS[Osr2State.FUNSCRIPT] == trace_ink(DRIVEN_BY_FUNSCRIPT)
    assert COLORS[Osr2State.ROBOT_HAND] == trace_ink(DRIVEN_BY_ROBOT_HAND)


def test_buffer_is_the_pill_s_own_word_drawn_and_never_one_of_the_states_the_wire_carries():
    assert hud_osr2.BUFFER not in {state.value for state in Osr2State}


class TestTheLine:
    def test_it_names_who_has_the_device(self):
        assert LABELS[Osr2State.FUNSCRIPT] == "FunScript"
        assert LABELS[Osr2State.ROBOT_HAND] == "Robot Hand"

    def test_a_funscript_driving_is_said_in_green(self):
        hud, _ = _drawn(Osr2Line(state=Osr2State.FUNSCRIPT))
        assert _has(hud, GREEN)

    def test_the_motion_driving_is_said_in_blue(self):
        hud, _ = _drawn(Osr2Line(state=Osr2State.ROBOT_HAND))
        assert _has(hud, BLUE)

    def test_nothing_driving_is_said_in_the_muted_gray(self):
        hud, _ = _drawn(Osr2Line(state=Osr2State.OFF))
        assert _has(hud, TEXT_MUTED)

    @pytest.mark.parametrize(("state", "word"), [(Osr2State.UNPLUGGED, "Unplugged"),
                                                 (Osr2State.NO_ANSWER, "No answer")])
    def test_an_osr2_the_computer_cannot_hear_is_named_for_why_in_the_gray_of_off(
        self, state, word,
    ):
        hud, _ = _drawn(Osr2Line(state=state))
        assert LABELS[state] == word
        assert _has(hud, TEXT_MUTED)

    def test_the_word_starts_in_one_place_whatever_it_says(self):
        def where_it_starts(state: str) -> int:
            hud, _ = _drawn(Osr2Line(state=state))
            pixels = np.array(hud.image.convert("RGB"))
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
        _hud, placed = _drawn(Osr2Line(state=Osr2State.OFF, controls=(park,)))
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
        (bar,) = Osr2Section().bars(10, 10, line)
        x, y, w, h = bar.rect

        assert track_command(bar, x, y + h // 2) == "max_intensity_0"
        assert track_command(bar, x + w - 1, y + h // 2) == "max_intensity_100"
        assert 10 + Osr2Section().width(Osr2Line(state=Osr2State.ROBOT_HAND)) < x
        assert (y, h) == (10, HEIGHT)

    def test_the_slider_holds_still_whatever_word_the_line_shows(self):
        section = Osr2Section()
        lines = [Osr2Line(state=state, max_intensity=60) for state in LABELS]

        assert len({section.width(line) for line in lines}) == 1
        assert len({section.bars(10, 10, line)[0].rect for line in lines}) == 1

    def test_a_line_with_no_max_intensity_has_no_slider_to_press(self):
        assert Osr2Section().bars(10, 10, Osr2Line(state=Osr2State.ROBOT_HAND)) == []


    def test_the_slider_is_filled_in_blue_as_far_as_the_max_intensity_goes(self):
        def filled(max_intensity: int) -> int:
            line = Osr2Line(state=Osr2State.ROBOT_HAND, max_intensity=max_intensity)
            hud, _ = _drawn(line)
            (bar,) = Osr2Section().bars(10, 10, line)
            x, y, w, h = bar.rect
            pixels = np.array(hud.image.convert("RGB"))[y:y + h, x:x + w]
            return int((pixels == np.array(BLUE)).all(axis=-1).sum())

        assert 0 < filled(20) < filled(80)

    def test_the_slider_says_its_level_as_a_number_beside_it(self):
        def left_of_the_bar(max_intensity: int) -> np.ndarray:
            line = Osr2Line(state=Osr2State.ROBOT_HAND, max_intensity=max_intensity)
            hud, _ = _drawn(line)
            (bar,) = Osr2Section().bars(10, 10, line)
            x, y, _w, h = bar.rect
            return np.array(hud.image.convert("RGB"))[y:y + h, :x]

        assert (left_of_the_bar(23) > 200).all(axis=-1).any()
        assert not np.array_equal(left_of_the_bar(23), left_of_the_bar(87))

    def test_the_slider_names_itself_where_it_was_drawn(self):
        line = Osr2Line(state=Osr2State.ROBOT_HAND, max_intensity=60)
        _hud, placed = _drawn(line)
        (bar,) = Osr2Section().bars(10, 10, line)

        assert (bar.rect, Button("", "", MAX_INTENSITY_TIP)) in placed


    def test_the_device_running_itself_leaves_nothing_for_the_max_intensity_to_hold(self):
        (bar,) = Osr2Section().bars(10, 10, Osr2Line(state=Osr2State.AUTO, max_intensity=60))

        assert bar.dim is True


def _park() -> Button:
    return Button("robot_hand_park", "P", "Parked")


class TestWhoTheLineNamesAsItsHostResolvedItSinceEachHudAnswersThatFromItsOwnInputs:
    def test_the_driver_is_named_when_nothing_is_holding_the_device(self):
        assert state_for(Osr2State.ROBOT_HAND, "") == Osr2State.ROBOT_HAND

    def test_a_hold_is_named_ahead_of_whoever_would_have_been_driving(self):
        for control in ("parked", "retracted"):
            assert state_for(Osr2State.FUNSCRIPT, control) == control

    def test_the_device_running_itself_beats_even_a_hold(self):
        assert state_for(Osr2State.AUTO, "parked") == Osr2State.AUTO

    def test_a_switched_off_device_beats_even_a_hold(self):
        for control in ("parked", "retracted"):
            assert state_for(Osr2State.OFF, control) == Osr2State.OFF

    def test_a_paused_room_is_named_parked_ahead_of_whoever_would_have_been_driving(self):
        assert state_for(Osr2State.ROBOT_HAND, OSR2_DRIVING, paused=True) == OSR2_PARKED
        assert state_for(Osr2State.ROBOT_HAND, OSR2_DRIVING, driving=Osr2State.FUNSCRIPT,
                         paused=True) == OSR2_PARKED

    @pytest.mark.parametrize("osr2", [Osr2State.AUTO, Osr2State.OFF, Osr2State.UNPLUGGED,
                                      Osr2State.NO_ANSWER])
    def test_the_device_running_itself_or_switched_off_beats_a_paused_room(self, osr2):
        assert state_for(osr2, OSR2_DRIVING, paused=True) == osr2

    def test_a_retracted_switch_keeps_its_own_word_through_a_paused_room(self):
        assert state_for(Osr2State.ROBOT_HAND, OSR2_RETRACTED, paused=True) == OSR2_RETRACTED

    def test_a_hud_that_knows_better_says_who_is_driving(self):
        assert state_for(Osr2State.ROBOT_HAND, "", driving=Osr2State.FUNSCRIPT) == Osr2State.FUNSCRIPT

    def test_a_switched_off_device_beats_whoever_a_hud_drew_driving(self):
        assert state_for(Osr2State.OFF, "", driving=Osr2State.FUNSCRIPT) == Osr2State.OFF

    @pytest.mark.parametrize("unheard", [Osr2State.UNPLUGGED, Osr2State.NO_ANSWER])
    def test_an_osr2_the_computer_cannot_hear_beats_a_hold_and_a_driver_as_off_does(
        self, unheard,
    ):
        assert state_for(unheard, "parked") == unheard
        assert state_for(unheard, "", driving=Osr2State.FUNSCRIPT) == unheard


class TestTheVisualizerUnderIt:
    @pytest.mark.parametrize("unheard", [Osr2State.OFF, Osr2State.UNPLUGGED, Osr2State.NO_ANSWER])
    def test_an_osr2_the_computer_cannot_hear_is_drawn_with_nothing_driving_it(self, unheard):
        drive = VisualizerResolver(clock=lambda: 0.0).resolve(
            DriveHud(waveform=(0.5, 0.6)), osr2=unheard, control="", composed=False)

        assert drive.driven == DRIVEN_BY_NOTHING

    def test_a_composed_trace_names_whoever_it_drew_at_the_playhead_since_the_wire_s_word_lags_the_arbiter_by_seconds(self):
        handoff = ((0, "funscript"), (40, "robot_hand"))
        for driven, word in (("funscript", Osr2State.FUNSCRIPT),
                             ("robot_hand", Osr2State.ROBOT_HAND), ("neutral", BUFFER)):
            drive = DriveHud(driven=driven, segments=handoff)
            assert driving_at_the_playhead(drive, Osr2State.OFF, composed=True) == word

    def test_no_composed_trace_leaves_the_wire_to_say_it(self):
        assert driving_at_the_playhead(None, Osr2State.ROBOT_HAND, composed=True) == ""

    def test_a_trace_with_no_handoffs_drawn_on_it_leaves_the_wire_to_say_it(self):
        drive = DriveHud(driven="funscript")

        assert driving_at_the_playhead(drive, Osr2State.ROBOT_HAND, composed=True) == ""

    def test_a_trace_the_funestra_did_not_compose_for_its_video_leaves_the_wire_to_say_it(self):
        drive = DriveHud(driven="funscript", segments=((0, "funscript"), (40, "robot_hand")))

        assert driving_at_the_playhead(drive, Osr2State.ROBOT_HAND, composed=False) == ""


class TestTheLineAHudShows:
    _HANDOFF = ((0, "funscript"), (40, "robot_hand"))

    def test_the_pill_names_whoever_the_composed_trace_has_at_the_playhead_over_the_wire_s_word(self):
        model = MainHudModel(osr2=Osr2State.FUNSCRIPT, osr2_control=OSR2_DRIVING)
        drive = DriveHud(driven="neutral", segments=self._HANDOFF)

        assert line_shown_for(model, drive, composed=True).state == BUFFER

    def test_a_hold_is_named_over_whoever_the_trace_has(self):
        model = HudModel("portrait", osr2=Osr2State.FUNSCRIPT, osr2_control=OSR2_PARKED)
        drive = DriveHud(driven="robot_hand", segments=self._HANDOFF)

        assert line_shown_for(model, drive, composed=True).state == OSR2_PARKED

    def test_a_paused_funestra_reads_parked(self):
        model = HudModel("portrait", osr2=Osr2State.ROBOT_HAND, osr2_control=OSR2_DRIVING, paused=True)

        assert line_shown_for(model, None, composed=False).state == OSR2_PARKED

    def test_it_carries_the_hud_s_own_controls_and_max_intensity(self):
        park = _park()
        model = MainHudModel(osr2=Osr2State.ROBOT_HAND, osr2_controls=(park,), max_intensity=60)

        assert line_shown_for(model, None, composed=False) == Osr2Line(
            state=Osr2State.ROBOT_HAND, controls=(park,), max_intensity=60)
