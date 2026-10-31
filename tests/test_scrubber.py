"""The scrubber a Funestra draws: its colors, the zoom while a stretch is marked, the frames of a running A/B range."""
from __future__ import annotations

import numpy as np
from shared_ui.palette import AMBER

from funestra.funscript import Funscript
from funestra.heatmap import build_heatmap
from funestra.scrubber import (
    HeatmapStrip,
    LoopThumbCapture,
    ZoomWindow,
    label_xs,
    loop_thumbnail_xys,
    time_to_x,
)
from funestra.timeline import BAR_INSET_Y, bar_track_x, progress_bar_bgra


def _funscript():
    return Funscript(actions=[(0, 0), (1000, 100), (2000, 0)])


WIN_W = 1000
TRACK_W = bar_track_x(WIN_W)[1] - bar_track_x(WIN_W)[0]


class TestHeatmapStrip:
    def test_a_track_nobody_has_measured_yet_gets_no_colors(self):
        """A HUD is as wide as what is on it, so its host has no width to
        offer until one has been drawn.  Nothing to measure across is not an
        error; it is the first frame, and it goes up as a plain bar."""
        strip = HeatmapStrip()

        strip.update("v0.mp4", _funscript(), 4000.0, track_w=0)

        assert strip.colors == []

    def test_builds_one_color_per_pixel_of_the_track_it_fills(self):
        fs = _funscript()
        strip = HeatmapStrip()

        strip.update("v0.mp4", fs, 4000.0, track_w=TRACK_W)

        assert strip.colors == build_heatmap(fs, TRACK_W, start_ms=0, end_ms=4000.0)

    def test_an_unscripted_item_has_no_strip(self):
        strip = HeatmapStrip()

        strip.update("plain.mp4", None, 4000.0, track_w=TRACK_W)

        assert strip.colors == []

    def test_caches_until_the_item_changes(self):
        strip = HeatmapStrip()
        strip.update("v0.mp4", _funscript(), 4000.0, track_w=TRACK_W)
        built = strip.colors

        strip.update("v0.mp4", Funscript(actions=[]), 4000.0, track_w=TRACK_W)
        assert strip.colors is built

        strip.update("v1.mp4", Funscript(actions=[]), 4000.0, track_w=TRACK_W)
        assert strip.colors != built

    def test_a_width_change_rebuilds(self):
        strip = HeatmapStrip()
        strip.update("v0.mp4", _funscript(), 4000.0, track_w=TRACK_W)

        strip.update("v0.mp4", _funscript(), 4000.0, track_w=500)

        assert len(strip.colors) == 500

    def test_the_full_view_spans_the_item(self):
        strip = HeatmapStrip()

        strip.update("v0.mp4", _funscript(), 4000.0, track_w=TRACK_W)

        assert strip.window == (0.0, 4000.0)
        assert strip.mark_in_ms is None

    def test_a_mark_zooms_the_strip_into_the_stretch_around_itself(self):
        fs = _funscript()
        strip = HeatmapStrip()

        strip.update("v0.mp4", fs, 600_000.0, track_w=TRACK_W, mark_in_ms=50_000, position_ms=50_000.0)

        assert strip.window == (48_000, 70_000)
        assert strip.mark_in_ms == 50_000
        assert strip.colors == build_heatmap(fs, TRACK_W, start_ms=48_000, end_ms=70_000)

    def test_an_unscripted_item_marked_keeps_the_plain_view(self):
        strip = HeatmapStrip()

        strip.update("plain.mp4", None, 600_000.0, track_w=TRACK_W, mark_in_ms=50_000, position_ms=50_000.0)

        assert strip.window == (0.0, 600_000.0)

    def test_the_marked_view_rescales_in_steps_not_continuously(self):
        strip = HeatmapStrip()

        def update(position_ms):
            strip.update("v0.mp4", _funscript(), 600_000.0, track_w=TRACK_W,
                         mark_in_ms=50_000, position_ms=position_ms)

        update(50_000.0)
        held = strip.colors
        update(60_000.0)
        assert strip.window == (48_000, 70_000)
        assert strip.colors is held

        update(66_800.0)
        assert strip.window == (46_000, 90_000)
        assert strip.colors is not held

    def test_closing_the_mark_restores_the_full_view(self):
        fs = _funscript()
        strip = HeatmapStrip()
        strip.update("v0.mp4", fs, 600_000.0, track_w=TRACK_W, mark_in_ms=50_000, position_ms=66_800.0)

        strip.update("v0.mp4", fs, 600_000.0, track_w=TRACK_W)

        assert strip.window == (0.0, 600_000.0)
        assert strip.mark_in_ms is None
        assert strip.colors == build_heatmap(fs, TRACK_W, start_ms=0, end_ms=600_000.0)

        strip.update("v0.mp4", fs, 600_000.0, track_w=TRACK_W, mark_in_ms=100_000, position_ms=100_000.0)
        assert strip.window == (98_000, 120_000)


class TestTimeToX:
    def test_maps_a_fraction_of_the_window_to_a_pixel(self):
        assert time_to_x(0, 0, 10_000, 100) == 0
        assert time_to_x(5_000, 0, 10_000, 100) == 50
        assert time_to_x(30_000, 20_000, 40_000, 100) == 50

    def test_clamps_to_the_strip(self):
        assert time_to_x(10_000, 0, 10_000, 100) == 99
        assert time_to_x(50_000, 20_000, 40_000, 100) == 99
        assert time_to_x(0, 20_000, 40_000, 100) == 0

    def test_an_empty_window_pins_left(self):
        assert time_to_x(500, 0, 0, 100) == 0


class TestZoomWindow:
    def test_the_first_window_spans_20s_with_a_10_percent_lead(self):
        assert ZoomWindow(in_ms=50_000).bounds == (48_000, 70_000)

    def test_holds_while_the_playhead_is_before_85_percent(self):
        zoom = ZoomWindow(in_ms=50_000)

        zoom.update(66_000)

        assert zoom.bounds == (48_000, 70_000)

    def test_doubles_once_the_playhead_passes_85_percent(self):
        zoom = ZoomWindow(in_ms=50_000)

        zoom.update(66_800)

        assert zoom.bounds == (46_000, 90_000)

    def test_a_far_jump_catches_up_in_doubling_steps(self):
        zoom = ZoomWindow(in_ms=50_000)

        zoom.update(200_000)

        assert zoom.bounds == (18_000, 370_000)


def _rgba(bar, y, x):
    px = bar[y, x]
    return int(px[2]), int(px[1]), int(px[0]), int(px[3])


class TestAScriptedItemsStrip:
    def _framed_strip(self, win_w=1000):
        x0, x1 = bar_track_x(win_w)
        strip = HeatmapStrip()
        strip.update("v.mp4", _funscript(), 4000.0, track_w=x1 - x0)
        return progress_bar_bgra(2000, 4000.0, (1000, 3000), win_w, heatmap=strip.colors), x0, x1

    def test_the_strip_runs_from_the_rows_edge_to_the_chips_slot(self):
        bgra, x0, x1 = self._framed_strip()
        my = bgra.shape[0] // 2
        assert x0 == 0
        assert bgra[my, 1, 3] > 0
        assert bgra[my, x1 + 2, 3] == 0
        assert bgra[my, bgra.shape[1] - 5, 3] == 0
        assert bgra[my, (x0 + x1) // 2, 3] > 0

    def test_it_has_a_two_tone_border(self):
        bgra, x0, _x1 = self._framed_strip()
        outer = _rgba(bgra, BAR_INSET_Y, x0 + 10)
        inner = _rgba(bgra, BAR_INSET_Y + 1, x0 + 10)
        assert max(outer[:3]) < 100
        assert min(inner[:3]) >= 200
        assert inner[3] >= 200

    def test_prominent_full_height_marks(self):
        bgra, x0, x1 = self._framed_strip()
        my = bgra.shape[0] // 2
        cx = x0 + (x1 - x0) // 2
        assert _rgba(bgra, my, cx) == (255, 255, 255, 255)
        white = [x for x in range(x0, x1) if _rgba(bgra, my, x) == (255, 255, 255, 255)]
        assert len(white) >= 3
        amber = [x for x in range(x0, x1) if _rgba(bgra, my, x)[:3] == AMBER]
        assert amber
        assert any(x < cx for x in amber)
        assert any(x > cx for x in amber)


class TestLoopThumbCapture:
    def test_asks_for_the_in_frame_first_then_the_out_frame_near_the_end(self):
        cap = LoopThumbCapture()

        assert cap.needed((2000, 4000), 2000) == "in"
        cap.set("in", object())
        assert cap.needed((2000, 4000), 2500) is None
        assert cap.needed((2000, 4000), 3700) == "out"
        cap.set("out", object())
        assert cap.needed((2000, 4000), 3900) is None

    def test_clears_when_the_range_ends(self):
        cap = LoopThumbCapture()
        cap.needed((2000, 4000), 2000)
        cap.set("in", object())

        assert cap.needed(None, 0) is None
        assert cap.in_thumb is None

    def test_asks_again_for_a_new_range(self):
        cap = LoopThumbCapture()
        cap.needed((2000, 4000), 2000)
        cap.set("in", object())

        assert cap.needed((5000, 7000), 5000) == "in"


class TestWhereTheLoopsTwoFramesGo:
    """Each hangs at the y its host gives -- just under the HUD the track is
    a block of -- lined up with its own mark along that track."""

    TRACK = (40, 868)
    WIN_W, TOP = 1000, 564
    FRAME_H, FRAME_W = 10, 20

    def _thumbs(self, *, out=True):
        thumbs = LoopThumbCapture()
        thumbs.set("in", np.zeros((self.FRAME_H, self.FRAME_W, 4), dtype=np.uint8))
        if out:
            thumbs.set("out", np.zeros((self.FRAME_H, self.FRAME_W, 4), dtype=np.uint8))
        return thumbs

    def _xys(self, heatmap, thumbs, bounds):
        return loop_thumbnail_xys(heatmap, thumbs, bounds, track=self.TRACK,
                                  win_w=self.WIN_W, top=self.TOP)

    def _scripted(self) -> HeatmapStrip:
        strip = HeatmapStrip()
        strip.update("v0.mp4", _funscript(), 4000.0, track_w=40)
        return strip

    def test_each_frame_sits_centered_under_its_own_mark(self):
        assert self._xys(self._scripted(), self._thumbs(), (2000, 3000)) == (
            (444, self.TOP), (651, self.TOP))

    def test_a_frame_not_grabbed_yet_has_nowhere_to_go(self):
        in_at, out_at = self._xys(self._scripted(), self._thumbs(out=False), (2000, 3000))

        assert (in_at, out_at) == ((444, self.TOP), None)

    def test_two_marks_too_close_together_push_their_frames_apart(self):
        (in_x, _y), (out_x, _oy) = self._xys(self._scripted(), self._thumbs(), (2000, 2050))

        assert out_x >= in_x + self.FRAME_W


class TestWhereTheLoopsTwoLabelsGo:
    def test_centers_and_avoids_overlap(self):
        assert label_xs(100, 500, 60, 60, 1000) == (70, 470)
        ix, ox = label_xs(100, 120, 60, 60, 1000)
        assert ox >= ix + 60
