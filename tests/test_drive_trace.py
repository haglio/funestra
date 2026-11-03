from __future__ import annotations

from itertools import pairwise

import numpy as np
import pytest

from funestra.descent_latch import DescentLatch
from funestra.drive_gate import next_handoff_touch
from funestra.drive_trace import osr2_visualizer
from funestra.funscript import HANDOFF_RAMP_MS, Funscript
from funestra.osr2_visualizer import (
    DRIVEN_BY_FUNSCRIPT,
    DRIVEN_BY_NEUTRAL,
    DRIVEN_BY_NOTHING,
    DRIVEN_BY_ROBOT_HAND,
    POSITION_MAX,
    TRACE_SAMPLES,
    DriveHud,
)
from funestra.playback_rate import MAX_RATE

SPAN_S = 7.9
STEP_MS = 100
RAMP_STEPS = HANDOFF_RAMP_MS // STEP_MS


def _motion(**over) -> DriveHud:
    base = {
        "speed": 50, "amplitude": 80, "center": 50, "trace_seconds": SPAN_S,
        "waveform": tuple(0.5 + 0.4 * np.sin(i / 6) for i in range(TRACE_SAMPLES))}
    base.update(over)
    return DriveHud(**base)


def _motion_at(ms: int, **over) -> DriveHud:
    steps = ms / STEP_MS
    return _motion(
        waveform=tuple(0.5 + 0.4 * np.sin((i + steps) / 6)
                       for i in range(TRACE_SAMPLES)),
        **over)


def _parked_motion(**over) -> DriveHud:
    over.setdefault("let_go", 0.8)
    over.setdefault(
        "waveform",
        tuple(0.5 - 0.4 * np.cos(i / 6) for i in range(TRACE_SAMPLES)))
    return _motion(**over)


def _script(*, until_ms: int) -> Funscript:
    return Funscript(actions=[(t, 0 if (t // 200) % 2 else 100)
                              for t in range(0, until_ms + 1, 200)])


def _script_ahead(*, from_ms: int = 8_000, to_ms: int = 9_000) -> Funscript:
    return Funscript(actions=[(t, 0 if (t // 200) % 2 else 100)
                              for t in range(from_ms, to_ms + 1, 200)])


def _read(script, *, at: int, published=None, latch=None) -> DriveHud:
    return osr2_visualizer(
        published if published is not None else _motion(),
        script=script, position_ms=at, latch=latch)


def _colors(hud: DriveHud) -> list[str]:
    return [who for _start, _end, who in hud.runs]


class TestOneLineTwoDrivers:
    def test_a_script_running_the_whole_span_is_all_its_own(self):
        script = _script(until_ms=120_000)

        hud = _read(script, at=0)

        assert hud.segments == ((0, DRIVEN_BY_FUNSCRIPT),)
        assert hud.waveform == script.planned_trace_window(
            0, round(SPAN_S * 1000), TRACE_SAMPLES)[0][:TRACE_SAMPLES]

    def test_a_script_under_a_max_intensity_is_drawn_as_shallow_as_the_device_is_sent(self):
        script = _script(until_ms=120_000)

        hud = osr2_visualizer(_motion(), script=script, position_ms=0, max_intensity=30)

        assert hud.waveform == script.planned_trace_window(
            0, round(SPAN_S * 1000), TRACE_SAMPLES, max_intensity=30)[0][:TRACE_SAMPLES]
        assert hud.position == round(POSITION_MAX * script.planned_position_at(
            0, 1.0, max_intensity=30) / 100)

    def test_the_end_of_a_scripted_stretch_hands_over_through_the_buffer(self):
        hud = _read(_script(until_ms=2_000), at=1_000,
                    published=_parked_motion())

        assert _colors(hud) == [
            DRIVEN_BY_FUNSCRIPT, DRIVEN_BY_NEUTRAL, DRIVEN_BY_ROBOT_HAND]

    def test_a_script_about_to_start_up_shows_the_motion_handing_over(self):
        hud = _read(_script_ahead(), at=0)

        assert _colors(hud) == [
            DRIVEN_BY_ROBOT_HAND, DRIVEN_BY_NEUTRAL, DRIVEN_BY_FUNSCRIPT]

    def test_the_runs_touch_so_the_line_never_breaks_at_the_joins(self):
        hud = _read(_script(until_ms=2_000), at=1_000,
                    published=_parked_motion())

        for left, right in pairwise(hud.runs):
            assert left[1] == right[0]

    def test_with_nothing_published_the_gap_is_nobody_s_and_rests_on_the_park(self):
        hud = osr2_visualizer(None, script=_script(until_ms=2_000), position_ms=0)
        gap_start = hud.runs[-1][0]

        assert _colors(hud) == [
            DRIVEN_BY_FUNSCRIPT, DRIVEN_BY_NEUTRAL, DRIVEN_BY_NOTHING]
        assert set(hud.waveform[gap_start:]) == {0.0}


class TestTheRampDownOntoThePark:
    def test_the_blue_runs_to_the_moment_the_script_turn_opens(self):
        script = _script_ahead()
        hud = _read(script, at=0)

        assert hud.runs[0][1] == 3_000 // STEP_MS

    def test_the_ramp_starts_where_the_motion_is_and_reaches_the_park(self):
        published = _motion()
        hud = _read(_script_ahead(), at=0, published=published)
        opens = 3_000 // STEP_MS

        assert hud.waveform[opens] == published.waveform[opens]
        descent = hud.waveform[opens:opens + RAMP_STEPS + 1]
        for left, right in pairwise(descent):
            assert right < left
        assert hud.waveform[opens + RAMP_STEPS] == 0.0

    def test_the_ramp_is_the_buffer_s_gray_not_genau_s_blue(self):
        hud = _read(_script_ahead(), at=0)

        assert hud.runs[1][2] == DRIVEN_BY_NEUTRAL

    def test_it_holds_still_as_the_trace_slides(self):
        script = _script_ahead()

        first = _read(script, at=0, published=_motion_at(0)).waveform
        later = _read(script, at=2 * STEP_MS,
                      published=_motion_at(2 * STEP_MS)).waveform

        assert later[:-2] == first[2:]

    def test_the_published_let_go_carries_the_ramp_after_the_flip(self):
        script = _script_ahead()

        after = _read(script, at=3_000, published=_parked_motion(let_go=0.73))

        assert after.waveform[0] == 0.73
        assert after.waveform[RAMP_STEPS] == 0.0

    def test_the_dot_walks_down_the_ramp_with_the_device(self):
        script = _script_ahead()
        published = _parked_motion(let_go=0.8)

        opened = _read(script, at=3_000, published=published)
        midway = _read(script, at=3_000 + HANDOFF_RAMP_MS // 2, published=published)
        landed = _read(script, at=3_000 + HANDOFF_RAMP_MS, published=published)

        assert opened.position == round(0.8 * POSITION_MAX)
        assert landed.position == 0
        assert landed.position < midway.position < opened.position


class TestTheClimbBackOut:
    def test_the_buffer_climbs_from_the_park_to_the_motion(self):
        published = _parked_motion()
        hud = _read(_script(until_ms=2_000), at=1_000, published=published)
        blue_start = hud.runs[-1][0]

        assert hud.waveform[blue_start - RAMP_STEPS] == 0.0
        rising = hud.waveform[blue_start - RAMP_STEPS:blue_start + 1]
        for left, right in pairwise(rising):
            assert right > left
        assert hud.waveform[blue_start] == published.waveform[0]

    def test_the_climb_is_the_buffer_s_gray_not_genau_s_blue(self):
        hud = _read(_script(until_ms=2_000), at=1_000, published=_parked_motion())

        assert hud.runs[-2][2] == DRIVEN_BY_NEUTRAL

    def test_the_climb_spends_no_motion(self):
        published = _parked_motion()
        hud = _read(_script(until_ms=2_000), at=1_000, published=published)
        blue_start = hud.runs[-1][0]

        assert hud.waveform[blue_start:] == published.waveform[:TRACE_SAMPLES - blue_start]

    def test_the_device_rests_on_the_park_before_the_climb(self):
        hud = _read(_script(until_ms=2_000), at=1_000, published=_parked_motion())
        blue_start = hud.runs[-1][0]

        assert hud.waveform[blue_start - RAMP_STEPS - 1] == 0.0

    def test_the_motion_resumes_at_the_far_end_of_the_quiet(self):
        script = _script(until_ms=2_000)
        hud = _read(script, at=1_000, published=_parked_motion())
        blue_start_ms = 1_000 + hud.runs[-1][0] * STEP_MS

        assert blue_start_ms == 2_000 + 5_000

    def test_a_motion_opening_on_the_park_needs_no_climb(self):
        published = _parked_motion(
            amplitude=100,
            waveform=tuple(0.5 - 0.5 * np.cos(i / 6) for i in range(TRACE_SAMPLES)))
        script = _script(until_ms=2_000)
        hud = _read(script, at=1_000, published=published)
        blue_start = hud.runs[-1][0]

        assert 1_000 + blue_start * STEP_MS == 2_000 + 3_000 + STEP_MS
        assert hud.waveform[blue_start] == published.waveform[1]


class TestAFloorOnTheParkEndsOnItsTouchDown:
    def _touching_motion(self, **over) -> DriveHud:
        over.setdefault(
            "waveform",
            tuple(0.5 + 0.5 * np.sin(i / 3) for i in range(TRACE_SAMPLES)))
        return _motion(amplitude=100, **over)

    def test_no_ramp_and_the_gray_runs_flat(self):
        hud = _read(_script_ahead(), at=0, published=self._touching_motion(),
                    latch=DescentLatch())
        blue_end = hud.runs[0][1]
        green_start = hud.runs[-1][0]

        assert _colors(hud) == [
            DRIVEN_BY_ROBOT_HAND, DRIVEN_BY_NEUTRAL, DRIVEN_BY_FUNSCRIPT]
        assert hud.waveform[blue_end] <= 0.03
        flat = hud.waveform[blue_end + 1:green_start - 10]
        assert max(flat) <= 0.03

    def test_the_blue_swings_past_the_boundary_to_the_touch(self):
        hud = _read(_script_ahead(), at=0, published=self._touching_motion(),
                    latch=DescentLatch())
        blue_end_ms = hud.runs[0][1] * STEP_MS

        assert blue_end_ms > 3_000

    def test_the_touch_is_selected_once(self):
        script = _script_ahead()
        latch = DescentLatch()

        first = _read(script, at=0, published=self._touching_motion(),
                      latch=latch)
        later = _read(script, at=0, published=self._touching_motion(
            waveform=tuple(0.5 + 0.5 * np.sin((i + 0.3) / 3)
                           for i in range(TRACE_SAMPLES))), latch=latch)

        assert later.runs[0][1] == first.runs[0][1]

    def test_the_extension_is_the_published_wave_itself(self):
        published = self._touching_motion()
        hud = _read(_script_ahead(), at=0, published=published, latch=DescentLatch())
        blue_end = hud.runs[0][1]

        feather_columns = 300 // STEP_MS
        for column in range(3_000 // STEP_MS, blue_end - feather_columns):
            assert hud.waveform[column] == published.waveform[column]
        for column in range(blue_end - feather_columns, blue_end):
            assert 0.0 <= hud.waveform[column] <= published.waveform[column] + 1e-9

    def test_a_far_boundary_stays_a_live_forecast(self):
        script = _script_ahead(from_ms=18_000, to_ms=19_000)
        latch = DescentLatch()

        _read(script, at=2_000, published=self._touching_motion(),
              latch=latch)
        assert latch.choice_for(13_000) is None

        _read(script, at=10_040, published=self._touching_motion(),
              latch=latch)
        assert latch.choice_for(13_000) is not None

    def test_a_raised_floor_still_ramps(self):
        hud = _read(_script_ahead(), at=0, latch=DescentLatch())
        opens = 3_000 // STEP_MS

        assert hud.runs[1][2] == DRIVEN_BY_NEUTRAL
        descent = hud.waveform[opens:opens + 5]
        for left, right in pairwise(descent):
            assert right < left


class TestTheDescentTopIsSelectedOnce:
    def test_the_held_top_does_not_move_with_the_publish(self):
        script = _script_ahead()
        latch = DescentLatch()
        opens = 3_000 // STEP_MS

        first = _read(script, at=0, published=_motion_at(0), latch=latch)
        later = _read(script, at=0, published=_motion_at(20), latch=latch)

        assert later.waveform[opens] == first.waveform[opens]

    def test_an_omnipause_park_re_selects_the_top(self):
        script = _script_ahead()
        latch = DescentLatch()
        opens = 3_000 // STEP_MS

        live = _read(script, at=0, published=_motion(), latch=latch)
        parked = _read(script, at=0, published=_parked_motion(let_go=0.44),
                       latch=latch)

        assert parked.waveform[opens] != live.waveform[opens]

    def test_the_wave_coming_live_again_re_selects_the_top(self):
        script = _script_ahead()
        latch = DescentLatch()
        opens = 3_000 // STEP_MS

        frozen = _read(script, at=0, published=_parked_motion(let_go=0.44),
                       latch=latch)
        resumed = _read(script, at=0, published=_motion_at(0), latch=latch)

        assert resumed.waveform[opens] != frozen.waveform[opens]

    @pytest.mark.parametrize(("control", "moved_to"), [
        ("amplitude", 90), ("center", 60), ("speed", 70),
    ])
    def test_moving_a_control_re_selects_the_top(self, control, moved_to):
        script = _script_ahead()
        opens = 3_000 // STEP_MS
        latch = DescentLatch()

        first = _read(script, at=0, published=_motion_at(0), latch=latch)
        moved = _read(script, at=0, published=_motion_at(20, **{control: moved_to}),
                      latch=latch)

        assert moved.waveform[opens] != first.waveform[opens]


class TestStillTrace:
    def test_a_motion_published_on_knots_is_read_where_its_knots_sit(self):
        published = _motion(slide=0.5, edge=0.5 + 0.4 * np.sin(TRACE_SAMPLES / 6))
        script = _script_ahead(from_ms=100_000, to_ms=101_000)

        composed = _read(script, at=0, published=published).waveform

        assert composed[0] == pytest.approx(
            (published.waveform[0] + published.waveform[1]) / 2)
        assert composed[TRACE_SAMPLES - 1] == pytest.approx(
            (published.waveform[TRACE_SAMPLES - 1] + published.edge) / 2)

    def test_the_shape_slides_along_rather_than_being_redrawn(self):
        script = _script(until_ms=120_000)

        first = _read(script, at=0).waveform
        later = _read(script, at=2 * STEP_MS).waveform

        assert later[:-2] == first[2:]

    def test_the_whole_handoff_slides_rigidly_too(self):
        script = _script(until_ms=2_000)
        published = _parked_motion()

        first = _read(script, at=1_000, published=published).waveform
        later = _read(script, at=1_000 + 2 * STEP_MS, published=published).waveform

        assert later[:-2] == first[2:]

    def test_a_playhead_between_two_samples_slides_the_stable_trace(self):
        script = _script(until_ms=120_000)

        at_knot = _read(script, at=0)
        between = _read(script, at=40)

        assert between.waveform == at_knot.waveform
        assert at_knot.slide == 0.0
        assert between.slide == 0.4

    def test_the_live_motion_reads_fixed_times_so_the_painter_slides_it(self):
        script = _script_ahead()

        traces = [
            _read(script, at=at, published=_motion_at(at)).waveform[1:20]
            for at in (0, 40, 80)
        ]

        for later in traces[1:]:
            for a, b in zip(traces[0], later, strict=True):
                assert abs(a - b) < 0.005


class TestPositionMarker:
    def test_a_script_driving_puts_the_marker_where_the_plan_has_the_device(self):
        script = _script(until_ms=120_000)

        hud = _read(script, at=400)

        assert hud.position == round(
            script.planned_position_at(400) / 100 * POSITION_MAX)

    def test_a_script_holding_the_device_parked_rests_the_marker_on_the_park(self):
        script = _script_ahead(from_ms=40_000, to_ms=41_000)

        hud = _read(script, at=37_000, published=_parked_motion())

        assert script.is_resting_at(37_000) is False
        assert hud.position == 0

    def test_genau_driving_leaves_the_marker_where_genau_published_it(self):
        published = _motion(position=1234)

        hud = _read(_script_ahead(), at=0, published=published)

        assert hud.position == 1234

    def test_the_dot_climbs_the_drawn_ramp_out_of_the_park(self):
        script = _script(until_ms=2_000)
        published = _parked_motion()

        resting = _read(script, at=4_500, published=published)
        midway = _read(script, at=5_000 + HANDOFF_RAMP_MS // 2, published=published)

        assert resting.position == 0
        assert 0 < midway.position < round(0.2 * POSITION_MAX)


class TestTheSeamCannotFlicker:
    def test_the_last_blue_column_sits_on_the_latched_top(self):
        latch = DescentLatch()
        published = _motion()
        hud = _read(_script_ahead(), at=1_000, published=published,
                    latch=latch)
        seam = hud.runs[0][1]

        top = latch.choice_for(3_000).top
        assert abs(hud.waveform[seam - 1] - top) < 0.12
        aged = _read(_script_ahead(), at=1_000, published=_motion_at(20),
                     latch=latch)
        assert abs(aged.waveform[seam - 1] - hud.waveform[seam - 1]) < 0.02


class TestForecastsDieWithTheirWave:
    def _touching(self, phase: float = 0.0, **over) -> DriveHud:
        over.setdefault(
            "waveform",
            tuple(0.5 + 0.5 * np.sin((i + phase) / 3) for i in range(TRACE_SAMPLES)))
        return _motion(amplitude=100, **over)

    def test_a_resume_re_chooses_the_touch_for_the_new_wave(self):
        script = _script_ahead()
        latch = DescentLatch()

        first = _read(script, at=0, published=self._touching(), latch=latch)
        _read(script, at=0, published=self._touching(let_go=0.0), latch=latch)
        moved = _read(script, at=0, published=self._touching(phase=9.4),
                      latch=latch)

        assert first.runs[0][1] != moved.runs[0][1]

    def test_a_parked_publish_never_seeds_a_pre_turn_latch(self):
        script = _script_ahead()
        latch = DescentLatch()

        _read(script, at=0, published=self._touching(let_go=0.0), latch=latch)

        assert latch.choice_for(3_000) is None

    def test_no_extension_is_drawn_off_a_parked_wave(self):
        script = _script_ahead()
        latch = DescentLatch()
        _read(script, at=2_800, published=self._touching(), latch=latch)

        landed = _read(script, at=3_120, published=self._touching(let_go=0.0),
                       latch=latch)

        assert DRIVEN_BY_ROBOT_HAND not in _colors(landed)


class TestThePillFollowsTheLine:
    def test_genau_while_the_dot_rides_the_extension(self):
        published = _motion(
            amplitude=100,
            waveform=tuple(0.5 + 0.5 * np.sin(i / 3) for i in range(TRACE_SAMPLES)))
        hud = _read(_script_ahead(), at=3_320, published=published,
                    latch=DescentLatch())

        assert hud.driven == DRIVEN_BY_ROBOT_HAND

    def test_buffer_through_the_gray(self):
        hud = _read(_script_ahead(), at=4_500, published=_parked_motion())

        assert hud.driven == DRIVEN_BY_NEUTRAL

    def test_funscript_through_the_cluster(self):
        hud = _read(_script(until_ms=120_000), at=1_000)

        assert hud.driven == DRIVEN_BY_FUNSCRIPT


class TestThePublishedTouch:
    def test_the_latched_touch_is_what_gets_published(self):
        script = _script_ahead()
        latch = DescentLatch()
        published = _motion(
            amplitude=100,
            waveform=tuple(0.5 + 0.5 * np.sin(i / 3) for i in range(TRACE_SAMPLES)))
        hud = _read(script, at=1_000, published=published, latch=latch)
        blue_end_ms = 1_000 + hud.runs[0][1] * STEP_MS

        assert next_handoff_touch(script, 1_000, latch) == latch.choice_for(3_000).touch
        assert next_handoff_touch(script, 3_200, latch) == latch.choice_for(3_000).touch
        assert abs(next_handoff_touch(script, 1_000, latch) - blue_end_ms) <= STEP_MS

    def test_the_status_reads_the_playhead_on_the_trace_s_grid(self):
        script = Funscript(actions=[(t, 0 if (t // 200) % 2 else 100)
                                  for t in range(8_005, 9_006, 200)])
        latch = DescentLatch()
        published = _motion(
            amplitude=100,
            waveform=tuple(0.5 + 0.5 * np.sin(i / 3) for i in range(TRACE_SAMPLES)))
        playheads = [*range(0, 2_960, 40), *range(2_960, 3_100),
                     *range(3_100, 11_960, 40), *range(11_960, 12_100)]

        disagreements = []
        for at in playheads:
            _read(script, at=at, published=published, latch=latch)
            on_the_grid = at - at % 40
            if next_handoff_touch(script, at, latch) != next_handoff_touch(script, on_the_grid, latch):
                disagreements.append(at)

        assert latch.choice_for(3_005).touch is not None
        assert disagreements == []

    def test_a_ramp_boundary_publishes_no_touch(self):
        script = _script_ahead()
        latch = DescentLatch()
        _read(script, at=1_000, latch=latch)

        assert next_handoff_touch(script, 1_000, latch) is None

    def test_nothing_latched_publishes_no_touch(self):

        assert next_handoff_touch(_script_ahead(), 1_000, DescentLatch()) is None
        assert next_handoff_touch(None, 1_000, DescentLatch()) is None


class TestALoopingFunestra:
    def test_the_loop_fills_the_trace_to_its_far_edge_at_the_fastest_rate(self):
        swings = Funscript(actions=[(0, 0), (1_250, 100), (2_500, 0), (3_760, 100), (5_010, 0)])

        hud = osr2_visualizer(_motion(trace_seconds=DriveHud.trace_seconds),
                            script=swings.looped(0, 5_000), position_ms=4_999, speed=MAX_RATE)

        assert hud.segments == ((0, DRIVEN_BY_FUNSCRIPT),)


class TestNothingToFoldIn:
    def test_an_unscripted_video_leaves_the_visualizer_alone(self):
        published = _motion()

        assert osr2_visualizer(published, script=None, position_ms=0) == published

    def test_a_single_run_still_names_its_driver(self):
        hud = _read(_script(until_ms=120_000), at=0)

        assert hud.segments == ((0, DRIVEN_BY_FUNSCRIPT),)

    def test_an_unchanging_trace_still_compares_equal_to_itself(self):
        script = _script(until_ms=120_000)

        assert _read(script, at=0) == _read(script, at=0)
