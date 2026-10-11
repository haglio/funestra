from __future__ import annotations

import json

import pytest

from funestra.funscript import (
    PARK_SETTLE_MS,
    QUIET_LEAD_IN_MS,
    Funscript,
    load,
    snap_loop,
)
from funestra.max_intensity import depth


class TestLoad:
    def test_parses_actions(self, tmp_path):
        data = {
            "actions": [
                {"at": 1000, "pos": 0},
                {"at": 2000, "pos": 100},
                {"at": 500, "pos": 50},
            ]
        }
        path = tmp_path / "test.funscript"
        path.write_text(json.dumps(data))

        fs = load(path)

        assert fs.actions == [(500, 50), (1000, 0), (2000, 100)]

    def test_a_script_listing_no_actions_loads_as_one_that_drives_nothing(self, tmp_path):
        """This reader used to raise where its two siblings answered none, so a
        Funestra had to know whose reader it held before it knew what an empty
        script looked like.  It is a script now, resting the whole way."""
        path = tmp_path / "empty.funscript"
        path.write_text(json.dumps({"version": "1.0"}))

        fs = load(path)

        assert fs.actions == []
        assert fs.is_resting_at(0)


class TestFirstRealEventMs:
    def test_dense_from_start_has_no_lead_in(self):
        fs = Funscript(actions=[(0, 0), (300, 100), (600, 0), (900, 100)])

        assert fs.first_real_event_ms is None

    def test_action_starting_late_reports_onset(self):
        fs = Funscript(actions=[(60000, 0), (60300, 100), (60600, 0)])

        assert fs.first_real_event_ms == 60000

    def test_isolated_leading_blip_is_skipped(self):
        # A stray blip at t=0, a long quiet gap, then dense action at 34s.
        fs = Funscript(actions=[
            (0, 50), (34000, 0), (34300, 100), (34600, 0), (34900, 100),
        ])

        assert fs.first_real_event_ms == 34000

    def test_sparse_throughout_has_no_onset(self):
        # Every action is isolated (10s apart): there is no dense onset to
        # rest up to, so drive normally rather than park the whole video.
        fs = Funscript(actions=[(0, 0), (10000, 100), (20000, 0), (30000, 100)])

        assert fs.first_real_event_ms is None

    def test_short_lead_in_is_not_worth_parking(self):
        # Dense action begins at 4s — under the "a long time" threshold, so no
        # parking (a momentary rest at the very start is not worth it).
        fs = Funscript(actions=[(4000, 0), (4300, 100), (4600, 0), (4900, 100)])

        assert fs.first_real_event_ms is None

    def test_a_lead_in_of_exactly_the_threshold_is_long_enough_to_park(self):
        # "At least this far in" — the boundary itself parks, and the millisecond
        # under it does not, which is the whole of what the threshold decides.
        def onset_at(start: int) -> int | None:
            return Funscript(actions=[(start, 0), (start + 300, 100),
                                      (start + 600, 0)]).first_real_event_ms

        assert onset_at(QUIET_LEAD_IN_MS) == QUIET_LEAD_IN_MS
        assert onset_at(QUIET_LEAD_IN_MS - 1) is None


class TestIsRestingAt:
    def test_on_a_dense_cluster_is_not_resting(self):
        fs = Funscript(actions=[(10000, 0), (10300, 100), (10600, 0), (10900, 100)])

        assert fs.is_resting_at(10300) is False

    def test_deep_gap_between_clusters_is_resting(self):
        fs = Funscript(actions=[
            (10000, 0), (10300, 100), (10600, 0),   # cluster A
            (40000, 0), (40300, 100), (40600, 0),   # cluster B
        ])

        assert fs.is_resting_at(25000) is True  # midway in the 30s gap

    def test_buffer_before_a_cluster_is_not_resting(self):
        # The funscript reclaims a QUIET_LEAD_IN_MS buffer ahead of its action,
        # so the OSR2 settles onto the script before it fires.
        fs = Funscript(actions=[(40000, 0), (40300, 100), (40600, 0)])

        assert fs.is_resting_at(37000) is False  # 3s before -> inside the buffer
        assert fs.is_resting_at(34000) is True   # 6s before -> still the gap

    def test_quiet_lead_in_is_resting(self):
        fs = Funscript(actions=[(60000, 0), (60300, 100), (60600, 0)])

        assert fs.is_resting_at(0) is True

    def test_isolated_blip_does_not_anchor_driving(self):
        # A stray blip with no dense neighbor must not pull the OSR2 off Genau.
        fs = Funscript(actions=[(20000, 50), (60000, 0), (60300, 100), (60600, 0)])

        assert fs.is_resting_at(20000) is True

    def test_sparse_funscript_is_all_resting(self):
        # Every action isolated (10s apart): no dense scripting, Genau drives.
        fs = Funscript(actions=[(0, 0), (10000, 100), (20000, 0), (30000, 100)])

        assert fs.is_resting_at(15000) is True


class TestTurnBoundsAt:
    """Whose turn it is, is is_resting_at; this says where that turn begins and
    ends.  Whoever draws the handoff needs the boundary itself: a ramp walking
    the device between the park and a motion has to be anchored to the moment
    the device changed hands, and anchored to anything recomputed per frame it
    slides around under its own picture."""

    def _two_clusters(self):
        return Funscript(actions=[
            (10000, 0), (10300, 100), (10600, 0),   # cluster A
            (40000, 0), (40300, 100), (40600, 0),   # cluster B
        ])

    def test_a_stretch_opens_a_long_buffer_ahead_of_its_cluster(self):
        """Five seconds, so whoever had the device can put it down and the
        script can walk it up to the cluster's opening action."""
        assert self._two_clusters().turn_bounds_at(10300)[0] == 5000

    def test_a_stretch_closes_in_time_for_the_next_driver_s_climb(self):
        """The other side is not symmetric.  The script is done once its own
        park glide is, and the driver taking over needs a handoff ramp's worth
        of the quiet to climb out of the park — so the turn closes exactly that
        far before the quiet ends, and the climb lands where the motion has
        always resumed.  Held to the end instead, the buffer was spent and the
        motion had to start cold."""
        assert self._two_clusters().turn_bounds_at(10300)[1] == 13600

    def test_the_buffer_itself_belongs_to_the_same_stretch(self):
        """The device is already the script's through its lead-in, which is the
        whole point of the buffer."""
        assert self._two_clusters().turn_bounds_at(6000) == (5000, 13600)

    def test_a_gap_runs_from_one_stretch_s_end_to_the_next_s_start(self):
        assert self._two_clusters().turn_bounds_at(25000) == (13600, 35000)

    def test_a_gap_before_the_first_cluster_has_no_beginning(self):
        """It began before the video did — nothing to anchor a climb to, and
        nothing that needs one: whoever has the device has had it all along."""
        assert self._two_clusters().turn_bounds_at(1000) == (None, 5000)

    def test_a_gap_after_the_last_cluster_has_no_end(self):
        assert self._two_clusters().turn_bounds_at(50000) == (43600, None)

    def test_clusters_close_enough_to_touch_are_one_stretch(self):
        """One turn, not two with an impossible gap between them.  Measured on
        the long lead-in even though the lead-out is short: whether the script
        gives the device back is about whether the other driver has room to do
        anything, and a gap this size leaves none."""
        fs = Funscript(actions=[
            (10000, 0), (10300, 100),
            (17000, 0), (17300, 100),               # 6.7s later: no room between
        ])

        assert fs.is_resting_at(13500) is False
        assert fs.turn_bounds_at(13500) == (5000, 20300)

    def test_a_script_with_no_dense_action_is_one_long_gap(self):
        fs = Funscript(actions=[(0, 0), (10000, 100), (20000, 0)])

        assert fs.turn_bounds_at(5000) == (None, None)


class TestNextActiveMs:
    def _two_clusters(self):
        return Funscript(actions=[
            (10000, 0), (10300, 100), (10600, 0),   # cluster A
            (40000, 0), (40300, 100), (40600, 0),   # cluster B
        ])

    def test_from_the_top_reaches_the_first_cluster(self):
        assert self._two_clusters().next_active_ms(0) == 10000

    def test_inside_a_gap_reaches_the_cluster_after_it(self):
        assert self._two_clusters().next_active_ms(25000) == 40000

    def test_lands_on_the_first_cycle_not_in_the_buffer_before_it(self):
        # is_resting_at hands the script back a QUIET_LEAD_IN_MS buffer ahead of
        # a cluster so the OSR2 settles onto it; a jump that stopped there would
        # be five seconds of nothing, so it goes all the way to the first cycle.
        fs = self._two_clusters()

        assert fs.is_resting_at(36000) is False   # inside the buffer
        assert fs.next_active_ms(25000) == 40000  # the jump still goes past it

    def test_inside_a_cluster_carries_on_to_the_next(self):
        """"Next" is forward: asked from the middle of a run, the answer is the
        run after it, not the one already playing."""
        assert self._two_clusters().next_active_ms(10300) == 40000

    def test_past_the_last_cluster_has_nowhere_to_go(self):
        assert self._two_clusters().next_active_ms(50000) is None

    def test_isolated_blips_are_not_somewhere_to_jump_to(self):
        # A lone action is not action; only densely-sampled runs count, the same
        # standard is_resting_at applies.
        fs = Funscript(actions=[
            (10000, 0), (10300, 100), (10600, 0),   # a real cluster
            (30000, 50),                            # a stray blip
        ])

        assert fs.next_active_ms(20000) is None

    def test_an_unscripted_stretch_of_a_scripted_video_still_answers(self):
        fs = Funscript(actions=[(60000, 0), (60300, 100), (60600, 0)])

        assert fs.next_active_ms(0) == 60000

    def test_a_script_with_no_dense_action_at_all_has_nowhere_to_go(self):
        fs = Funscript(actions=[(0, 0), (10000, 100), (20000, 0), (30000, 100)])

        assert fs.next_active_ms(0) is None


class TestSnapLoop:
    def _make_fs(self):
        return Funscript(actions=[
            (0, 100), (1000, 0), (2000, 100), (3000, 0),
            (4000, 100), (5000, 0), (6000, 100),
        ])

    def test_snaps_outward_to_base_positions(self):
        fs = self._make_fs()

        result = snap_loop(fs, 2500, 3500)

        assert result == (2000, 4000)

    def test_in_already_on_base(self):
        fs = self._make_fs()

        result = snap_loop(fs, 2000, 3500)

        assert result == (2000, 4000)

    def test_no_base_before_in_keeps_the_mark(self):
        # Nothing to pull the in point back onto — the first base is ahead of it —
        # so it stays where it was marked rather than jumping to the script's start.
        fs = Funscript(actions=[
            (1000, 0), (2000, 100), (3000, 0), (4000, 100),
        ])

        result = snap_loop(fs, 500, 2500)

        assert result == (500, 2500)

    def test_no_base_after_out_keeps_the_mark(self):
        # The last base is before the out point, and snapping is outward only, so
        # the loop still ends where it was marked — never short of it.
        fs = Funscript(actions=[
            (0, 100), (1000, 0), (2000, 100), (3000, 0),
        ])

        result = snap_loop(fs, 2500, 3500)

        assert result == (2000, 3500)

    def test_zero_duration_extends(self):
        fs = self._make_fs()

        result = snap_loop(fs, 2050, 2050)

        assert result[1] - result[0] >= 500

    def test_a_distant_base_does_not_stretch_the_loop(self):
        # Full cycles for the first two seconds, then a long stretch of shallow
        # ones that never reach a base.  A mark inside that stretch has no base
        # near either end, and a loop stretched out to the far ones would run for
        # a minute instead of the five seconds that were marked.
        actions = [(0, 100), (500, 0), (1000, 100), (1500, 0), (2000, 100)]
        actions += [(t, 60 if (t // 500) % 2 else 20)
                    for t in range(2500, 60001, 500)]
        fs = Funscript(actions=actions)

        in_ms, out_ms = snap_loop(fs, 30000, 35000)

        assert (in_ms, out_ms) == (30000, 35000)

    def test_a_script_with_no_base_at_all_keeps_the_mark(self):
        # A script authored to a reduced range never reaches a base, so there is
        # nothing anywhere to snap to — which must not be read as "loop the file".
        fs = Funscript(actions=[(t, 80 if (t // 500) % 2 else 0)
                                for t in range(0, 60001, 500)])

        assert snap_loop(fs, 30000, 35000) == (30000, 35000)

    def test_no_funscript_keeps_the_mark(self):
        # An unscripted video loops too; there is simply nothing to snap to.
        assert snap_loop(None, 30000, 35000) == (30000, 35000)

    def test_no_funscript_still_widens_to_the_minimum(self):
        assert snap_loop(None, 30000, 30100) == (30000, 30500)


class TestPositionAt:
    def test_between_two_actions_it_reads_the_move_the_device_is_making(self):
        """The driver sends "be at the next one in this long", so between two
        actions the device really is on its way — a value that stepped would be
        a picture of something else."""
        fs = Funscript(actions=[(0, 0), (400, 80)])

        assert fs.position_at(200) == 40.0

    def test_before_the_first_and_past_the_last_it_holds(self):
        """Which is where the device holds too."""
        fs = Funscript(actions=[(500, 20), (1500, 60)])

        assert fs.position_at(0) == 20.0
        assert fs.position_at(9000) == 60.0


def _gapped() -> Funscript:
    # A dense cluster, a 20s interior gap, then a second cluster whose opening
    # action sits high — so the rise's target is visible — and a tail.
    first = [(i * 200, 100 if i % 2 else 0) for i in range(6)]
    second = [(21_000 + i * 200, 0 if i % 2 else 80) for i in range(6)]
    return Funscript(actions=first + second)


class TestPlan:
    """Where the device is *sent*, as opposed to where the script's line
    interpolates: through every quiet stretch the neutral is the parked
    position, with a timed rise back to each cluster's opening action."""

    def test_inside_a_cluster_the_plan_is_the_script(self):
        fs = _gapped()

        assert fs.is_parked_at(300) is False
        assert fs.planned_position_at(300) == fs.position_at(300)

    def test_a_gap_rests_at_park_not_at_the_last_position(self):
        """position_at drifts across a gap toward the far cluster; the device
        does not follow it — its neutral between clusters is the park."""
        fs = _gapped()

        assert fs.is_parked_at(10_000) is True
        assert fs.planned_position_at(10_000) == 0.0

    def test_the_tail_after_the_last_action_rests_at_park(self):
        fs = _gapped()

        assert fs.is_parked_at(30_000) is True
        assert fs.planned_position_at(30_000) == 0.0

    def test_the_drop_out_of_a_cluster_glides_down_onto_the_park(self):
        """The device walks onto its rest over PARK_SETTLE_MS, so the plan walks
        with it — dropping in one sample drew a cliff the device then spent half a
        second not taking."""
        fs = _gapped()
        last = 1000  # the first cluster's closing action

        assert fs.is_parked_at(last + PARK_SETTLE_MS // 2) is True
        assert fs.planned_position_at(last + PARK_SETTLE_MS // 2) == (
            fs.position_at(last) / 2)
        assert fs.planned_position_at(last + PARK_SETTLE_MS) == 0.0

    def test_the_rise_starts_a_beat_ahead_and_lands_on_the_opening_action(self):
        fs = _gapped()

        assert fs.is_parked_at(19_999) is True   # still parked
        assert fs.is_parked_at(20_000) is False  # the rise begins
        assert fs.planned_position_at(20_000) == 0.0
        assert fs.planned_position_at(20_500) == fs.position_at(21_000) / 2
        assert fs.planned_position_at(21_000) == fs.position_at(21_000)

    def test_a_stray_blip_in_a_quiet_stretch_is_sat_out(self):
        """An isolated action with no dense neighbors is noise, not a motion;
        the device stays at its rest rather than lunging at it."""
        fs = Funscript(actions=[(0, 0), (200, 100), (400, 0),
                                (10_000, 90),
                                (20_000, 0), (20_200, 100), (20_400, 0)])

        assert fs.is_parked_at(10_000) is True
        assert fs.planned_position_at(10_000) == 0.0

    def test_a_script_of_nothing_but_blips_rests_throughout(self):
        """No dense action anywhere is one long quiet stretch — the same script
        is_resting_at already hands to Genau whole."""
        fs = Funscript(actions=[(0, 50), (10_000, 100), (20_000, 0)])

        assert fs.is_parked_at(10_000) is True


class TestThePlanAsAPicture:
    """The plan sampled for a HUD to draw — whole knots off a grid fixed to the
    script, and the fraction of a knot the playhead sits past the first of them."""

    def test_the_picture_slides_rather_than_being_resampled(self):
        """Sampling from the playhead put the points at a new offset every frame,
        so every peak landed somewhere slightly different and the line boiled in
        place.  On a grid fixed to the script, moving along it is a window
        sliding: the values a window drops are the ones the last one had."""
        fs = _gapped()

        first, _slide = fs.planned_trace_window(0, 1000, 5)
        stepped, _slide = fs.planned_trace_window(250, 1000, 5)

        assert stepped[:3] == first[1:4]

    def test_a_playhead_between_two_knots_reads_the_knot_before_it(self):
        """The script does not change while it plays, so its picture is computed
        once and reread, and the leftover fraction goes to the drawer to shift the
        stable shape by.  Reading blended values instead morphed the heights at
        fixed columns every frame — the shape changed while it moved."""
        fs = _gapped()

        at_knot, none_over = fs.planned_trace_window(0, 500, 3)
        halfway, half_over = fs.planned_trace_window(125, 500, 3)

        assert halfway == at_knot
        assert none_over == 0.0
        assert half_over == 0.5

    def test_it_carries_one_knot_past_the_far_edge(self):
        """The drawer shifts the line left by the fraction, so without a spare
        knot the line would fall short of the border by up to a sample."""
        values, _slide = _gapped().planned_trace_window(0, 500, 3)

        assert len(values) == 4

    def test_every_sample_is_a_height_the_trace_can_draw(self):
        values, _slide = _gapped().planned_trace_window(0, 1000, 40)

        assert all(0.0 <= value <= 1.0 for value in values)

    def test_past_the_end_of_the_script_it_rests_on_the_park(self):
        fs = Funscript(actions=[(0, 0), (200, 100), (400, 40)])

        assert fs.planned_trace_window(50_000, 500, 3)[0] == (0.0, 0.0, 0.0, 0.0)

    def test_an_unscripted_video_has_no_picture_at_all(self):
        assert Funscript(actions=[]).planned_trace_window(0, 1000, 4) == ((), 0.0)

    def test_a_span_of_no_time_is_all_park_rather_than_a_division_by_zero(self):
        """A Funestra stopped dead publishes a span of nothing — the trace's seconds
        scaled by a playback speed of zero — and asks for a picture of it anyway."""
        assert _gapped().planned_trace_window(0, 0, 3) == ((0.0,) * 4, 0.0)


class TestDepthAtSpeed:
    def _fast(self):
        # A full cycle every 200ms: faster than the device can travel, so at
        # double speed the only way to keep the timing is to go half as far.
        return Funscript(actions=[(0, 0), (200, 100), (400, 0), (600, 100)])

    def test_normal_speed_leaves_every_position_where_the_script_put_it(self):
        assert self._fast().paced_position_at(200, 1.0) == 100

    def test_a_script_already_at_the_devices_limit_halves_its_depth_at_double_speed(self):
        assert self._fast().paced_position_at(200, 2.0) == 50

    def test_a_script_inside_the_devices_reach_keeps_its_depth_when_sped_up(self):
        # A cycle a second: even doubled it is well inside what the device can
        # travel, so there is nothing to give up.
        fs = Funscript(actions=[(0, 0), (1000, 100), (2000, 0), (3000, 100)])

        assert fs.paced_position_at(1000, 2.0) == 100

    def test_the_shrunk_motion_sits_on_the_park_rather_than_the_middle(self):
        # A stretch riding high and fast: halved, its floor comes down toward
        # the park with everything else instead of the motion staying where it
        # was and closing in on its own middle.
        fs = Funscript(actions=[(0, 20), (100, 100), (200, 20), (300, 100)])

        assert fs.paced_position_at(0, 2.0) == 10
        assert fs.paced_position_at(100, 2.0) == 50

    def test_the_drawn_plan_gives_up_the_same_depth_the_device_is_given(self):
        fs = self._fast()

        full, _ = fs.planned_trace_window(0, 600, 4, speed=1.0)
        paced, _ = fs.planned_trace_window(0, 600, 4, speed=2.0)

        assert max(full) == 1.0
        assert max(paced) == 0.5


class TestDepthUnderTheMaxIntensity:
    def _steady(self):
        # A full cycle every two seconds: a hundred units a second.
        return Funscript(actions=[(0, 0), (1000, 100), (2000, 0), (3000, 100), (4000, 0)])

    def test_a_script_past_the_max_intensity_keeps_the_share_of_its_depth_it_leaves(self):
        assert self._steady().paced_position_at(1000, 1.0, max_intensity=30) == pytest.approx(
            100 * depth(100.0, 30))


    def test_the_plan_gives_up_the_same_depth_the_device_is_given(self):
        fs = self._steady()

        assert fs.planned_position_at(1000, 1.0, max_intensity=30) == pytest.approx(
            fs.paced_position_at(1000, 1.0, max_intensity=30))

    def test_the_drawn_plan_gives_it_up_too(self):
        fs = self._steady()

        drawn, _ = fs.planned_trace_window(0, 3000, 4, speed=1.0, max_intensity=30)

        assert max(drawn) == pytest.approx(depth(100.0, 30))


class TestPlayedOnALoop:
    def _two_swings(self):
        return Funscript(actions=[(0, 0), (1_250, 100), (2_500, 0), (3_760, 100), (5_010, 0)])

    def test_the_loop_comes_round_again_where_the_script_would_have_run_out(self):
        looped = self._two_swings().looped(0, 5_000)

        assert [looped.position_at(t) for t in (5_000, 6_250, 7_500, 8_760)] == [0, 100, 0, 100]

    def test_right_after_the_seam_the_device_is_still_on_its_way_down_from_the_pass_before(self):
        ends_high = Funscript(actions=[(1_000, 0), (2_250, 100), (3_500, 0), (4_750, 100)])

        assert ends_high.looped(0, 5_000).planned_position_at(0) == 80

    def test_a_clip_not_open_yet_has_no_loop_to_repeat(self):
        swings = self._two_swings()

        assert swings.looped(0, 0) is swings

    def test_a_loop_over_a_quiet_stretch_never_rises_for_a_cluster_past_its_end(self):
        script = Funscript(actions=[(t, (t // 200) % 2 * 100) for t in range(30_000, 35_001, 200)])

        assert script.is_resting_at(26_000) is False
        assert script.looped(20_000, 27_000).is_resting_at(26_000) is True

    def test_the_same_loop_asked_for_every_frame_is_laid_out_once(self):
        swings = self._two_swings()

        assert swings.looped(0, 5_000) is swings.looped(0, 5_000)
