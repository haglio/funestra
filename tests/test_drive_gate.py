from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from funestra.descent_latch import DescentChoice, DescentLatch, DriveKey
from funestra.drive_gate import DriveGate, next_handoff_touch
from funestra.funscript import Funscript
from funestra.osr2_visualizer import DRIVEN_BY_FUNSCRIPT, TRACE_SAMPLES, DriveHud

SPAN_S = 7.9
STEP_MS = 100
FIRST_VIDEO = Path("videos/Jane Doe - scene one.mp4")
SECOND_VIDEO = Path("videos/Jane Doe - scene two.mp4")
CHOSEN_TOUCH_MS = 3_600
NEWER_BY_MS = 200


def _a_motion_on_the_park(ms: int = 0, **over) -> DriveHud:
    steps = ms / STEP_MS
    base = {
        "speed": 50, "amplitude": 100, "center": 50, "trace_seconds": SPAN_S,
        "waveform": tuple(0.5 - 0.5 * np.cos((i + steps) / 6) for i in range(TRACE_SAMPLES))}
    base.update(over)
    return DriveHud(**base)


def _script() -> Funscript:
    return Funscript(actions=[(t, 0 if (t // 200) % 2 else 100)
                              for t in range(8_000, 9_001, 200)])


class FakeSession:
    def __init__(self) -> None:
        self.funscript_as_played = _script()
        self.current_video = FIRST_VIDEO
        self.position_ms = 0.0
        self.speed = 1.0


def _gate_holding_a_forecast() -> tuple[DriveGate, FakeSession]:
    session = FakeSession()
    gate = DriveGate(session)
    gate.visualizer(_a_motion_on_the_park())
    assert gate.handoff_touch() == CHOSEN_TOUCH_MS
    return gate, session


def _a_newer_publish_arrives(gate: DriveGate) -> None:
    gate.visualizer(_a_motion_on_the_park(NEWER_BY_MS))


class TestChoosingAForecast:
    def test_the_trace_chooses_a_touch_down_for_the_boundary_ahead(self):
        gate = DriveGate(FakeSession())

        gate.visualizer(_a_motion_on_the_park())

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_with_no_motion_published_there_is_nothing_to_choose_from(self):
        gate = DriveGate(FakeSession())

        gate.visualizer(None)

        assert gate.handoff_touch() is None


class TestTheDeviceRunningItself:
    def test_the_publish_is_drawn_whole_rather_than_composed_with_the_script(self):
        session = FakeSession()
        gate = DriveGate(session)
        published = _a_motion_on_the_park()

        hud = gate.visualizer(published, device_drives_itself=True)

        assert hud.waveform == published.waveform
        assert hud.segments == ()

    def test_with_nothing_published_there_is_still_a_visualizer_to_draw(self):
        gate = DriveGate(FakeSession())

        assert gate.visualizer(None, device_drives_itself=True) is not None

    def test_no_forecast_survives_the_device_taking_itself(self):
        gate, _session = _gate_holding_a_forecast()

        gate.visualizer(_a_motion_on_the_park(NEWER_BY_MS), device_drives_itself=True)

        assert gate.handoff_touch() is None


class TestTheVideoUnderGenau:
    def test_genaus_publish_is_drawn_whole_while_genau_has_the_screen(self):
        gate = DriveGate(FakeSession())
        published = _a_motion_on_the_park()

        hud = gate.visualizer(published, video_shows=False)

        assert hud.waveform == published.waveform
        assert hud.segments == ()

    def test_no_forecast_survives_genau_taking_the_screen(self):
        gate, _session = _gate_holding_a_forecast()

        gate.visualizer(_a_motion_on_the_park(NEWER_BY_MS), video_shows=False)

        assert gate.handoff_touch() is None

    def test_genau_driving_on_its_own_screen_is_genau_seen_live_for_the_video_under_it(self):
        gate = DriveGate(FakeSession())
        gate.visualizer(_a_motion_on_the_park(), video_shows=False)

        hud = gate.visualizer(_a_motion_on_the_park(let_go=0.44))

        assert hud.let_go == 0.44


class TestAChoiceIsHeldBecauseRereadEveryFrameTheSeamFlickered:
    def test_a_newer_publish_does_not_move_it(self):
        gate, _session = _gate_holding_a_forecast()

        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_a_frames_worth_of_playing_does_not_move_it(self):
        gate, session = _gate_holding_a_forecast()

        session.position_ms = 40
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_a_second_frame_does_not_move_it_either_since_each_step_is_measured_from_the_frame_before_never_from_the_start(self):
        gate, session = _gate_holding_a_forecast()

        for ms in (300, 600):
            session.position_ms = ms
            _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_a_stall_too_short_to_be_a_pause_does_not_move_it(self):
        gate, session = _gate_holding_a_forecast()
        for _ in range(5):
            gate.visualizer(_a_motion_on_the_park())

        session.position_ms = 40
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_a_pause_still_running_does_not_move_it(self):
        gate, _session = _gate_holding_a_forecast()

        for _ in range(40):
            _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_publishes_whose_age_beats_against_the_frame_clock_do_not_move_it(self):
        gate, session = _gate_holding_a_forecast()

        for frame, age in enumerate((70, 130, 190, 250, 310), start=1):
            session.position_ms = 40 * frame
            gate.visualizer(_a_motion_on_the_park(age))

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS


    @pytest.mark.parametrize("moved_to_ms", [40, 300, 600, -300, 900, -250, -251, 400, 401, 940])
    def test_at_every_playhead_a_case_moves_to_a_re_choice_can_be_told_from_a_carry(self, moved_to_ms):
        gate, session = _gate_holding_a_forecast()
        gate.visualizer(None)

        session.position_ms = moved_to_ms
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS


class TestWhatVoidsAChoice:
    def test_a_stint_with_nothing_published(self):
        gate, _session = _gate_holding_a_forecast()

        gate.visualizer(None)
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_a_different_video(self):
        gate, session = _gate_holding_a_forecast()

        session.current_video = SECOND_VIDEO
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_a_rewind_leaves_nothing_chosen_since_the_old_touch_would_cut_the_realigned_wave_anywhere(self):
        gate, session = _gate_holding_a_forecast()

        session.position_ms = -300
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() is None

    def test_a_jump_forward_since_a_choice_is_carried_only_through_one_continuous_approach(self):
        gate, session = _gate_holding_a_forecast()

        session.position_ms = 900
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_the_end_of_a_pause_long_enough_to_slide_the_wave(self):
        gate, session = _gate_holding_a_forecast()
        for _ in range(26):
            gate.visualizer(_a_motion_on_the_park())

        session.position_ms = 40
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS


class TestExactlyWhereTheseRulesBeginEachFigureTunedOnARealDevice:
    def test_a_step_back_the_width_of_the_window_is_still_playing_since_the_trace_s_grid_makes_some_frames_read_as_going_backward(self):
        gate, session = _gate_holding_a_forecast()

        session.position_ms = -250
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_one_millisecond_further_back_is_a_rewind(self):
        gate, session = _gate_holding_a_forecast()

        session.position_ms = -251
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_a_slow_frame_may_carry_the_playhead_this_far_forward(self):
        gate, session = _gate_holding_a_forecast()

        session.position_ms = 400
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_one_millisecond_further_on_is_a_jump(self):
        gate, session = _gate_holding_a_forecast()

        session.position_ms = 401
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_twenty_five_standing_frames_are_not_yet_a_pause(self):
        gate, session = _gate_holding_a_forecast()
        for _ in range(24):
            gate.visualizer(_a_motion_on_the_park())

        session.position_ms = 40
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS

    def test_twenty_six_of_them_are(self):
        gate, session = _gate_holding_a_forecast()
        for _ in range(25):
            gate.visualizer(_a_motion_on_the_park())

        session.position_ms = 40
        _a_newer_publish_arrives(gate)

        assert gate.handoff_touch() != CHOSEN_TOUCH_MS

    def test_a_pause_a_seek_ended_is_voided_once_and_not_again(self):
        gate, session = _gate_holding_a_forecast()
        for _ in range(30):
            gate.visualizer(_a_motion_on_the_park())
        session.position_ms = 900
        _a_newer_publish_arrives(gate)
        chosen_where_it_landed = gate.handoff_touch()

        session.position_ms = 940
        gate.visualizer(_a_motion_on_the_park(NEWER_BY_MS * 2))

        assert gate.handoff_touch() == chosen_where_it_landed


class TestHowFastTheVideoIsRunning:
    def test_the_touch_is_chosen_at_the_rate_the_video_is_playing_at(self):
        session = FakeSession()
        session.speed = 2.0
        gate = DriveGate(session)

        gate.visualizer(_a_motion_on_the_park())

        assert gate.handoff_touch() not in (None, CHOSEN_TOUCH_MS)


class TestWhetherGenauHasBeenSeenLiveHere:
    def test_a_handoff_from_before_this_video_is_read_as_still_live(self):
        gate = DriveGate(FakeSession())

        hud = gate.visualizer(_a_motion_on_the_park(let_go=0.44))

        assert hud.let_go is None

    def test_once_genau_has_been_seen_live_a_handoff_is_honored(self):
        gate = DriveGate(FakeSession())
        gate.visualizer(_a_motion_on_the_park())

        hud = gate.visualizer(_a_motion_on_the_park(let_go=0.44))

        assert hud.let_go == 0.44

    def test_a_new_video_makes_genau_prove_itself_live_again(self):
        session = FakeSession()
        gate = DriveGate(session)
        gate.visualizer(_a_motion_on_the_park())

        session.current_video = SECOND_VIDEO
        hud = gate.visualizer(_a_motion_on_the_park(let_go=0.44))

        assert hud.let_go is None

    def test_a_stint_with_nothing_published_does_not_re_arm_it_since_the_device_is_still_where_genau_left_it(self):
        gate = DriveGate(FakeSession())
        gate.visualizer(_a_motion_on_the_park())

        gate.visualizer(None)
        hud = gate.visualizer(_a_motion_on_the_park(let_go=0.44))

        assert hud.let_go == 0.44

    @pytest.mark.parametrize("what_moved", ["a rewind", "a jump forward", "a pause"])
    def test_nothing_that_only_voids_a_forecast_re_arms_it_since_in_the_same_video_the_published_handoff_still_describes_the_device(self, what_moved):
        session = FakeSession()
        gate = DriveGate(session)
        gate.visualizer(_a_motion_on_the_park())
        if what_moved == "a pause":
            for _ in range(30):
                gate.visualizer(_a_motion_on_the_park())
        session.position_ms = {"a rewind": -300, "a jump forward": 900,
                               "a pause": 40}[what_moved]

        hud = gate.visualizer(_a_motion_on_the_park(NEWER_BY_MS, let_go=0.44))

        assert hud.let_go == 0.44


class TestALoopingFunestra:
    def test_the_trace_is_drawn_from_the_script_as_the_funestra_will_play_it(self):
        swings = Funscript(actions=[(0, 0), (1_250, 100), (2_500, 0), (3_760, 100), (5_010, 0)])
        session = FakeSession()
        session.current_funscript = swings
        session.funscript_as_played = swings.looped(0, 5_000)
        session.position_ms = 4_000.0

        hud = DriveGate(session).visualizer(_a_motion_on_the_park(4_000))

        assert hud.segments == ((0, DRIVEN_BY_FUNSCRIPT),)


class TestAFunestraHeldDownByTheMaxIntensity:
    def test_its_script_is_drawn_as_shallow_as_it_is_sent(self):
        swings = Funscript(actions=[(t, 0 if (t // 200) % 2 else 100)
                                    for t in range(0, 20_001, 200)])
        session = FakeSession()
        session.funscript_as_played = swings
        session.max_intensity = 30

        hud = DriveGate(session).visualizer(_a_motion_on_the_park())

        assert hud.waveform == swings.planned_trace_window(
            0, round(SPAN_S * 1000), TRACE_SAMPLES, max_intensity=30)[0][:TRACE_SAMPLES]


class TestAHostOnAnOlderBranchRunningOnTheSameInstall:
    def test_is_drawn_from_the_script_it_has(self):
        session = FakeSession()
        session.current_funscript = session.funscript_as_played
        del session.funscript_as_played
        gate = DriveGate(session)

        gate.visualizer(_a_motion_on_the_park())

        assert gate.handoff_touch() == CHOSEN_TOUCH_MS


class TestTheTouchTheTraceChose:
    BOUNDARY_MS = 3_000
    TOUCHING = DriveKey(center=50, amplitude=100, speed=50, let_go=None)

    @classmethod
    def _latched(cls, top: float = 0.35, touch: int | None = 3_600,
                 key: DriveKey | None = None) -> DescentLatch:
        latch = DescentLatch()
        latch.remember(cls.BOUNDARY_MS,
                       DescentChoice(key=key or cls.TOUCHING, top=top, touch=touch),
                       stale_before=0)
        return latch

    def test_an_unscripted_video_has_no_handoff_to_chose_one_for(self):
        assert next_handoff_touch(None, 0, self._latched()) is None

    def test_resting_before_a_turn_takes_the_turn_it_is_approaching(self):
        assert next_handoff_touch(_script(), 0, self._latched()) == 3_600

    def test_inside_a_turn_it_takes_the_boundary_just_crossed_which_the_arbiter_is_still_ending(self):
        assert next_handoff_touch(_script(), 5_000, self._latched()) == 3_600

    def test_a_rest_with_no_turn_after_it_has_no_boundary_at_all_whatever_the_latch_still_holds(self):
        assert next_handoff_touch(_script(), 20_000, self._latched()) is None

    def test_a_boundary_with_nothing_latched_yet_says_so(self):
        assert next_handoff_touch(_script(), 0, DescentLatch()) is None

    def test_a_ramped_handoff_has_no_touch_down_to_name(self):
        ramped = self._latched(
            top=0.12, touch=None,
            key=DriveKey(center=50, amplitude=80, speed=50, let_go=None))

        assert next_handoff_touch(_script(), 0, ramped) is None
