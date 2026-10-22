from __future__ import annotations

from shared_ui.heat import heat_at

from funestra.funscript import Funscript
from funestra.heatmap import bin_speeds, build_heatmap


class TestTheStripIsTheFamilysHeatOverTheArithmetic:
    def test_each_bin_is_its_own_speed_in_the_familys_heat_colors(self):
        fs = Funscript(actions=[(1000, 0), (1500, 100), (2000, 0)])

        colors = build_heatmap(fs, 4, start_ms=0, end_ms=4000)

        assert colors == [
            heat_at(speed)
            for speed in bin_speeds(fs, 4, start_ms=0, end_ms=4000)
        ]

    def test_an_empty_window_draws_nothing(self):
        fs = Funscript(actions=[(0, 0), (1000, 100)])

        assert build_heatmap(fs, 10, start_ms=0, end_ms=0) == []


class TestHowMuchTravelLandsInEachBin:
    def test_an_empty_window_has_no_bins(self):
        fs = Funscript(actions=[(0, 0), (1000, 100)])

        assert bin_speeds(fs, 10, start_ms=0, end_ms=0) == []

    def test_a_script_with_nothing_to_move_between_is_idle_throughout(self):
        assert bin_speeds(Funscript(actions=[]), 4, start_ms=0, end_ms=10_000) == [0] * 4
        assert bin_speeds(
            Funscript(actions=[(500, 80)]), 4, start_ms=0, end_ms=10_000) == [0] * 4

    def test_full_travel_per_bin_reads_as_100_units_per_second(self):
        fs = Funscript(actions=[(0, 0), (1000, 100), (2000, 0), (3000, 100), (4000, 0)])

        assert bin_speeds(fs, 4, start_ms=0, end_ms=4000) == [100] * 4

    def test_a_segment_spanning_bins_splits_its_travel_by_overlap(self):
        fs = Funscript(actions=[(0, 0), (2000, 100)])

        assert bin_speeds(fs, 2, start_ms=0, end_ms=2000) == [50, 50]

    def test_bins_before_the_first_action_and_after_the_last_are_idle(self):
        fs = Funscript(actions=[(1000, 0), (1500, 100), (2000, 0)])

        assert bin_speeds(fs, 4, start_ms=0, end_ms=4000) == [0, 200, 0, 0]

    def test_an_instantaneous_jump_between_duplicate_timestamps_is_ignored(self):
        fs = Funscript(actions=[(0, 0), (1000, 100), (1000, 20), (2000, 120)])

        assert bin_speeds(fs, 2, start_ms=0, end_ms=2000) == [100, 100]

    def test_one_bin_averages_the_whole_video(self):
        fs = Funscript(actions=[(0, 0), (1000, 100)])

        assert bin_speeds(fs, 1, start_ms=0, end_ms=2000) == [50]

    def test_travel_past_the_video_end_does_not_count(self):
        fs = Funscript(actions=[(0, 0), (2000, 100)])

        assert bin_speeds(fs, 1, start_ms=0, end_ms=1000) == [50]


class TestAWindowInsideTheVideo:
    def test_its_bins_see_only_their_own_window(self):
        fs = Funscript(actions=[(0, 0), (1000, 100), (2000, 0), (3000, 100), (4000, 0)])

        assert bin_speeds(fs, 2, start_ms=1000, end_ms=3000) == [100, 100]

    def test_activity_entirely_before_it_is_excluded(self):
        fs = Funscript(actions=[(0, 0), (1000, 100)])

        assert bin_speeds(fs, 2, start_ms=2000, end_ms=4000) == [0, 0]

    def test_a_segment_straddling_its_start_counts_only_the_overlap(self):
        fs = Funscript(actions=[(500, 0), (1500, 100)])

        assert bin_speeds(fs, 1, start_ms=1000, end_ms=2000) == [50]

