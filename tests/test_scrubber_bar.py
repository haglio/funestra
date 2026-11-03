from __future__ import annotations

from shared_ui.palette import RED, YELLOW

from funestra.scrubber_bar import (
    BAR_INSET_Y,
    HEATMAP_ALPHA,
    TrackMarks,
    bar_track_x,
    progress_bar_bgra,
)
from funestra.volume import PLACE_W


def _rgba(bar, y, x):
    px = bar[y, x]
    return int(px[2]), int(px[1]), int(px[0]), int(px[3])


class TestBarTrackX:
    def test_the_track_stops_clear_of_the_volume_slot_at_the_right(self):
        assert bar_track_x(1000)[1] == 1000 - PLACE_W

    def test_the_track_starts_where_the_row_laying_it_out_says(self):
        assert bar_track_x(1920, left=183) == (183, 1920 - PLACE_W)

    def test_the_track_starts_after_a_visualizer_wider_than_half_the_row(self):
        assert bar_track_x(302, left=172) == (172, 302 - PLACE_W)

    def test_a_row_with_nothing_before_the_track_starts_it_at_the_edge(self):
        assert bar_track_x(326) == (0, 326 - PLACE_W)

    def test_clamps_so_the_track_never_inverts_on_a_narrow_window(self):
        for left in (0, 100):
            x0, x1 = bar_track_x(50, left=left)
            assert 0 <= x0 < x1 <= 50


class TestProgressBar:
    def test_the_track_runs_from_the_rows_edge_and_leaves_the_chips_slot_clear(self):
        bar = progress_bar_bgra(TrackMarks(0, 10_000), 1000)
        x0, x1 = bar_track_x(1000)
        my = bar.shape[0] // 2

        assert bar[my, 1, 3] > 0
        assert bar[my, (x0 + x1) // 2, 3] > 0
        assert bar[my, x1 + 2, 3] == 0
        assert bar[my, 995, 3] == 0

    def test_has_a_two_tone_border_around_the_track(self):
        bar = progress_bar_bgra(TrackMarks(0, 10_000), 1000)
        x0, x1 = bar_track_x(1000)
        xc = (x0 + x1) // 2
        fill = _rgba(bar, bar.shape[0] // 2, xc)
        outer = _rgba(bar, BAR_INSET_Y, xc)
        inner = _rgba(bar, BAR_INSET_Y + 1, xc)
        assert max(outer[:3]) < min(fill[:3])
        assert min(inner[:3]) > max(fill[:3])
        assert inner[3] >= 200

    def test_a_prominent_white_playcursor(self):
        bar = progress_bar_bgra(TrackMarks(5_000, 10_000), 1000)
        x0, x1 = bar_track_x(1000)
        my = bar.shape[0] // 2
        assert _rgba(bar, my, x0 + (x1 - x0) // 2) == (255, 255, 255, 255)
        white = [x for x in range(x0, x1) if _rgba(bar, my, x) == (255, 255, 255, 255)]
        assert len(white) >= 3

    def test_draws_prominent_yellow_loop_marks(self):
        bar = progress_bar_bgra(TrackMarks(0, 10_000, (2_500, 7_500)), 1000)
        x0, x1 = bar_track_x(1000)
        my = bar.shape[0] // 2
        yellow = [x for x in range(x0, x1) if _rgba(bar, my, x)[:3] == YELLOW]
        assert len(yellow) >= 6
        xc = (x0 + x1) // 2
        assert any(x < xc for x in yellow)
        assert any(x > xc for x in yellow)

    def test_no_loop_marks_without_a_loop(self):
        bar = progress_bar_bgra(TrackMarks(0, 10_000), 1000)
        my = bar.shape[0] // 2
        assert not any(_rgba(bar, my, x)[:3] == YELLOW for x in range(1000))

    def test_record_in_point_shows_red(self):
        bar = progress_bar_bgra(TrackMarks(0, 10_000, record_in_ms=5_000), 1000)
        x0, x1 = bar_track_x(1000)
        my = bar.shape[0] // 2
        red = [x for x in range(x0, x1) if _rgba(bar, my, x)[:3] == RED]
        assert len(red) >= 3

    def test_track_fill_is_uniform_either_side_of_the_cursor(self):
        bar = progress_bar_bgra(TrackMarks(5_000, 10_000), 1000)
        x0, x1 = bar_track_x(1000)
        my = bar.shape[0] // 2
        assert _rgba(bar, my, x0 + 30) == _rgba(bar, my, x1 - 30)

    def test_zero_duration_is_safe(self):
        bar = progress_bar_bgra(TrackMarks(0, 0), 800, height=20)
        assert bar.shape == (20, 800, 4)

    def test_a_funscripts_colors_fill_the_track_in_place_of_the_dark_fill(self):
        x0, x1 = bar_track_x(1000)
        colors = [(40 + x % 200, 90, 220 - x % 180) for x in range(x1 - x0)]

        bar = progress_bar_bgra(TrackMarks(0, 10_000), 1000, heatmap=colors)

        middle = bar.shape[0] // 2
        assert [_rgba(bar, middle, x) for x in range(x0 + 10, x1 - 10)] == [
            (*colors[x - x0], HEATMAP_ALPHA) for x in range(x0 + 10, x1 - 10)]

    def test_the_track_ends_before_the_volume_slot(self):
        bar = progress_bar_bgra(TrackMarks(10_000, 10_000), 1000)
        my = bar.shape[0] // 2
        _x0, x1 = bar_track_x(1000)
        assert bar[my, x1 + 2, 3] == 0
